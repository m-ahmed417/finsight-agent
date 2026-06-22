import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

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

CITATION_REQUIRED_SECTIONS = (
    "## 4. Financial Performance",
    "## 6. Risk Factors",
    "## 7. Bull Case",
    "## 8. Bear Case",
)

CITATION_PATTERN = re.compile(r"\[([A-Za-z][A-Za-z0-9_-]*)\]")


class CitationAuditStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"


class SectionCitationAudit(BaseModel):
    heading: str
    present: bool
    requires_citation: bool
    citations: list[str] = Field(default_factory=list)
    known_citations: list[str] = Field(default_factory=list)
    unknown_citations: list[str] = Field(default_factory=list)
    missing_required_citation: bool = False


class ReportCitationAudit(BaseModel):
    status: CitationAuditStatus
    known_source_ids: list[str] = Field(default_factory=list)
    sections: list[SectionCitationAudit] = Field(default_factory=list)
    missing_required_sections: list[str] = Field(default_factory=list)
    unknown_citations: list[str] = Field(default_factory=list)
    sections_missing_required_citations: list[str] = Field(default_factory=list)


def audit_report_citations(
    report: str | None,
    *,
    sources: list[dict[str, Any]] | None = None,
) -> ReportCitationAudit:
    known_source_ids = _known_source_ids(sources or [])
    known_source_id_set = set(known_source_ids)
    report_text = report or ""

    section_audits: list[SectionCitationAudit] = []
    missing_required_sections: list[str] = []
    sections_missing_required_citations: list[str] = []
    all_unknown_citations: list[str] = []

    for heading in REQUIRED_SECTIONS:
        body = _extract_section_body(report_text, heading)
        present = body is not None
        requires_citation = heading in CITATION_REQUIRED_SECTIONS
        citations = _extract_citations(body or "")
        known_citations = [
            citation for citation in citations if citation in known_source_id_set
        ]
        unknown_citations = [
            citation for citation in citations if citation not in known_source_id_set
        ]
        missing_required_citation = (
            present and requires_citation and not citations
        )

        if not present:
            missing_required_sections.append(heading)
        if missing_required_citation:
            sections_missing_required_citations.append(heading)
        for citation in unknown_citations:
            if citation not in all_unknown_citations:
                all_unknown_citations.append(citation)

        section_audits.append(
            SectionCitationAudit(
                heading=heading,
                present=present,
                requires_citation=requires_citation,
                citations=citations,
                known_citations=known_citations,
                unknown_citations=unknown_citations,
                missing_required_citation=missing_required_citation,
            )
        )

    status = (
        CitationAuditStatus.WARNING
        if (
            missing_required_sections
            or sections_missing_required_citations
            or all_unknown_citations
        )
        else CitationAuditStatus.PASSED
    )
    return ReportCitationAudit(
        status=status,
        known_source_ids=known_source_ids,
        sections=section_audits,
        missing_required_sections=missing_required_sections,
        unknown_citations=all_unknown_citations,
        sections_missing_required_citations=sections_missing_required_citations,
    )


def _known_source_ids(sources: list[dict[str, Any]]) -> list[str]:
    known_source_ids: list[str] = []
    for source in sources:
        source_id = source.get("source_id")
        if source_id is None:
            continue
        normalized = str(source_id).strip()
        if normalized and normalized not in known_source_ids:
            known_source_ids.append(normalized)
    return known_source_ids


def _extract_section_body(report: str, heading: str) -> str | None:
    start = report.find(heading)
    if start == -1:
        return None

    body_start = start + len(heading)
    if report[body_start : body_start + 2] == "\n\n":
        body_start += 2
    elif report[body_start : body_start + 1] == "\n":
        body_start += 1

    next_heading = report.find("\n## ", body_start)
    body_end = len(report) if next_heading == -1 else next_heading
    return report[body_start:body_end]


def _extract_citations(text: str) -> list[str]:
    citations: list[str] = []
    for match in CITATION_PATTERN.finditer(text):
        source_id = match.group(1)
        if source_id not in citations:
            citations.append(source_id)
    return citations
