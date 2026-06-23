import pytest
from pydantic import ValidationError

from finsight_agent.evals.models import (
    EvalCase,
    EvalCaseResult,
    EvalCheckResult,
    EvalExpectations,
    EvalSuiteResult,
)


def test_eval_case_validates_and_normalizes_expected_contract() -> None:
    eval_case = EvalCase.model_validate(
        {
            "id": " normal_aapl_fixture ",
            "query": " AAPL ",
            "description": " Normal fixture-backed SEC run. ",
            "sec_fixture": " sample_sec_fixture ",
            "llm_fixture": " mock_valid_report_draft ",
            "expected": {
                "required_citations": [" sec_company_facts ", "latest_10k"],
                "forbidden_phrases": [" you should buy ", "guaranteed"],
            },
        }
    )

    assert eval_case.id == "normal_aapl_fixture"
    assert eval_case.query == "AAPL"
    assert eval_case.description == "Normal fixture-backed SEC run."
    assert eval_case.sec_fixture == "sample_sec_fixture"
    assert eval_case.llm_fixture == "mock_valid_report_draft"
    assert eval_case.expected.status == "completed"
    assert eval_case.expected.report_quality_status == "passed"
    assert eval_case.expected.compliance_status == "allowed"
    assert eval_case.expected.required_citations == [
        "sec_company_facts",
        "latest_10k",
    ]
    assert eval_case.expected.forbidden_phrases == [
        "you should buy",
        "guaranteed",
    ]
    assert eval_case.expected.required_warning_codes == []
    assert eval_case.expected.forbidden_warning_codes == []


@pytest.mark.parametrize(
    "field_name",
    ["id", "query", "description", "sec_fixture", "llm_fixture"],
)
def test_eval_case_rejects_blank_required_fields(field_name: str) -> None:
    payload = {
        "id": "normal_aapl_fixture",
        "query": "AAPL",
        "description": "Normal fixture-backed SEC run.",
        "sec_fixture": "sample_sec_fixture",
        "llm_fixture": "mock_valid_report_draft",
        "expected": {},
    }
    payload[field_name] = " "

    with pytest.raises(ValidationError, match="Eval case field cannot be empty"):
        EvalCase.model_validate(payload)


def test_eval_case_rejects_unstable_case_id() -> None:
    with pytest.raises(ValidationError, match="Eval case id must be stable"):
        EvalCase.model_validate(
            {
                "id": "Normal AAPL Fixture",
                "query": "AAPL",
                "description": "Normal fixture-backed SEC run.",
                "sec_fixture": "sample_sec_fixture",
                "llm_fixture": "mock_valid_report_draft",
                "expected": {},
            }
        )


def test_eval_expectations_reject_blank_list_values() -> None:
    with pytest.raises(
        ValidationError,
        match="Eval expectation list values cannot be empty",
    ):
        EvalExpectations.model_validate(
            {
                "required_citations": ["sec_company_facts", " "],
            }
        )


def test_eval_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvalCase.model_validate(
            {
                "id": "normal_aapl_fixture",
                "query": "AAPL",
                "description": "Normal fixture-backed SEC run.",
                "sec_fixture": "sample_sec_fixture",
                "llm_fixture": "mock_valid_report_draft",
                "expected": {},
                "live_sec_client": object(),
            }
        )


def test_eval_case_result_status_is_derived_from_checks() -> None:
    result = EvalCaseResult(
        case_id="normal_aapl_fixture",
        checks=[
            EvalCheckResult(
                name="report_quality_status",
                status="passed",
                expected="passed",
                actual="passed",
            ),
            EvalCheckResult(
                name="citation_audit_status",
                status="failed",
                expected="passed",
                actual="warning",
                message="Citation audit did not pass.",
            ),
        ],
        metrics={"required_sections_present": True},
        warnings=["report_quality_warning"],
    )

    assert result.status == "failed"
    assert result.model_dump(mode="json") == {
        "case_id": "normal_aapl_fixture",
        "checks": [
            {
                "name": "report_quality_status",
                "status": "passed",
                "expected": "passed",
                "actual": "passed",
                "message": None,
            },
            {
                "name": "citation_audit_status",
                "status": "failed",
                "expected": "passed",
                "actual": "warning",
                "message": "Citation audit did not pass.",
            },
        ],
        "metrics": {"required_sections_present": True},
        "warnings": ["report_quality_warning"],
        "status": "failed",
    }


def test_eval_suite_result_computes_summary_counts_and_pass_rate() -> None:
    suite = EvalSuiteResult(
        suite="deterministic_graph_quality",
        cases=[
            EvalCaseResult(
                case_id="normal_aapl_fixture",
                checks=[EvalCheckResult(name="report_quality_status", status="passed")],
            ),
            EvalCaseResult(
                case_id="unknown_citation_llm_draft",
                checks=[
                    EvalCheckResult(
                        name="citation_audit_status",
                        status="failed",
                        expected="passed",
                        actual="warning",
                    )
                ],
            ),
        ],
    )

    assert suite.case_count == 2
    assert suite.passed == 1
    assert suite.failed == 1
    assert suite.pass_rate == 0.5
    assert suite.model_dump(mode="json")["failed"] == 1
