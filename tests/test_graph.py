import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from finsight_agent.app.graph.builder import (
    _compliance_check,
    _extract_metrics,
    build_research_graph,
)
from finsight_agent.app.services.company_resolver import CompanyRecord, CompanyResolver
from finsight_agent.app.services.report_generator import RESEARCH_ONLY_NOTICE

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SCAFFOLD_REPORT_MARKERS = (
    "mvp draft",
    "future versions will",
    "pending deterministic synthesis",
    "not been generated yet",
    "future llm-assisted step",
    "no sources were recorded",
    "has not been performed yet",
)


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


class BusinessSectionMissingSECClient(FakeSECClient):
    def fetch_filing_document(
        self,
        cik: str,
        accession_number: str,
        primary_document: str,
    ) -> str:
        return (
            "Item 1A. Risk Factors\n\n"
            "The Company faces intense competition in all markets in which it operates.\n\n"
            "Item 1B. Unresolved Staff Comments\n\n"
            "None."
        )


class CacheMetadataSECClient(FakeSECClient):
    def fetch_company_submissions_with_metadata(self, cik: str) -> SimpleNamespace:
        return SimpleNamespace(
            data=self.submissions,
            metadata=SimpleNamespace(
                url="https://data.sec.gov/submissions/CIK0000320193.json",
                cache_key="company_submissions:0000320193",
                cache_status="miss",
                cache_age_seconds=0.25,
                cache_ttl_seconds=86400.0,
                cache_expires_at="2026-06-17T10:00:00+00:00",
                cache_stale=False,
            ),
        )

    def fetch_company_facts_with_metadata(self, cik: str) -> SimpleNamespace:
        return SimpleNamespace(
            data=self.company_facts,
            metadata=SimpleNamespace(
                url=(
                    "https://data.sec.gov/api/xbrl/companyfacts/"
                    "CIK0000320193.json"
                ),
                cache_key="company_facts:0000320193",
                cache_status="hit",
                cache_age_seconds=120.5,
                cache_ttl_seconds=21600.0,
                cache_expires_at="2026-06-16T16:00:00+00:00",
                cache_stale=False,
            ),
        )

    def fetch_filing_document_with_metadata(
        self,
        *,
        cik: str,
        accession_number: str,
        primary_document: str,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            data=(FIXTURES_DIR / "sample_10k_excerpt.txt").read_text(),
            metadata=SimpleNamespace(
                url=(
                    "https://www.sec.gov/Archives/edgar/data/320193/"
                    "000032019324000123/aapl-20240928.htm"
                ),
                cache_key=(
                    "filing_document:0000320193:"
                    "000032019324000123:aapl-20240928.htm"
                ),
                cache_status="miss",
                cache_age_seconds=0.5,
                cache_ttl_seconds=604800.0,
                cache_expires_at="2026-06-23T10:00:00+00:00",
                cache_stale=False,
            ),
        )


class FakeLLMClient:
    provider = "fake"
    model_name = "fake-model"

    def summarize_risks(self, risk_factors: list[dict]) -> dict:
        self.last_call_metadata = {
            "input_tokens": 120,
            "output_tokens": 42,
            "total_tokens": 162,
            "provider_request_id": "risk-req-123",
        }
        return {
            "themes": [
                {
                    "title": "LLM summarized risk",
                    "summary": "A mock LLM summarized this risk from extracted filing text.",
                    "source_form": risk_factors[0]["form"],
                    "filing_date": risk_factors[0]["filing_date"],
                    "accession_number": risk_factors[0]["accession_number"],
                    "source_url": risk_factors[0]["source_url"],
                    "source_ids": risk_factors[0]["source_ids"],
                }
            ],
            "warnings": [],
        }

    def draft_report(self, evidence: dict) -> dict:
        self.last_call_metadata = {
            "input_tokens": 300,
            "output_tokens": 150,
            "total_tokens": 450,
            "provider_request_id": "draft-req-456",
        }
        return {
            "sections": {
                "executive_summary": ["LLM-written graph summary."],
                "financial_performance": (
                    "LLM-written graph financial performance. [sec_company_facts]"
                ),
                "risk_factors": ["LLM-written graph risk factor. [latest_10k]"],
                "bull_case": ["LLM-written graph bull case. [sec_company_facts]"],
                "bear_case": ["LLM-written graph bear case. [latest_10k]"],
                "open_questions": ["LLM-written graph open question."],
            },
            "warnings": [],
        }


