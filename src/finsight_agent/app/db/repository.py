from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm import Session

from finsight_agent.app.db.models import AgentStep, LLMCallEvent, ResearchRun, utc_now
from finsight_agent.app.research_status import (
    IN_PROGRESS_RESEARCH_STATUSES,
    RESEARCH_STATUS_COMPLETED,
    RESEARCH_STATUS_FAILED,
    RESEARCH_STATUS_QUEUED,
    RESEARCH_STATUS_RUNNING,
)

FILING_TEXT_EXCERPT_LENGTH = 2000
STALE_RESEARCH_RUN_ERROR = {
    "code": "research_run_stale",
    "message": (
        "Research run was marked failed because it remained queued or "
        "running past the stale-run cutoff."
    ),
    "severity": "error",
}


@dataclass(frozen=True)
class ResearchRunListCursor:
    created_at: datetime
    run_id: str


class ResearchRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_pending_run(
        self,
        *,
        run_id: UUID,
        query: str,
        retried_from_run_id: UUID | None = None,
    ) -> ResearchRun:
        run = ResearchRun(
            id=str(run_id),
            query=query,
            status=RESEARCH_STATUS_QUEUED,
            retried_from_run_id=(
                str(retried_from_run_id) if retried_from_run_id is not None else None
            ),
            risk_factors_json=[],
            risk_themes_json=[],
            warnings_json=[],
            errors_json=[],
            sources_json=[],
        )
        self._session.add(run)
        self._session.commit()
        self._session.refresh(run)
        return run

    def mark_running(self, run_id: UUID) -> ResearchRun | None:
        statement = (
            update(ResearchRun)
            .where(ResearchRun.id == str(run_id))
            .where(ResearchRun.status == RESEARCH_STATUS_QUEUED)
            .values(status=RESEARCH_STATUS_RUNNING, completed_at=None)
        )
        result = self._session.execute(statement)
        if result.rowcount != 1:
            self._session.rollback()
            return None

        self._session.commit()
        return self.get_by_id(run_id)

    def mark_failed(self, run_id: UUID, *, error: str) -> ResearchRun | None:
        run = self.get_by_id(run_id)
        if run is None:
            return None

        run.status = RESEARCH_STATUS_FAILED
        run.errors_json = [
            *(run.errors_json or []),
            {
                "code": "research_run_failed",
                "message": error,
                "severity": "error",
            },
        ]
        run.completed_at = utc_now()
        self._session.commit()
        self._session.refresh(run)
        return run

    def mark_completed_from_graph_result(
        self,
        run_id: UUID,
        *,
        graph_result: dict,
    ) -> ResearchRun | None:
        return self._mark_from_graph_result(
            run_id,
            status=RESEARCH_STATUS_COMPLETED,
            graph_result=graph_result,
        )

    def mark_failed_from_graph_result(
        self,
        run_id: UUID,
        *,
        graph_result: dict,
    ) -> ResearchRun | None:
        return self._mark_from_graph_result(
            run_id,
            status=RESEARCH_STATUS_FAILED,
            graph_result=graph_result,
        )

    def get_stale_in_progress_runs(
        self,
        *,
        older_than: datetime,
    ) -> list[ResearchRun]:
        statement = (
            select(ResearchRun)
            .where(ResearchRun.status.in_(IN_PROGRESS_RESEARCH_STATUSES))
            .where(ResearchRun.completed_at.is_(None))
            .where(ResearchRun.created_at < older_than)
            .order_by(ResearchRun.created_at, ResearchRun.id)
        )
        return list(self._session.scalars(statement))

    def mark_stale_in_progress_runs_failed(
        self,
        *,
        older_than: datetime,
    ) -> list[ResearchRun]:
        stale_runs = self.get_stale_in_progress_runs(older_than=older_than)
        for run in stale_runs:
            run.status = RESEARCH_STATUS_FAILED
            run.errors_json = [*(run.errors_json or []), dict(STALE_RESEARCH_RUN_ERROR)]
            run.completed_at = utc_now()

        self._session.commit()
        for run in stale_runs:
            self._session.refresh(run)
        return stale_runs

    def list_recent_runs(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
        before: ResearchRunListCursor | None = None,
    ) -> list[ResearchRun]:
        if limit <= 0:
            return []

        statement = select(ResearchRun).order_by(
            ResearchRun.created_at.desc(),
            ResearchRun.id.desc(),
        )
        if status is not None:
            statement = statement.where(ResearchRun.status == status)
        if before is not None:
            statement = statement.where(
                or_(
                    ResearchRun.created_at < before.created_at,
                    and_(
                        ResearchRun.created_at == before.created_at,
                        ResearchRun.id < before.run_id,
                    ),
                )
            )

        return list(self._session.scalars(statement.limit(limit)))

    def list_retry_chain(self, run_id: UUID) -> list[ResearchRun]:
        run = self.get_by_id(run_id)
        if run is None:
            return []

        root_run = self._find_retry_root(run)
        chain_by_id = {root_run.id: root_run}
        frontier_ids = {root_run.id}
        while frontier_ids:
            statement = (
                select(ResearchRun)
                .where(ResearchRun.retried_from_run_id.in_(frontier_ids))
                .order_by(ResearchRun.created_at, ResearchRun.id)
            )
            children = [
                child
                for child in self._session.scalars(statement)
                if child.id not in chain_by_id
            ]
            frontier_ids = {child.id for child in children}
            chain_by_id.update({child.id: child for child in children})

        return sorted(
            chain_by_id.values(),
            key=lambda chain_run: (chain_run.created_at, chain_run.id),
        )

    def _mark_from_graph_result(
        self,
        run_id: UUID,
        *,
        status: str,
        graph_result: dict,
    ) -> ResearchRun | None:
        run = self.get_by_id(run_id)
        if run is None:
            return None

        _apply_graph_result_to_run(run, status=status, graph_result=graph_result)
        self._replace_agent_steps(run_id, graph_result.get("agent_steps", []))
        self._replace_llm_call_events(run_id, graph_result.get("llm_call_events", []))
        self._session.commit()
        self._session.refresh(run)
        return run

    def create_from_graph_result(
        self,
        *,
        run_id: UUID,
        query: str,
        status: str,
        graph_result: dict,
    ) -> ResearchRun:
        run = ResearchRun(
            id=str(run_id),
            query=query,
        )
        _apply_graph_result_to_run(run, status=status, graph_result=graph_result)
        self._session.add(run)
        self._session.flush()
        self._add_agent_steps(run_id, graph_result.get("agent_steps", []))
        self._add_llm_call_events(run_id, graph_result.get("llm_call_events", []))
        self._session.commit()
        self._session.refresh(run)
        return run

    def get_by_id(self, run_id: UUID) -> ResearchRun | None:
        return self._session.get(ResearchRun, str(run_id))

    def get_steps_for_run(self, run_id: UUID) -> list[AgentStep]:
        statement = (
            select(AgentStep)
            .where(AgentStep.research_run_id == str(run_id))
            .order_by(AgentStep.id)
        )
        return list(self._session.scalars(statement))

    def get_llm_call_events_for_run(self, run_id: UUID) -> list[LLMCallEvent]:
        statement = (
            select(LLMCallEvent)
            .where(LLMCallEvent.research_run_id == str(run_id))
            .order_by(LLMCallEvent.id)
        )
        return list(self._session.scalars(statement))

    def _find_retry_root(self, run: ResearchRun) -> ResearchRun:
        root_run = run
        seen_ids = {root_run.id}
        while root_run.retried_from_run_id is not None:
            parent_run = self._session.get(ResearchRun, root_run.retried_from_run_id)
            if parent_run is None or parent_run.id in seen_ids:
                break
            root_run = parent_run
            seen_ids.add(root_run.id)
        return root_run

    def _replace_agent_steps(self, run_id: UUID, steps: list[dict]) -> None:
        statement = delete(AgentStep).where(AgentStep.research_run_id == str(run_id))
        self._session.execute(statement)
        self._add_agent_steps(run_id, steps)

    def _replace_llm_call_events(self, run_id: UUID, events: list[dict]) -> None:
        statement = delete(LLMCallEvent).where(
            LLMCallEvent.research_run_id == str(run_id)
        )
        self._session.execute(statement)
        self._add_llm_call_events(run_id, events)

    def _add_agent_steps(self, run_id: UUID, steps: list[dict]) -> None:
        for step in steps:
            self._session.add(
                AgentStep(
                    research_run_id=str(run_id),
                    node_name=step["node_name"],
                    status=step["status"],
                    message=step.get("message"),
                    error_message=step.get("error_message"),
                    started_at=step.get("started_at"),
                    completed_at=step.get("completed_at"),
                    duration_seconds=step.get("duration_seconds"),
                    llm_provider=step.get("llm_provider"),
                    llm_model=step.get("llm_model"),
                    llm_used=step.get("llm_used"),
                    llm_fallback_reason=step.get("llm_fallback_reason"),
                )
            )

    def _add_llm_call_events(self, run_id: UUID, events: list[dict]) -> None:
        for event in events:
            self._session.add(
                LLMCallEvent(
                    research_run_id=str(run_id),
                    node_name=event["node_name"],
                    task=event["task"],
                    status=event["status"],
                    llm_provider=event.get("llm_provider"),
                    llm_model=event.get("llm_model"),
                    prompt_version=event.get("prompt_version"),
                    started_at=event.get("started_at"),
                    completed_at=event.get("completed_at"),
                    duration_seconds=event.get("duration_seconds"),
                    input_tokens=event.get("input_tokens"),
                    output_tokens=event.get("output_tokens"),
                    total_tokens=event.get("total_tokens"),
                    provider_request_id=event.get("provider_request_id"),
                    error_type=event.get("error_type"),
                    error_message=event.get("error_message"),
                    fallback_used=event.get("fallback_used"),
                    fallback_reason=event.get("fallback_reason"),
                )
            )


def _apply_graph_result_to_run(
    run: ResearchRun,
    *,
    status: str,
    graph_result: dict,
) -> None:
    run.status = status
    run.ticker = graph_result.get("ticker")
    run.company_name = graph_result.get("company_name")
    run.compliance_status = graph_result.get("compliance_status")
    run.report_quality_status = graph_result.get("report_quality_status")
    run.report_quality_details_json = graph_result.get("report_quality_details")
    run.final_report = graph_result.get("final_report")
    run.financial_metrics_json = graph_result.get("financial_metrics")
    run.filing_text_excerpt = _filing_text_excerpt(graph_result.get("filing_text"))
    run.risk_factors_json = graph_result.get("risk_factors", [])
    run.risk_themes_json = graph_result.get("risk_themes", [])
    run.research_insights_json = graph_result.get("research_insights")
    run.warnings_json = graph_result.get("warnings", [])
    run.errors_json = graph_result.get("errors", [])
    run.sources_json = graph_result.get("sources", [])
    run.completed_at = utc_now()


def _filing_text_excerpt(filing_text: str | None) -> str | None:
    if not filing_text:
        return None
    return filing_text[:FILING_TEXT_EXCERPT_LENGTH]
