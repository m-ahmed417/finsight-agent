import subprocess
import sys

from finsight_agent.evals.models import (
    EvalCaseResult,
    EvalCheckResult,
    EvalSuiteResult,
)
from finsight_agent.evals.run import format_suite_result, run


def test_format_suite_result_includes_concise_passing_summary() -> None:
    suite = EvalSuiteResult(
        suite="deterministic_graph_quality",
        cases=[
            EvalCaseResult(
                case_id="normal_aapl_sec_fixture",
                checks=[EvalCheckResult(name="report_quality_status", status="passed")],
            )
        ],
    )

    output = format_suite_result(suite)

    assert output == "\n".join(
        [
            "FinSight eval suite: deterministic_graph_quality",
            "Cases: 1 | Passed: 1 | Failed: 0 | Pass rate: 100.0%",
            "Status: passed",
        ]
    )


def test_format_suite_result_includes_failed_case_ids_and_check_messages() -> None:
    suite = EvalSuiteResult(
        suite="deterministic_graph_quality",
        cases=[
            EvalCaseResult(
                case_id="normal_aapl_sec_fixture",
                checks=[EvalCheckResult(name="report_quality_status", status="passed")],
            ),
            EvalCaseResult(
                case_id="missing_business_section",
                checks=[
                    EvalCheckResult(
                        name="required_warning_codes",
                        status="failed",
                        expected=["business_section_unavailable"],
                        actual=[],
                        message=(
                            "Missing required warning codes: "
                            "business_section_unavailable."
                        ),
                    )
                ],
            ),
        ],
    )

    output = format_suite_result(suite)

    assert "Cases: 2 | Passed: 1 | Failed: 1 | Pass rate: 50.0%" in output
    assert "Status: failed" in output
    assert "Failed cases:" in output
    assert "- missing_business_section" in output
    assert "  - required_warning_codes: Missing required warning codes:" in output


def test_run_returns_zero_for_passing_suite(capsys) -> None:
    suite = EvalSuiteResult(
        suite="deterministic_graph_quality",
        cases=[
            EvalCaseResult(
                case_id="normal_aapl_sec_fixture",
                checks=[EvalCheckResult(name="report_quality_status", status="passed")],
            )
        ],
    )

    exit_code = run(suite_runner=lambda: suite)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Status: passed" in captured.out
    assert captured.err == ""


def test_run_returns_nonzero_for_failing_suite(capsys) -> None:
    suite = EvalSuiteResult(
        suite="deterministic_graph_quality",
        cases=[
            EvalCaseResult(
                case_id="missing_business_section",
                checks=[
                    EvalCheckResult(
                        name="required_warning_codes",
                        status="failed",
                        message="Missing required warning codes.",
                    )
                ],
            )
        ],
    )

    exit_code = run(suite_runner=lambda: suite)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Status: failed" in captured.out
    assert "- missing_business_section" in captured.out


def test_module_entrypoint_runs_deterministic_suite_without_live_services() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "finsight_agent.evals.run"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0
    assert "FinSight eval suite: deterministic_graph_quality" in completed.stdout
    assert "Status: passed" in completed.stdout
    assert completed.stderr == ""