class FailingLLMClient:
    provider = "fake"
    model_name = "fake-model"

    def summarize_risks(self, risk_factors: list[dict]) -> dict:
        self.last_call_metadata = {"provider_request_id": "risk-fail-req"}
        raise RuntimeError("LLM unavailable")

    def draft_report(self, evidence: dict) -> dict:
        self.last_call_metadata = {"provider_request_id": "draft-fail-req"}
        raise RuntimeError("LLM report drafting unavailable")


class EmptyThemesLLMClient:
    provider = "fake"
    model_name = "fake-model"

    def summarize_risks(self, risk_factors: list[dict]) -> dict:
        return {"themes": [], "warnings": []}


class WarningLLMClient(FakeLLMClient):
    def summarize_risks(self, risk_factors: list[dict]) -> dict:
        result = super().summarize_risks(risk_factors)
        return {
            **result,
            "warnings": ["Risk summary used condensed provider output."],
        }

    def draft_report(self, evidence: dict) -> dict:
        result = super().draft_report(evidence)
        return {
            **result,
            "warnings": ["Report draft used condensed provider output."],
        }


class InvalidReportDraftLLMClient(FakeLLMClient):
    def draft_report(self, evidence: dict) -> dict:
        self.last_call_metadata = {
            "input_tokens": 300,
            "output_tokens": 150,
            "total_tokens": 450,
            "provider_request_id": "draft-req-456",
        }
        return {"sections": {"executive_summary": []}, "warnings": []}


class CitationlessReportDraftLLMClient(FakeLLMClient):
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


class UnknownCitationReportDraftLLMClient(FakeLLMClient):
    def draft_report(self, evidence: dict) -> dict:
        return {
            "sections": {
                "executive_summary": ["LLM-written graph summary."],
                "financial_performance": (
                    "LLM-written graph financial performance. "
                    "[sec_company_facts] [made_up_source]"
                ),
                "risk_factors": ["LLM-written graph risk factor. [latest_10k]"],
                "bull_case": ["LLM-written graph bull case. [sec_company_facts]"],
                "bear_case": ["LLM-written graph bear case. [latest_10k]"],
                "open_questions": ["LLM-written graph open question."],
            },
            "warnings": [],
        }


class UnsafeReportDraftLLMClient(FakeLLMClient):
    def draft_report(self, evidence: dict) -> dict:
        return {
            "sections": {
                "executive_summary": ["LLM-written graph summary."],
                "financial_performance": (
                    "LLM-written graph financial performance. [sec_company_facts]"
                ),
                "risk_factors": ["LLM-written graph risk factor. [latest_10k]"],
                "bull_case": [
                    "You should buy this stock because growth is guaranteed. "
                    "[sec_company_facts]"
                ],
                "bear_case": ["The price will crash if execution weakens. [latest_10k]"],
                "open_questions": ["LLM-written graph open question."],
            },
            "warnings": [],
        }


class UnrewritableUnsafeReportDraftLLMClient(FakeLLMClient):
    def draft_report(self, evidence: dict) -> dict:
        return {
            "sections": {
                "executive_summary": ["LLM-written graph summary."],
                "financial_performance": (
                    "LLM-written graph financial performance. [sec_company_facts]"
                ),
                "risk_factors": ["LLM-written graph risk factor. [latest_10k]"],
                "bull_case": ["This report includes buybuy wording. [sec_company_facts]"],
                "bear_case": ["LLM-written graph bear case. [latest_10k]"],
                "open_questions": ["LLM-written graph open question."],
            },
            "warnings": [],
        }


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def source_by_type(sources: list[dict], source_type: str) -> dict:
    return next(source for source in sources if source["source_type"] == source_type)


def extract_report_section(report: str, heading: str) -> str:
    start = report.find(heading)
    assert start != -1
    next_heading = report.find("\n## ", start + len(heading))
    if next_heading == -1:
        return report[start:]
    return report[start:next_heading]


def assert_agent_step(
    result: dict,
    *,
    node_name: str,
    status: str,
    message: str,
) -> dict:
    step = next(
        step for step in result["agent_steps"] if step["node_name"] == node_name
    )
    assert_step_matches(
        step,
        node_name=node_name,
        status=status,
        message=message,
    )
    return step


def assert_step_matches(
    step: dict,
    *,
    node_name: str,
    status: str,
    message: str,
) -> None:
    assert step["node_name"] == node_name
    assert step["status"] == status
    assert step["message"] == message
    assert_step_has_timing(step)


