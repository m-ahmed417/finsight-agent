from typing import Protocol
from uuid import UUID, uuid4

from finsight_agent.app.services.graph_result_validator import (
    GraphResultValidationError,
    validate_graph_result,
)
from finsight_agent.app.research_status import RESEARCH_STATUS_FAILED


class ResearchRunNotFoundError(LookupError):
    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        super().__init__(f"Research run {run_id} was not found.")


class ResearchRunNotRetryableError(ValueError):
    def __init__(self, *, run_id: UUID, status: str) -> None:
        self.run_id = run_id
        self.status = status
        super().__init__(
            f"Research run {run_id} cannot be retried while status is {status!r}."
        )


class ResearchGraphRunner(Protocol):
    def invoke(self, state: dict) -> object:
        """Run the research workflow from an initial state."""


class ResearchRunRepository(Protocol):
    def create_pending_run(
        self,
        *,
        run_id: UUID,
        query: str,
        retried_from_run_id: UUID | None = None,
    ) -> object:
        """Persist a queued research run."""

    def get_by_id(self, run_id: UUID) -> object | None:
        """Return a persisted research run by ID."""

    def mark_running(self, run_id: UUID) -> object | None:
        """Mark a queued research run as running."""

    def mark_completed_from_graph_result(
        self,
        run_id: UUID,
        *,
        graph_result: dict,
    ) -> object | None:
        """Persist a completed graph result onto an existing research run."""

    def mark_failed_from_graph_result(
        self,
        run_id: UUID,
        *,
        graph_result: dict,
    ) -> object | None:
        """Persist a failed graph result onto an existing research run."""

    def mark_failed(self, run_id: UUID, *, error: str) -> object | None:
        """Mark a research run failed when no valid graph result is available."""


def enqueue_research_run(
    *,
    query: str,
    repository: ResearchRunRepository,
    run_id: UUID | None = None,
    retried_from_run_id: UUID | None = None,
) -> object:
    research_run_id = run_id or uuid4()
    return repository.create_pending_run(
        run_id=research_run_id,
        query=query,
        retried_from_run_id=retried_from_run_id,
    )


def retry_failed_research_run(
    *,
    run_id: UUID,
    repository: ResearchRunRepository,
    new_run_id: UUID | None = None,
) -> object:
    original_run = repository.get_by_id(run_id)
    if original_run is None:
        raise ResearchRunNotFoundError(run_id)

    status = str(original_run.status)
    if status != RESEARCH_STATUS_FAILED:
        raise ResearchRunNotRetryableError(run_id=run_id, status=status)

    return enqueue_research_run(
        query=original_run.query,
        repository=repository,
        run_id=new_run_id,
        retried_from_run_id=run_id,
    )


def execute_research_run(
    *,
    run_id: UUID,
    query: str,
    graph_runner: ResearchGraphRunner,
    repository: ResearchRunRepository,
) -> object | None:
    running_run = repository.mark_running(run_id)
    if running_run is None:
        return None

    try:
        raw_graph_result = graph_runner.invoke({"user_query": query})
        graph_result = validate_graph_result(raw_graph_result)
    except GraphResultValidationError as exc:
        return repository.mark_failed(
            run_id,
            error=f"Graph result validation failed: {exc}",
        )
    except Exception as exc:
        return repository.mark_failed(
            run_id,
            error=f"Research job failed before valid graph output: {exc}",
        )

    if graph_result.get("errors", []):
        return repository.mark_failed_from_graph_result(
            run_id,
            graph_result=graph_result,
        )

    return repository.mark_completed_from_graph_result(
        run_id,
        graph_result=graph_result,
    )
