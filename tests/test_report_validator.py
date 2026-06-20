import pytest

from finsight_agent.app.services.report_generator import RESEARCH_ONLY_NOTICE
from finsight_agent.app.services.report_validator import (
    ReportQualityStatus,
    validate_report_quality,
)


VALID_REPORT = "\n\n".join(
    [
        "# FinSight Research Brief: Apple Inc. (AAPL)",
        f"## 1. Research-Only Notice\n\n{RESEARCH_ONLY_NOTICE}",
        "## 2. Executive Summary\n\n- Apple was reviewed using SEC evidence.",
        "## 3. Company Overview\n\nApple Inc. is described for research context.",
        "## 4. Financial Performance\n\nRevenue and margin data were reviewed. [sec_company_facts]",
        "## 5. Key Financial Metrics\n\n| Fiscal Year | Revenue |\n| --- | ---: |\n| 2024 | 100 |",
        "## 6. Risk Factors\n\n- **Competition**: Competition could pressure results. [latest_10k]",
        "## 7. Bull Case\n\n- **Revenue growth**: Growth could support performance. [sec_company_facts]",
        "## 8. Bear Case\n\n- **Competition**: Competition could pressure performance. [latest_10k]",
        "## 9. Open Questions for Further Research\n\n- What changed in the latest filing?",
        "## 10. Sources Used\n\n- [sec_company_facts] SEC company facts: https://data.sec.gov/example.json\n- [latest_10k] Latest 10-K: https://www.sec.gov/Archives/example.htm",
        (
            "## 11. Limitations\n\n"
            "- This report is limited to the SEC-derived evidence available in this run."
        ),
    ]
)

VALID_SOURCES = [
    {"source_id": "sec_company_facts", "label": "SEC company facts"},
    {"source_id": "latest_10k", "label": "Latest 10-K filing"},
]


def test_valid_report_quality_passes_without_warnings() -> None:
    result = validate_report_quality(VALID_REPORT, sources=VALID_SOURCES)

    assert result.status == ReportQualityStatus.PASSED
    assert result.warnings == []


def test_missing_required_section_returns_warning() -> None:
    report = VALID_REPORT.replace(
        "## 8. Bear Case\n\n- **Competition**: Competition could pressure performance. [latest_10k]\n\n",
        "",
    )

    result = validate_report_quality(report)

    assert result.status == ReportQualityStatus.WARNING
    assert {
        "code": "missing_report_section",
        "message": "Report is missing required section: ## 8. Bear Case.",
        "severity": "warning",
    } in result.warnings


def test_missing_disclaimer_returns_warning() -> None:
    result = validate_report_quality(VALID_REPORT.replace(RESEARCH_ONLY_NOTICE, ""))

    assert result.status == ReportQualityStatus.WARNING
    assert {
        "code": "missing_report_disclaimer",
        "message": "Report is missing the required research-only disclaimer.",
        "severity": "warning",
    } in result.warnings


def test_missing_sec_source_returns_warning() -> None:
    report = VALID_REPORT.replace(
        "- [sec_company_facts] SEC company facts: https://data.sec.gov/example.json\n- [latest_10k] Latest 10-K: https://www.sec.gov/Archives/example.htm",
        "- Internal note only",
    )

    result = validate_report_quality(report)

    assert result.status == ReportQualityStatus.WARNING
    assert {
        "code": "missing_sec_source",
        "message": "Report does not include an SEC source URL or SEC filing citation.",
        "severity": "warning",
    } in result.warnings


def test_unknown_report_citation_returns_warning() -> None:
    report = VALID_REPORT.replace("[latest_10k]", "[unknown_source]", 1)

    result = validate_report_quality(report, sources=VALID_SOURCES)

    assert result.status == ReportQualityStatus.WARNING
    assert {
        "code": "unknown_report_citation",
        "message": "Report cites unknown source_id: unknown_source.",
        "severity": "warning",
    } in result.warnings


def test_key_section_without_citation_returns_warning() -> None:
    report = VALID_REPORT.replace(
        "- **Revenue growth**: Growth could support performance. [sec_company_facts]",
        "- **Revenue growth**: Growth could support performance.",
    )

    result = validate_report_quality(report, sources=VALID_SOURCES)

    assert result.status == ReportQualityStatus.WARNING
    assert {
        "code": "missing_section_citation",
        "message": "Report section is missing source_id citations: ## 7. Bull Case.",
        "severity": "warning",
    } in result.warnings


def test_empty_quality_sections_return_warnings() -> None:
    report = VALID_REPORT.replace(
        "## 7. Bull Case\n\n- **Revenue growth**: Growth could support performance. [sec_company_facts]",
        "## 7. Bull Case\n\nThis section is pending deterministic synthesis from grounded financial metrics and filing evidence.",
    )

    result = validate_report_quality(report)

    assert result.status == ReportQualityStatus.WARNING
    assert {
        "code": "weak_report_section",
        "message": "Report section needs stronger source-grounded content: ## 7. Bull Case.",
        "severity": "warning",
    } in result.warnings


@pytest.mark.parametrize(
    ("section", "replacement"),
    [
        (
            "## 3. Company Overview",
            (
                "A detailed business overview has not been generated yet. This section "
                "will later be grounded in filing text and company descriptions."
            ),
        ),
        (
            "## 6. Risk Factors",
            (
                "Risk factor analysis has not been performed yet. Future versions will "
                "summarize risks from the latest available 10-K filing. [latest_10k]"
            ),
        ),
        (
            "## 7. Bull Case",
            (
                "This section is pending deterministic synthesis from grounded "
                "financial metrics and filing evidence. [sec_company_facts]"
            ),
        ),
        (
            "## 8. Bear Case",
            (
                "A future LLM-assisted step will summarize this extracted text into "
                "source-grounded risk themes. [latest_10k]"
            ),
        ),
        (
            "## 10. Sources Used",
            "No sources were recorded.",
        ),
        (
            "## 11. Limitations",
            "This report is an MVP draft and does not yet include risk-factor analysis.",
        ),
    ],
)
def test_scaffold_language_in_protected_sections_returns_warning(
    section: str,
    replacement: str,
) -> None:
    report = _replace_section_body(VALID_REPORT, section, replacement)

    result = validate_report_quality(report, sources=VALID_SOURCES)

    assert result.status == ReportQualityStatus.WARNING
    assert _weak_section_warning(section) in result.warnings


def test_professional_missing_data_limitations_do_not_trigger_weak_warning() -> None:
    report = _replace_section_body(
        VALID_REPORT,
        "## 11. Limitations",
        (
            "- Risk-factor text was not available in this run, so this report does "
            "not summarize filing risk themes.\n"
            "- Financial metrics were unavailable from SEC company facts for this run."
        ),
    )

    result = validate_report_quality(report, sources=VALID_SOURCES)

    assert result.status == ReportQualityStatus.PASSED
    assert not any(
        warning["code"] == "weak_report_section" for warning in result.warnings
    )


def _replace_section_body(report: str, section: str, replacement: str) -> str:
    start = report.find(section)
    assert start != -1
    body_start = start + len(section) + len("\n\n")
    next_heading = report.find("\n\n## ", body_start)
    body_end = len(report) if next_heading == -1 else next_heading
    return f"{report[:body_start]}{replacement}{report[body_end:]}"


def _weak_section_warning(section: str) -> dict[str, str]:
    return {
        "code": "weak_report_section",
        "message": f"Report section needs stronger source-grounded content: {section}.",
        "severity": "warning",
    }
