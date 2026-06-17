from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finsight_agent.app.config import get_settings
from finsight_agent.app import main as app_main
from finsight_agent.app.db.models import Base
from finsight_agent.app.db.repository import ResearchRunRepository
from finsight_agent.app.main import create_app
from finsight_agent.app.research_status import (
    RESEARCH_STATUS_COMPLETED,
    RESEARCH_STATUS_FAILED,
    RESEARCH_STATUS_RUNNING,
)


def test_create_app_returns_fastapi_application() -> None:
    get_settings.cache_clear()

    app = create_app()

    assert isinstance(app, FastAPI)
    assert app.title == "FinSight"


def test_create_app_registers_health_route() -> None:
    get_settings.cache_clear()

    app = create_app()
    route_paths = {route.path for route in app.routes}

    assert "/health" in route_paths


def test_create_app_recovers_stale_in_progress_runs_on_startup(
    tmp_path,
    monkeypatch,
) -> None:
    session_factory = make_session_factory(tmp_path)
    fixed_now = datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)
    stale_created_at = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)
    fresh_created_at = datetime(2026, 6, 16, 12, 30, tzinfo=timezone.utc)
    stale_queued_id, stale_running_id, fresh_running_id, completed_id = seed_runs(
        session_factory,
        stale_created_at=stale_created_at,
        fresh_created_at=fresh_created_at,
    )
    monkeypatch.setenv("RESEARCH_RUN_STALE_AFTER_SECONDS", "3600")
    monkeypatch.setattr(app_main, "init_db", lambda: None)
    monkeypatch.setattr(app_main, "SessionLocal", session_factory)
    monkeypatch.setattr(app_main, "utc_now", lambda: fixed_now)
    get_settings.cache_clear()

    app = app_main.create_app()
    with TestClient(app):
        pass

    session = session_factory()
    try:
        repository = ResearchRunRepository(session)
        stale_queued = repository.get_by_id(stale_queued_id)
        stale_running = repository.get_by_id(stale_running_id)
        fresh_running = repository.get_by_id(fresh_running_id)
        completed = repository.get_by_id(completed_id)

        assert stale_queued is not None
        assert stale_queued.status == RESEARCH_STATUS_FAILED
        assert stale_queued.completed_at is not None
        assert stale_queued.errors_json[0]["code"] == "research_run_stale"
        assert stale_running is not None
        assert stale_running.status == RESEARCH_STATUS_FAILED
        assert stale_running.completed_at is not None
        assert stale_running.errors_json[0]["code"] == "research_run_stale"
        assert fresh_running is not None
        assert fresh_running.status == RESEARCH_STATUS_RUNNING
        assert fresh_running.completed_at is None
        assert completed is not None
        assert completed.status == RESEARCH_STATUS_COMPLETED
    finally:
        session.close()
        get_settings.cache_clear()


def make_session_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'startup-recovery.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def seed_runs(session_factory, *, stale_created_at: datetime, fresh_created_at: datetime):
    session = session_factory()
    try:
        repository = ResearchRunRepository(session)
        stale_queued_id = repository.create_pending_run(
            run_id=uuid4(),
            query="AAPL",
        ).id
        stale_running_id = repository.create_pending_run(
            run_id=uuid4(),
            query="MSFT",
        ).id
        repository.mark_running(UUID(stale_running_id))
        fresh_running_id = repository.create_pending_run(
            run_id=uuid4(),
            query="NVDA",
        ).id
        repository.mark_running(UUID(fresh_running_id))
        completed_id = repository.create_from_graph_result(
            run_id=uuid4(),
            query="META",
            status=RESEARCH_STATUS_COMPLETED,
            graph_result={"warnings": [], "errors": [], "sources": [], "agent_steps": []},
        ).id

        set_created_at(repository, session, stale_queued_id, stale_created_at)
        set_created_at(repository, session, stale_running_id, stale_created_at)
        set_created_at(repository, session, fresh_running_id, fresh_created_at)
        set_created_at(repository, session, completed_id, stale_created_at)
        return (
            UUID(stale_queued_id),
            UUID(stale_running_id),
            UUID(fresh_running_id),
            UUID(completed_id),
        )
    finally:
        session.close()


def set_created_at(repository, session, run_id: str, created_at: datetime) -> None:
    run = repository.get_by_id(UUID(run_id))
    assert run is not None
    run.created_at = created_at
    session.commit()
