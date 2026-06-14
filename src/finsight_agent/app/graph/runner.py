from functools import lru_cache
from typing import Any

from finsight_agent.app.config import get_settings
from finsight_agent.app.graph.builder import build_research_graph
from finsight_agent.app.services.llm_client import get_llm_client
from finsight_agent.app.services.resolver_loader import get_cached_company_resolver
from finsight_agent.app.services.sec_client import SECClient


def build_research_graph_runner(
    sec_client: Any | None = None,
    resolver: Any | None = None,
    llm_client: Any | None = None,
):
    settings = get_settings()
    configured_resolver = resolver or get_cached_company_resolver()
    configured_sec_client = sec_client or SECClient(user_agent=settings.sec_user_agent)
    configured_llm_client = llm_client or get_llm_client(settings)
    return build_research_graph(
        resolver=configured_resolver,
        sec_client=configured_sec_client,
        llm_client=configured_llm_client,
    )


@lru_cache
def get_cached_research_graph_runner():
    return build_research_graph_runner()
