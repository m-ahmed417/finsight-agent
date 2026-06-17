from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finsight_agent.app.db.models import Base
from finsight_agent.app.db.repository import ResearchRunRepository
from finsight_agent.app.research_status import (
    RESEARCH_STATUS_COMPLETED,
    RESEARCH_STATUS_FAILED,
    RESEARCH_STATUS_QUEUED,
    RESEARCH_STATUS_RUNNING,
)


def make_repository(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    return ResearchRunRepository(session), session


def set_created_at(repository, session, run_id, created_at: datetime) -> None:
    run = repository.get_by_id(run_id)
    assert run is not None
    run.created_at = created_at
    session.commit()


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


def test_repository_creates_pending_research_run(tmp_path) -> None:
    repository, session = make_repository(tmp_path)
    run_id = uuid4()

    created = repository.create_pending_run(run_id=run_id, query="AAPL")
    retrieved = repository.get_by_id(run_id)
    steps = repository.get_steps_for_run(run_id)

    assert retrieved is not None
    assert retrieved.id == str(run_id)
    assert retrieved.query == "AAPL"
    assert retrieved.status == "queued"
    assert retrieved.ticker is None
    assert retrieved.company_name is None
    assert retrieved.compliance_status is None
    assert retrieved.report_quality_status is None
    assert retrieved.final_report is None
    assert retrieved.financial_metrics_json is None
    assert retrieved.filing_text_excerpt is None
    assert retrieved.risk_factors_json == []
    assert retrieved.risk_themes_json == []
    assert retrieved.research_insights_json is None
    assert retrieved.warnings_json == []
    assert retrieved.errors_json == []
    assert retrieved.sources_json == []
    assert retrieved.created_at is not None
    assert retrieved.completed_at is None
    assert created.id == retrieved.id
    assert steps == []

    session.close()


def test_repository_marks_research_run_running(tmp_path) -> None:
    repository, session = make_repository(tmp_path)
    run_id = uuid4()
    repository.create_pending_run(run_id=run_id, query="AAPL")

    updated = repository.mark_running(run_id)
    retrieved = repository.get_by_id(run_id)

    assert updated is not None
    assert retrieved is not None
    assert updated.id == str(run_id)
    assert retrieved.status == "running"
    assert retrieved.completed_at is None
    assert retrieved.errors_json == []

    session.close()


def test_repository_only_marks_queued_research_runs_running(tmp_path) -> None:
    repository, session = make_repository(tmp_path)
    queued_id = uuid4()
    running_id = uuid4()
    completed_id = uuid4()
    failed_id = uuid4()

    repository.create_pending_run(run_id=queued_id, query="AAPL")
    repository.create_pending_run(run_id=running_id, query="MSFT")
    repository.mark_running(running_id)
    repository.create_from_graph_result(
        run_id=completed_id,
        query="META",
        status=RESEARCH_STATUS_COMPLETED,
        graph_result={"warnings": [], "errors": [], "sources": [], "agent_steps": []},
    )
    repository.create_pending_run(run_id=failed_id, query="UNKNOWN")
    failed_run = repository.mark_failed(failed_id, error="Already failed.")
    assert failed_run is not None
    failed_completed_at = failed_run.completed_at

    claimed_run = repository.mark_running(queued_id)

    assert claimed_run is not None
    assert claimed_run.status == RESEARCH_STATUS_RUNNING
    assert repository.mark_running(running_id) is None
    assert repository.mark_running(completed_id) is None
    assert repository.mark_running(failed_id) is None

    still_running = repository.get_by_id(running_id)
    completed_run = repository.get_by_id(completed_id)
    still_failed = repository.get_by_id(failed_id)
    assert still_running is not None
    assert still_running.status == RESEARCH_STATUS_RUNNING
    assert completed_run is not None
    assert completed_run.status == RESEARCH_STATUS_COMPLETED
    assert completed_run.completed_at is not None
    assert still_failed is not None
    assert still_failed.status == RESEARCH_STATUS_FAILED
    assert still_failed.completed_at == failed_completed_at
    assert still_failed.errors_json[0]["code"] == "research_run_failed"

    session.close()


def test_repository_marks_research_run_failed(tmp_path) -> None:
    repository, session = make_repository(tmp_path)
    run_id = uuid4()
    repository.create_pending_run(run_id=run_id, query="AAPL")

    updated = repository.mark_failed(run_id, error="Worker crashed before graph output.")
    retrieved = repository.get_by_id(run_id)

    assert updated is not None
    assert retrieved is not None
    assert retrieved.status == "failed"
    assert retrieved.completed_at is not None
    assert retrieved.errors_json == [
        {
            "code": "research_run_failed",
            "message": "Worker crashed before graph output.",
            "severity": "error",
        }
    ]

    session.close()


def test_repository_marks_existing_research_run_completed_from_graph_result(
    tmp_path,
) -> None:
    repository, session = make_repository(tmp_path)
    run_id = uuid4()
    repository.create_pending_run(run_id=run_id, query="AAPL")
    repository.mark_running(run_id)

    updated = repository.mark_completed_from_graph_result(
        run_id,
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
            "sources": [{"source_id": "sec_company_facts"}],
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
            "final_report": "# FinSight Research Brief: Apple Inc. (AAPL)",
        },
    )
    retrieved = repository.get_by_id(run_id)
    steps = repository.get_steps_for_run(run_id)

    assert updated is not None
    assert retrieved is not None
    assert updated.id == str(run_id)
    assert retrieved.id == str(run_id)
    assert retrieved.query == "AAPL"
    assert retrieved.status == "completed"
    assert retrieved.ticker == "AAPL"
    assert retrieved.company_name == "Apple Inc."
    assert retrieved.compliance_status == "allowed"
    assert retrieved.report_quality_status == "passed"
    assert retrieved.final_report == "# FinSight Research Brief: Apple Inc. (AAPL)"
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
    assert retrieved.sources_json == [{"source_id": "sec_company_facts"}]
    assert retrieved.completed_at is not None
    assert [step.node_name for step in steps] == ["resolve_company", "fetch_sec_data"]
    assert [step.status for step in steps] == ["completed", "completed"]
    assert steps[0].message == "Resolved AAPL to Apple Inc."

    session.close()


