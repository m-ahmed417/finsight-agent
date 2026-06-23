from finsight_agent.app.services.report_generator import RESEARCH_ONLY_NOTICE
from finsight_agent.app.services.report_validator import REQUIRED_SECTIONS
from finsight_agent.evals.evaluators import (
    evaluate_citation_audit,
    evaluate_forbidden_language,
    evaluate_report_quality_checks,
    evaluate_report_sections,
    evaluate_research_only_disclaimer,
    evaluate_scaffold_language,
    evaluate_warning_codes,
)
from finsight_agent.evals.models import EvalExpectations, EvalStatus


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
            "[sec_company_facts]"
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

PASSING_REPORT_QUALITY_DETAILS = {
    "citation_audit": {
        "status": "passed",
        "known_source_ids": ["sec_company_facts", "latest_10k"],
        "unknown_citations": [],
        "sections_missing_required_citations": [],
    }
}


def test_evaluate_report_sections_passes_when_all_required_sections_exist() -> None:
    check = evaluate_report_sections(VALID_REPORT)

    assert check.name == "required_report_sections"
    assert check.status == EvalStatus.PASSED
    assert check.expected == list(REQUIRED_SECTIONS)
    assert check.actual == []
    assert check.message is None


def test_evaluate_report_sections_fails_with_missing_section_names() -> None:
    report = VALID_REPORT.replace(
        (
            "## 8. Bear Case\n\n"
            "- **Competition**: Competition could pressure performance. [latest_10k]\n\n"
        ),
        "",
    )

    check = evaluate_report_sections(report)

    assert check.status == EvalStatus.FAILED
    assert check.actual == ["## 8. Bear Case"]
    assert check.message == "Report is missing required sections."


def test_evaluate_research_only_disclaimer_fails_when_missing() -> None:
    check = evaluate_research_only_disclaimer(
        VALID_REPORT.replace(RESEARCH_ONLY_NOTICE, "")
    )

    assert check.name == "research_only_disclaimer"
    assert check.status == EvalStatus.FAILED
    assert check.expected is True
    assert check.actual is False


def test_evaluate_forbidden_language_finds_builtin_and_case_specific_terms() -> None:
    report = f"{VALID_REPORT}\n\nThis is guaranteed, and you should buy it."

    check = evaluate_forbidden_language(report, forbidden_phrases=["you should buy"])

    assert check.name == "forbidden_language"
    assert check.status == EvalStatus.FAILED
    assert check.expected == []
    assert check.actual == ["buy", "guaranteed", "you should buy"]
    assert check.message == "Report contains forbidden language."


def test_evaluate_scaffold_language_finds_placeholder_language() -> None:
    report = VALID_REPORT.replace(
        "- **Revenue growth**: Growth could support performance. [sec_company_facts]",
        (
            "Future versions will summarize this section from grounded evidence. "
            "[sec_company_facts]"
        ),
    )

    check = evaluate_scaffold_language(report)

    assert check.name == "scaffold_language"
    assert check.status == EvalStatus.FAILED
    assert check.expected == []
    assert check.actual == ["future versions will"]


def test_evaluate_citation_audit_passes_required_citation_checks() -> None:
    checks = _checks_by_name(
        evaluate_citation_audit(
            PASSING_REPORT_QUALITY_DETAILS,
            required_citations=["sec_company_facts", "latest_10k"],
        )
    )

    assert checks["citation_audit_status"].status == EvalStatus.PASSED
    assert checks["required_citations"].status == EvalStatus.PASSED
    assert checks["required_citations"].actual == [
        "sec_company_facts",
        "latest_10k",
    ]
    assert checks["unknown_citations"].status == EvalStatus.PASSED
    assert checks["sections_missing_required_citations"].status == EvalStatus.PASSED


def test_evaluate_citation_audit_fails_unknown_and_missing_citation_details() -> None:
    details = {
        "citation_audit": {
            "status": "warning",
            "known_source_ids": ["sec_company_facts"],
            "unknown_citations": ["invented_source"],
            "sections_missing_required_citations": ["## 7. Bull Case"],
        }
    }

    checks = _checks_by_name(
        evaluate_citation_audit(
            details,
            required_citations=["sec_company_facts", "latest_10k"],
        )
    )

    assert checks["citation_audit_status"].status == EvalStatus.FAILED
    assert checks["required_citations"].status == EvalStatus.FAILED
    assert checks["required_citations"].actual == ["sec_company_facts"]
    assert checks["required_citations"].message == (
        "Citation audit is missing required known source IDs: latest_10k."
    )
    assert checks["unknown_citations"].status == EvalStatus.FAILED
    assert checks["unknown_citations"].actual == ["invented_source"]
    assert checks["sections_missing_required_citations"].status == EvalStatus.FAILED
    assert checks["sections_missing_required_citations"].actual == [
        "## 7. Bull Case"
    ]


