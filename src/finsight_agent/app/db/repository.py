from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from finsight_agent.app.db.models import AgentStep, ResearchRun, utc_now

FILING_TEXT_EXCERPT_LENGTH = 2000


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
            compliance_status=graph_result.get("compliance_status"),
            report_quality_status=graph_result.get("report_quality_status"),
            final_report=graph_result.get("final_report"),
            financial_metrics_json=graph_result.get("financial_metrics"),
            filing_text_excerpt=_filing_text_excerpt(graph_result.get("filing_text")),
            risk_factors_json=graph_result.get("risk_factors", []),
            risk_themes_json=graph_result.get("risk_themes", []),
            research_insights_json=graph_result.get("research_insights"),
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


def _filing_text_excerpt(filing_text: str | None) -> str | None:
    if not filing_text:
        return None
    return filing_text[:FILING_TEXT_EXCERPT_LENGTH]
