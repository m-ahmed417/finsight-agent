from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI

from finsight_agent.app.api.routes import router
from finsight_agent.app.config import get_settings
from finsight_agent.app.db.database import SessionLocal, init_db
from finsight_agent.app.db.models import utc_now
from finsight_agent.app.db.repository import ResearchRunRepository


def recover_stale_research_runs(*, stale_after_seconds: float) -> int:
    older_than = utc_now() - timedelta(seconds=stale_after_seconds)
    session = SessionLocal()
    try:
        repository = ResearchRunRepository(session)
        stale_runs = repository.mark_stale_in_progress_runs_failed(
            older_than=older_than,
        )
        return len(stale_runs)
    finally:
        session.close()


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        recover_stale_research_runs(
            stale_after_seconds=settings.research_run_stale_after_seconds,
        )
        yield

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Production-style AI equity research assistant.",
        lifespan=lifespan,
    )
    init_db()
    app.include_router(router)
    return app


app = create_app()
