from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finsight_agent.app.db.models import Base
from finsight_agent.app.db.repository import ResearchRunRepository


def make_repository(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    return ResearchRunRepository(session), session


def test_repository_creates_and_retrieves_research_run(tmp_path) -> None:
    repository, session = make_repository(tmp_path)
    run_id = uuid4()

    created = repository.create_from_graph_result(
        run_id=run_id,
        query="AAPL",
        status="completed",
        graph_result={
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "compliance_status": "allowed",
            "report_quality_status": "passed",
            "financial_metrics": {"periods": [{"fy": 2024, "revenue": 1250000000}]},
            "filing_text": "Risk factor text " * 300,
            "risk_factors": [
                {
                    "form": "10-K",
                    "filing_date": "2024-11-01",
                    "accession_number": "0000320193-24-000123",
                    "text": "Competition risk text.",
                }
            ],
            "risk_themes": [
                {
                    "title": "Competitive pressure",
                    "summary": "Competition could pressure operating performance.",
                }
            ],
            "research_insights": {
                "bull_case": [
                    {
                        "title": "Revenue growth",
                        "summary": "Extracted revenue increased year over year.",
                    }
                ],
                "bear_case": [],
                "open_questions": [],
            },
            "warnings": [],
            "errors": [],
            "sources": [],
            "agent_steps": [
                {
                    "node_name": "resolve_company",
                    "status": "completed",
                    "message": "Resolved AAPL to Apple Inc.",
                },
                {
                    "node_name": "fetch_sec_data",
                    "status": "completed",
                    "message": "Fetched SEC submissions and company facts.",
                },
            ],
            "final_report": None,
        },
    )
    retrieved = repository.get_by_id(run_id)
    steps = repository.get_steps_for_run(run_id)

    assert retrieved is not None
    assert retrieved.id == str(run_id)
    assert retrieved.query == "AAPL"
    assert retrieved.status == "completed"
    assert retrieved.ticker == "AAPL"
    assert retrieved.company_name == "Apple Inc."
    assert retrieved.compliance_status == "allowed"
    assert retrieved.report_quality_status == "passed"
    assert retrieved.financial_metrics_json == {
        "periods": [{"fy": 2024, "revenue": 1250000000}]
    }
    assert retrieved.filing_text_excerpt.startswith("Risk factor text")
    assert len(retrieved.filing_text_excerpt) == 2000
    assert retrieved.risk_factors_json == [
        {
            "form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "0000320193-24-000123",
            "text": "Competition risk text.",
        }
    ]
    assert retrieved.risk_themes_json == [
        {
            "title": "Competitive pressure",
            "summary": "Competition could pressure operating performance.",
        }
    ]
    assert retrieved.research_insights_json["bull_case"][0]["title"] == "Revenue growth"
    assert retrieved.warnings_json == []
    assert retrieved.errors_json == []
    assert retrieved.sources_json == []
    assert retrieved.completed_at is not None
    assert created.id == retrieved.id
    assert [step.node_name for step in steps] == ["resolve_company", "fetch_sec_data"]
    assert [step.status for step in steps] == ["completed", "completed"]
    assert steps[0].message == "Resolved AAPL to Apple Inc."

    session.close()


def test_repository_returns_none_for_unknown_run_id(tmp_path) -> None:
    repository, session = make_repository(tmp_path)

    assert repository.get_by_id(uuid4()) is None

    session.close()


def test_repository_returns_empty_steps_for_unknown_run_id(tmp_path) -> None:
    repository, session = make_repository(tmp_path)

    assert repository.get_steps_for_run(uuid4()) == []

    session.close()
