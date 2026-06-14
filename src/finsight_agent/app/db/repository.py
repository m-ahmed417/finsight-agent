from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from finsight_agent.app.db.models import AgentStep, ResearchRun, utc_now


class ResearchRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

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
            status=status,
            ticker=graph_result.get("ticker"),
            company_name=graph_result.get("company_name"),
            final_report=graph_result.get("final_report"),
            financial_metrics_json=graph_result.get("financial_metrics"),
            warnings_json=graph_result.get("warnings", []),
            errors_json=graph_result.get("errors", []),
            sources_json=graph_result.get("sources", []),
            completed_at=utc_now(),
        )
        self._session.add(run)
        self._session.flush()
        for step in graph_result.get("agent_steps", []):
            self._session.add(
                AgentStep(
                    research_run_id=str(run_id),
                    node_name=step["node_name"],
                    status=step["status"],
                    message=step.get("message"),
                    error_message=step.get("error_message"),
                )
            )
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
