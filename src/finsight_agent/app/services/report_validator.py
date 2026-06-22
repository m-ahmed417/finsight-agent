import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from finsight_agent.app.services.compliance import find_forbidden_terms
from finsight_agent.app.services.report_citation_audit import audit_report_citations
from finsight_agent.app.services.report_generator import RESEARCH_ONLY_NOTICE

REQUIRED_SECTIONS = (
    "## 1. Research-Only Notice",
    "## 2. Executive Summary",
    "## 3. Company Overview",
    "## 4. Financial Performance",
    "## 5. Key Financial Metrics",
    "## 6. Risk Factors",
    "## 7. Bull Case",
    "## 8. Bear Case",
    "## 9. Open Questions for Further Research",
    "## 10. Sources Used",
    "## 11. Limitations",
)

CONTENT_SECTIONS = (
    "## 3. Company Overview",
    "## 6. Risk Factors",
    "## 7. Bull Case",
    "## 8. Bear Case",
    "## 10. Sources Used",
    "## 11. Limitations",
)

CITATION_REQUIRED_SECTIONS = (
    "## 4. Financial Performance",
    "## 6. Risk Factors",
    "## 7. Bull Case",
    "## 8. Bear Case",
)

WEAK_SECTION_MARKERS = (
    "mvp draft",
    "future versions will",
    "future llm-assisted step",
    "has not been performed yet",
    "not been generated yet",
    "not generated yet",
    "pending deterministic synthesis",
    "risk factor analysis has not been performed yet",
    "no sources were recorded",
    "will later be grounded",
)

CITATION_PATTERN = re.compile(r"\[([A-Za-z][A-Za-z0-9_-]*)\]")


class ReportQualityStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"


class ReportQualityResult(BaseModel):
    status: ReportQualityStatus
    warnings: list[dict[str, str]] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


def validate_report_quality(
    report: str | None,
    *,
    sources: list[dict[str, Any]] | None = None,
) -> ReportQualityResult:
    citation_audit = audit_report_citations(report, sources=sources)
    details = {
        "citation_audit": citation_audit.model_dump(mode="json"),
    }
    warnings: list[dict[str, str]] = []
    if not report:
        return ReportQualityResult(
            status=ReportQualityStatus.WARNING,
            warnings=[
                _warning(
                    "missing_report",
                    "No final report was available for quality validation.",
                )
            ],
            details=details,
        )

    warnings.extend(_section_warnings(report))
    if RESEARCH_ONLY_NOTICE not in report:
        warnings.append(
            _warning(
                "missing_report_disclaimer",
                "Report is missing the required research-only disclaimer.",
            )
        )

    if not _has_sec_source_signal(report):
        warnings.append(
            _warning(
                "missing_sec_source",
                "Report does not include an SEC source URL or SEC filing citation.",
            )
        )

    warnings.extend(_weak_section_warnings(report))
    warnings.extend(_missing_citation_warnings(report))
    warnings.extend(_unknown_citation_warnings(report, sources))
    unsafe_terms = find_forbidden_terms(report)
    if unsafe_terms:
        warnings.append(
            _warning(
                "unsafe_language_detected",
                "Report quality validation found unsafe financial-advice language.",
            )
        )

    status = ReportQualityStatus.WARNING if warnings else ReportQualityStatus.PASSED
    return ReportQualityResult(status=status, warnings=warnings, details=details)


def _section_warnings(report: str) -> list[dict[str, str]]:
    return [
        _warning(
            "missing_report_section",
            f"Report is missing required section: {section}.",
        )
        for section in REQUIRED_SECTIONS
        if section not in report
    ]


def _weak_section_warnings(report: str) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for section in CONTENT_SECTIONS:
        section_text = _extract_section(report, section)
        if not section_text:
            continue
        normalized_section = section_text.casefold()
        if any(marker in normalized_section for marker in WEAK_SECTION_MARKERS):
            warnings.append(
                _warning(
                    "weak_report_section",
                    f"Report section needs stronger source-grounded content: {section}.",
                )
            )
    return warnings


def _missing_citation_warnings(report: str) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for section in CITATION_REQUIRED_SECTIONS:
        section_text = _extract_section(report, section)
        if not section_text:
            continue
        if not _extract_citations(section_text):
            warnings.append(
                _warning(
                    "missing_section_citation",
                    f"Report section is missing source_id citations: {section}.",
                )
            )
    return warnings


def _unknown_citation_warnings(
    report: str,
    sources: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    if sources is None:
        return []

    known_source_ids = _source_ids_from_sources(sources)
    unknown_source_ids = [
        source_id
        for source_id in _extract_citations(report)
        if source_id not in known_source_ids
    ]

    return [
        _warning(
            "unknown_report_citation",
            f"Report cites unknown source_id: {source_id}.",
        )
        for source_id in sorted(set(unknown_source_ids))
    ]


def _extract_citations(text: str) -> list[str]:
    citations: list[str] = []
    seen: set[str] = set()
    for match in CITATION_PATTERN.finditer(text):
        source_id = match.group(1)
        if source_id not in seen:
            citations.append(source_id)
            seen.add(source_id)
    return citations


def _source_ids_from_sources(sources: list[dict[str, Any]]) -> set[str]:
    source_ids: set[str] = set()
    for source in sources:
        source_id = source.get("source_id")
        if source_id is None:
            continue
        normalized = str(source_id).strip()
        if normalized:
            source_ids.add(normalized)
    return source_ids


def _extract_section(report: str, heading: str) -> str:
    start = report.find(heading)
    if start == -1:
        return ""
    next_heading = report.find("\n## ", start + len(heading))
    if next_heading == -1:
        return report[start:]
    return report[start:next_heading]


def _has_sec_source_signal(report: str) -> bool:
    normalized_report = report.casefold()
    return (
        "https://data.sec.gov/" in normalized_report
        or "https://www.sec.gov/archives/" in normalized_report
        or "latest 10-k:" in normalized_report
        or "latest 10-q:" in normalized_report
        or "sec company facts" in normalized_report
    )


def _warning(code: str, message: str) -> dict[str, str]:
    return {
        "code": code,
        "message": message,
        "severity": "warning",
    }