def assert_step_has_timing(step: dict) -> None:
    started_at = datetime.fromisoformat(step["started_at"])
    completed_at = datetime.fromisoformat(step["completed_at"])
    assert started_at.tzinfo is not None
    assert completed_at.tzinfo is not None
    assert completed_at >= started_at
    assert isinstance(step["duration_seconds"], int | float)
    assert step["duration_seconds"] >= 0.0
    computed_duration = (completed_at - started_at).total_seconds()
    assert abs(computed_duration - step["duration_seconds"]) < 0.001


def assert_llm_call_has_timing(event: dict) -> None:
    started_at = datetime.fromisoformat(event["started_at"])
    completed_at = datetime.fromisoformat(event["completed_at"])
    assert started_at.tzinfo is not None
    assert completed_at.tzinfo is not None
    assert completed_at >= started_at
    assert isinstance(event["duration_seconds"], int | float)
    assert event["duration_seconds"] >= 0.0


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
    assert len(result["risk_factors"]) == 1
    risk_factor = result["risk_factors"][0]
    expected_risk_text = (
        "The Company faces intense competition in all markets in which it operates.\n"
        "Supply chain disruption, component shortages, or manufacturing delays could\n"
        "adversely affect results of operations. The Company's business also depends on\n"
        "continued access to third-party software, services, and distribution channels."
    )
    assert {
        "source_id": risk_factor["source_id"],
        "source_type": risk_factor["source_type"],
        "form": risk_factor["form"],
        "filing_date": risk_factor["filing_date"],
        "accession_number": risk_factor["accession_number"],
        "source_url": risk_factor["source_url"],
        "source_ids": risk_factor["source_ids"],
        "section": risk_factor["section"],
        "section_label": risk_factor["section_label"],
        "text": risk_factor["text"],
    } == {
        "source_id": "latest_10k",
        "source_type": "sec_risk_factors",
        "form": "10-K",
        "filing_date": "2024-11-01",
        "accession_number": "0000320193-24-000123",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019324000123/aapl-20240928.htm"
        ),
        "source_ids": ["latest_10k"],
        "section": "Item 1A",
        "section_label": "Risk Factors",
        "text": expected_risk_text,
    }
    assert risk_factor["text_character_count"] == len(expected_risk_text)
    assert datetime.fromisoformat(risk_factor["extracted_at"])
    expected_business_text = (
        "Apple Inc. designs, manufactures, and markets smartphones, personal computers,\n"
        "tablets, wearables, and accessories."
    )
    assert len(result["business_sections"]) == 1
    business_section = result["business_sections"][0]
    assert {
        "source_id": business_section["source_id"],
        "source_type": business_section["source_type"],
        "form": business_section["form"],
        "filing_date": business_section["filing_date"],
        "accession_number": business_section["accession_number"],
        "source_url": business_section["source_url"],
        "source_ids": business_section["source_ids"],
        "section": business_section["section"],
        "section_label": business_section["section_label"],
        "text": business_section["text"],
    } == {
        "source_id": "latest_10k",
        "source_type": "sec_business_section",
        "form": "10-K",
        "filing_date": "2024-11-01",
        "accession_number": "0000320193-24-000123",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019324000123/aapl-20240928.htm"
        ),
        "source_ids": ["latest_10k"],
        "section": "Item 1",
        "section_label": "Business",
        "text": expected_business_text,
    }
    assert business_section["text_character_count"] == len(expected_business_text)
    assert datetime.fromisoformat(business_section["extracted_at"])
    assert result["business_overview"] == {
        "status": "available",
        "summary": (
            "Apple Inc. (AAPL) has Item 1 Business evidence from the latest "
            "10-K filed 2024-11-01. Use this SEC filing evidence for company "
            "overview context without adding external company descriptions."
        ),
        "source": "10-K filed 2024-11-01, accession 0000320193-24-000123",
        "source_ids": ["latest_10k"],
        "source_form": "10-K",
        "filing_date": "2024-11-01",
        "accession_number": "0000320193-24-000123",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019324000123/aapl-20240928.htm"
        ),
        "section": "Item 1",
        "section_label": "Business",
        "text_character_count": len(expected_business_text),
        "limitations": [],
    }
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
            "source_ids": ["latest_10k"],
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
            "source_ids": ["latest_10k"],
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
            "source_ids": ["latest_10k"],
        },
    ]
    assert result["research_insights"]["bull_case"] == [
        {
            "title": "Revenue growth",
            "summary": (
                "Extracted revenue increased 25.00% year over year in fiscal 2024."
            ),
            "source": "SEC company facts",
            "source_ids": ["sec_company_facts"],
        },
        {
            "title": "Positive free cash flow",
            "summary": "Extracted free cash flow was 280000000 in fiscal 2024.",
            "source": "SEC company facts",
            "source_ids": ["sec_company_facts"],
        },
    ]
    assert result["research_insights"]["bear_case"][0]["title"] == "Competitive pressure"
    assert result["research_insights"]["bear_case"][0]["source_ids"] == ["latest_10k"]
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
    assert submissions_source["publisher"] == "U.S. Securities and Exchange Commission"
    assert company_facts_source["publisher"] == "U.S. Securities and Exchange Commission"
    assert submissions_source["company_name"] == "Apple Inc."
    assert submissions_source["ticker"] == "AAPL"
    assert submissions_source["data_format"] == "json"
    assert submissions_source["retrieval_method"] == "http_get"
    assert submissions_source["url"] == (
        "https://data.sec.gov/submissions/CIK0000320193.json"
    )
    assert company_facts_source["url"] == (
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    )
    assert submissions_source["cik"] == "0000320193"
    assert datetime.fromisoformat(submissions_source["retrieved_at"])
    assert company_facts_source["metric_extraction_status"] == "metrics_extracted"
    assert company_facts_source["metric_fiscal_years"] == [2023, 2024]
    assert company_facts_source["filing_forms_used"] == ["10-K"]
    assert company_facts_source["xbrl_tags_used"] == [
        "Assets",
        "CashAndCashEquivalentsAtCarryingValue",
        "Liabilities",
        "LongTermDebt",
        "NetCashProvidedByUsedInOperatingActivities",
        "NetIncomeLoss",
        "OperatingIncomeLoss",
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
    ]
    assert datetime.fromisoformat(company_facts_source["retrieved_at"])
    assert datetime.fromisoformat(company_facts_source["metric_extracted_at"])
    assert {
        "source_id": filing_10k_source["source_id"],
        "source_type": filing_10k_source["source_type"],
        "label": filing_10k_source["label"],
        "publisher": filing_10k_source["publisher"],
        "cik": filing_10k_source["cik"],
        "company_name": filing_10k_source["company_name"],
        "ticker": filing_10k_source["ticker"],
        "form": filing_10k_source["form"],
        "filing_date": filing_10k_source["filing_date"],
        "report_date": filing_10k_source["report_date"],
        "accession_number": filing_10k_source["accession_number"],
        "accession_path": filing_10k_source["accession_path"],
        "primary_document": filing_10k_source["primary_document"],
        "url": filing_10k_source["url"],
        "data_format": filing_10k_source["data_format"],
        "metadata_source_ids": filing_10k_source["metadata_source_ids"],
        "extraction_status": filing_10k_source["extraction_status"],
        "extracted_sections": filing_10k_source["extracted_sections"],
    } == {
        "source_id": "latest_10k",
        "source_type": "sec_filing",
        "label": "Latest 10-K filing",
        "publisher": "U.S. Securities and Exchange Commission",
        "cik": "0000320193",
        "company_name": "Apple Inc.",
        "ticker": "AAPL",
        "form": "10-K",
        "filing_date": "2024-11-01",
        "report_date": "2024-09-28",
        "accession_number": "0000320193-24-000123",
        "accession_path": "000032019324000123",
        "primary_document": "aapl-20240928.htm",
        "url": (
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019324000123/aapl-20240928.htm"
        ),
        "data_format": "html",
        "metadata_source_ids": ["sec_submissions"],
        "extraction_status": "business_and_risk_factors_extracted",
        "extracted_sections": ["Item 1 Business", "Item 1A Risk Factors"],
    }
    assert filing_10k_source["document_character_count"] == len(result["filing_text"])
    assert filing_10k_source["business_text_character_count"] == len(
        expected_business_text
    )
    assert filing_10k_source["risk_factor_text_character_count"] == len(
        expected_risk_text
    )
    assert datetime.fromisoformat(filing_10k_source["metadata_retrieved_at"])
    assert datetime.fromisoformat(filing_10k_source["document_retrieved_at"])
    assert filing_10q_source["source_id"] == "latest_10q"
    assert filing_10q_source["accession_number"] == "0000320193-24-000099"
    assert filing_10q_source["metadata_source_ids"] == ["sec_submissions"]
    assert datetime.fromisoformat(filing_10q_source["metadata_retrieved_at"])
    assert "# FinSight Research Brief: Apple Inc. (AAPL)" in result["final_report"]
    assert RESEARCH_ONLY_NOTICE in result["final_report"]
    assert "## 5. Key Financial Metrics" in result["final_report"]
    assert "[sec_company_facts]" in result["final_report"]
    assert "[latest_10k]" in result["final_report"]
    overview_section = extract_report_section(
        result["final_report"],
        "## 3. Company Overview",
    )
    sources_section = extract_report_section(
        result["final_report"],
        "## 10. Sources Used",
    )
    assert result["business_overview"]["summary"] in overview_section
    assert (
        "Source: 10-K filed 2024-11-01, accession 0000320193-24-000123."
        in overview_section
    )
    assert "[latest_10k]" in overview_section
    assert expected_business_text not in result["final_report"]
    assert "smartphones" not in result["final_report"].casefold()
    assert "extracted sections: Item 1 Business, Item 1A Risk Factors" in sources_section
    assert result["compliance_status"] == "allowed"
    assert result["report_quality_status"] == "passed"
    assert not any(
        marker in result["final_report"].casefold()
        for marker in SCAFFOLD_REPORT_MARKERS
    )
    assert not any(
        warning["code"] == "report_quality_warning"
        for warning in result["warnings"]
    )
    step_by_name = {step["node_name"]: step for step in result["agent_steps"]}
    assert step_by_name["fetch_sec_data"]["message"] == (
        "Fetched SEC submissions and company facts for CIK 0000320193; "
        "recorded sources: sec_submissions, sec_company_facts."
    )
    assert step_by_name["identify_filings"]["message"] == (
        "Identified latest 10-K 0000320193-24-000123 filed 2024-11-01 and "
        "latest 10-Q 0000320193-24-000099 filed 2024-08-02."
    )
    assert step_by_name["fetch_filing_text"]["message"] == (
        "Retrieved latest 10-K business and risk-factor text; "
        f"document characters: {len(result['filing_text'])}, "
        f"business characters: {len(expected_business_text)}, "
        f"risk-factor characters: {len(expected_risk_text)}."
    )
    assert step_by_name["extract_metrics"]["message"] == (
        "Extracted financial metrics from SEC company facts; "
        "fiscal years: 2023, 2024; XBRL tags used: 9."
    )
    assert step_by_name["analyze_risks"]["llm_used"] is False
    assert step_by_name["analyze_risks"]["llm_fallback_reason"] == (
        "No LLM client configured."
    )
    assert step_by_name["draft_report"]["llm_used"] is False
    assert step_by_name["draft_report"]["llm_fallback_reason"] == (
        "No report-drafting LLM client configured."
    )
    assert result["llm_call_events"] == [
        {
            "node_name": "analyze_risks",
            "task": "risk_analysis",
            "status": "skipped",
            "prompt_version": "risk_analysis:v1",
            "fallback_used": True,
            "fallback_reason": "No LLM client configured.",
        },
        {
            "node_name": "draft_report",
            "task": "report_drafting",
            "status": "skipped",
            "prompt_version": "report_drafting:v1",
            "fallback_used": True,
            "fallback_reason": "No report-drafting LLM client configured.",
        },
    ]
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
    assert_agent_step(
        result,
        node_name="validate_report",
        status="completed",
        message="Report quality validation completed without warnings.",
    )
    assert all(step["status"] == "completed" for step in result["agent_steps"])
    for step in result["agent_steps"]:
        assert_step_has_timing(step)
    assert result["errors"] == []