def test_repository_marks_existing_research_run_failed_from_graph_result(
    tmp_path,
) -> None:
    repository, session = make_repository(tmp_path)
    run_id = uuid4()
    repository.create_pending_run(run_id=run_id, query="AAPL")
    repository.mark_running(run_id)

    updated = repository.mark_failed_from_graph_result(
        run_id,
        graph_result={
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "financial_metrics": {"periods": []},
            "warnings": [
                {
                    "code": "sec_submissions_unavailable",
                    "message": "SEC submissions could not be fetched.",
                    "severity": "warning",
                }
            ],
            "errors": [
                {
                    "code": "sec_company_facts_unavailable",
                    "message": "Could not fetch SEC company facts.",
                    "severity": "error",
                }
            ],
            "sources": [{"source_id": "sec_submissions"}],
            "agent_steps": [
                {
                    "node_name": "resolve_company",
                    "status": "completed",
                    "message": "Resolved AAPL to Apple Inc.",
                },
                {
                    "node_name": "fetch_sec_data",
                    "status": "failed",
                    "error_message": "Could not fetch SEC company facts.",
                },
            ],
        },
    )
    retrieved = repository.get_by_id(run_id)
    steps = repository.get_steps_for_run(run_id)

    assert updated is not None
    assert retrieved is not None
    assert updated.id == str(run_id)
    assert retrieved.status == "failed"
    assert retrieved.ticker == "AAPL"
    assert retrieved.company_name == "Apple Inc."
    assert retrieved.final_report is None
    assert retrieved.financial_metrics_json == {"periods": []}
    assert retrieved.filing_text_excerpt is None
    assert retrieved.risk_factors_json == []
    assert retrieved.risk_themes_json == []
    assert retrieved.research_insights_json is None
    assert retrieved.warnings_json == [
        {
            "code": "sec_submissions_unavailable",
            "message": "SEC submissions could not be fetched.",
            "severity": "warning",
        }
    ]
    assert retrieved.errors_json == [
        {
            "code": "sec_company_facts_unavailable",
            "message": "Could not fetch SEC company facts.",
            "severity": "error",
        }
    ]
    assert retrieved.sources_json == [{"source_id": "sec_submissions"}]
    assert retrieved.completed_at is not None
    assert [step.node_name for step in steps] == ["resolve_company", "fetch_sec_data"]
    assert [step.status for step in steps] == ["completed", "failed"]
    assert steps[1].error_message == "Could not fetch SEC company facts."

    session.close()


