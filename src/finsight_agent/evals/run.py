from collections.abc import Callable
import sys
from typing import TextIO

from finsight_agent.evals.graph_suite import run_deterministic_graph_eval_suite
from finsight_agent.evals.models import EvalStatus, EvalSuiteResult

SuiteRunner = Callable[[], EvalSuiteResult]


def format_suite_result(suite: EvalSuiteResult) -> str:
    lines = [
        f"FinSight eval suite: {suite.suite}",
        (
            f"Cases: {suite.case_count} | Passed: {suite.passed} | "
            f"Failed: {suite.failed} | Pass rate: {suite.pass_rate:.1%}"
        ),
        f"Status: {'passed' if suite.failed == 0 else 'failed'}",
    ]

    failed_cases = [
        case for case in suite.cases if case.status == EvalStatus.FAILED
    ]
    if failed_cases:
        lines.append("Failed cases:")
        for case in failed_cases:
            lines.append(f"- {case.case_id}")
            for check in case.checks:
                if check.status != EvalStatus.FAILED:
                    continue
                message = check.message or (
                    f"expected {check.expected!r}, got {check.actual!r}"
                )
                lines.append(f"  - {check.name}: {message}")

    return "\n".join(lines)


def run(
    *,
    suite_runner: SuiteRunner = run_deterministic_graph_eval_suite,
    stdout: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    suite = suite_runner()
    print(format_suite_result(suite), file=output)
    return 0 if suite.failed == 0 else 1


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
