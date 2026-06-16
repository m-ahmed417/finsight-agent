from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from finsight_agent.app.db.models import AgentStep, ResearchRun, utc_now
from finsight_agent.app.research_status import (
    RESEARCH_STATUS_COMPLETED,
    RESEARCH_STATUS_FAILED,
    RESEARCH_STATUS_QUEUED,
    RESEARCH_STATUS_RUNNING,
)

FILING_TEXT_EXCERPT_LENGTH = 2000


class ResearchRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_pending_run(self, *, run_id: UUID, query: str) -> ResearchRun:
        run = ResearchRun(
            id=str(run_id),
            query=query,
            status=RESEARCH_STATUS_QUEUED,
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
        run = self.get_by_id(run_id)
        if run is None:
            return None

        run.status = RESEARCH_STATUS_RUNNING
        run.completed_at = None
        self._session.commit()
        self._session.refresh(run)
        return run

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

    def _replace_agent_steps(self, run_id: UUID, steps: list[dict]) -> None:
        statement = delete(AgentStep).where(AgentStep.research_run_id == str(run_id))
        self._session.execute(statement)
        self._add_agent_steps(run_id, steps)

    def _add_agent_steps(self, run_id: UUID, steps: list[dict]) -> None:
        for step in steps:
            self._session.add(
                AgentStep(
                    research_run_id=str(run_id),
                    node_name=step["node_name"],
                    status=step["status"],
                    message=step.get("message"),
                    error_message=step.get("error_message"),
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
