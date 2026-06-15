import json
from pathlib import Path

from finsight_agent.app.config import get_settings
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

    def fetch_filing_document(
        self,
        cik: str,
        accession_number: str,
        primary_document: str,
    ) -> str:
        return (FIXTURES_DIR / "sample_10k_excerpt.txt").read_text()


class FakeLLMClient:
    def summarize_risks(self, risk_factors: list[dict]) -> dict:
        return {
            "themes": [
                {
                    "title": "Injected LLM theme",
                    "summary": "The injected LLM client was used.",
                    "source_form": risk_factors[0]["form"],
                    "filing_date": risk_factors[0]["filing_date"],
                    "accession_number": risk_factors[0]["accession_number"],
                    "source_url": risk_factors[0]["source_url"],
                }
            ],
            "warnings": [],
        }


def test_build_research_graph_runner_wires_resolver_and_sec_client() -> None:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )
    graph_runner = build_research_graph_runner(
        resolver=resolver,
        sec_client=FakeSECClient(),
        llm_client=FakeLLMClient(),
    )

    result = graph_runner.invoke({"user_query": "AAPL"})

    assert result["ticker"] == "AAPL"
    assert result["company_name"] == "Apple Inc."
    assert result["cik"] == "0000320193"
    assert result["latest_10k"]["accession_number"] == "0000320193-24-000123"
    assert result["financial_metrics"]["periods"][1]["free_cash_flow"] == 280000000
    assert result["risk_themes"][0]["title"] == "Injected LLM theme"
    assert result["errors"] == []


def test_build_research_graph_runner_passes_sec_settings(
    monkeypatch,
    tmp_path,
) -> None:
    captured: dict[str, object] = {}

    class CapturingSECClient:
        def __init__(
            self,
            user_agent: str,
            cache_dir: str | None = None,
            min_request_interval_seconds: float = 0.0,
        ) -> None:
            captured["user_agent"] = user_agent
            captured["cache_dir"] = cache_dir
            captured["min_request_interval_seconds"] = min_request_interval_seconds

        def fetch_company_submissions(self, cik: str) -> dict:
            return {}

        def fetch_company_facts(self, cik: str) -> dict:
            return {}

        def fetch_filing_document(
            self,
            cik: str,
            accession_number: str,
            primary_document: str,
        ) -> str:
            return ""

    get_settings.cache_clear()
    cache_dir = tmp_path / "sec-cache"
    monkeypatch.setenv("SEC_USER_AGENT", "FinSightTest/0.1 test@example.com")
    monkeypatch.setenv("SEC_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("SEC_REQUEST_INTERVAL_SECONDS", "0.25")
    monkeypatch.setattr(
        "finsight_agent.app.graph.runner.SECClient",
        CapturingSECClient,
    )
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )

    build_research_graph_runner(resolver=resolver, llm_client=FakeLLMClient())

    assert captured == {
        "user_agent": "FinSightTest/0.1 test@example.com",
        "cache_dir": str(cache_dir),
        "min_request_interval_seconds": 0.25,
    }
    get_settings.cache_clear()