def test_research_graph_records_sec_cache_metadata_when_available() -> None:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )
    sec_client = CacheMetadataSECClient(
        submissions=load_fixture("sample_submissions.json"),
        company_facts=load_fixture("sample_company_facts.json"),
    )
    graph = build_research_graph(resolver=resolver, sec_client=sec_client)

    result = graph.invoke({"user_query": "AAPL"})

    submissions_source = source_by_type(result["sources"], "sec_submissions")
    company_facts_source = source_by_type(result["sources"], "sec_company_facts")
    filing_10k_source = next(
        source
        for source in result["sources"]
        if source["source_type"] == "sec_filing" and source["form"] == "10-K"
    )
    assert submissions_source["cache_status"] == "miss"
    assert submissions_source["cache_key"] == "company_submissions:0000320193"
    assert submissions_source["cache_age_seconds"] == 0.25
    assert submissions_source["cache_ttl_seconds"] == 86400.0
    assert submissions_source["cache_expires_at"] == "2026-06-17T10:00:00+00:00"
    assert submissions_source["cache_stale"] is False
    assert company_facts_source["cache_status"] == "hit"
    assert company_facts_source["cache_key"] == "company_facts:0000320193"
    assert company_facts_source["cache_age_seconds"] == 120.5
    assert company_facts_source["cache_ttl_seconds"] == 21600.0
    assert company_facts_source["cache_expires_at"] == "2026-06-16T16:00:00+00:00"
    assert company_facts_source["cache_stale"] is False
    assert filing_10k_source["document_cache_status"] == "miss"
    assert filing_10k_source["document_cache_key"] == (
        "filing_document:0000320193:000032019324000123:aapl-20240928.htm"
    )
    assert filing_10k_source["document_cache_age_seconds"] == 0.5
    assert filing_10k_source["document_cache_ttl_seconds"] == 604800.0
    assert filing_10k_source["document_cache_expires_at"] == (
        "2026-06-23T10:00:00+00:00"
    )
    assert filing_10k_source["document_cache_stale"] is False


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
    assert len(result["agent_steps"]) == 1
    assert_agent_step(
        result,
        node_name="resolve_company",
        status="failed",
        message="Could not confidently resolve the company.",
    )


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
    assert len(result["agent_steps"]) == 1
    assert_agent_step(
        result,
        node_name="resolve_company",
        status="failed",
        message="Multiple companies matched the query.",
    )


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
    assert_step_matches(
        result["agent_steps"][-1],
        node_name="fetch_sec_data",
        status="failed",
        message="SEC unavailable",
    )


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
    assert result["business_sections"] == []
    assert result["business_overview"] == {
        "status": "limited",
        "summary": (
            "Apple Inc. (AAPL) business overview is limited to resolved company "
            "identity because Item 1 Business evidence was not available in this run."
        ),
        "source_ids": [],
        "limitations": ["Filing document unavailable"],
    }
    assert result["risk_factors"] == []
    assert result["risk_themes"] == []
    assert result["financial_metrics"]["periods"][1]["revenue"] == 1250000000
    assert result["research_insights"]["bear_case"] == []
    assert result["final_report"] is not None
    assert {
        "code": "filing_text_unavailable",
        "message": "Filing document unavailable",
        "severity": "warning",
        "details": {"reason": "Filing document unavailable"},
    } in result["warnings"]
    assert_agent_step(
        result,
        node_name="fetch_filing_text",
        status="completed",
        message="Could not retrieve latest 10-K risk-factor text.",
    )
    assert_agent_step(
        result,
        node_name="analyze_risks",
        status="completed",
        message="Risk-factor text was unavailable for analysis.",
    )
    assert result["errors"] == []


