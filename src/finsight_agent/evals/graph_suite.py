from collections.abc import Sequence
from typing import Any

from finsight_agent.app.graph.builder import build_research_graph
from finsight_agent.app.services.company_resolver import CompanyRecord, CompanyResolver
from finsight_agent.evals.evaluators import evaluate_report_quality_checks
from finsight_agent.evals.models import (
    EvalCase,
    EvalCaseResult,
    EvalCheckResult,
    EvalExpectations,
    EvalStatus,
    EvalSuiteResult,
)

DETERMINISTIC_GRAPH_EVAL_SUITE = "deterministic_graph_quality"
EXPECTED_RESEARCH_CITATIONS = ["sec_company_facts", "latest_10k"]


class GraphEvalConfigurationError(ValueError):
    """Raised when a deterministic graph eval case references unknown fixtures."""


SAMPLE_SUBMISSIONS: dict[str, Any] = {
    "cik": "0000320193",
    "name": "Apple Inc.",
    "filings": {
        "recent": {
            "accessionNumber": [
                "0000320193-24-000123",
                "0000320193-24-000099",
                "0000320193-23-000106",
                "0000320193-24-000050",
                "0000320193-24-000051",
            ],
            "filingDate": [
                "2024-11-01",
                "2024-08-02",
                "2023-11-03",
                "2024-07-01",
                "2024-06-01",
            ],
            "reportDate": [
                "2024-09-28",
                "2024-06-29",
                "2023-09-30",
                "2024-03-30",
                "2024-03-30",
            ],
            "form": [
                "10-K",
                "10-Q",
                "10-K",
                "10-K/A",
                "8-K",
            ],
            "primaryDocument": [
                "aapl-20240928.htm",
                "aapl-20240629.htm",
                "aapl-20230930.htm",
                "aapl-20240330x10ka.htm",
                "aapl-20240601.htm",
            ],
            "primaryDocDescription": [
                "10-K",
                "10-Q",
                "10-K",
                "10-K/A",
                "8-K",
            ],
        }
    },
}

SAMPLE_COMPANY_FACTS: dict[str, Any] = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {
                    "USD": [
                        {
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                            "val": 1000000000,
                        },
                        {
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-Q",
                            "filed": "2024-08-02",
                            "val": 1100000000,
                        },
                        {
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2024-11-01",
                            "val": 1250000000,
                        },
                    ]
                }
            },
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        {
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                            "val": 150000000,
                        },
                        {
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2024-11-01",
                            "val": 250000000,
                        },
                    ]
                }
            },
            "OperatingIncomeLoss": {
                "units": {
                    "USD": [
                        {
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                            "val": 220000000,
                        },
                        {
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2024-11-01",
                            "val": 300000000,
                        },
                    ]
                }
            },
            "Assets": {
                "units": {
                    "USD": [
                        {
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                            "val": 3500000000,
                        },
                        {
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2024-11-01",
                            "val": 4000000000,
                        },
                    ]
                }
            },
            "Liabilities": {
                "units": {
                    "USD": [
                        {
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                            "val": 2100000000,
                        },
                        {
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2024-11-01",
                            "val": 2400000000,
                        },
                    ]
                }
            },
            "CashAndCashEquivalentsAtCarryingValue": {
                "units": {
                    "USD": [
                        {
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                            "val": 700000000,
                        },
                        {
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2024-11-01",
                            "val": 900000000,
                        },
                    ]
                }
            },
            "LongTermDebt": {
                "units": {
                    "USD": [
                        {
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                            "val": 800000000,
                        },
                        {
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2024-11-01",
                            "val": 850000000,
                        },
                    ]
                }
            },
            "NetCashProvidedByUsedInOperatingActivities": {
                "units": {
                    "USD": [
                        {
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                            "val": 300000000,
                        },
                        {
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2024-11-01",
                            "val": 400000000,
                        },
                    ]
                }
            },
            "PaymentsToAcquirePropertyPlantAndEquipment": {
                "units": {
                    "USD": [
                        {
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                            "val": 100000000,
                        },
                        {
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2024-11-01",
                            "val": 120000000,
                        },
                    ]
                }
            },
        }
    },
}

