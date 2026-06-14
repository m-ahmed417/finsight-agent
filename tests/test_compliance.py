from finsight_agent.app.services.compliance import (
    ComplianceStatus,
    check_report_compliance,
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