def test_research_graph_warns_when_business_section_is_missing() -> None:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )
    sec_client = BusinessSectionMissingSECClient(
        submissions=load_fixture("sample_submissions.json"),
        company_facts=load_fixture("sample_company_facts.json"),
    )
    graph = build_research_graph(resolver=resolver, sec_client=sec_client)

    result = graph.invoke({"user_query": "AAPL"})

    assert result["business_sections"] == []
    assert result["business_overview"] == {
        "status": "limited",
        "summary": (
            "Apple Inc. (AAPL) business overview is limited to resolved company "
            "identity because Item 1 Business evidence was not available in this run."
        ),
        "source_ids": [],
        "limitations": ["Item 1 business section could not be extracted."],
    }
    assert len(result["risk_factors"]) == 1
    assert result["final_report"] is not None
    assert {
        "code": "business_section_unavailable",
        "message": "Item 1 business section could not be extracted.",
        "severity": "warning",
        "details": {
            "source_id": "latest_10k",
            "accession_number": "0000320193-24-000123",
            "primary_document": "aapl-20240928.htm",
            "document_character_count": len(result["filing_text"]),
        },
    } in result["warnings"]
    filing_10k_source = next(
        source
        for source in result["sources"]
        if source["source_type"] == "sec_filing" and source["form"] == "10-K"
    )
    assert filing_10k_source["extraction_status"] == "risk_factors_extracted"
    assert filing_10k_source["extracted_sections"] == ["Item 1A Risk Factors"]
    assert "business_text_character_count" not in filing_10k_source
    assert_agent_step(
        result,
        node_name="fetch_filing_text",
        status="completed",
        message=(
            "Retrieved latest 10-K risk-factor text; business section unavailable; "
            f"document characters: {len(result['filing_text'])}, "
            f"risk-factor characters: {len(result['risk_factors'][0]['text'])}."
        ),
    )
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
            "source_ids": ["latest_10k"],
        }
    ]
    risk_step = assert_agent_step(
        result,
        node_name="analyze_risks",
        status="completed",
        message="Generated LLM-assisted risk themes from extracted 10-K text.",
    )
    assert risk_step["llm_provider"] == "fake"
    assert risk_step["llm_model"] == "fake-model"
    assert risk_step["llm_used"] is True
    assert risk_step.get("llm_fallback_reason") is None
    risk_call = result["llm_call_events"][0]
    assert risk_call["node_name"] == "analyze_risks"
    assert risk_call["task"] == "risk_analysis"
    assert risk_call["status"] == "completed"
    assert risk_call["llm_provider"] == "fake"
    assert risk_call["llm_model"] == "fake-model"
    assert risk_call["prompt_version"] == "risk_analysis:v1"
    assert risk_call["input_tokens"] == 120
    assert risk_call["output_tokens"] == 42
    assert risk_call["total_tokens"] == 162
    assert risk_call["provider_request_id"] == "risk-req-123"
    assert risk_call["fallback_used"] is False
    assert_llm_call_has_timing(risk_call)
    assert result["llm_report_sections"]["executive_summary"] == [
        "LLM-written graph summary."
    ]
    assert "LLM-written graph bull case." in result["final_report"]
    draft_step = assert_agent_step(
        result,
        node_name="draft_report",
        status="completed",
        message="Generated LLM-assisted report sections from structured evidence.",
    )
    assert draft_step["llm_provider"] == "fake"
    assert draft_step["llm_model"] == "fake-model"
    assert draft_step["llm_used"] is True
    assert draft_step.get("llm_fallback_reason") is None
    draft_call = result["llm_call_events"][1]
    assert draft_call["node_name"] == "draft_report"
    assert draft_call["task"] == "report_drafting"
    assert draft_call["status"] == "completed"
    assert draft_call["llm_provider"] == "fake"
    assert draft_call["llm_model"] == "fake-model"
    assert draft_call["prompt_version"] == "report_drafting:v1"
    assert draft_call["input_tokens"] == 300
    assert draft_call["output_tokens"] == 150
    assert draft_call["total_tokens"] == 450
    assert draft_call["provider_request_id"] == "draft-req-456"
    assert draft_call["fallback_used"] is False
    assert_llm_call_has_timing(draft_call)


