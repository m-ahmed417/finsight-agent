import json
from pathlib import Path

from finsight_agent.app.graph.builder import build_research_graph
from finsight_agent.app.services.company_resolver import CompanyRecord, CompanyResolver

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FakeSECClient:
    def __init__(self, submissions: dict, company_facts: dict) -> None:
        self.submissions = submissions
        self.company_facts = company_facts

    def fetch_company_submissions(self, cik: str) -> dict:
        return self.submissions

    def fetch_company_facts(self, cik: str) -> dict:
        return self.company_facts


class FailingSECClient:
    def fetch_company_submissions(self, cik: str) -> dict:
        raise RuntimeError("SEC unavailable")

    def fetch_company_facts(self, cik: str) -> dict:
        raise RuntimeError("SEC unavailable")


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def test_research_graph_successful_run_resolves_fetches_filings_and_metrics() -> None:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )
    sec_client = FakeSECClient(
        submissions=load_fixture("sample_submissions.json"),
        company_facts=load_fixture("sample_company_facts.json"),
    )
    graph = build_research_graph(resolver=resolver, sec_client=sec_client)

    result = graph.invoke({"user_query": "AAPL"})

    assert result["ticker"] == "AAPL"
    assert result["company_name"] == "Apple Inc."
    assert result["cik"] == "0000320193"
    assert result["latest_10k"]["accession_number"] == "0000320193-24-000123"
    assert result["latest_10q"]["accession_number"] == "0000320193-24-000099"
    assert result["financial_metrics"]["periods"][1]["revenue"] == 1250000000
    assert result["financial_metrics"]["periods"][1]["free_cash_flow"] == 280000000
    assert result["errors"] == []


def test_research_graph_stops_when_company_is_not_found() -> None:
    resolver = CompanyResolver(companies=[])
    sec_client = FakeSECClient(submissions={}, company_facts={})
    graph = build_research_graph(resolver=resolver, sec_client=sec_client)

    result = graph.invoke({"user_query": "UNKNOWN"})

    assert result["ticker"] is None
    assert result["company_name"] is None
    assert result["financial_metrics"] is None
    assert result["errors"] == [
        {
            "code": "company_not_found",
            "message": "Could not confidently resolve the company.",
            "severity": "error",
        }
    ]


def test_research_graph_stops_when_company_is_ambiguous() -> None:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
            CompanyRecord(
                ticker="APLE",
                company_name="Apple Hospitality REIT, Inc.",
                cik="1418121",
            ),
        ]
    )
    sec_client = FakeSECClient(submissions={}, company_facts={})
    graph = build_research_graph(resolver=resolver, sec_client=sec_client)

    result = graph.invoke({"user_query": "Apple"})

    assert result["ticker"] is None
    assert result["financial_metrics"] is None
    assert result["candidate_matches"] == [
        {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "cik": "0000320193",
        },
        {
            "ticker": "APLE",
            "company_name": "Apple Hospitality REIT, Inc.",
            "cik": "0001418121",
        },
    ]
    assert result["errors"][0]["code"] == "company_ambiguous"


def test_research_graph_records_sec_fetch_failure() -> None:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )
    graph = build_research_graph(resolver=resolver, sec_client=FailingSECClient())

    result = graph.invoke({"user_query": "AAPL"})

    assert result["ticker"] == "AAPL"
    assert result["financial_metrics"] is None
    assert result["errors"] == [
        {
            "code": "sec_fetch_failed",
            "message": "SEC unavailable",
            "severity": "error",
        }
    ]
