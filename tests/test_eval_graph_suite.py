from finsight_agent.evals.graph_suite import (
    DETERMINISTIC_GRAPH_EVAL_SUITE,
    run_deterministic_graph_eval_case,
    run_deterministic_graph_eval_suite,
)
from finsight_agent.evals.models import EvalCase, EvalStatus


def test_deterministic_graph_eval_suite_runs_fixture_backed_cases() -> None:
    suite = run_deterministic_graph_eval_suite()

    assert suite.suite == DETERMINISTIC_GRAPH_EVAL_SUITE
    assert suite.case_count >= 6
    assert suite.passed == suite.case_count
    assert suite.failed == 0
    assert suite.pass_rate == 1.0
    assert {
        case.case_id for case in suite.cases
    }.issuperset(
        {
            "normal_aapl_sec_fixture",
            "missing_business_section",
            "missing_risk_section",
            "citationless_llm_report_draft",
            "unknown_citation_llm_report_draft",
            "unsafe_llm_report_draft",
        }
    )

    normal_case = _case(suite, "normal_aapl_sec_fixture")
    assert normal_case.status == EvalStatus.PASSED
    assert _checks_by_name(normal_case.checks)["workflow_status"].actual == "completed"
    assert _checks_by_name(normal_case.checks)["compliance_status"].actual == "allowed"
    assert _checks_by_name(normal_case.checks)["report_quality_status"].actual == "passed"

    missing_risk_case = _case(suite, "missing_risk_section")
    missing_risk_checks = _checks_by_name(missing_risk_case.checks)
    assert missing_risk_checks["required_warning_codes"].status == EvalStatus.PASSED
    assert "risk_factors_unavailable" in missing_risk_checks[
        "required_warning_codes"
    ].actual
    assert "risk_analysis_unavailable" in missing_risk_checks[
        "required_warning_codes"
    ].actual

    unsafe_case = _case(suite, "unsafe_llm_report_draft")
    unsafe_checks = _checks_by_name(unsafe_case.checks)
    assert unsafe_checks["compliance_status"].actual == "needs_rewrite"
    assert unsafe_checks["forbidden_language"].status == EvalStatus.PASSED
    assert unsafe_checks["required_warning_codes"].actual == ["compliance_warning"]


def test_graph_eval_case_reports_failed_check_messages() -> None:
    eval_case = EvalCase.model_validate(
        {
            "id": "normal_case_with_wrong_warning_expectation",
            "query": "AAPL",
            "description": "Normal fixture with intentionally wrong warning expectation.",
            "sec_fixture": "sample_10k_excerpt",
            "llm_fixture": "valid_report_draft",
            "expected": {
                "required_citations": ["sec_company_facts", "latest_10k"],
                "required_warning_codes": ["business_section_unavailable"],
            },
        }
    )

    result = run_deterministic_graph_eval_case(eval_case)

    assert result.status == EvalStatus.FAILED
    check = _checks_by_name(result.checks)["required_warning_codes"]
    assert check.status == EvalStatus.FAILED
    assert check.message == (
        "Missing required warning codes: business_section_unavailable."
    )


def test_graph_eval_case_rejects_unknown_fixture_names() -> None:
    eval_case = EvalCase.model_validate(
        {
            "id": "unknown_fixture_case",
            "query": "AAPL",
            "description": "Case with unknown fixture names.",
            "sec_fixture": "unknown_sec_fixture",
            "llm_fixture": "valid_report_draft",
            "expected": {},
        }
    )

    result = run_deterministic_graph_eval_case(eval_case)

    assert result.status == EvalStatus.FAILED
    check = _checks_by_name(result.checks)["graph_execution"]
    assert check.status == EvalStatus.FAILED
    assert check.message == "Unknown SEC eval fixture: unknown_sec_fixture."


def _case(suite, case_id: str):
    return next(case for case in suite.cases if case.case_id == case_id)


def _checks_by_name(checks):
    return {check.name: check for check in checks}
