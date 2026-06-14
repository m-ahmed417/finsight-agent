from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from finsight_agent.app.api.dependencies import (
    ResearchGraphRunner,
    get_research_repository,
    get_research_graph_runner,
)
from finsight_agent.app.api.schemas import (
    AgentStepResponse,
    HealthResponse,
    ResearchRequest,
    ResearchResponse,
)
from finsight_agent.app.db.models import AgentStep, ResearchRun
from finsight_agent.app.db.repository import ResearchRunRepository

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/research", response_model=ResearchResponse)
def research(
    request: ResearchRequest,
    graph_runner: ResearchGraphRunner = Depends(get_research_graph_runner),
    repository: ResearchRunRepository = Depends(get_research_repository),
) -> ResearchResponse:
    graph_result = graph_runner.invoke({"user_query": request.query})
    errors = graph_result.get("errors", [])
    run_id = uuid4()
    run = repository.create_from_graph_result(
        run_id=run_id,
        query=request.query,
        status="failed" if errors else "completed",
        graph_result=graph_result,
    )

    return _research_run_to_response(run)


@router.get("/research/{run_id}", response_model=ResearchResponse)
def get_research(
    run_id: UUID,
    repository: ResearchRunRepository = Depends(get_research_repository),
) -> ResearchResponse:
    run = repository.get_by_id(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research run not found.",
        )

    return _research_run_to_response(run)


@router.get("/research/{run_id}/steps", response_model=list[AgentStepResponse])
def get_research_steps(
    run_id: UUID,
    repository: ResearchRunRepository = Depends(get_research_repository),
) -> list[AgentStepResponse]:
    run = repository.get_by_id(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research run not found.",
        )

    return [_agent_step_to_response(step) for step in repository.get_steps_for_run(run_id)]


def _research_run_to_response(run: ResearchRun) -> ResearchResponse:
    return ResearchResponse(
        run_id=UUID(run.id),
        query=run.query,
        status=run.status,
        ticker=run.ticker,
        company_name=run.company_name,
        report=run.final_report,
        financial_metrics=run.financial_metrics_json,
        warnings=run.warnings_json,
        errors=run.errors_json,
        sources=run.sources_json,
    )


def _agent_step_to_response(step: AgentStep) -> AgentStepResponse:
    return AgentStepResponse(
        id=step.id,
        research_run_id=step.research_run_id,
        node_name=step.node_name,
        status=step.status,
        message=step.message,
        error_message=step.error_message,
    )
