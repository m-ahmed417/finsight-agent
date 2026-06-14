import json
from pathlib import Path

from finsight_agent.app.graph.runner import (
    build_research_graph_runner,
    build_static_company_resolver,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FakeSECClient:
    def fetch_company_submissions(self, cik: str) -> dict:
        return json.loads((FIXTURES_DIR / "sample_submissions.json").read_text())

    def fetch_company_facts(self, cik: str) -> dict:
        return json.loads((FIXTURES_DIR / "sample_company_facts.json").read_text())


def test_static_company_resolver_supports_mvp_tickers() -> None:
    resolver = build_static_company_resolver()

    apple = resolver.resolve("AAPL")
    microsoft = resolver.resolve("MSFT")
    tesla = resolver.resolve("TSLA")
    nvidia = resolver.resolve("NVDA")

    assert apple.company is not None
    assert apple.company.cik == "0000320193"
    assert microsoft.company is not None
    assert microsoft.company.cik == "0000789019"
    assert tesla.company is not None
    assert tesla.company.cik == "0001318605"
    assert nvidia.company is not None
    assert nvidia.company.cik == "0001045810"


def test_build_research_graph_runner_wires_static_resolver_and_sec_client() -> None:
    graph_runner = build_research_graph_runner(sec_client=FakeSECClient())

    result = graph_runner.invoke({"user_query": "AAPL"})

    assert result["ticker"] == "AAPL"
    assert result["company_name"] == "Apple Inc."
    assert result["cik"] == "0000320193"
    assert result["latest_10k"]["accession_number"] == "0000320193-24-000123"
    assert result["financial_metrics"]["periods"][1]["free_cash_flow"] == 280000000
    assert result["errors"] == []
