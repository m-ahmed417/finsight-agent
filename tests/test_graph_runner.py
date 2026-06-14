import json
from pathlib import Path

from finsight_agent.app.graph.runner import (
    build_research_graph_runner,
)
from finsight_agent.app.services.company_resolver import CompanyRecord, CompanyResolver

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FakeSECClient:
    def fetch_company_submissions(self, cik: str) -> dict:
        return json.loads((FIXTURES_DIR / "sample_submissions.json").read_text())

    def fetch_company_facts(self, cik: str) -> dict:
        return json.loads((FIXTURES_DIR / "sample_company_facts.json").read_text())


def test_build_research_graph_runner_wires_resolver_and_sec_client() -> None:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )
    graph_runner = build_research_graph_runner(
        resolver=resolver,
        sec_client=FakeSECClient(),
    )

    result = graph_runner.invoke({"user_query": "AAPL"})

    assert result["ticker"] == "AAPL"
    assert result["company_name"] == "Apple Inc."
    assert result["cik"] == "0000320193"
    assert result["latest_10k"]["accession_number"] == "0000320193-24-000123"
    assert result["financial_metrics"]["periods"][1]["free_cash_flow"] == 280000000
    assert result["errors"] == []
