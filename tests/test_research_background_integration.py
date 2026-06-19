from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finsight_agent.app.api import dependencies
from finsight_agent.app.db.models import Base
from finsight_agent.app.main import app


class FakeGraphRunner:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.invocations: list[dict] = []

    def invoke(self, state: dict) -> dict:
        self.invocations.append(state)
        return self.result


def test_post_research_background_task_persists_completed_run_for_polling(
    tmp_path,
    monkeypatch,
) -> None:
    session_factory = _make_session_factory(tmp_path)
    graph_runner = FakeGraphRunner(
        {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "compliance_status": "allowed",
            "report_quality_status": "passed",
            "final_report": "# FinSight Research Brief: Apple Inc. (AAPL)",
            "financial_metrics": {"periods": [{"fy": 2024, "revenue": 1250000000}]},
            "filing_text": "Risk factor text from latest 10-K.",
            "risk_factors": [{"form": "10-K", "text": "Risk factor text."}],
            "risk_themes": [{"title": "Competitive pressure"}],
            "research_insights": {
                "bull_case": [{"title": "Revenue growth"}],
                "bear_case": [{"title": "Competitive pressure"}],
                "open_questions": [],
            },
            "warnings": [],
            "errors": [],
            "sources": [{"source_id": "sec_company_facts"}],
            "agent_steps": [
                {
                    "node_name": "resolve_company",
                    "status": "completed",
                    "message": "Resolved AAPL to Apple Inc.",
                    "started_at": "2026-06-16T13:00:00+00:00",
                    "completed_at": "2026-06-16T13:00:02+00:00",
                    "duration_seconds": 2.0,
                },
                {
                    "node_name": "fetch_sec_data",
                    "status": "completed",
                    "message": "Fetched SEC submissions and company facts.",
                },
            ],
        }
    )
    _patch_research_dependencies(
        monkeypatch,
        session_factory=session_factory,
        graph_runner=graph_runner,
    )

    with TestClient(app) as client:
        post_response = client.post("/research", json={"query": "AAPL"})
        run_id = post_response.json()["run_id"]
        get_response = client.get(f"/research/{run_id}")
        progress_response = client.get(f"/research/{run_id}/progress")
        steps_response = client.get(f"/research/{run_id}/steps")

    assert post_response.status_code == 202
    assert post_response.json()["status"] == "queued"
    assert graph_runner.invocations == [{"user_query": "AAPL"}]

    assert get_response.status_code == 200
    body = get_response.json()
    assert body["run_id"] == run_id
    assert body["query"] == "AAPL"
    assert body["status"] == "completed"
    assert body["ticker"] == "AAPL"
    assert body["company_name"] == "Apple Inc."
    assert body["compliance_status"] == "allowed"
    assert body["report_quality_status"] == "passed"
    assert body["financial_metrics"]["periods"][0]["revenue"] == 1250000000
    assert body["filing_text_excerpt"] == "Risk factor text from latest 10-K."
    assert body["risk_factors"] == [{"form": "10-K", "text": "Risk factor text."}]
    assert body["risk_themes"] == [{"title": "Competitive pressure"}]
    assert body["research_insights"]["bull_case"] == [{"title": "Revenue growth"}]
    assert body["report"] == "# FinSight Research Brief: Apple Inc. (AAPL)"
    assert body["errors"] == []
    assert len(body["sources"]) == 1
    assert body["sources"][0]["source_id"] == "sec_company_facts"

    assert progress_response.status_code == 200
    assert progress_response.json() == {
        "run_id": run_id,
        "status": "completed",
        "total_steps": 2,
        "completed_steps": 2,
        "failed_steps": 0,
        "workflow_started_at": "2026-06-16T13:00:00Z",
        "workflow_completed_at": "2026-06-16T13:00:02Z",
        "workflow_duration_seconds": 2.0,
        "latest_step": {
            "id": 2,
            "research_run_id": run_id,
            "node_name": "fetch_sec_data",
            "status": "completed",
            "message": "Fetched SEC submissions and company facts.",
            "error_message": None,
            "started_at": None,
            "completed_at": None,
            "duration_seconds": None,
        },
    }

    assert steps_response.status_code == 200
    assert steps_response.json() == [
        {
            "id": 1,
            "research_run_id": run_id,
            "node_name": "resolve_company",
            "status": "completed",
            "message": "Resolved AAPL to Apple Inc.",
            "error_message": None,
            "started_at": "2026-06-16T13:00:00Z",
            "completed_at": "2026-06-16T13:00:02Z",
            "duration_seconds": 2.0,
        },
        {
            "id": 2,
            "research_run_id": run_id,
            "node_name": "fetch_sec_data",
            "status": "completed",
            "message": "Fetched SEC submissions and company facts.",
            "error_message": None,
            "started_at": None,
            "completed_at": None,
            "duration_seconds": None,
        },
    ]


