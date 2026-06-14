import json
from datetime import datetime
from pathlib import Path

from finsight_agent.app.graph.builder import (
    _compliance_check,
    _extract_metrics,
    build_research_graph,
)
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


class FakeLLMClient:
    def summarize_risks(self, risk_factors: list[dict]) -> dict:
        return {
            "themes": [
                {
                    "title": "LLM summarized risk",
                    "summary": "A mock LLM summarized this risk from extracted filing text.",
                    "source_form": risk_factors[0]["form"],
                    "filing_date": risk_factors[0]["filing_date"],
                    "accession_number": risk_factors[0]["accession_number"],
                    "source_url": risk_factors[0]["source_url"],
                }
            ],
            "warnings": [],
        }

    def draft_report(self, evidence: dict) -> dict:
        return {
            "sections": {
                "executive_summary": ["LLM-written graph summary."],
                "financial_performance": "LLM-written graph financial performance.",
                "risk_factors": ["LLM-written graph risk factor."],
                "bull_case": ["LLM-written graph bull case."],
                "bear_case": ["LLM-written graph bear case."],
                "open_questions": ["LLM-written graph open question."],
            },
            "warnings": [],
        }


class FailingLLMClient:
    def summarize_risks(self, risk_factors: list[dict]) -> dict:
        raise RuntimeError("LLM unavailable")

    def draft_report(self, evidence: dict) -> dict:
        raise RuntimeError("LLM report drafting unavailable")


class EmptyThemesLLMClient:
    def summarize_risks(self, risk_factors: list[dict]) -> dict:
        return {"themes": [], "warnings": []}


class InvalidReportDraftLLMClient(FakeLLMClient):
    def draft_report(self, evidence: dict) -> dict:
        return {"sections": {"executive_summary": []}, "warnings": []}


class UnsafeReportDraftLLMClient(FakeLLMClient):
    def draft_report(self, evidence: dict) -> dict:
        return {
            "sections": {
                "executive_summary": ["LLM-written graph summary."],
                "financial_performance": "LLM-written graph financial performance.",
                "risk_factors": ["LLM-written graph risk factor."],
                "bull_case": ["You should buy this stock because growth is guaranteed."],
                "bear_case": ["The price will crash if execution weakens."],
                "open_questions": ["LLM-written graph open question."],
            },
            "warnings": [],
        }


class UnrewritableUnsafeReportDraftLLMClient(FakeLLMClient):
    def draft_report(self, evidence: dict) -> dict:
        return {
            "sections": {
                "executive_summary": ["LLM-written graph summary."],
                "financial_performance": "LLM-written graph financial performance.",
                "risk_factors": ["LLM-written graph risk factor."],
                "bull_case": ["This report includes buybuy wording."],
                "bear_case": ["LLM-written graph bear case."],
                "open_questions": ["LLM-written graph open question."],
            },
            "warnings": [],
        }


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def source_by_type(sources: list[dict], source_type: str) -> dict:
    return next(source for source in sources if source["source_type"] == source_type)


def test_extract_metrics_does_not_mutate_existing_state_warnings() -> None:
    existing_warnings = [
        {
            "code": "existing_warning",
            "message": "Existing warning.",
            "severity": "warning",
        }
    ]
    state = {
        "company_facts": {},
        "warnings": existing_warnings,
        "agent_steps": [],
    }

    result = _extract_metrics(state)

    assert state["warnings"] == [
        {
            "code": "existing_warning",
            "message": "Existing warning.",
            "severity": "warning",
        }
    ]
    assert result["warnings"] is not state["warnings"]
    assert result["warnings"] == [
        *existing_warnings,
        {
            "code": "metric_warning",
            "message": "Revenue could not be extracted from SEC company facts.",
            "severity": "warning",
        },
    ]


