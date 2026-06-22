import base64
import binascii
from collections.abc import Iterable
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from finsight_agent.app.api.dependencies import (
    ResearchJobExecutor,
    get_company_resolver,
    get_research_job_executor,
    get_research_repository,
)
from finsight_agent.app.api.schemas import (
    AgentStepResponse,
    CompanySearchResult,
    HealthResponse,
    LLMCallEventResponse,
    LLMUsageSummaryResponse,
    ResearchProgressResponse,
    ResearchRequest,
    ResearchResponse,
    ResearchRunListResponse,
    ResearchRunSummary,
)
from finsight_agent.app.db.models import AgentStep, LLMCallEvent, ResearchRun
from finsight_agent.app.db.repository import ResearchRunListCursor, ResearchRunRepository
from finsight_agent.app.research_status import ResearchStatus
from finsight_agent.app.services.company_resolver import CompanyResolver
from finsight_agent.app.services.research_job import (
    ResearchRunNotFoundError,
    ResearchRunNotRetryableError,
    enqueue_research_run,
    retry_failed_research_run,
)
from finsight_agent.app.services.llm_usage import summarize_llm_usage

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


@router.post(
    "/research",
    response_model=ResearchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def research(
    request: ResearchRequest,
    background_tasks: BackgroundTasks,
    repository: ResearchRunRepository = Depends(get_research_repository),
    research_job_executor: ResearchJobExecutor = Depends(get_research_job_executor),
) -> ResearchResponse:
    run = enqueue_research_run(
        query=request.query,
        repository=repository,
    )
    background_tasks.add_task(
        research_job_executor,
        run_id=UUID(run.id),
        query=request.query,
    )

    return _research_run_to_response(run)


@router.get(
    "/research",
    response_model=ResearchRunListResponse,
    summary="List compact research run summaries",
    description=(
        "Returns paginated compact summaries for recent research runs. Use the "
        "next_cursor value as the cursor query parameter to request the next page."
    ),
)
def list_research_runs(
    status: ResearchStatus | None = Query(
        default=None,
        description="Optional lifecycle status filter.",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of recent research runs to return.",
    ),
    cursor: str | None = Query(
        default=None,
        description="Opaque cursor returned by the previous research list response.",
    ),
    repository: ResearchRunRepository = Depends(get_research_repository),
) -> ResearchRunListResponse:
    try:
        before = _decode_research_list_cursor(cursor) if cursor is not None else None
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Invalid research list cursor.",
        ) from exc

    runs = repository.list_recent_runs(status=status, limit=limit + 1, before=before)
    page_runs = runs[:limit]
    has_more = len(runs) > limit
    return ResearchRunListResponse(
        items=[_research_run_to_summary(run) for run in page_runs],
        next_cursor=(
            _encode_research_list_cursor(page_runs[-1])
            if has_more and page_runs
            else None
        ),
        has_more=has_more,
    )


@router.post(
    "/research/{run_id}/retry",
    response_model=ResearchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_research(
    run_id: UUID,
    background_tasks: BackgroundTasks,
    repository: ResearchRunRepository = Depends(get_research_repository),
    research_job_executor: ResearchJobExecutor = Depends(get_research_job_executor),
) -> ResearchResponse:
    try:
        retry_run = retry_failed_research_run(
            run_id=run_id,
            repository=repository,
        )
    except ResearchRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research run not found.",
        ) from exc
    except ResearchRunNotRetryableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed research runs can be retried.",
        ) from exc

    background_tasks.add_task(
        research_job_executor,
        run_id=UUID(retry_run.id),
        query=retry_run.query,
    )
    return _research_run_to_response(retry_run)


@router.get("/research/{run_id}/retries", response_model=list[ResearchResponse])
def get_research_retry_chain(
    run_id: UUID,
    repository: ResearchRunRepository = Depends(get_research_repository),
) -> list[ResearchResponse]:
    retry_chain = repository.list_retry_chain(run_id)
    if not retry_chain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research run not found.",
        )

    return [_research_run_to_response(run) for run in retry_chain]


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


@router.get("/research/{run_id}/progress", response_model=ResearchProgressResponse)
def get_research_progress(
    run_id: UUID,
    repository: ResearchRunRepository = Depends(get_research_repository),
) -> ResearchProgressResponse:
    run = repository.get_by_id(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research run not found.",
        )

    return _research_progress_to_response(
        run,
        repository.get_steps_for_run(run_id),
    )


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


@router.get("/research/{run_id}/llm-calls", response_model=list[LLMCallEventResponse])
def get_research_llm_calls(
    run_id: UUID,
    repository: ResearchRunRepository = Depends(get_research_repository),
) -> list[LLMCallEventResponse]:
    run = repository.get_by_id(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research run not found.",
        )

    return [
        _llm_call_event_to_response(event)
        for event in repository.get_llm_call_events_for_run(run_id)
    ]


@router.get("/research/{run_id}/llm-usage", response_model=LLMUsageSummaryResponse)
def get_research_llm_usage(
    run_id: UUID,
    repository: ResearchRunRepository = Depends(get_research_repository),
) -> LLMUsageSummaryResponse:
    run = repository.get_by_id(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research run not found.",
        )

    return _llm_usage_summary_to_response(
        run,
        repository.get_llm_call_events_for_run(run_id),
    )


