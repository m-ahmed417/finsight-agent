from enum import StrEnum

from pydantic import BaseModel, Field

from finsight_agent.app.services.report_generator import RESEARCH_ONLY_NOTICE

FORBIDDEN_TERMS = (
    "buy",
    "sell",
    "hold",
    "strong buy",
    "strong sell",
    "guaranteed",
    "risk-free",
    "you should invest",
    "put your money into",
    "allocate your portfolio",
    "price will go up",
    "price will crash",
)


class ComplianceStatus(StrEnum):
    ALLOWED = "allowed"
    NEEDS_REWRITE = "needs_rewrite"
    BLOCKED = "blocked"


class ComplianceResult(BaseModel):
    status: ComplianceStatus
    safe_report: str | None = None
    flagged_terms: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def check_report_compliance(report: str) -> ComplianceResult:
    flagged_terms = _find_forbidden_terms(report)
    if flagged_terms:
        return ComplianceResult(
            status=ComplianceStatus.BLOCKED,
            flagged_terms=flagged_terms,
            safe_report=None,
        )

    safe_report = report
    warnings: list[str] = []
    if RESEARCH_ONLY_NOTICE not in safe_report:
        safe_report = f"{RESEARCH_ONLY_NOTICE}\n\n{safe_report}"
        warnings.append("Required research-only disclaimer was added.")

    return ComplianceResult(
        status=ComplianceStatus.ALLOWED,
        safe_report=safe_report,
        flagged_terms=[],
        warnings=warnings,
    )


def _find_forbidden_terms(report: str) -> list[str]:
    normalized_report = report.replace(RESEARCH_ONLY_NOTICE, "").casefold()
    return [term for term in FORBIDDEN_TERMS if term in normalized_report]
