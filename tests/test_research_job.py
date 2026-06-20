from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from finsight_agent.app.services.research_job import (
    ResearchRunNotFoundError,
    ResearchRunNotRetryableError,
    enqueue_research_run,
    execute_research_run,
    retry_failed_research_run,
)

DEFAULT_RUNNING_RUN = SimpleNamespace(status="running")


class FakeGraphRunner:
    def __init__(
        self,
        result: object | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.invocations: list[dict] = []

    def invoke(self, state: dict) -> object:
        self.invocations.append(state)
        if self.error is not None:
            raise self.error
        return self.result


class FakeRepository:
    def __init__(self, *, running_run: object | None = DEFAULT_RUNNING_RUN) -> None:
        self.running_run = running_run
        self.runs: dict[UUID, SimpleNamespace] = {}
        self.pending_runs: list[dict] = []
        self.running_run_ids: list[UUID] = []
        self.completed_updates: list[dict] = []
        self.failed_graph_updates: list[dict] = []
        self.failed_updates: list[dict] = []

    def create_pending_run(
        self,
        *,
        run_id: UUID,
        query: str,
        retried_from_run_id: UUID | None = None,
    ) -> SimpleNamespace:
        pending_run = {"run_id": run_id, "query": query}
        if retried_from_run_id is not None:
            pending_run["retried_from_run_id"] = retried_from_run_id
        self.pending_runs.append(pending_run)
        run = SimpleNamespace(
            id=str(run_id),
            query=query,
            status="queued",
            retried_from_run_id=(
                str(retried_from_run_id) if retried_from_run_id is not None else None
            ),
        )
        self.runs[run_id] = run
        return run

    def get_by_id(self, run_id: UUID) -> SimpleNamespace | None:
        return self.runs.get(run_id)

    def mark_running(self, run_id: UUID) -> SimpleNamespace | None:
        self.running_run_ids.append(run_id)
        return self.running_run

    def mark_completed_from_graph_result(
        self,
        run_id: UUID,
        *,
        graph_result: dict,
    ) -> SimpleNamespace:
        self.completed_updates.append({"run_id": run_id, "graph_result": graph_result})
        return SimpleNamespace(id=str(run_id), status="completed")

    def mark_failed_from_graph_result(
        self,
        run_id: UUID,
        *,
        graph_result: dict,
    ) -> SimpleNamespace:
        self.failed_graph_updates.append({"run_id": run_id, "graph_result": graph_result})
        return SimpleNamespace(id=str(run_id), status="failed")

    def mark_failed(self, run_id: UUID, *, error: str) -> SimpleNamespace:
        self.failed_updates.append({"run_id": run_id, "error": error})
        return SimpleNamespace(id=str(run_id), status="failed")


def test_enqueue_research_run_creates_pending_run_with_provided_id() -> None:
    repository = FakeRepository()
    run_id = uuid4()

    run = enqueue_research_run(
        query="AAPL",
        repository=repository,
        run_id=run_id,
    )

    assert run.id == str(run_id)
    assert run.query == "AAPL"
    assert run.status == "queued"
    assert repository.pending_runs == [{"run_id": run_id, "query": "AAPL"}]


def test_enqueue_research_run_can_record_retry_lineage() -> None:
    repository = FakeRepository()
    run_id = uuid4()
    original_run_id = uuid4()

    run = enqueue_research_run(
        query="AAPL",
        repository=repository,
        run_id=run_id,
        retried_from_run_id=original_run_id,
    )

    assert run.id == str(run_id)
    assert run.retried_from_run_id == str(original_run_id)
    assert repository.pending_runs == [
        {
            "run_id": run_id,
            "query": "AAPL",
            "retried_from_run_id": original_run_id,
        }
    ]


def test_retry_failed_research_run_creates_new_queued_run_with_retry_lineage() -> None:
    repository = FakeRepository()
    original_run_id = uuid4()
    retry_run_id = uuid4()
    repository.runs[original_run_id] = SimpleNamespace(
        id=str(original_run_id),
        query="AAPL",
        status="failed",
    )

    retried_run = retry_failed_research_run(
        run_id=original_run_id,
        repository=repository,
        new_run_id=retry_run_id,
    )

    assert retried_run.id == str(retry_run_id)
    assert retried_run.query == "AAPL"
    assert retried_run.status == "queued"
    assert retried_run.retried_from_run_id == str(original_run_id)
    assert repository.pending_runs == [
        {
            "run_id": retry_run_id,
            "query": "AAPL",
            "retried_from_run_id": original_run_id,
        }
    ]
    assert repository.runs[original_run_id].status == "failed"


def test_retry_failed_research_run_raises_when_original_run_is_missing() -> None:
    repository = FakeRepository()
    missing_run_id = uuid4()

    try:
        retry_failed_research_run(run_id=missing_run_id, repository=repository)
    except ResearchRunNotFoundError as exc:
        assert exc.run_id == missing_run_id
    else:
        raise AssertionError("Expected ResearchRunNotFoundError.")

    assert repository.pending_runs == []


@pytest.mark.parametrize("status", ["queued", "running", "completed"])
def test_retry_failed_research_run_raises_when_original_run_is_not_failed(
    status: str,
) -> None:
    repository = FakeRepository()
    original_run_id = uuid4()
    repository.runs[original_run_id] = SimpleNamespace(
        id=str(original_run_id),
        query="AAPL",
        status=status,
    )

    try:
        retry_failed_research_run(run_id=original_run_id, repository=repository)
    except ResearchRunNotRetryableError as exc:
        assert exc.run_id == original_run_id
        assert exc.status == status
    else:
        raise AssertionError("Expected ResearchRunNotRetryableError.")

    assert repository.pending_runs == []


def test_execute_research_run_marks_completed_when_graph_has_no_errors() -> None:
    repository = FakeRepository()
    graph_result = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "warnings": [],
        "errors": [],
        "sources": [],
        "agent_steps": [
            {
                "node_name": "resolve_company",
                "status": "completed",
                "message": "Resolved AAPL to Apple Inc.",
            }
        ],
    }
    graph_runner = FakeGraphRunner(result=graph_result)
    run_id = uuid4()

    run = execute_research_run(
        run_id=run_id,
        query="AAPL",
        graph_runner=graph_runner,
        repository=repository,
    )

    assert run.status == "completed"
    assert repository.running_run_ids == [run_id]
    assert graph_runner.invocations == [{"user_query": "AAPL"}]
    assert repository.completed_updates == [
        {
            "run_id": run_id,
            "graph_result": {
                **graph_result,
                "llm_call_events": [],
            },
        }
    ]
    assert repository.failed_graph_updates == []
    assert repository.failed_updates == []


