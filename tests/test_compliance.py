from finsight_agent.app.services.compliance import (
    ComplianceStatus,
    check_report_compliance,
    find_forbidden_terms,
    rewrite_unsafe_report,
)
from finsight_agent.app.services.report_generator import RESEARCH_ONLY_NOTICE


def test_safe_report_passes_compliance() -> None:
    report = (
        f"## 1. Research-Only Notice\n\n{RESEARCH_ONLY_NOTICE}\n\n"
        "The bull case depends on revenue growth and margin expansion."
    )

    result = check_report_compliance(report)

    assert result.status == ComplianceStatus.ALLOWED
    assert result.flagged_terms == []
    assert result.safe_report == report


def test_missing_disclaimer_is_added_to_safe_report() -> None:
    result = check_report_compliance("The bear case includes margin pressure.")

    assert result.status == ComplianceStatus.ALLOWED
    assert RESEARCH_ONLY_NOTICE in result.safe_report
    assert result.warnings == ["Required research-only disclaimer was added."]


def test_unsafe_buy_recommendation_is_blocked() -> None:
    result = check_report_compliance("You should buy this stock.")

    assert result.status == ComplianceStatus.BLOCKED
    assert "buy" in result.flagged_terms
    assert result.safe_report is None


def test_unsafe_guaranteed_language_is_blocked() -> None:
    result = check_report_compliance("This company is guaranteed to go up.")

    assert result.status == ComplianceStatus.BLOCKED
    assert "guaranteed" in result.flagged_terms
    assert result.safe_report is None


def test_safe_research_language_is_allowed() -> None:
    result = check_report_compliance(
        "The bull case depends on revenue growth, while the bear case includes execution risk."
    )

    assert result.status == ComplianceStatus.ALLOWED
    assert result.flagged_terms == []


def test_public_forbidden_term_scan_ignores_required_disclaimer() -> None:
    assert find_forbidden_terms(RESEARCH_ONLY_NOTICE) == []
    assert find_forbidden_terms(f"{RESEARCH_ONLY_NOTICE}\n\nYou should buy this stock.") == [
        "buy"
    ]


def test_unsafe_report_can_be_rewritten_into_neutral_research_language() -> None:
    result = rewrite_unsafe_report("You should buy this stock because it is guaranteed.")

    assert result.status == ComplianceStatus.NEEDS_REWRITE
    assert result.safe_report is not None
    report_body = result.safe_report.replace(RESEARCH_ONLY_NOTICE, "")
    assert "buy" not in report_body.casefold()
    assert "guaranteed" not in report_body.casefold()
    assert RESEARCH_ONLY_NOTICE in result.safe_report
    assert result.flagged_terms == []
    assert (
        "Unsafe financial-advice language was rewritten into neutral research phrasing."
        in result.warnings
    )


def test_unsafe_price_prediction_language_can_be_rewritten() -> None:
    result = rewrite_unsafe_report("The price will crash after the filing.")

    assert result.status == ComplianceStatus.NEEDS_REWRITE
    assert result.safe_report is not None
    assert "price will crash" not in result.safe_report.casefold()
    assert "future price movement is uncertain" in result.safe_report.casefold()


def test_rewrite_blocks_when_unsafe_language_remains_after_rewrite() -> None:
    result = rewrite_unsafe_report("This report includes buybuy wording.")

    assert result.status == ComplianceStatus.BLOCKED
    assert result.safe_report is None
    assert "buy" in result.flagged_terms