def test_evaluate_citation_audit_allows_expected_degraded_missing_citations() -> None:
    details = {
        "citation_audit": {
            "status": "warning",
            "known_source_ids": ["sec_company_facts", "latest_10k"],
            "unknown_citations": [],
            "sections_missing_required_citations": [
                "## 6. Risk Factors",
                "## 8. Bear Case",
            ],
        }
    }

    checks = _checks_by_name(
        evaluate_citation_audit(
            details,
            expected_status="warning",
            required_citations=["sec_company_facts", "latest_10k"],
            allowed_missing_required_citation_sections=[
                "## 6. Risk Factors",
                "## 8. Bear Case",
            ],
        )
    )

    assert checks["citation_audit_status"].status == EvalStatus.PASSED
    assert checks["required_citations"].status == EvalStatus.PASSED
    assert checks["unknown_citations"].status == EvalStatus.PASSED
    assert checks["sections_missing_required_citations"].status == EvalStatus.PASSED


def test_evaluate_citation_audit_handles_missing_details_without_raising() -> None:
    checks = _checks_by_name(
        evaluate_citation_audit(
            None,
            required_citations=["sec_company_facts"],
        )
    )

    assert checks["citation_audit_status"].status == EvalStatus.FAILED
    assert checks["citation_audit_status"].actual is None
    assert checks["required_citations"].status == EvalStatus.FAILED
    assert checks["unknown_citations"].status == EvalStatus.PASSED


def test_evaluate_warning_codes_checks_required_and_forbidden_codes() -> None:
    checks = _checks_by_name(
        evaluate_warning_codes(
            [
                {"code": "filing_text_unavailable", "message": "No filing text."},
                "llm_report_drafting_fallback",
                {"message": "No code should be ignored."},
            ],
            required_warning_codes=[
                "filing_text_unavailable",
                "llm_report_drafting_fallback",
            ],
            forbidden_warning_codes=["report_quality_warning"],
        )
    )

    assert checks["required_warning_codes"].status == EvalStatus.PASSED
    assert checks["required_warning_codes"].actual == [
        "filing_text_unavailable",
        "llm_report_drafting_fallback",
    ]
    assert checks["forbidden_warning_codes"].status == EvalStatus.PASSED


def test_evaluate_warning_codes_fails_missing_required_and_present_forbidden() -> None:
    checks = _checks_by_name(
        evaluate_warning_codes(
            [{"code": "report_quality_warning", "message": "Quality warning."}],
            required_warning_codes=["filing_text_unavailable"],
            forbidden_warning_codes=["report_quality_warning"],
        )
    )

    assert checks["required_warning_codes"].status == EvalStatus.FAILED
    assert checks["required_warning_codes"].message == (
        "Missing required warning codes: filing_text_unavailable."
    )
    assert checks["forbidden_warning_codes"].status == EvalStatus.FAILED
    assert checks["forbidden_warning_codes"].actual == ["report_quality_warning"]


def test_evaluate_report_quality_checks_returns_aggregate_check_list() -> None:
    checks = evaluate_report_quality_checks(
        report=VALID_REPORT,
        report_quality_details=PASSING_REPORT_QUALITY_DETAILS,
        warnings=[],
        expectations=EvalExpectations(
            required_citations=["sec_company_facts", "latest_10k"],
            forbidden_phrases=["you should buy"],
            forbidden_warning_codes=["report_quality_warning"],
        ),
    )

    assert [check.name for check in checks] == [
        "required_report_sections",
        "research_only_disclaimer",
        "forbidden_language",
        "scaffold_language",
        "citation_audit_status",
        "required_citations",
        "unknown_citations",
        "sections_missing_required_citations",
        "required_warning_codes",
        "forbidden_warning_codes",
    ]
    assert all(check.status == EvalStatus.PASSED for check in checks)


def _checks_by_name(checks):
    return {check.name: check for check in checks}
