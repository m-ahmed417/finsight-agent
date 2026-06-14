from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from finsight_agent.app.api.dependencies import (
    ResearchGraphRunner,
    get_company_resolver,
    get_research_repository,
    get_research_graph_runner,
)
from finsight_agent.app.api.schemas import (
    AgentStepResponse,
    CompanySearchResult,
    HealthResponse,
    ResearchRequest,
    ResearchResponse,
)
from finsight_agent.app.db.models import AgentStep, ResearchRun
from finsight_agent.app.db.repository import ResearchRunRepository
from finsight_agent.app.services.company_resolver import CompanyResolver

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/companies/search", response_model=list[CompanySearchResult])
def search_companies(
    q: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(10, ge=1, le=50),
    resolver: CompanyResolver = Depends(get_company_resolver),
) -> list[CompanySearchResult]:
    query = q.strip()
    if not query:
        raise HTTPException(
            status_code=422,
            detail="Company search query cannot be empty.",
        )

    return [
        CompanySearchResult(
            ticker=company.ticker,
            company_name=company.company_name,
            cik=company.cik,
            exchange=company.exchange,
        )
        for company in resolver.search(query, limit=limit)
    ]


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
        filing_text_excerpt=run.filing_text_excerpt,
        risk_factors=run.risk_factors_json,
        risk_themes=run.risk_themes_json,
        research_insights=run.research_insights_json,
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