SAMPLE_10K_EXCERPT = """Item 1. Business

Apple Inc. designs, manufactures, and markets smartphones, personal computers,
tablets, wearables, and accessories.

Item 1A. Risk Factors

The Company faces intense competition in all markets in which it operates.
Supply chain disruption, component shortages, or manufacturing delays could
adversely affect results of operations. The Company's business also depends on
continued access to third-party software, services, and distribution channels.

Item 1B. Unresolved Staff Comments

None."""

BUSINESS_SECTION_MISSING_10K = """Item 1A. Risk Factors

The Company faces intense competition in all markets in which it operates.

Item 1B. Unresolved Staff Comments

None."""

RISK_SECTION_MISSING_10K = """PART I

Item 1. Business

The company provides regulated utility services to regional customers through
long-term operating assets.

Item 2. Properties

The company owns and leases property used for operations."""

HEADING_VARIANT_10K = """PART I

ITEM 1 - BUSINESS

Example Software Corp. provides compliance workflow software and support
services to enterprise customers through subscription contracts.

ITEM 1A: RISK FACTORS

The company faces implementation risk, customer renewal risk, and competition
from larger software vendors.

ITEM 2. PROPERTIES

The company leases office space for administrative operations."""

SEC_DOCUMENT_FIXTURES = {
    "sample_10k_excerpt": SAMPLE_10K_EXCERPT,
    "business_section_missing": BUSINESS_SECTION_MISSING_10K,
    "risk_section_missing": RISK_SECTION_MISSING_10K,
    "heading_variant_10k": HEADING_VARIANT_10K,
}


class FixtureSECClient:
    def __init__(self, document_text: str) -> None:
        self.document_text = document_text

    def fetch_company_submissions(self, cik: str) -> dict[str, Any]:
        return SAMPLE_SUBMISSIONS

    def fetch_company_facts(self, cik: str) -> dict[str, Any]:
        return SAMPLE_COMPANY_FACTS

    def fetch_filing_document(
        self,
        cik: str,
        accession_number: str,
        primary_document: str,
    ) -> str:
        return self.document_text