def test_compliance_check_does_not_mutate_existing_warning_or_error_lists() -> None:
    existing_warnings = [
        {
            "code": "existing_warning",
            "message": "Existing warning.",
            "severity": "warning",
        }
    ]
    existing_errors: list[dict[str, str]] = []
    state = {
        "report_draft": "This report includes buybuy wording.",
        "warnings": existing_warnings,
        "errors": existing_errors,
        "agent_steps": [],
    }

    result = _compliance_check(state)

    assert state["warnings"] == existing_warnings
    assert state["errors"] == []
    assert result["warnings"] is not state["warnings"]
    assert result["errors"] is not state["errors"]
    assert result["errors"] == [
        {
            "code": "compliance_blocked",
            "message": "Report contained unsafe financial-advice language.",
            "severity": "error",
        }
    ]


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
    assert result["research_insights"]["bull_case"] == [
        {
            "title": "Revenue growth",
            "summary": (
                "Extracted revenue increased 25.00% year over year in fiscal 2024."
            ),
            "source": "SEC company facts",
        },
        {
            "title": "Positive free cash flow",
            "summary": "Extracted free cash flow was 280000000 in fiscal 2024.",
            "source": "SEC company facts",
        },
    ]
    assert result["research_insights"]["bear_case"][0]["title"] == "Competitive pressure"
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
    source_ids = [source["source_id"] for source in result["sources"]]
    assert source_ids == [
        "sec_submissions",
        "sec_company_facts",
        "latest_10k",
        "latest_10q",
    ]
    assert len(source_ids) == len(set(source_ids))
    assert submissions_source["source_id"] == "sec_submissions"
    assert company_facts_source["source_id"] == "sec_company_facts"
    assert submissions_source["url"] == (
        "https://data.sec.gov/submissions/CIK0000320193.json"
    )
    assert company_facts_source["url"] == (
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    )
    assert submissions_source["cik"] == "0000320193"
    assert datetime.fromisoformat(submissions_source["retrieved_at"])
    assert filing_10k_source == {
        "source_id": "latest_10k",
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
    assert filing_10q_source["source_id"] == "latest_10q"
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
        "synthesize_research",
        "draft_report",
        "generate_report",
        "compliance_check",
        "validate_report",
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
    assert result["research_insights"]["bear_case"] == []
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


def test_research_graph_can_use_injected_llm_client_for_risk_themes() -> None:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )
    sec_client = FakeSECClient(
        submissions=load_fixture("sample_submissions.json"),
        company_facts=load_fixture("sample_company_facts.json"),
    )
    graph = build_research_graph(
        resolver=resolver,
        sec_client=sec_client,
        llm_client=FakeLLMClient(),
    )

    result = graph.invoke({"user_query": "AAPL"})

    assert result["risk_themes"] == [
        {
            "title": "LLM summarized risk",
            "summary": "A mock LLM summarized this risk from extracted filing text.",
            "source_form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "0000320193-24-000123",
            "source_url": (
                "https://www.sec.gov/Archives/edgar/data/320193/"
                "000032019324000123/aapl-20240928.htm"
            ),
        }
    ]
    assert {
        "node_name": "analyze_risks",
        "status": "completed",
        "message": "Generated LLM-assisted risk themes from extracted 10-K text.",
    } in result["agent_steps"]
    assert result["llm_report_sections"]["executive_summary"] == [
        "LLM-written graph summary."
    ]
    assert "LLM-written graph bull case." in result["final_report"]
    assert {
        "node_name": "draft_report",
        "status": "completed",
        "message": "Generated LLM-assisted report sections from structured evidence.",
    } in result["agent_steps"]


def test_research_graph_falls_back_to_deterministic_risk_analysis_when_llm_fails() -> None:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )
    sec_client = FakeSECClient(
        submissions=load_fixture("sample_submissions.json"),
        company_facts=load_fixture("sample_company_facts.json"),
    )
    graph = build_research_graph(
        resolver=resolver,
        sec_client=sec_client,
        llm_client=FailingLLMClient(),
    )

    result = graph.invoke({"user_query": "AAPL"})

    assert result["risk_themes"][0]["title"] == "Competitive pressure"
    assert {
        "code": "llm_risk_analysis_unavailable",
        "message": "LLM unavailable",
        "severity": "warning",
    } in result["warnings"]
    assert {
        "node_name": "analyze_risks",
        "status": "completed",
        "message": "Generated deterministic risk themes from extracted 10-K text.",
    } in result["agent_steps"]