def _research_run_to_response(run: ResearchRun) -> ResearchResponse:
    return ResearchResponse(
        run_id=UUID(run.id),
        retried_from_run_id=(
            UUID(run.retried_from_run_id)
            if run.retried_from_run_id is not None
            else None
        ),
        query=run.query,
        status=run.status,
        created_at=run.created_at,
        completed_at=run.completed_at,
        duration_seconds=_duration_seconds(run.created_at, run.completed_at),
        ticker=run.ticker,
        company_name=run.company_name,
        compliance_status=run.compliance_status,
        report_quality_status=run.report_quality_status,
        report_quality_details=run.report_quality_details_json,
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


def _research_run_to_summary(run: ResearchRun) -> ResearchRunSummary:
    return ResearchRunSummary(
        run_id=UUID(run.id),
        retried_from_run_id=(
            UUID(run.retried_from_run_id)
            if run.retried_from_run_id is not None
            else None
        ),
        query=run.query,
        status=run.status,
        created_at=run.created_at,
        completed_at=run.completed_at,
        duration_seconds=_duration_seconds(run.created_at, run.completed_at),
        ticker=run.ticker,
        company_name=run.company_name,
        warnings_count=len(run.warnings_json or []),
        errors_count=len(run.errors_json or []),
        has_report=bool((run.final_report or "").strip()),
    )


def _research_progress_to_response(
    run: ResearchRun,
    steps: list[AgentStep],
) -> ResearchProgressResponse:
    step_responses = [_agent_step_to_response(step) for step in steps]
    workflow_started_at = _earliest_datetime(
        step.started_at for step in step_responses
    )
    workflow_completed_at = _latest_datetime(
        step.completed_at for step in step_responses
    )
    return ResearchProgressResponse(
        run_id=UUID(run.id),
        status=run.status,
        total_steps=len(step_responses),
        completed_steps=_count_steps_by_status(step_responses, "completed"),
        failed_steps=_count_steps_by_status(step_responses, "failed"),
        latest_step=step_responses[-1] if step_responses else None,
        workflow_started_at=workflow_started_at,
        workflow_completed_at=workflow_completed_at,
        workflow_duration_seconds=_duration_seconds(
            workflow_started_at,
            workflow_completed_at,
        ),
    )


def _encode_research_list_cursor(run: ResearchRun) -> str:
    payload = {
        "created_at": _as_utc(run.created_at).isoformat(),
        "run_id": str(UUID(run.id)),
    }
    raw_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw_payload).decode().rstrip("=")


def _decode_research_list_cursor(cursor: str) -> ResearchRunListCursor:
    try:
        padded_cursor = cursor + ("=" * (-len(cursor) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded_cursor.encode()).decode())
        created_at = datetime.fromisoformat(payload["created_at"])
        run_id = str(UUID(payload["run_id"]))
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        binascii.Error,
    ) as exc:
        raise ValueError("Invalid research list cursor.") from exc

    return ResearchRunListCursor(created_at=_as_utc(created_at), run_id=run_id)


def _duration_seconds(
    created_at: datetime | None,
    completed_at: datetime | None,
) -> float | None:
    if created_at is None or completed_at is None:
        return None

    created_at_utc = _as_utc(created_at)
    completed_at_utc = _as_utc(completed_at)
    return max((completed_at_utc - created_at_utc).total_seconds(), 0.0)


def _count_steps_by_status(steps: list[AgentStepResponse], status_value: str) -> int:
    return sum(1 for step in steps if step.status == status_value)


def _earliest_datetime(values: Iterable[datetime | None]) -> datetime | None:
    datetimes = [value for value in values if value is not None]
    if not datetimes:
        return None
    return min(_as_utc(value) for value in datetimes)


def _latest_datetime(values: Iterable[datetime | None]) -> datetime | None:
    datetimes = [value for value in values if value is not None]
    if not datetimes:
        return None
    return max(_as_utc(value) for value in datetimes)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _agent_step_to_response(step: AgentStep) -> AgentStepResponse:
    return AgentStepResponse(
        id=step.id,
        research_run_id=step.research_run_id,
        node_name=step.node_name,
        status=step.status,
        message=step.message,
        error_message=step.error_message,
        started_at=_nullable_as_utc(step.started_at),
        completed_at=_nullable_as_utc(step.completed_at),
        duration_seconds=step.duration_seconds,
        llm_provider=step.llm_provider,
        llm_model=step.llm_model,
        llm_used=step.llm_used,
        llm_fallback_reason=step.llm_fallback_reason,
    )


def _llm_call_event_to_response(event: LLMCallEvent) -> LLMCallEventResponse:
    return LLMCallEventResponse(
        id=event.id,
        research_run_id=event.research_run_id,
        node_name=event.node_name,
        task=event.task,
        status=event.status,
        llm_provider=event.llm_provider,
        llm_model=event.llm_model,
        prompt_version=event.prompt_version,
        started_at=_nullable_as_utc(event.started_at),
        completed_at=_nullable_as_utc(event.completed_at),
        duration_seconds=event.duration_seconds,
        input_tokens=event.input_tokens,
        output_tokens=event.output_tokens,
        total_tokens=event.total_tokens,
        provider_request_id=event.provider_request_id,
        error_type=event.error_type,
        error_message=event.error_message,
        fallback_used=event.fallback_used,
        fallback_reason=event.fallback_reason,
    )


def _llm_usage_summary_to_response(
    run: ResearchRun,
    events: list[LLMCallEvent],
) -> LLMUsageSummaryResponse:
    return LLMUsageSummaryResponse(
        run_id=UUID(run.id),
        status=run.status,
        **summarize_llm_usage(events),
    )


def _nullable_as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return _as_utc(value)
