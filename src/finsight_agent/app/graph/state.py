from typing import Any, TypedDict


class FinSightState(TypedDict, total=False):
    user_query: str

    ticker: str | None
    company_name: str | None
    cik: str | None
    resolution_status: str | None
    resolution_confidence: float | None
    candidate_matches: list[dict[str, Any]]

    sec_submissions: dict[str, Any] | None
    company_facts: dict[str, Any] | None
    latest_10k: dict[str, Any] | None
    latest_10q: dict[str, Any] | None
    filing_text: str | None
    business_sections: list[dict[str, Any]]
    business_overview: dict[str, Any] | None
    risk_factors: list[dict[str, Any]]
    risk_themes: list[dict[str, Any]]
    financial_metrics: dict[str, Any] | None
    research_insights: dict[str, Any] | None
    llm_report_sections: dict[str, Any] | None
    report_draft: str | None
    final_report: str | None
    compliance_status: str | None
    report_quality_status: str | None

    agent_steps: list[dict[str, Any]]
    llm_call_events: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    errors: list[dict[str, Any]]
