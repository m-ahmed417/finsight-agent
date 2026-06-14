from functools import lru_cache
from typing import Any

from finsight_agent.app.config import get_settings
from finsight_agent.app.graph.builder import build_research_graph
from finsight_agent.app.services.company_resolver import CompanyRecord, CompanyResolver
from finsight_agent.app.services.sec_client import SECClient


def build_static_company_resolver() -> CompanyResolver:
    return CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
            CompanyRecord(
                ticker="MSFT",
                company_name="Microsoft Corporation",
                cik="789019",
            ),
            CompanyRecord(ticker="TSLA", company_name="Tesla, Inc.", cik="1318605"),
            CompanyRecord(
                ticker="NVDA",
                company_name="NVIDIA Corporation",
                cik="1045810",
            ),
        ]
    )


def build_research_graph_runner(sec_client: Any | None = None):
    settings = get_settings()
    resolver = build_static_company_resolver()
    configured_sec_client = sec_client or SECClient(user_agent=settings.sec_user_agent)
    return build_research_graph(resolver=resolver, sec_client=configured_sec_client)


@lru_cache
def get_cached_research_graph_runner():
    return build_research_graph_runner()