def test_repository_lifecycle_updates_return_none_for_unknown_run(tmp_path) -> None:
    repository, session = make_repository(tmp_path)
    run_id = uuid4()

    assert repository.mark_running(run_id) is None
    assert repository.mark_failed(run_id, error="Missing run.") is None
    assert repository.mark_completed_from_graph_result(run_id, graph_result={}) is None
    assert repository.mark_failed_from_graph_result(run_id, graph_result={}) is None

    session.close()


def test_repository_finds_stale_in_progress_runs(tmp_path) -> None:
    repository, session = make_repository(tmp_path)
    stale_queued_time = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)
    stale_running_time = datetime(2026, 6, 16, 10, 30, tzinfo=timezone.utc)
    fresh_time = datetime(2026, 6, 16, 12, 30, tzinfo=timezone.utc)
    cutoff = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)

    stale_queued_id = uuid4()
    stale_running_id = uuid4()
    fresh_queued_id = uuid4()
    fresh_running_id = uuid4()
    completed_id = uuid4()
    failed_id = uuid4()

    repository.create_pending_run(run_id=stale_queued_id, query="AAPL")
    set_created_at(repository, session, stale_queued_id, stale_queued_time)
    repository.create_pending_run(run_id=stale_running_id, query="MSFT")
    repository.mark_running(stale_running_id)
    set_created_at(repository, session, stale_running_id, stale_running_time)
    repository.create_pending_run(run_id=fresh_queued_id, query="NVDA")
    set_created_at(repository, session, fresh_queued_id, fresh_time)
    repository.create_pending_run(run_id=fresh_running_id, query="GOOGL")
    repository.mark_running(fresh_running_id)
    set_created_at(repository, session, fresh_running_id, fresh_time)
    repository.create_from_graph_result(
        run_id=completed_id,
        query="META",
        status=RESEARCH_STATUS_COMPLETED,
        graph_result={"warnings": [], "errors": [], "sources": [], "agent_steps": []},
    )
    set_created_at(repository, session, completed_id, stale_queued_time)
    repository.create_pending_run(run_id=failed_id, query="UNKNOWN")
    repository.mark_failed(failed_id, error="Already failed.")
    set_created_at(repository, session, failed_id, stale_queued_time)

    stale_runs = repository.get_stale_in_progress_runs(older_than=cutoff)

    assert [run.id for run in stale_runs] == [
        str(stale_queued_id),
        str(stale_running_id),
    ]
    assert [run.status for run in stale_runs] == [
        RESEARCH_STATUS_QUEUED,
        RESEARCH_STATUS_RUNNING,
    ]

    session.close()


def test_repository_marks_stale_in_progress_runs_failed(tmp_path) -> None:
    repository, session = make_repository(tmp_path)
    stale_queued_time = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)
    stale_running_time = datetime(2026, 6, 16, 10, 30, tzinfo=timezone.utc)
    fresh_time = datetime(2026, 6, 16, 12, 30, tzinfo=timezone.utc)
    cutoff = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    stale_queued_id = uuid4()
    stale_running_id = uuid4()
    fresh_running_id = uuid4()

    repository.create_pending_run(run_id=stale_queued_id, query="AAPL")
    set_created_at(repository, session, stale_queued_id, stale_queued_time)
    repository.create_pending_run(run_id=stale_running_id, query="MSFT")
    repository.mark_running(stale_running_id)
    set_created_at(repository, session, stale_running_id, stale_running_time)
    repository.create_pending_run(run_id=fresh_running_id, query="NVDA")
    repository.mark_running(fresh_running_id)
    set_created_at(repository, session, fresh_running_id, fresh_time)

    recovered = repository.mark_stale_in_progress_runs_failed(older_than=cutoff)

    assert [run.id for run in recovered] == [
        str(stale_queued_id),
        str(stale_running_id),
    ]
    for run_id in [stale_queued_id, stale_running_id]:
        run = repository.get_by_id(run_id)
        assert run is not None
        assert run.status == RESEARCH_STATUS_FAILED
        assert run.completed_at is not None
        assert run.errors_json == [
            {
                "code": "research_run_stale",
                "message": (
                    "Research run was marked failed because it remained queued or "
                    "running past the stale-run cutoff."
                ),
                "severity": "error",
            }
        ]

    fresh_run = repository.get_by_id(fresh_running_id)
    assert fresh_run is not None
    assert fresh_run.status == RESEARCH_STATUS_RUNNING
    assert fresh_run.completed_at is None
    assert fresh_run.errors_json == []

    session.close()