class ValidReportDraftLLMClient:
    provider = "fake"
    model_name = "fake-model"

    def summarize_risks(self, risk_factors: list[dict[str, Any]]) -> dict[str, Any]:
        self.last_call_metadata = {
            "input_tokens": 120,
            "output_tokens": 42,
            "total_tokens": 162,
            "provider_request_id": "risk-eval-req",
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

    def draft_report(self, evidence: dict[str, Any]) -> dict[str, Any]:
        self.last_call_metadata = {
            "input_tokens": 300,
            "output_tokens": 150,
            "total_tokens": 450,
            "provider_request_id": "draft-eval-req",
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


class CitationlessReportDraftLLMClient(ValidReportDraftLLMClient):
    def draft_report(self, evidence: dict[str, Any]) -> dict[str, Any]:
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


class UnknownCitationReportDraftLLMClient(ValidReportDraftLLMClient):
    def draft_report(self, evidence: dict[str, Any]) -> dict[str, Any]:
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


class UnsafeReportDraftLLMClient(ValidReportDraftLLMClient):
    def draft_report(self, evidence: dict[str, Any]) -> dict[str, Any]:
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


LLM_FIXTURES = {
    "none": None,
    "valid_report_draft": ValidReportDraftLLMClient,
    "citationless_report_draft": CitationlessReportDraftLLMClient,
    "unknown_citation_report_draft": UnknownCitationReportDraftLLMClient,
    "unsafe_report_draft": UnsafeReportDraftLLMClient,
}

DETERMINISTIC_GRAPH_EVAL_CASES = [
    EvalCase(
        id="normal_aapl_sec_fixture",
        query="AAPL",
        description="Normal fixture-backed SEC run with valid fake LLM output.",
        sec_fixture="sample_10k_excerpt",
        llm_fixture="valid_report_draft",
        expected=EvalExpectations(
            required_citations=EXPECTED_RESEARCH_CITATIONS,
            forbidden_phrases=["you should buy"],
            forbidden_warning_codes=["report_quality_warning"],
        ),
    ),
    EvalCase(
        id="heading_variant_filing",
        query="AAPL",
        description="Latest 10-K uses heading punctuation variants.",
        sec_fixture="heading_variant_10k",
        llm_fixture="none",
        expected=EvalExpectations(
            required_citations=EXPECTED_RESEARCH_CITATIONS,
            forbidden_warning_codes=["report_quality_warning"],
        ),
    ),
    EvalCase(
        id="missing_business_section",
        query="AAPL",
        description="Item 1 Business section cannot be extracted.",
        sec_fixture="business_section_missing",
        llm_fixture="none",
        expected=EvalExpectations(
            required_citations=EXPECTED_RESEARCH_CITATIONS,
            required_warning_codes=["business_section_unavailable"],
            forbidden_warning_codes=["report_quality_warning"],
        ),
    ),
    EvalCase(
        id="missing_risk_section",
        query="AAPL",
        description="Item 1A Risk Factors section cannot be extracted.",
        sec_fixture="risk_section_missing",
        llm_fixture="none",
        expected=EvalExpectations(
            report_quality_status="warning",
            citation_audit_status="warning",
            required_citations=EXPECTED_RESEARCH_CITATIONS,
            required_warning_codes=[
                "risk_factors_unavailable",
                "risk_analysis_unavailable",
                "report_quality_warning",
            ],
            allowed_missing_citation_sections=[
                "## 6. Risk Factors",
                "## 8. Bear Case",
            ],
        ),
    ),
    EvalCase(
        id="citationless_llm_report_draft",
        query="AAPL",
        description="LLM draft omits required source citations and must fall back.",
        sec_fixture="sample_10k_excerpt",
        llm_fixture="citationless_report_draft",
        expected=EvalExpectations(
            required_citations=EXPECTED_RESEARCH_CITATIONS,
            required_warning_codes=["llm_report_drafting_unavailable"],
            forbidden_warning_codes=["report_quality_warning"],
        ),
    ),
    EvalCase(
        id="unknown_citation_llm_report_draft",
        query="AAPL",
        description="LLM draft cites an unknown source and must fall back.",
        sec_fixture="sample_10k_excerpt",
        llm_fixture="unknown_citation_report_draft",
        expected=EvalExpectations(
            required_citations=EXPECTED_RESEARCH_CITATIONS,
            required_warning_codes=["llm_report_drafting_unavailable"],
            forbidden_warning_codes=["report_quality_warning"],
        ),
    ),
    EvalCase(
        id="unsafe_llm_report_draft",
        query="AAPL",
        description="LLM draft uses advice language and must be rewritten safely.",
        sec_fixture="sample_10k_excerpt",
        llm_fixture="unsafe_report_draft",
        expected=EvalExpectations(
            compliance_status="needs_rewrite",
            required_citations=EXPECTED_RESEARCH_CITATIONS,
            forbidden_phrases=["you should buy", "guaranteed", "price will crash"],
            required_warning_codes=["compliance_warning"],
            forbidden_warning_codes=["report_quality_warning"],
        ),
    ),
]


def run_deterministic_graph_eval_suite(
    cases: Sequence[EvalCase] | None = None,
) -> EvalSuiteResult:
    eval_cases = cases or DETERMINISTIC_GRAPH_EVAL_CASES
    return EvalSuiteResult(
        suite=DETERMINISTIC_GRAPH_EVAL_SUITE,
        cases=[run_deterministic_graph_eval_case(eval_case) for eval_case in eval_cases],
    )


def run_deterministic_graph_eval_case(eval_case: EvalCase) -> EvalCaseResult:
    try:
        graph_result = _run_graph(eval_case)
    except GraphEvalConfigurationError as exc:
        return _failed_execution_result(eval_case.id, str(exc))
    except Exception as exc:
        return _failed_execution_result(
            eval_case.id,
            f"{type(exc).__name__}: {exc}",
        )

    checks = [
        _status_check(
            name="graph_execution",
            expected="completed",
            actual="completed",
        ),
        _status_check(
            name="workflow_status",
            expected=eval_case.expected.status,
            actual=_workflow_status(graph_result),
        ),
        _status_check(
            name="compliance_status",
            expected=eval_case.expected.compliance_status,
            actual=graph_result.get("compliance_status"),
        ),
        _status_check(
            name="report_quality_status",
            expected=eval_case.expected.report_quality_status,
            actual=graph_result.get("report_quality_status"),
        ),
        *evaluate_report_quality_checks(
            report=graph_result.get("final_report"),
            report_quality_details=graph_result.get("report_quality_details"),
            warnings=graph_result.get("warnings", []),
            expectations=eval_case.expected,
        ),
    ]
    return EvalCaseResult(
        case_id=eval_case.id,
        checks=checks,
        metrics={
            "final_report_present": graph_result.get("final_report") is not None,
            "warning_count": len(graph_result.get("warnings", [])),
            "source_count": len(graph_result.get("sources", [])),
        },
        warnings=_eval_result_warnings(graph_result),
    )


def _run_graph(eval_case: EvalCase) -> dict[str, Any]:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )
    graph = build_research_graph(
        resolver=resolver,
        sec_client=_sec_client(eval_case.sec_fixture),
        llm_client=_llm_client(eval_case.llm_fixture),
    )
    return graph.invoke({"user_query": eval_case.query})


def _sec_client(sec_fixture: str) -> FixtureSECClient:
    document_text = SEC_DOCUMENT_FIXTURES.get(sec_fixture)
    if document_text is None:
        raise GraphEvalConfigurationError(f"Unknown SEC eval fixture: {sec_fixture}.")
    return FixtureSECClient(document_text)


def _llm_client(llm_fixture: str) -> Any | None:
    llm_client_factory = LLM_FIXTURES.get(llm_fixture)
    if llm_client_factory is None:
        if llm_fixture == "none":
            return None
        raise GraphEvalConfigurationError(f"Unknown LLM eval fixture: {llm_fixture}.")
    return llm_client_factory()


def _failed_execution_result(case_id: str, message: str) -> EvalCaseResult:
    return EvalCaseResult(
        case_id=case_id,
        checks=[
            EvalCheckResult(
                name="graph_execution",
                status=EvalStatus.FAILED,
                expected="completed",
                actual="failed",
                message=message,
            )
        ],
    )


def _status_check(
    *,
    name: str,
    expected: str | None,
    actual: Any,
) -> EvalCheckResult:
    normalized_actual = str(actual).strip() if actual is not None else None
    passed = expected == normalized_actual
    return EvalCheckResult(
        name=name,
        status=EvalStatus.PASSED if passed else EvalStatus.FAILED,
        expected=expected,
        actual=normalized_actual,
        message=(
            f"Expected {name} to be {expected}, got {normalized_actual}."
            if not passed
            else None
        ),
    )


def _workflow_status(graph_result: dict[str, Any]) -> str:
    if graph_result.get("errors"):
        return "failed"
    return "completed"


def _eval_result_warnings(graph_result: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for warning in graph_result.get("warnings", []):
        if not isinstance(warning, dict):
            continue
        code = str(warning.get("code") or "").strip()
        if code:
            warnings.append(code)
    return warnings
