from collections.abc import Iterator
from typing import Protocol
from uuid import UUID

from finsight_agent.app.db.database import SessionLocal, get_db_session
from finsight_agent.app.db.repository import ResearchRunRepository
from finsight_agent.app.graph.runner import (
    get_cached_research_graph_runner,
)
from finsight_agent.app.services.company_resolver import CompanyResolver
from finsight_agent.app.services.research_job import execute_research_run
from finsight_agent.app.services.resolver_loader import get_cached_company_resolver


class ResearchGraphRunner(Protocol):
    def invoke(self, state: dict) -> dict:
        """Run the research workflow from an initial state."""


class ResearchJobExecutor(Protocol):
    def __call__(self, *, run_id: UUID, query: str) -> object | None:
        """Execute an already queued research run."""


def get_research_graph_runner() -> ResearchGraphRunner:
    return get_cached_research_graph_runner()


def get_company_resolver() -> CompanyResolver:
    return get_cached_company_resolver()


def get_research_repository() -> Iterator[ResearchRunRepository]:
    for session in get_db_session():
        yield ResearchRunRepository(session)


def execute_research_run_background(*, run_id: UUID, query: str) -> object | None:
    session = SessionLocal()
    try:
        repository = ResearchRunRepository(session)
        return execute_research_run(
            run_id=run_id,
            query=query,
            graph_runner=get_research_graph_runner(),
            repository=repository,
        )
    finally:
        session.close()


def get_research_job_executor() -> ResearchJobExecutor:
    return execute_research_run_background