def test_post_research_background_task_persists_failed_run_for_polling(
    tmp_path,
    monkeypatch,
) -> None:
    session_factory = _make_session_factory(tmp_path)
    graph_runner = FakeGraphRunner(
        {
            "ticker": None,
            "company_name": None,
            "warnings": [],
            "errors": [
                {
                    "code": "company_not_found",
                    "message": "Could not confidently resolve the company.",
                    "severity": "error",
                }
            ],
            "sources": [],
            "agent_steps": [
                {
                    "node_name": "resolve_company",
                    "status": "failed",
                    "error_message": "Could not confidently resolve the company.",
                }
            ],
        }
    )
    _patch_research_dependencies(
        monkeypatch,
        session_factory=session_factory,
        graph_runner=graph_runner,
    )

    with TestClient(app) as client:
        post_response = client.post("/research", json={"query": "UNKNOWN"})
        run_id = post_response.json()["run_id"]
        get_response = client.get(f"/research/{run_id}")
        steps_response = client.get(f"/research/{run_id}/steps")

    assert post_response.status_code == 202
    assert post_response.json()["status"] == "queued"
    assert graph_runner.invocations == [{"user_query": "UNKNOWN"}]

    assert get_response.status_code == 200
    body = get_response.json()
    assert body["run_id"] == run_id
    assert body["query"] == "UNKNOWN"
    assert body["status"] == "failed"
    assert body["ticker"] is None
    assert body["company_name"] is None
    assert body["report"] is None
    assert body["errors"] == [
        {
            "code": "company_not_found",
            "message": "Could not confidently resolve the company.",
            "severity": "error",
            "details": None,
        }
    ]

    assert steps_response.status_code == 200
    assert steps_response.json() == [
        {
            "id": 1,
            "research_run_id": run_id,
            "node_name": "resolve_company",
            "status": "failed",
            "message": None,
            "error_message": "Could not confidently resolve the company.",
            "started_at": None,
            "completed_at": None,
            "duration_seconds": None,
        }
    ]


def test_post_research_retry_persists_retry_lineage_for_polling(
    tmp_path,
    monkeypatch,
) -> None:
    session_factory = _make_session_factory(tmp_path)
    graph_runner = FakeGraphRunner(
        {
            "ticker": None,
            "company_name": None,
            "warnings": [],
            "errors": [
                {
                    "code": "company_not_found",
                    "message": "Could not confidently resolve the company.",
                    "severity": "error",
                }
            ],
            "sources": [],
            "agent_steps": [],
        }
    )
    _patch_research_dependencies(
        monkeypatch,
        session_factory=session_factory,
        graph_runner=graph_runner,
    )

    with TestClient(app) as client:
        failed_response = client.post("/research", json={"query": "UNKNOWN"})
        failed_run_id = failed_response.json()["run_id"]
        retry_response = client.post(f"/research/{failed_run_id}/retry")
        retry_run_id = retry_response.json()["run_id"]
        get_retry_response = client.get(f"/research/{retry_run_id}")
        retry_chain_response = client.get(f"/research/{retry_run_id}/retries")

    assert failed_response.status_code == 202
    assert retry_response.status_code == 202
    assert retry_run_id != failed_run_id
    assert retry_response.json()["retried_from_run_id"] == failed_run_id
    assert get_retry_response.status_code == 200
    assert get_retry_response.json()["retried_from_run_id"] == failed_run_id
    assert retry_chain_response.status_code == 200
    assert [run["run_id"] for run in retry_chain_response.json()] == [
        failed_run_id,
        retry_run_id,
    ]
    assert graph_runner.invocations == [
        {"user_query": "UNKNOWN"},
        {"user_query": "UNKNOWN"},
    ]


def _make_session_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'research-background.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _patch_research_dependencies(
    monkeypatch,
    *,
    session_factory,
    graph_runner: FakeGraphRunner,
) -> None:
    def get_test_db_session() -> Iterator:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides.clear()
    monkeypatch.setattr(dependencies, "SessionLocal", session_factory)
    monkeypatch.setattr(dependencies, "get_db_session", get_test_db_session)
    monkeypatch.setattr(
        dependencies,
        "get_research_graph_runner",
        lambda: graph_runner,
    )