def test_repository_lists_recent_research_runs_newest_first_with_limit(tmp_path) -> None:
    repository, session = make_repository(tmp_path)
    oldest_id = create_run_with_created_at(
        repository,
        session,
        query="AAPL",
        status=RESEARCH_STATUS_COMPLETED,
        created_at=datetime(2026, 6, 16, 9, 0, tzinfo=timezone.utc),
    )
    newest_id = create_run_with_created_at(
        repository,
        session,
        query="MSFT",
        status=RESEARCH_STATUS_FAILED,
        created_at=datetime(2026, 6, 16, 11, 0, tzinfo=timezone.utc),
    )
    middle_id = create_run_with_created_at(
        repository,
        session,
        query="NVDA",
        status=RESEARCH_STATUS_RUNNING,
        created_at=datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc),
    )

    recent_runs = repository.list_recent_runs(limit=2)

    assert [run.id for run in recent_runs] == [str(newest_id), str(middle_id)]
    assert [run.query for run in recent_runs] == ["MSFT", "NVDA"]
    assert str(oldest_id) not in [run.id for run in recent_runs]

    session.close()


def test_repository_lists_recent_research_runs_filtered_by_status(tmp_path) -> None:
    repository, session = make_repository(tmp_path)
    older_failed_id = create_run_with_created_at(
        repository,
        session,
        query="AAPL",
        status=RESEARCH_STATUS_FAILED,
        created_at=datetime(2026, 6, 16, 9, 0, tzinfo=timezone.utc),
    )
    create_run_with_created_at(
        repository,
        session,
        query="MSFT",
        status=RESEARCH_STATUS_COMPLETED,
        created_at=datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc),
    )
    newer_failed_id = create_run_with_created_at(
        repository,
        session,
        query="NVDA",
        status=RESEARCH_STATUS_FAILED,
        created_at=datetime(2026, 6, 16, 11, 0, tzinfo=timezone.utc),
    )

    failed_runs = repository.list_recent_runs(
        status=RESEARCH_STATUS_FAILED,
        limit=10,
    )

    assert [run.id for run in failed_runs] == [
        str(newer_failed_id),
        str(older_failed_id),
    ]
    assert [run.status for run in failed_runs] == [
        RESEARCH_STATUS_FAILED,
        RESEARCH_STATUS_FAILED,
    ]

    session.close()


def test_repository_returns_none_for_unknown_run_id(tmp_path) -> None:
    repository, session = make_repository(tmp_path)

    assert repository.get_by_id(uuid4()) is None

    session.close()


def create_run_with_created_at(
    repository,
    session,
    *,
    query: str,
    status: str,
    created_at: datetime,
):
    run_id = uuid4()
    if status == RESEARCH_STATUS_COMPLETED:
        repository.create_from_graph_result(
            run_id=run_id,
            query=query,
            status=RESEARCH_STATUS_COMPLETED,
            graph_result={"warnings": [], "errors": [], "sources": [], "agent_steps": []},
        )
    elif status == RESEARCH_STATUS_FAILED:
        repository.create_pending_run(run_id=run_id, query=query)
        repository.mark_failed(run_id, error="Run failed.")
    elif status == RESEARCH_STATUS_RUNNING:
        repository.create_pending_run(run_id=run_id, query=query)
        repository.mark_running(run_id)
    else:
        repository.create_pending_run(run_id=run_id, query=query)

    set_created_at(repository, session, run_id, created_at)
    return run_id


def test_repository_returns_empty_steps_for_unknown_run_id(tmp_path) -> None:
    repository, session = make_repository(tmp_path)

    assert repository.get_steps_for_run(uuid4()) == []

    session.close()
