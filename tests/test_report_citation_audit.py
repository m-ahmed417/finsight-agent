from finsight_agent.app.services.report_citation_audit import (
    CitationAuditStatus,
    audit_report_citations,
)
from finsight_agent.app.services.report_generator import RESEARCH_ONLY_NOTICE


VALID_SOURCES = [
    {"source_id": "sec_company_facts", "label": "SEC company facts"},
    {"source_id": "latest_10k", "label": "Latest 10-K filing"},
]


VALID_REPORT = "\n\n".join(
    [
        "# FinSight Research Brief: Apple Inc. (AAPL)",
        f"## 1. Research-Only Notice\n\n{RESEARCH_ONLY_NOTICE}",
        "## 2. Executive Summary\n\n- Apple was reviewed using SEC evidence.",
        "## 3. Company Overview\n\nApple is described from filing evidence. [latest_10k]",
        (
            "## 4. Financial Performance\n\n"
            "Revenue and margin data were reviewed. [sec_company_facts]"
        ),
        (
            "## 5. Key Financial Metrics\n\n"
            "| Fiscal Year | Revenue |\n| --- | ---: |\n| 2024 | $1.25B |"
        ),
        (
            "## 6. Risk Factors\n\n"
            "- **Competition**: Competition could pressure results. [latest_10k]"
        ),
        (
            "## 7. Bull Case\n\n"
            "- **Revenue growth**: Growth could support performance. "
            "[sec_company_facts] [sec_company_facts]"
        ),
        (
            "## 8. Bear Case\n\n"
            "- **Competition**: Competition could pressure performance. [latest_10k]"
        ),
        "## 9. Open Questions for Further Research\n\n- What changed in the latest filing?",
        (
            "## 10. Sources Used\n\n"
            "- [sec_company_facts] SEC company facts: https://data.sec.gov/example.json\n"
            "- [latest_10k] Latest 10-K: https://www.sec.gov/Archives/example.htm"
        ),
        (
            "## 11. Limitations\n\n"
            "- This report is limited to SEC-derived evidence."
        ),
    ]
)


def test_audit_report_citations_extracts_section_citations_in_report_order() -> None:
    audit = audit_report_citations(VALID_REPORT, sources=VALID_SOURCES)

    assert audit.status == CitationAuditStatus.PASSED
    assert audit.known_source_ids == ["sec_company_facts", "latest_10k"]
    assert audit.missing_required_sections == []
    assert audit.unknown_citations == []
    assert audit.sections_missing_required_citations == []
    assert [section.heading for section in audit.sections] == [
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
    ]

    overview = _section(audit, "## 3. Company Overview")
    assert overview.present is True
    assert overview.requires_citation is False
    assert overview.citations == ["latest_10k"]
    assert overview.known_citations == ["latest_10k"]
    assert overview.unknown_citations == []
    assert overview.missing_required_citation is False

    financial_performance = _section(audit, "## 4. Financial Performance")
    assert financial_performance.requires_citation is True
    assert financial_performance.citations == ["sec_company_facts"]
    assert financial_performance.known_citations == ["sec_company_facts"]
    assert financial_performance.missing_required_citation is False

    bull_case = _section(audit, "## 7. Bull Case")
    assert bull_case.citations == ["sec_company_facts"]

    sources_used = _section(audit, "## 10. Sources Used")
    assert sources_used.requires_citation is False
    assert sources_used.citations == ["sec_company_facts", "latest_10k"]


def test_audit_report_citations_records_unknown_citations_by_section() -> None:
    report = VALID_REPORT.replace("[latest_10k]", "[unknown_source]", 1)

    audit = audit_report_citations(report, sources=VALID_SOURCES)

    assert audit.status == CitationAuditStatus.WARNING
    assert audit.unknown_citations == ["unknown_source"]
    overview = _section(audit, "## 3. Company Overview")
    assert overview.citations == ["unknown_source"]
    assert overview.known_citations == []
    assert overview.unknown_citations == ["unknown_source"]


def test_audit_report_citations_records_missing_required_citations() -> None:
    report = VALID_REPORT.replace(
        "- **Revenue growth**: Growth could support performance. "
        "[sec_company_facts] [sec_company_facts]",
        "- **Revenue growth**: Growth could support performance.",
    )

    audit = audit_report_citations(report, sources=VALID_SOURCES)

    assert audit.status == CitationAuditStatus.WARNING
    assert audit.sections_missing_required_citations == ["## 7. Bull Case"]
    bull_case = _section(audit, "## 7. Bull Case")
    assert bull_case.present is True
    assert bull_case.requires_citation is True
    assert bull_case.citations == []
    assert bull_case.known_citations == []
    assert bull_case.unknown_citations == []
    assert bull_case.missing_required_citation is True


def test_audit_report_citations_records_missing_sections_separately() -> None:
    report = VALID_REPORT.replace(
        (
            "## 8. Bear Case\n\n"
            "- **Competition**: Competition could pressure performance. [latest_10k]\n\n"
        ),
        "",
    )

    audit = audit_report_citations(report, sources=VALID_SOURCES)

    assert audit.status == CitationAuditStatus.WARNING
    assert audit.missing_required_sections == ["## 8. Bear Case"]
    assert audit.sections_missing_required_citations == []
    bear_case = _section(audit, "## 8. Bear Case")
    assert bear_case.present is False
    assert bear_case.requires_citation is True
    assert bear_case.citations == []
    assert bear_case.missing_required_citation is False


def test_audit_report_citations_handles_missing_report_without_crashing() -> None:
    audit = audit_report_citations(None, sources=VALID_SOURCES)

    assert audit.status == CitationAuditStatus.WARNING
    assert audit.known_source_ids == ["sec_company_facts", "latest_10k"]
    assert audit.missing_required_sections == [
        section.heading for section in audit.sections
    ]
    assert audit.unknown_citations == []
    assert audit.sections_missing_required_citations == []
    assert all(section.present is False for section in audit.sections)


def test_audit_report_citations_ignores_non_source_bracketed_text() -> None:
    report = VALID_REPORT.replace(
        "Revenue and margin data were reviewed. [sec_company_facts]",
        "Revenue and margin data were reviewed. [sec_company_facts] [not a source] [1]",
    )

    audit = audit_report_citations(report, sources=VALID_SOURCES)

    financial_performance = _section(audit, "## 4. Financial Performance")
    assert financial_performance.citations == ["sec_company_facts"]
    assert audit.unknown_citations == []


def _section(audit, heading: str):
    return next(section for section in audit.sections if section.heading == heading)