def test_research_graph_falls_back_when_llm_returns_empty_themes() -> None:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )
    sec_client = FakeSECClient(
        submissions=load_fixture("sample_submissions.json"),
        company_facts=load_fixture("sample_company_facts.json"),
    )
    graph = build_research_graph(
        resolver=resolver,
        sec_client=sec_client,
        llm_client=EmptyThemesLLMClient(),
    )

    result = graph.invoke({"user_query": "AAPL"})

    assert result["risk_themes"][0]["title"] == "Competitive pressure"
    assert {
        "code": "llm_risk_analysis_unavailable",
        "message": "LLM risk analysis must include at least one theme.",
        "severity": "warning",
    } in result["warnings"]


def test_research_graph_falls_back_when_llm_report_draft_is_invalid() -> None:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )
    sec_client = FakeSECClient(
        submissions=load_fixture("sample_submissions.json"),
        company_facts=load_fixture("sample_company_facts.json"),
    )
    graph = build_research_graph(
        resolver=resolver,
        sec_client=sec_client,
        llm_client=InvalidReportDraftLLMClient(),
    )

    result = graph.invoke({"user_query": "AAPL"})

    assert result["llm_report_sections"] is None
    assert "LLM-written graph bull case." not in result["final_report"]
    assert "Revenue growth" in result["final_report"]
    assert {
        "code": "llm_report_drafting_unavailable",
        "message": "LLM report draft must include valid report sections.",
        "severity": "warning",
    } in result["warnings"]
    assert {
        "node_name": "draft_report",
        "status": "completed",
        "message": "Using deterministic report generator after LLM report drafting failed.",
    } in result["agent_steps"]


def test_research_graph_rewrites_unsafe_llm_report_language() -> None:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )
    sec_client = FakeSECClient(
        submissions=load_fixture("sample_submissions.json"),
        company_facts=load_fixture("sample_company_facts.json"),
    )
    graph = build_research_graph(
        resolver=resolver,
        sec_client=sec_client,
        llm_client=UnsafeReportDraftLLMClient(),
    )

    result = graph.invoke({"user_query": "AAPL"})

    assert result["compliance_status"] == "needs_rewrite"
    assert result["final_report"] is not None
    assert "you should buy" not in result["final_report"].casefold()
    assert "guaranteed" not in result["final_report"].casefold()
    assert "price will crash" not in result["final_report"].casefold()
    assert {
        "code": "compliance_warning",
        "message": (
            "Unsafe financial-advice language was rewritten into neutral "
            "research phrasing."
        ),
        "severity": "warning",
    } in result["warnings"]
    assert {
        "node_name": "compliance_check",
        "status": "completed",
        "message": "Report required deterministic compliance rewrite and passed.",
    } in result["agent_steps"]
    assert {
        "node_name": "validate_report",
        "status": "completed",
        "message": "Report quality validation completed without warnings.",
    } in result["agent_steps"]
    assert result["errors"] == []


def test_research_graph_blocks_when_rewrite_cannot_make_report_safe() -> None:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )
    sec_client = FakeSECClient(
        submissions=load_fixture("sample_submissions.json"),
        company_facts=load_fixture("sample_company_facts.json"),
    )
    graph = build_research_graph(
        resolver=resolver,
        sec_client=sec_client,
        llm_client=UnrewritableUnsafeReportDraftLLMClient(),
    )

    result = graph.invoke({"user_query": "AAPL"})

    assert result["compliance_status"] == "blocked"
    assert result["final_report"] is None
    assert {
        "code": "compliance_blocked",
        "message": "Report contained unsafe financial-advice language.",
        "severity": "error",
    } in result["errors"]
    assert {
        "node_name": "compliance_check",
        "status": "failed",
        "message": "Report contained unsafe financial-advice language.",
    } in result["agent_steps"]
    assert not any(
        step["node_name"] == "validate_report" for step in result["agent_steps"]
    )