def test_execute_research_run_marks_failed_when_graph_result_has_errors() -> None:
    repository = FakeRepository()
    graph_result = {
        "ticker": None,
        "company_name": None,
        "warnings": [],
        "errors": [
            {
                "code": "company_not_found",
                "message": "Could not confidently resolve the company.",
                "severity": "error",
            }
        ],
        "sources": [],
        "agent_steps": [
            {
                "node_name": "resolve_company",
                "status": "failed",
                "error_message": "Could not confidently resolve the company.",
            }
        ],
    }
    graph_runner = FakeGraphRunner(result=graph_result)
    run_id = uuid4()

    run = execute_research_run(
        run_id=run_id,
        query="UNKNOWN",
        graph_runner=graph_runner,
        repository=repository,
    )

    assert run.status == "failed"
    assert repository.running_run_ids == [run_id]
    assert graph_runner.invocations == [{"user_query": "UNKNOWN"}]
    assert repository.completed_updates == []
    assert repository.failed_graph_updates == [
        {
            "run_id": run_id,
            "graph_result": {
                **graph_result,
                "llm_call_events": [],
            },
        }
    ]
    assert repository.failed_updates == []


def test_execute_research_run_marks_failed_when_graph_result_is_invalid() -> None:
    repository = FakeRepository()
    graph_runner = FakeGraphRunner(result={"sources": [{"source_id": " "}]})
    run_id = uuid4()

    run = execute_research_run(
        run_id=run_id,
        query="AAPL",
        graph_runner=graph_runner,
        repository=repository,
    )

    assert run.status == "failed"
    assert repository.completed_updates == []
    assert repository.failed_graph_updates == []
    assert len(repository.failed_updates) == 1
    assert repository.failed_updates[0]["run_id"] == run_id
    assert repository.failed_updates[0]["error"].startswith(
        "Graph result validation failed:"
    )


def test_execute_research_run_marks_failed_when_graph_raises() -> None:
    repository = FakeRepository()
    graph_runner = FakeGraphRunner(error=RuntimeError("SEC request timed out."))
    run_id = uuid4()

    run = execute_research_run(
        run_id=run_id,
        query="AAPL",
        graph_runner=graph_runner,
        repository=repository,
    )

    assert run.status == "failed"
    assert repository.completed_updates == []
    assert repository.failed_graph_updates == []
    assert repository.failed_updates == [
        {
            "run_id": run_id,
            "error": "Research job failed before valid graph output: SEC request timed out.",
        }
    ]


def test_execute_research_run_skips_graph_when_run_is_missing() -> None:
    repository = FakeRepository(running_run=None)
    graph_runner = FakeGraphRunner(result={"errors": []})
    run_id = uuid4()

    run = execute_research_run(
        run_id=run_id,
        query="AAPL",
        graph_runner=graph_runner,
        repository=repository,
    )

    assert run is None
    assert repository.running_run_ids == [run_id]
    assert graph_runner.invocations == []
    assert repository.completed_updates == []
    assert repository.failed_graph_updates == []
    assert repository.failed_updates == []
