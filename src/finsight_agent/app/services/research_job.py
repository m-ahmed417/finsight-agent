from typing import Protocol
from uuid import UUID, uuid4

from finsight_agent.app.services.graph_result_validator import (
    GraphResultValidationError,
    validate_graph_result,
)


class ResearchGraphRunner(Protocol):
    def invoke(self, state: dict) -> object:
        """Run the research workflow from an initial state."""


class ResearchRunRepository(Protocol):
    def create_pending_run(self, *, run_id: UUID, query: str) -> object:
        """Persist a queued research run."""

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
) -> object:
    research_run_id = run_id or uuid4()
    return repository.create_pending_run(run_id=research_run_id, query=query)


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