def test_research_graph_preserves_llm_warnings_as_structured_workflow_warnings() -> None:
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
        llm_client=WarningLLMClient(),
    )

    result = graph.invoke({"user_query": "AAPL"})

    assert {
        "code": "llm_risk_analysis_warning",
        "message": "Risk summary used condensed provider output.",
        "severity": "warning",
    } in result["warnings"]
    assert {
        "code": "llm_report_drafting_warning",
        "message": "Report draft used condensed provider output.",
        "severity": "warning",
    } in result["warnings"]
    assert not any(isinstance(warning, str) for warning in result["warnings"])
    assert result["report_quality_status"] == "passed"


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
        "details": {
            "llm_provider": "fake",
            "llm_model": "fake-model",
            "fallback": "deterministic_risk_analysis",
        },
    } in result["warnings"]
    risk_step = assert_agent_step(
        result,
        node_name="analyze_risks",
        status="completed",
        message="Generated deterministic risk themes from extracted 10-K text.",
    )
    assert risk_step["llm_provider"] == "fake"
    assert risk_step["llm_model"] == "fake-model"
    assert risk_step["llm_used"] is False
    assert risk_step["llm_fallback_reason"] == "LLM unavailable"
    risk_call = result["llm_call_events"][0]
    assert risk_call["node_name"] == "analyze_risks"
    assert risk_call["task"] == "risk_analysis"
    assert risk_call["status"] == "failed"
    assert risk_call["llm_provider"] == "fake"
    assert risk_call["llm_model"] == "fake-model"
    assert risk_call["prompt_version"] == "risk_analysis:v1"
    assert risk_call["provider_request_id"] == "risk-fail-req"
    assert risk_call["error_type"] == "RuntimeError"
    assert risk_call["error_message"] == "LLM unavailable"
    assert risk_call["fallback_used"] is True
    assert risk_call["fallback_reason"] == "LLM unavailable"
    assert_llm_call_has_timing(risk_call)


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
        "details": {
            "llm_provider": "fake",
            "llm_model": "fake-model",
            "fallback": "deterministic_risk_analysis",
        },
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
        "details": {
            "llm_provider": "fake",
            "llm_model": "fake-model",
            "fallback": "deterministic_report_generator",
        },
    } in result["warnings"]
    draft_step = assert_agent_step(
        result,
        node_name="draft_report",
        status="completed",
        message="Using deterministic report generator after LLM report drafting failed.",
    )
    assert draft_step["llm_provider"] == "fake"
    assert draft_step["llm_model"] == "fake-model"
    assert draft_step["llm_used"] is False
    assert draft_step["llm_fallback_reason"] == (
        "LLM report draft must include valid report sections."
    )
    draft_call = result["llm_call_events"][1]
    assert draft_call["node_name"] == "draft_report"
    assert draft_call["task"] == "report_drafting"
    assert draft_call["status"] == "failed"
    assert draft_call["llm_provider"] == "fake"
    assert draft_call["llm_model"] == "fake-model"
    assert draft_call["prompt_version"] == "report_drafting:v1"
    assert draft_call["input_tokens"] == 300
    assert draft_call["output_tokens"] == 150
    assert draft_call["total_tokens"] == 450
    assert draft_call["provider_request_id"] == "draft-req-456"
    assert draft_call["error_type"] == "ValueError"
    assert draft_call["error_message"] == (
        "LLM report draft must include valid report sections."
    )
    assert draft_call["fallback_used"] is True
    assert draft_call["fallback_reason"] == (
        "LLM report draft must include valid report sections."
    )
    assert_llm_call_has_timing(draft_call)


