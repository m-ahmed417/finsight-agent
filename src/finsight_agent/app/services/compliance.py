import re
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

COMPLIANCE_REWRITE_WARNING = (
    "Unsafe financial-advice language was rewritten into neutral research phrasing."
)

REWRITE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bstrong\s+buy\b", re.IGNORECASE),
        "a positive research view",
    ),
    (
        re.compile(r"\bstrong\s+sell\b", re.IGNORECASE),
        "a negative research view",
    ),
    (
        re.compile(r"\byou\s+should\s+invest\b", re.IGNORECASE),
        "readers may review the evidence",
    ),
    (
        re.compile(r"\byou\s+should\s+buy\b", re.IGNORECASE),
        "the evidence may support a positive research view of",
    ),
    (
        re.compile(r"\byou\s+should\s+sell\b", re.IGNORECASE),
        "the evidence may support a negative research view of",
    ),
    (
        re.compile(r"\byou\s+should\s+hold\b", re.IGNORECASE),
        "the evidence may support a neutral research view of",
    ),
    (
        re.compile(r"\bput\s+your\s+money\s+into\b", re.IGNORECASE),
        "review the evidence for",
    ),
    (
        re.compile(r"\ballocate\s+your\s+portfolio\b", re.IGNORECASE),
        "review portfolio implications independently",
    ),
    (
        re.compile(r"\bprice\s+will\s+go\s+up\b", re.IGNORECASE),
        "future price movement is uncertain",
    ),
    (
        re.compile(r"\bprice\s+will\s+crash\b", re.IGNORECASE),
        "future price movement is uncertain",
    ),
    (
        re.compile(r"\bguaranteed\b", re.IGNORECASE),
        "uncertain",
    ),
    (
        re.compile(r"\brisk-free\b", re.IGNORECASE),
        "subject to risk",
    ),
    (
        re.compile(r"\bbuy\b", re.IGNORECASE),
        "positive research view",
    ),
    (
        re.compile(r"\bsell\b", re.IGNORECASE),
        "negative research view",
    ),
    (
        re.compile(r"\bhold\b", re.IGNORECASE),
        "neutral research view",
    ),
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
    flagged_terms = find_forbidden_terms(report)
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


def rewrite_unsafe_report(report: str) -> ComplianceResult:
    report_without_notice = report.replace(RESEARCH_ONLY_NOTICE, "", 1)
    rewritten_report = report_without_notice
    for pattern, replacement in REWRITE_RULES:
        rewritten_report = pattern.sub(replacement, rewritten_report)

    if RESEARCH_ONLY_NOTICE in report:
        rewritten_report = f"{RESEARCH_ONLY_NOTICE}{rewritten_report}"

    if rewritten_report == report:
        return check_report_compliance(report)

    compliance_result = check_report_compliance(rewritten_report)
    if compliance_result.safe_report is None:
        return compliance_result

    return ComplianceResult(
        status=ComplianceStatus.NEEDS_REWRITE,
        safe_report=compliance_result.safe_report,
        flagged_terms=[],
        warnings=[COMPLIANCE_REWRITE_WARNING, *compliance_result.warnings],
    )


def find_forbidden_terms(report: str) -> list[str]:
    normalized_report = report.replace(RESEARCH_ONLY_NOTICE, "").casefold()
    return [term for term in FORBIDDEN_TERMS if term in normalized_report]
