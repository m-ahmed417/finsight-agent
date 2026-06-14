from collections.abc import Iterator
from typing import Protocol

from finsight_agent.app.db.database import get_db_session
from finsight_agent.app.db.repository import ResearchRunRepository
from finsight_agent.app.graph.runner import (
    build_static_company_resolver,
    get_cached_research_graph_runner,
)
from finsight_agent.app.services.company_resolver import CompanyResolver


class ResearchGraphRunner(Protocol):
    def invoke(self, state: dict) -> dict:
        """Run the research workflow from an initial state."""


def get_research_graph_runner() -> ResearchGraphRunner:
    return get_cached_research_graph_runner()


def get_company_resolver() -> CompanyResolver:
    return build_static_company_resolver()


def get_research_repository() -> Iterator[ResearchRunRepository]:
    for session in get_db_session():
        yield ResearchRunRepository(session)