def test_research_graph_falls_back_when_llm_report_draft_lacks_citations() -> None:
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
        llm_client=CitationlessReportDraftLLMClient(),
    )

    result = graph.invoke({"user_query": "AAPL"})

    assert result["llm_report_sections"] is None
    assert "LLM-written graph bull case." not in result["final_report"]
    assert "[sec_company_facts]" in result["final_report"]
    assert "[latest_10k]" in result["final_report"]
    assert {
        "code": "llm_report_drafting_unavailable",
        "message": (
            "LLM report draft must include known source_id citations in "
            "source-grounded sections."
        ),
        "severity": "warning",
        "details": {
            "llm_provider": "fake",
            "llm_model": "fake-model",
            "fallback": "deterministic_report_generator",
        },
    } in result["warnings"]
    draft_step = assert_agent_step(
        result,
        node_name="draft_report",
        status="completed",
        message="Using deterministic report generator after LLM report drafting failed.",
    )
    assert draft_step["llm_provider"] == "fake"
    assert draft_step["llm_model"] == "fake-model"
    assert draft_step["llm_used"] is False
    assert draft_step["llm_fallback_reason"] == (
        "LLM report draft must include known source_id citations in "
        "source-grounded sections."
    )


def test_research_graph_falls_back_when_llm_report_draft_uses_unknown_citation() -> None:
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
        llm_client=UnknownCitationReportDraftLLMClient(),
    )

    result = graph.invoke({"user_query": "AAPL"})

    assert result["llm_report_sections"] is None
    assert "LLM-written graph financial performance" not in result["final_report"]
    assert "[made_up_source]" not in result["final_report"]
    assert {
        "code": "llm_report_drafting_unavailable",
        "message": "LLM report draft cited unknown source_id: made_up_source.",
        "severity": "warning",
        "details": {
            "llm_provider": "fake",
            "llm_model": "fake-model",
            "fallback": "deterministic_report_generator",
        },
    } in result["warnings"]
    draft_step = assert_agent_step(
        result,
        node_name="draft_report",
        status="completed",
        message="Using deterministic report generator after LLM report drafting failed.",
    )
    assert draft_step["llm_used"] is False
    assert draft_step["llm_fallback_reason"] == (
        "LLM report draft cited unknown source_id: made_up_source."
    )
    assert result["report_quality_status"] == "passed"


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
    assert_agent_step(
        result,
        node_name="compliance_check",
        status="completed",
        message="Report required deterministic compliance rewrite and passed.",
    )
    assert result["report_quality_status"] == "passed"
    assert_agent_step(
        result,
        node_name="validate_report",
        status="completed",
        message="Report quality validation completed without warnings.",
    )
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
    assert_agent_step(
        result,
        node_name="compliance_check",
        status="failed",
        message="Report contained unsafe financial-advice language.",
    )
    assert not any(
        step["node_name"] == "validate_report" for step in result["agent_steps"]
    )
