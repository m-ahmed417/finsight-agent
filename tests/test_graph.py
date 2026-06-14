import json
from datetime import datetime
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

    def fetch_filing_document(
        self,
        cik: str,
        accession_number: str,
        primary_document: str,
    ) -> str:
        return (FIXTURES_DIR / "sample_10k_excerpt.txt").read_text()


class FailingSECClient:
    def fetch_company_submissions(self, cik: str) -> dict:
        raise RuntimeError("SEC unavailable")

    def fetch_company_facts(self, cik: str) -> dict:
        raise RuntimeError("SEC unavailable")


class FilingDocumentFailingSECClient(FakeSECClient):
    def fetch_filing_document(
        self,
        cik: str,
        accession_number: str,
        primary_document: str,
    ) -> str:
        raise RuntimeError("Filing document unavailable")


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def source_by_type(sources: list[dict], source_type: str) -> dict:
    return next(source for source in sources if source["source_type"] == source_type)


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
    assert "The Company faces intense competition" in result["filing_text"]
    assert result["risk_factors"] == [
        {
            "source_type": "sec_risk_factors",
            "form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "0000320193-24-000123",
            "source_url": (
                "https://www.sec.gov/Archives/edgar/data/320193/"
                "000032019324000123/aapl-20240928.htm"
            ),
            "text": (
                "The Company faces intense competition in all markets in which it operates.\n"
                "Supply chain disruption, component shortages, or manufacturing delays could\n"
                "adversely affect results of operations. The Company's business also depends on\n"
                "continued access to third-party software, services, and distribution channels."
            ),
        }
    ]
    assert result["risk_themes"] == [
        {
            "title": "Competitive pressure",
            "summary": (
                "The filing describes competition as a material business risk that "
                "could pressure operating performance."
            ),
            "source_form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "0000320193-24-000123",
            "source_url": (
                "https://www.sec.gov/Archives/edgar/data/320193/"
                "000032019324000123/aapl-20240928.htm"
            ),
        },
        {
            "title": "Supply chain and manufacturing disruption",
            "summary": (
                "The filing indicates that supply chain disruption, component "
                "availability, or manufacturing delays could affect operations."
            ),
            "source_form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "0000320193-24-000123",
            "source_url": (
                "https://www.sec.gov/Archives/edgar/data/320193/"
                "000032019324000123/aapl-20240928.htm"
            ),
        },
        {
            "title": "Third-party platform and distribution dependence",
            "summary": (
                "The filing notes dependence on third-party software, services, or "
                "distribution channels as an operating risk."
            ),
            "source_form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "0000320193-24-000123",
            "source_url": (
                "https://www.sec.gov/Archives/edgar/data/320193/"
                "000032019324000123/aapl-20240928.htm"
            ),
        },
    ]
    assert result["sources"]
    submissions_source = source_by_type(result["sources"], "sec_submissions")
    company_facts_source = source_by_type(result["sources"], "sec_company_facts")
    filing_10k_source = next(
        source
        for source in result["sources"]
        if source["source_type"] == "sec_filing" and source["form"] == "10-K"
    )
    filing_10q_source = next(
        source
        for source in result["sources"]
        if source["source_type"] == "sec_filing" and source["form"] == "10-Q"
    )
    assert submissions_source["url"] == (
        "https://data.sec.gov/submissions/CIK0000320193.json"
    )
    assert company_facts_source["url"] == (
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    )
    assert submissions_source["cik"] == "0000320193"
    assert datetime.fromisoformat(submissions_source["retrieved_at"])
    assert filing_10k_source == {
        "source_type": "sec_filing",
        "label": "Latest 10-K filing",
        "cik": "0000320193",
        "form": "10-K",
        "filing_date": "2024-11-01",
        "report_date": "2024-09-28",
        "accession_number": "0000320193-24-000123",
        "primary_document": "aapl-20240928.htm",
        "url": (
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019324000123/aapl-20240928.htm"
        ),
    }
    assert filing_10q_source["accession_number"] == "0000320193-24-000099"
    assert "# FinSight Research Brief: Apple Inc. (AAPL)" in result["final_report"]
    assert "## 5. Key Financial Metrics" in result["final_report"]
    assert result["compliance_status"] == "allowed"
    assert [step["node_name"] for step in result["agent_steps"]] == [
        "resolve_company",
        "fetch_sec_data",
        "identify_filings",
        "fetch_filing_text",
        "analyze_risks",
        "extract_metrics",
        "generate_report",
        "compliance_check",
    ]
    assert all(step["status"] == "completed" for step in result["agent_steps"])
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
    assert result["agent_steps"] == [
        {
            "node_name": "resolve_company",
            "status": "failed",
            "message": "Could not confidently resolve the company.",
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
    assert result["agent_steps"] == [
        {
            "node_name": "resolve_company",
            "status": "failed",
            "message": "Multiple companies matched the query.",
        }
    ]


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
    assert result["agent_steps"][-1] == {
        "node_name": "fetch_sec_data",
        "status": "failed",
        "message": "SEC unavailable",
    }


def test_research_graph_continues_when_filing_text_is_unavailable() -> None:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )
    sec_client = FilingDocumentFailingSECClient(
        submissions=load_fixture("sample_submissions.json"),
        company_facts=load_fixture("sample_company_facts.json"),
    )
    graph = build_research_graph(resolver=resolver, sec_client=sec_client)

    result = graph.invoke({"user_query": "AAPL"})

    assert result["ticker"] == "AAPL"
    assert result["filing_text"] is None
    assert result["risk_factors"] == []
    assert result["risk_themes"] == []
    assert result["financial_metrics"]["periods"][1]["revenue"] == 1250000000
    assert result["final_report"] is not None
    assert {
        "code": "filing_text_unavailable",
        "message": "Filing document unavailable",
        "severity": "warning",
    } in result["warnings"]
    assert {
        "node_name": "fetch_filing_text",
        "status": "completed",
        "message": "Could not retrieve latest 10-K risk-factor text.",
    } in result["agent_steps"]
    assert {
        "node_name": "analyze_risks",
        "status": "completed",
        "message": "Risk-factor text was unavailable for analysis.",
    } in result["agent_steps"]
    assert result["errors"] == []
