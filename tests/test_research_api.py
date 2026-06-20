from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from finsight_agent.app.api.dependencies import (
    get_research_job_executor,
    get_research_repository,
)
from finsight_agent.app.main import app

DEFAULT_CREATED_AT = datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)
DEFAULT_COMPLETED_AT = datetime(2026, 6, 16, 13, 2, 30, tzinfo=timezone.utc)


class FakeResearchRepository:
    def __init__(self) -> None:
        self.pending_runs: list[dict] = []
        self.running_run_ids: list[UUID] = []
        self.completed_updates: list[dict] = []
        self.failed_graph_updates: list[dict] = []
        self.failed_updates: list[dict] = []
        self.list_recent_calls: list[dict] = []
        self.runs: dict[UUID, SimpleNamespace] = {}

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
        run = _make_run(
            run_id=run_id,
            query=query,
            status="queued",
            retried_from_run_id=retried_from_run_id,
        )
        self.runs[run_id] = run
        return run

    def mark_running(self, run_id: UUID) -> SimpleNamespace | None:
        self.running_run_ids.append(run_id)
        run = self.runs.get(run_id)
        if run is None:
            return None
        run.status = "running"
        return run

    def mark_completed_from_graph_result(
        self,
        run_id: UUID,
        *,
        graph_result: dict,
    ) -> SimpleNamespace:
        self.completed_updates.append({"run_id": run_id, "graph_result": graph_result})
        return self._update_from_graph_result(
            run_id=run_id,
            status="completed",
            graph_result=graph_result,
        )

    def mark_failed_from_graph_result(
        self,
        run_id: UUID,
        *,
        graph_result: dict,
    ) -> SimpleNamespace:
        self.failed_graph_updates.append({"run_id": run_id, "graph_result": graph_result})
        return self._update_from_graph_result(
            run_id=run_id,
            status="failed",
            graph_result=graph_result,
        )

    def mark_failed(self, run_id: UUID, *, error: str) -> SimpleNamespace:
        self.failed_updates.append({"run_id": run_id, "error": error})
        run = self.runs[run_id]
        run.status = "failed"
        run.errors_json = [
            {
                "code": "research_run_failed",
                "message": error,
                "severity": "error",
            }
        ]
        return run

    def get_by_id(self, run_id: UUID) -> SimpleNamespace | None:
        return self.runs.get(run_id)

    def list_recent_runs(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
        before: object | None = None,
    ) -> list[SimpleNamespace]:
        self.list_recent_calls.append(
            {"status": status, "limit": limit, "before": before}
        )
        runs = list(self.runs.values())
        if status is not None:
            runs = [run for run in runs if run.status == status]
        if before is not None:
            runs = [
                run
                for run in runs
                if (run.created_at, run.id) < (before.created_at, before.run_id)
            ]

        return sorted(
            runs,
            key=lambda run: (run.created_at, run.id),
            reverse=True,
        )[:limit]

    def list_retry_chain(self, run_id: UUID) -> list[SimpleNamespace]:
        run = self.runs.get(run_id)
        if run is None:
            return []

        root = run
        seen_ids = {root.id}
        while root.retried_from_run_id is not None:
            parent = self.runs.get(UUID(root.retried_from_run_id))
            if parent is None or parent.id in seen_ids:
                break
            root = parent
            seen_ids.add(root.id)

        chain_by_id = {root.id: root}
        frontier = {root.id}
        while frontier:
            children = [
                candidate
                for candidate in self.runs.values()
                if candidate.retried_from_run_id in frontier
                and candidate.id not in chain_by_id
            ]
            frontier = {child.id for child in children}
            chain_by_id.update({child.id: child for child in children})

        return sorted(
            chain_by_id.values(),
            key=lambda chain_run: (chain_run.created_at, chain_run.id),
        )

    def get_steps_for_run(self, run_id: UUID) -> list[SimpleNamespace]:
        run = self.runs.get(run_id)
        if run is None:
            return []
        return [
            SimpleNamespace(
                id=index,
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
            for index, step in enumerate(run.agent_steps, start=1)
        ]

    def get_llm_call_events_for_run(self, run_id: UUID) -> list[SimpleNamespace]:
        run = self.runs.get(run_id)
        if run is None:
            return []
        return [
            SimpleNamespace(
                id=index,
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
            for index, event in enumerate(run.llm_call_events, start=1)
        ]

    def _update_from_graph_result(
        self,
        *,
        run_id: UUID,
        status: str,
        graph_result: dict,
    ) -> SimpleNamespace:
        existing = self.runs[run_id]
        run = _make_run(
            run_id=run_id,
            query=existing.query,
            status=status,
            graph_result=graph_result,
            retried_from_run_id=(
                UUID(existing.retried_from_run_id)
                if existing.retried_from_run_id is not None
                else None
            ),
        )
        self.runs[run_id] = run
        return run


class FakeResearchJobExecutor:
    def __init__(
        self,
        *,
        repository: FakeResearchRepository,
        graph_result: dict | None = None,
    ) -> None:
        self.repository = repository
        self.graph_result = graph_result
        self.invocations: list[dict] = []

    def __call__(self, *, run_id: UUID, query: str) -> None:
        self.invocations.append({"run_id": run_id, "query": query})
        if self.graph_result is None:
            return

        self.repository.mark_running(run_id)
        if self.graph_result.get("errors", []):
            self.repository.mark_failed_from_graph_result(
                run_id,
                graph_result=self.graph_result,
            )
            return

        self.repository.mark_completed_from_graph_result(
            run_id,
            graph_result=self.graph_result,
        )


def _make_run(
    *,
    run_id: UUID,
    query: str,
    status: str,
    graph_result: dict | None = None,
    created_at: datetime = DEFAULT_CREATED_AT,
    retried_from_run_id: UUID | None = None,
) -> SimpleNamespace:
    result = graph_result or {}
    return SimpleNamespace(
        id=str(run_id),
        query=query,
        status=status,
        retried_from_run_id=(
            str(retried_from_run_id) if retried_from_run_id is not None else None
        ),
        created_at=created_at,
        completed_at=(
            DEFAULT_COMPLETED_AT if status in {"completed", "failed"} else None
        ),
        ticker=result.get("ticker"),
        company_name=result.get("company_name"),
        compliance_status=result.get("compliance_status"),
        report_quality_status=result.get("report_quality_status"),
        final_report=result.get("final_report"),
        financial_metrics_json=result.get("financial_metrics"),
        filing_text_excerpt=(
            result.get("filing_text", "")[:2000] if result.get("filing_text") else None
        ),
        risk_factors_json=result.get("risk_factors", []),
        risk_themes_json=result.get("risk_themes", []),
        research_insights_json=result.get("research_insights"),
        warnings_json=result.get("warnings", []),
        errors_json=result.get("errors", []),
        sources_json=result.get("sources", []),
        agent_steps=result.get("agent_steps", []),
        llm_call_events=result.get("llm_call_events", []),
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_post_research_queues_run_and_schedules_background_job(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    job_executor = FakeResearchJobExecutor(repository=repository)
    app.dependency_overrides[get_research_repository] = lambda: repository
    app.dependency_overrides[get_research_job_executor] = lambda: job_executor

    response = client.post("/research", json={"query": "AAPL"})

    assert response.status_code == 202
    body = response.json()
    run_id = UUID(body["run_id"])
    assert body["query"] == "AAPL"
    assert body["status"] == "queued"
    assert body["retried_from_run_id"] is None
    assert body["ticker"] is None
    assert body["company_name"] is None
    assert body["report"] is None
    assert body["financial_metrics"] is None
    assert body["warnings"] == []
    assert body["errors"] == []
    assert body["sources"] == []
    assert repository.pending_runs == [{"run_id": run_id, "query": "AAPL"}]
    assert job_executor.invocations == [{"run_id": run_id, "query": "AAPL"}]


def test_get_research_lists_recent_runs_newest_first_with_limit(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    oldest_id = uuid4()
    newest_id = uuid4()
    middle_id = uuid4()
    repository.runs[oldest_id] = _make_run(
        run_id=oldest_id,
        query="AAPL",
        status="completed",
        created_at=DEFAULT_CREATED_AT - timedelta(hours=2),
    )
    repository.runs[newest_id] = _make_run(
        run_id=newest_id,
        query="MSFT",
        status="failed",
        created_at=DEFAULT_CREATED_AT,
        graph_result={
            "ticker": "MSFT",
            "company_name": "Microsoft Corporation",
            "final_report": "# FinSight Research Brief: Microsoft Corporation (MSFT)",
            "warnings": [
                {
                    "code": "report_quality_warning",
                    "message": "Report completed with warnings.",
                }
            ],
            "errors": [
                {
                    "code": "research_run_failed",
                    "message": "Research run failed.",
                }
            ],
        },
    )
    repository.runs[middle_id] = _make_run(
        run_id=middle_id,
        query="NVDA",
        status="running",
        created_at=DEFAULT_CREATED_AT - timedelta(hours=1),
    )
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.get("/research?limit=2")

    assert response.status_code == 200
    body = response.json()
    assert body["has_more"] is True
    assert body["next_cursor"] is not None
    assert [run["run_id"] for run in body["items"]] == [
        str(newest_id),
        str(middle_id),
    ]
    assert [run["query"] for run in body["items"]] == ["MSFT", "NVDA"]
    assert body["items"][0]["ticker"] == "MSFT"
    assert body["items"][0]["company_name"] == "Microsoft Corporation"
    assert body["items"][0]["warnings_count"] == 1
    assert body["items"][0]["errors_count"] == 1
    assert body["items"][0]["has_report"] is True
    assert_summary_excludes_detail_fields(body["items"][0])
    assert str(oldest_id) not in [run["run_id"] for run in body["items"]]
    assert repository.list_recent_calls == [
        {"status": None, "limit": 3, "before": None}
    ]


def test_get_research_lists_recent_runs_filtered_by_status(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    older_failed_id = uuid4()
    completed_id = uuid4()
    newer_failed_id = uuid4()
    repository.runs[older_failed_id] = _make_run(
        run_id=older_failed_id,
        query="AAPL",
        status="failed",
        created_at=DEFAULT_CREATED_AT - timedelta(hours=2),
    )
    repository.runs[completed_id] = _make_run(
        run_id=completed_id,
        query="MSFT",
        status="completed",
        created_at=DEFAULT_CREATED_AT - timedelta(hours=1),
    )
    repository.runs[newer_failed_id] = _make_run(
        run_id=newer_failed_id,
        query="NVDA",
        status="failed",
        created_at=DEFAULT_CREATED_AT,
        graph_result={
            "errors": [
                {
                    "code": "research_run_failed",
                    "message": "Research run failed.",
                },
                {
                    "code": "company_not_found",
                    "message": "Could not confidently resolve the company.",
                },
            ],
            "warnings": [],
        },
    )
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.get("/research?status=failed&limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["has_more"] is False
    assert body["next_cursor"] is None
    assert [run["run_id"] for run in body["items"]] == [
        str(newer_failed_id),
        str(older_failed_id),
    ]
    assert [run["status"] for run in body["items"]] == ["failed", "failed"]
    assert body["items"][0]["warnings_count"] == 0
    assert body["items"][0]["errors_count"] == 2
    assert body["items"][0]["has_report"] is False
    assert_summary_excludes_detail_fields(body["items"][0])
    assert str(completed_id) not in [run["run_id"] for run in body["items"]]
    assert repository.list_recent_calls == [
        {"status": "failed", "limit": 11, "before": None}
    ]


def test_get_research_list_uses_cursor_for_next_page(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    newest_id = uuid4()
    middle_id = uuid4()
    oldest_id = uuid4()
    repository.runs[newest_id] = _make_run(
        run_id=newest_id,
        query="AAPL",
        status="completed",
        created_at=DEFAULT_CREATED_AT,
    )
    repository.runs[middle_id] = _make_run(
        run_id=middle_id,
        query="MSFT",
        status="failed",
        created_at=DEFAULT_CREATED_AT - timedelta(hours=1),
    )
    repository.runs[oldest_id] = _make_run(
        run_id=oldest_id,
        query="NVDA",
        status="queued",
        created_at=DEFAULT_CREATED_AT - timedelta(hours=2),
    )
    app.dependency_overrides[get_research_repository] = lambda: repository

    first_response = client.get("/research?limit=2")
    next_cursor = first_response.json()["next_cursor"]
    second_response = client.get(f"/research?limit=2&cursor={next_cursor}")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert [run["run_id"] for run in first_response.json()["items"]] == [
        str(newest_id),
        str(middle_id),
    ]
    assert first_response.json()["has_more"] is True
    assert next_cursor is not None
    assert second_response.json()["items"] == [
        {
            "run_id": str(oldest_id),
            "retried_from_run_id": None,
            "query": "NVDA",
            "status": "queued",
            "created_at": (
                DEFAULT_CREATED_AT - timedelta(hours=2)
            ).isoformat().replace("+00:00", "Z"),
            "completed_at": None,
            "duration_seconds": None,
            "ticker": None,
            "company_name": None,
            "warnings_count": 0,
            "errors_count": 0,
            "has_report": False,
        }
    ]
    assert second_response.json()["has_more"] is False
    assert second_response.json()["next_cursor"] is None
    assert repository.list_recent_calls[1]["before"] is not None
    assert repository.list_recent_calls[1]["before"].run_id == str(middle_id)


def test_get_research_list_rejects_invalid_cursor(client: TestClient) -> None:
    repository = FakeResearchRepository()
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.get("/research?cursor=not-a-valid-cursor")

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid research list cursor."
    assert repository.list_recent_calls == []


def test_get_research_list_rejects_invalid_status(client: TestClient) -> None:
    repository = FakeResearchRepository()
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.get("/research?status=cancelled")

    assert response.status_code == 422
    assert repository.list_recent_calls == []


def test_get_research_list_rejects_invalid_limit(client: TestClient) -> None:
    repository = FakeResearchRepository()
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.get("/research?limit=0")

    assert response.status_code == 422
    assert repository.list_recent_calls == []


@pytest.mark.parametrize("status", ["queued", "running"])
def test_get_research_returns_in_progress_lifecycle_statuses(
    client: TestClient,
    status: str,
) -> None:
    repository = FakeResearchRepository()
    run_id = uuid4()
    repository.runs[run_id] = _make_run(run_id=run_id, query="AAPL", status=status)
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.get(f"/research/{run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == str(run_id)
    assert body["query"] == "AAPL"
    assert body["status"] == status
    assert_datetime_matches(body["created_at"], DEFAULT_CREATED_AT)
    assert body["completed_at"] is None
    assert body["duration_seconds"] is None
    assert body["ticker"] is None
    assert body["company_name"] is None
    assert body["report"] is None
    assert body["financial_metrics"] is None
    assert body["risk_factors"] == []
    assert body["risk_themes"] == []
    assert body["warnings"] == []
    assert body["errors"] == []
    assert body["sources"] == []


def test_post_research_background_job_can_complete_run(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    graph_result = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "compliance_status": "allowed",
        "report_quality_status": "passed",
        "final_report": "# FinSight Research Brief: Apple Inc. (AAPL)",
        "financial_metrics": {"periods": [{"fy": 2024, "revenue": 1250000000}]},
        "filing_text": "Risk factor text from latest 10-K.",
        "risk_factors": [{"form": "10-K", "text": "Risk factor text."}],
        "risk_themes": [{"title": "Competitive pressure"}],
        "research_insights": {
            "bull_case": [{"title": "Revenue growth"}],
            "bear_case": [{"title": "Competitive pressure"}],
            "open_questions": [],
        },
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
    job_executor = FakeResearchJobExecutor(
        repository=repository,
        graph_result=graph_result,
    )
    app.dependency_overrides[get_research_repository] = lambda: repository
    app.dependency_overrides[get_research_job_executor] = lambda: job_executor

    post_response = client.post("/research", json={"query": "AAPL"})
    run_id = post_response.json()["run_id"]
    get_response = client.get(f"/research/{run_id}")

    assert post_response.status_code == 202
    assert post_response.json()["status"] == "queued"
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["run_id"] == run_id
    assert body["query"] == "AAPL"
    assert body["status"] == "completed"
    assert_datetime_matches(body["created_at"], DEFAULT_CREATED_AT)
    assert_datetime_matches(body["completed_at"], DEFAULT_COMPLETED_AT)
    assert body["duration_seconds"] == 150.0
    assert body["ticker"] == "AAPL"
    assert body["company_name"] == "Apple Inc."
    assert body["compliance_status"] == "allowed"
    assert body["report_quality_status"] == "passed"
    assert body["financial_metrics"]["periods"][0]["revenue"] == 1250000000
    assert body["filing_text_excerpt"] == "Risk factor text from latest 10-K."
    assert body["risk_factors"] == [{"form": "10-K", "text": "Risk factor text."}]
    assert body["risk_themes"] == [{"title": "Competitive pressure"}]
    assert body["research_insights"]["bear_case"] == [{"title": "Competitive pressure"}]
    assert body["report"] == "# FinSight Research Brief: Apple Inc. (AAPL)"
    assert repository.running_run_ids == [UUID(run_id)]
    assert repository.completed_updates[0]["run_id"] == UUID(run_id)


def test_post_research_background_job_can_fail_run_from_graph_errors(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    graph_result = {
        "ticker": None,
        "company_name": None,
        "compliance_status": None,
        "report_quality_status": None,
        "financial_metrics": None,
        "warnings": [],
        "errors": [
            {
                "code": "company_not_found",
                "message": "Could not confidently resolve the company.",
                "severity": "error",
            }
        ],
        "sources": [],
    }
    job_executor = FakeResearchJobExecutor(
        repository=repository,
        graph_result=graph_result,
    )
    app.dependency_overrides[get_research_repository] = lambda: repository
    app.dependency_overrides[get_research_job_executor] = lambda: job_executor

    post_response = client.post("/research", json={"query": "UNKNOWN"})
    run_id = post_response.json()["run_id"]
    get_response = client.get(f"/research/{run_id}")

    assert post_response.status_code == 202
    assert post_response.json()["status"] == "queued"
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["status"] == "failed"
    assert body["ticker"] is None
    assert body["company_name"] is None
    assert body["compliance_status"] is None
    assert body["report_quality_status"] is None
    assert body["financial_metrics"] is None
    assert body["errors"][0]["code"] == "company_not_found"
    assert repository.failed_graph_updates[0]["run_id"] == UUID(run_id)


def test_post_research_retry_creates_new_queued_run_from_failed_run(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    failed_run_id = uuid4()
    repository.runs[failed_run_id] = _make_run(
        run_id=failed_run_id,
        query="AAPL",
        status="failed",
        graph_result={
            "errors": [
                {
                    "code": "research_run_stale",
                    "message": "Research run was marked failed.",
                    "severity": "error",
                }
            ],
            "warnings": [],
            "sources": [],
        },
    )
    job_executor = FakeResearchJobExecutor(repository=repository)
    app.dependency_overrides[get_research_repository] = lambda: repository
    app.dependency_overrides[get_research_job_executor] = lambda: job_executor

    response = client.post(f"/research/{failed_run_id}/retry")

    assert response.status_code == 202
    body = response.json()
    retry_run_id = UUID(body["run_id"])
    assert retry_run_id != failed_run_id
    assert body["query"] == "AAPL"
    assert body["status"] == "queued"
    assert body["retried_from_run_id"] == str(failed_run_id)
    assert body["completed_at"] is None
    assert body["duration_seconds"] is None
    assert body["errors"] == []
    assert repository.runs[failed_run_id].status == "failed"
    assert repository.pending_runs == [
        {
            "run_id": retry_run_id,
            "query": "AAPL",
            "retried_from_run_id": failed_run_id,
        }
    ]
    assert job_executor.invocations == [{"run_id": retry_run_id, "query": "AAPL"}]


def test_get_research_retries_returns_retry_chain_from_any_run(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    original_id = uuid4()
    first_retry_id = uuid4()
    second_retry_id = uuid4()
    unrelated_id = uuid4()
    repository.runs[original_id] = _make_run(
        run_id=original_id,
        query="AAPL",
        status="failed",
        created_at=DEFAULT_CREATED_AT - timedelta(hours=3),
    )
    repository.runs[first_retry_id] = _make_run(
        run_id=first_retry_id,
        query="AAPL",
        status="failed",
        created_at=DEFAULT_CREATED_AT - timedelta(hours=2),
        retried_from_run_id=original_id,
    )
    repository.runs[second_retry_id] = _make_run(
        run_id=second_retry_id,
        query="AAPL",
        status="queued",
        created_at=DEFAULT_CREATED_AT - timedelta(hours=1),
        retried_from_run_id=first_retry_id,
    )
    repository.runs[unrelated_id] = _make_run(
        run_id=unrelated_id,
        query="MSFT",
        status="queued",
        created_at=DEFAULT_CREATED_AT,
    )
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.get(f"/research/{first_retry_id}/retries")

    assert response.status_code == 200
    body = response.json()
    assert [run["run_id"] for run in body] == [
        str(original_id),
        str(first_retry_id),
        str(second_retry_id),
    ]
    assert [run["retried_from_run_id"] for run in body] == [
        None,
        str(original_id),
        str(first_retry_id),
    ]
    assert str(unrelated_id) not in [run["run_id"] for run in body]


def test_get_research_retries_returns_404_for_unknown_run_id(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.get(f"/research/{uuid4()}/retries")

    assert response.status_code == 404
    assert response.json()["detail"] == "Research run not found."


def test_post_research_retry_returns_404_for_unknown_run_id(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    job_executor = FakeResearchJobExecutor(repository=repository)
    app.dependency_overrides[get_research_repository] = lambda: repository
    app.dependency_overrides[get_research_job_executor] = lambda: job_executor

    response = client.post(f"/research/{uuid4()}/retry")

    assert response.status_code == 404
    assert response.json()["detail"] == "Research run not found."
    assert repository.pending_runs == []
    assert job_executor.invocations == []


@pytest.mark.parametrize("status", ["queued", "running", "completed"])
def test_post_research_retry_returns_409_for_non_failed_run(
    client: TestClient,
    status: str,
) -> None:
    repository = FakeResearchRepository()
    run_id = uuid4()
    repository.runs[run_id] = _make_run(run_id=run_id, query="AAPL", status=status)
    job_executor = FakeResearchJobExecutor(repository=repository)
    app.dependency_overrides[get_research_repository] = lambda: repository
    app.dependency_overrides[get_research_job_executor] = lambda: job_executor

    response = client.post(f"/research/{run_id}/retry")

    assert response.status_code == 409
    assert response.json()["detail"] == "Only failed research runs can be retried."
    assert repository.pending_runs == []
    assert job_executor.invocations == []


def test_post_research_rejects_empty_query(client: TestClient) -> None:
    app.dependency_overrides[get_research_repository] = lambda: FakeResearchRepository()

    response = client.post("/research", json={"query": "   "})

    assert response.status_code == 422


def test_post_research_rejects_missing_query(client: TestClient) -> None:
    app.dependency_overrides[get_research_repository] = lambda: FakeResearchRepository()

    response = client.post("/research", json={})

    assert response.status_code == 422


def test_get_research_preserves_typed_output_metadata_from_stored_run(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    graph_result = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "compliance_status": "allowed",
        "report_quality_status": "warning",
        "final_report": "# FinSight Research Brief: Apple Inc. (AAPL)",
        "financial_metrics": {"periods": []},
        "warnings": [
            {
                "code": "report_quality_warning",
                "message": "Report quality validation completed with warnings.",
                "details": {"validator_code": "weak_section"},
                "source_id": "latest_10k",
            }
        ],
        "errors": [],
        "sources": [
            {
                "source_id": "latest_10k",
                "source_type": "sec_filing",
                "label": "Latest 10-K filing",
                "publisher": "U.S. Securities and Exchange Commission",
                "cik": "0000320193",
                "company_name": "Apple Inc.",
                "ticker": "AAPL",
                "url": "https://www.sec.gov/Archives/example.htm",
                "form": "10-K",
                "filing_date": "2024-11-01",
                "report_date": "2024-09-28",
                "accession_number": "0000320193-24-000123",
                "accession_path": "000032019324000123",
                "primary_document": "aapl-20240928.htm",
                "metadata_source_ids": ["sec_submissions"],
                "document_retrieved_at": "2026-06-15T10:01:00+00:00",
                "document_character_count": 12345,
                "extraction_status": "risk_factors_extracted",
                "extracted_sections": ["Item 1A Risk Factors"],
                "risk_factor_text_character_count": 1500,
                "cache_status": "hit",
            }
        ],
        "agent_steps": [],
    }
    job_executor = FakeResearchJobExecutor(
        repository=repository,
        graph_result=graph_result,
    )
    app.dependency_overrides[get_research_repository] = lambda: repository
    app.dependency_overrides[get_research_job_executor] = lambda: job_executor

    post_response = client.post("/research", json={"query": "AAPL"})
    run_id = post_response.json()["run_id"]
    get_response = client.get(f"/research/{run_id}")

    assert get_response.status_code == 200
    body = get_response.json()
    assert body["warnings"] == [
        {
            "code": "report_quality_warning",
            "message": "Report quality validation completed with warnings.",
            "severity": "warning",
            "details": {"validator_code": "weak_section"},
            "source_id": "latest_10k",
        }
    ]
    assert body["errors"] == []
    assert len(body["sources"]) == 1
    source = body["sources"][0]
    assert source["source_id"] == "latest_10k"
    assert source["source_type"] == "sec_filing"
    assert source["metadata_source_ids"] == ["sec_submissions"]
    assert source["document_character_count"] == 12345
    assert source["extracted_sections"] == ["Item 1A Risk Factors"]
    assert source["cache_status"] == "hit"


def test_research_response_contract_defaults_diagnostic_severities(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    graph_result = {
        "ticker": None,
        "company_name": None,
        "compliance_status": None,
        "report_quality_status": None,
        "financial_metrics": None,
        "warnings": [
            {
                "code": "metric_warning",
                "message": "Revenue could not be extracted.",
            }
        ],
        "errors": [
            {
                "code": "company_not_found",
                "message": "Could not confidently resolve the company.",
            }
        ],
        "sources": [{"source_id": "sec_submissions"}],
        "agent_steps": [],
    }
    job_executor = FakeResearchJobExecutor(
        repository=repository,
        graph_result=graph_result,
    )
    app.dependency_overrides[get_research_repository] = lambda: repository
    app.dependency_overrides[get_research_job_executor] = lambda: job_executor

    post_response = client.post("/research", json={"query": "UNKNOWN"})
    run_id = post_response.json()["run_id"]
    response = client.get(f"/research/{run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["warnings"] == [
        {
            "code": "metric_warning",
            "message": "Revenue could not be extracted.",
            "severity": "warning",
            "details": None,
        }
    ]
    assert body["errors"] == [
        {
            "code": "company_not_found",
            "message": "Could not confidently resolve the company.",
            "severity": "error",
            "details": None,
        }
    ]
    assert body["sources"][0]["source_id"] == "sec_submissions"


def test_get_research_steps_returns_stored_steps(client: TestClient) -> None:
    repository = FakeResearchRepository()
    graph_result = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "financial_metrics": {"periods": []},
        "warnings": [],
        "errors": [],
        "sources": [],
        "agent_steps": [
            {
                "node_name": "resolve_company",
                "status": "completed",
                "message": "Resolved AAPL to Apple Inc.",
                "started_at": datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc),
                "completed_at": datetime(
                    2026,
                    6,
                    16,
                    13,
                    0,
                    2,
                    tzinfo=timezone.utc,
                ),
                "duration_seconds": 2.0,
                "llm_provider": "openai",
                "llm_model": "gpt-test-model",
                "llm_used": True,
                "llm_fallback_reason": None,
            },
            {
                "node_name": "fetch_sec_data",
                "status": "completed",
                "message": "Fetched SEC submissions and company facts.",
            },
        ],
    }
    job_executor = FakeResearchJobExecutor(
        repository=repository,
        graph_result=graph_result,
    )
    app.dependency_overrides[get_research_repository] = lambda: repository
    app.dependency_overrides[get_research_job_executor] = lambda: job_executor

    post_response = client.post("/research", json={"query": "AAPL"})
    run_id = post_response.json()["run_id"]
    response = client.get(f"/research/{run_id}/steps")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 1,
            "research_run_id": run_id,
            "node_name": "resolve_company",
            "status": "completed",
            "message": "Resolved AAPL to Apple Inc.",
            "error_message": None,
            "started_at": "2026-06-16T13:00:00Z",
            "completed_at": "2026-06-16T13:00:02Z",
            "duration_seconds": 2.0,
            "llm_provider": "openai",
            "llm_model": "gpt-test-model",
            "llm_used": True,
            "llm_fallback_reason": None,
        },
        {
            "id": 2,
            "research_run_id": run_id,
            "node_name": "fetch_sec_data",
            "status": "completed",
            "message": "Fetched SEC submissions and company facts.",
            "error_message": None,
            "started_at": None,
            "completed_at": None,
            "duration_seconds": None,
            "llm_provider": None,
            "llm_model": None,
            "llm_used": None,
            "llm_fallback_reason": None,
        },
    ]


def test_get_research_llm_calls_returns_stored_model_call_audit_events(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    graph_result = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "financial_metrics": {"periods": []},
        "warnings": [],
        "errors": [],
        "sources": [],
        "agent_steps": [],
        "llm_call_events": [
            {
                "node_name": "analyze_risks",
                "task": "risk_analysis",
                "status": "completed",
                "llm_provider": "openai",
                "llm_model": "gpt-test-model",
                "prompt_version": "risk_analysis:v1",
                "started_at": datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc),
                "completed_at": datetime(
                    2026,
                    6,
                    16,
                    13,
                    0,
                    1,
                    tzinfo=timezone.utc,
                ),
                "duration_seconds": 1.0,
                "input_tokens": 120,
                "output_tokens": 42,
                "total_tokens": 162,
                "provider_request_id": "req_123",
                "fallback_used": False,
            },
            {
                "node_name": "draft_report",
                "task": "report_drafting",
                "status": "failed",
                "llm_provider": "openai",
                "llm_model": "gpt-test-model",
                "prompt_version": "report_drafting:v1",
                "started_at": datetime(2026, 6, 16, 13, 0, 2, tzinfo=timezone.utc),
                "completed_at": datetime(
                    2026,
                    6,
                    16,
                    13,
                    0,
                    3,
                    tzinfo=timezone.utc,
                ),
                "duration_seconds": 1.0,
                "provider_request_id": "req_456",
                "error_type": "LLMClientError",
                "error_message": "LLM response must contain valid JSON.",
                "fallback_used": True,
                "fallback_reason": "LLM response must contain valid JSON.",
            },
        ],
    }
    job_executor = FakeResearchJobExecutor(
        repository=repository,
        graph_result=graph_result,
    )
    app.dependency_overrides[get_research_repository] = lambda: repository
    app.dependency_overrides[get_research_job_executor] = lambda: job_executor

    post_response = client.post("/research", json={"query": "AAPL"})
    run_id = post_response.json()["run_id"]
    response = client.get(f"/research/{run_id}/llm-calls")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 1,
            "research_run_id": run_id,
            "node_name": "analyze_risks",
            "task": "risk_analysis",
            "status": "completed",
            "llm_provider": "openai",
            "llm_model": "gpt-test-model",
            "prompt_version": "risk_analysis:v1",
            "started_at": "2026-06-16T13:00:00Z",
            "completed_at": "2026-06-16T13:00:01Z",
            "duration_seconds": 1.0,
            "input_tokens": 120,
            "output_tokens": 42,
            "total_tokens": 162,
            "provider_request_id": "req_123",
            "error_type": None,
            "error_message": None,
            "fallback_used": False,
            "fallback_reason": None,
        },
        {
            "id": 2,
            "research_run_id": run_id,
            "node_name": "draft_report",
            "task": "report_drafting",
            "status": "failed",
            "llm_provider": "openai",
            "llm_model": "gpt-test-model",
            "prompt_version": "report_drafting:v1",
            "started_at": "2026-06-16T13:00:02Z",
            "completed_at": "2026-06-16T13:00:03Z",
            "duration_seconds": 1.0,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "provider_request_id": "req_456",
            "error_type": "LLMClientError",
            "error_message": "LLM response must contain valid JSON.",
            "fallback_used": True,
            "fallback_reason": "LLM response must contain valid JSON.",
        },
    ]


def test_get_research_llm_usage_returns_rollup_summary(client: TestClient) -> None:
    repository = FakeResearchRepository()
    graph_result = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "financial_metrics": {"periods": []},
        "warnings": [],
        "errors": [],
        "sources": [],
        "agent_steps": [],
        "llm_call_events": [
            {
                "node_name": "analyze_risks",
                "task": "risk_analysis",
                "status": "completed",
                "llm_provider": "openai",
                "llm_model": "gpt-test-model",
                "prompt_version": "risk_analysis:v1",
                "duration_seconds": 1.0,
                "input_tokens": 120,
                "output_tokens": 42,
                "total_tokens": 162,
                "fallback_used": False,
            },
            {
                "node_name": "draft_report",
                "task": "report_drafting",
                "status": "failed",
                "llm_provider": "openai",
                "llm_model": "gpt-test-model",
                "prompt_version": "report_drafting:v1",
                "duration_seconds": 2.5,
                "input_tokens": 300,
                "output_tokens": None,
                "total_tokens": None,
                "fallback_used": True,
                "fallback_reason": "LLM response must contain valid JSON.",
            },
            {
                "node_name": "draft_report",
                "task": "report_drafting",
                "status": "skipped",
                "prompt_version": "report_drafting:v1",
                "fallback_used": True,
                "fallback_reason": "No report-drafting LLM client configured.",
            },
        ],
    }
    job_executor = FakeResearchJobExecutor(
        repository=repository,
        graph_result=graph_result,
    )
    app.dependency_overrides[get_research_repository] = lambda: repository
    app.dependency_overrides[get_research_job_executor] = lambda: job_executor

    post_response = client.post("/research", json={"query": "AAPL"})
    run_id = post_response.json()["run_id"]
    response = client.get(f"/research/{run_id}/llm-usage")

    assert response.status_code == 200
    assert response.json() == {
        "run_id": run_id,
        "status": "completed",
        "total_calls": 3,
        "completed_calls": 1,
        "failed_calls": 1,
        "skipped_calls": 1,
        "fallback_count": 2,
        "total_duration_seconds": 3.5,
        "total_input_tokens": 420,
        "total_output_tokens": 42,
        "total_tokens": 162,
        "providers": ["openai"],
        "models": ["gpt-test-model"],
    }


def test_get_research_progress_returns_stored_step_summary(client: TestClient) -> None:
    repository = FakeResearchRepository()
    graph_result = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "financial_metrics": {"periods": []},
        "warnings": [],
        "errors": [],
        "sources": [],
        "agent_steps": [
            {
                "node_name": "resolve_company",
                "status": "completed",
                "message": "Resolved AAPL to Apple Inc.",
                "started_at": datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc),
                "completed_at": datetime(
                    2026,
                    6,
                    16,
                    13,
                    0,
                    1,
                    tzinfo=timezone.utc,
                ),
                "duration_seconds": 1.0,
                "llm_provider": "openai",
                "llm_model": "gpt-test-model",
                "llm_used": True,
                "llm_fallback_reason": None,
            },
            {
                "node_name": "fetch_sec_data",
                "status": "completed",
                "message": "Fetched SEC submissions and company facts.",
                "started_at": datetime(
                    2026,
                    6,
                    16,
                    13,
                    0,
                    1,
                    tzinfo=timezone.utc,
                ),
                "completed_at": datetime(
                    2026,
                    6,
                    16,
                    13,
                    0,
                    3,
                    tzinfo=timezone.utc,
                ),
                "duration_seconds": 2.0,
                "llm_provider": "openai",
                "llm_model": "gpt-test-model",
                "llm_used": True,
                "llm_fallback_reason": None,
            },
        ],
    }
    job_executor = FakeResearchJobExecutor(
        repository=repository,
        graph_result=graph_result,
    )
    app.dependency_overrides[get_research_repository] = lambda: repository
    app.dependency_overrides[get_research_job_executor] = lambda: job_executor

    post_response = client.post("/research", json={"query": "AAPL"})
    run_id = post_response.json()["run_id"]
    response = client.get(f"/research/{run_id}/progress")

    assert response.status_code == 200
    assert response.json() == {
        "run_id": run_id,
        "status": "completed",
        "total_steps": 2,
        "completed_steps": 2,
        "failed_steps": 0,
        "workflow_started_at": "2026-06-16T13:00:00Z",
        "workflow_completed_at": "2026-06-16T13:00:03Z",
        "workflow_duration_seconds": 3.0,
        "latest_step": {
            "id": 2,
            "research_run_id": run_id,
            "node_name": "fetch_sec_data",
            "status": "completed",
            "message": "Fetched SEC submissions and company facts.",
            "error_message": None,
            "started_at": "2026-06-16T13:00:01Z",
            "completed_at": "2026-06-16T13:00:03Z",
            "duration_seconds": 2.0,
            "llm_provider": "openai",
            "llm_model": "gpt-test-model",
            "llm_used": True,
            "llm_fallback_reason": None,
        },
    }


def test_get_research_progress_returns_empty_summary_for_queued_run(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    job_executor = FakeResearchJobExecutor(repository=repository)
    app.dependency_overrides[get_research_repository] = lambda: repository
    app.dependency_overrides[get_research_job_executor] = lambda: job_executor

    post_response = client.post("/research", json={"query": "AAPL"})
    run_id = post_response.json()["run_id"]
    response = client.get(f"/research/{run_id}/progress")

    assert response.status_code == 200
    assert response.json() == {
        "run_id": run_id,
        "status": "queued",
        "total_steps": 0,
        "completed_steps": 0,
        "failed_steps": 0,
        "workflow_started_at": None,
        "workflow_completed_at": None,
        "workflow_duration_seconds": None,
        "latest_step": None,
    }


def test_research_openapi_uses_typed_output_schemas(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi = response.json()
    schemas = openapi["components"]["schemas"]
    research_properties = schemas["ResearchResponse"]["properties"]
    list_response_schema = openapi["paths"]["/research"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    list_operation = openapi["paths"]["/research"]["get"]
    post_response_schema = openapi["paths"]["/research"]["post"]["responses"]["202"][
        "content"
    ]["application/json"]["schema"]
    steps_response_schema = openapi["paths"]["/research/{run_id}/steps"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    llm_calls_response_schema = openapi["paths"]["/research/{run_id}/llm-calls"][
        "get"
    ]["responses"]["200"]["content"]["application/json"]["schema"]
    llm_usage_response_schema = openapi["paths"]["/research/{run_id}/llm-usage"][
        "get"
    ]["responses"]["200"]["content"]["application/json"]["schema"]
    progress_response_schema = openapi["paths"]["/research/{run_id}/progress"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    retry_response_schema = openapi["paths"]["/research/{run_id}/retry"]["post"][
        "responses"
    ]["202"]["content"]["application/json"]["schema"]
    retry_chain_response_schema = openapi["paths"]["/research/{run_id}/retries"][
        "get"
    ]["responses"]["200"]["content"]["application/json"]["schema"]

    assert list_response_schema["$ref"] == "#/components/schemas/ResearchRunListResponse"
    assert "compact" in list_operation["summary"].lower()
    assert "paginated" in list_operation["description"].lower()
    assert post_response_schema["$ref"] == "#/components/schemas/ResearchResponse"
    assert retry_response_schema["$ref"] == "#/components/schemas/ResearchResponse"
    assert retry_chain_response_schema["items"]["$ref"] == (
        "#/components/schemas/ResearchResponse"
    )
    assert research_properties["status"]["enum"] == [
        "queued",
        "running",
        "completed",
        "failed",
    ]
    assert_openapi_datetime_property(research_properties["created_at"])
    assert_openapi_datetime_property(research_properties["completed_at"])
    assert_openapi_number_property(research_properties["duration_seconds"])
    assert_openapi_uuid_property(research_properties["retried_from_run_id"])
    assert "retry" in research_properties["retried_from_run_id"]["description"].lower()
    assert "polling" in research_properties["status"]["description"].lower()
    assert research_properties["warnings"]["items"]["$ref"] == (
        "#/components/schemas/ResearchWarning"
    )
    assert research_properties["errors"]["items"]["$ref"] == (
        "#/components/schemas/ResearchError"
    )
    assert research_properties["sources"]["items"]["$ref"] == (
        "#/components/schemas/SourceMetadata"
    )
    assert steps_response_schema["items"]["$ref"] == (
        "#/components/schemas/AgentStepResponse"
    )
    assert llm_calls_response_schema["items"]["$ref"] == (
        "#/components/schemas/LLMCallEventResponse"
    )
    assert llm_usage_response_schema["$ref"] == (
        "#/components/schemas/LLMUsageSummaryResponse"
    )
    assert progress_response_schema["$ref"] == (
        "#/components/schemas/ResearchProgressResponse"
    )
    assert schemas["AgentStepResponse"]["properties"]["node_name"]["type"] == "string"
    assert schemas["AgentStepResponse"]["properties"]["status"]["type"] == "string"
    assert_openapi_datetime_property(
        schemas["AgentStepResponse"]["properties"]["started_at"]
    )
    assert_openapi_datetime_property(
        schemas["AgentStepResponse"]["properties"]["completed_at"]
    )
    assert_openapi_number_property(
        schemas["AgentStepResponse"]["properties"]["duration_seconds"]
    )
    assert schemas["AgentStepResponse"]["properties"]["llm_provider"]["anyOf"][0][
        "type"
    ] == "string"
    assert schemas["AgentStepResponse"]["properties"]["llm_model"]["anyOf"][0][
        "type"
    ] == "string"
    assert schemas["AgentStepResponse"]["properties"]["llm_used"]["anyOf"][0][
        "type"
    ] == "boolean"
    assert schemas["AgentStepResponse"]["properties"]["llm_fallback_reason"]["anyOf"][
        0
    ]["type"] == "string"
    llm_call_properties = schemas["LLMCallEventResponse"]["properties"]
    assert llm_call_properties["node_name"]["type"] == "string"
    assert llm_call_properties["task"]["type"] == "string"
    assert llm_call_properties["status"]["type"] == "string"
    assert llm_call_properties["llm_provider"]["anyOf"][0]["type"] == "string"
    assert llm_call_properties["llm_model"]["anyOf"][0]["type"] == "string"
    assert llm_call_properties["prompt_version"]["anyOf"][0]["type"] == "string"
    assert_openapi_datetime_property(llm_call_properties["started_at"])
    assert_openapi_datetime_property(llm_call_properties["completed_at"])
    assert_openapi_number_property(llm_call_properties["duration_seconds"])
    assert_openapi_integer_property(llm_call_properties["input_tokens"])
    assert_openapi_integer_property(llm_call_properties["output_tokens"])
    assert_openapi_integer_property(llm_call_properties["total_tokens"])
    assert llm_call_properties["fallback_used"]["anyOf"][0]["type"] == "boolean"
    llm_usage_properties = schemas["LLMUsageSummaryResponse"]["properties"]
    assert_openapi_uuid_property(llm_usage_properties["run_id"])
    assert llm_usage_properties["status"]["enum"] == [
        "queued",
        "running",
        "completed",
        "failed",
    ]
    assert_openapi_integer_property(llm_usage_properties["total_calls"])
    assert_openapi_integer_property(llm_usage_properties["completed_calls"])
    assert_openapi_integer_property(llm_usage_properties["failed_calls"])
    assert_openapi_integer_property(llm_usage_properties["skipped_calls"])
    assert_openapi_integer_property(llm_usage_properties["fallback_count"])
    assert_openapi_number_property(llm_usage_properties["total_duration_seconds"])
    assert_openapi_integer_property(llm_usage_properties["total_input_tokens"])
    assert_openapi_integer_property(llm_usage_properties["total_output_tokens"])
    assert_openapi_integer_property(llm_usage_properties["total_tokens"])
    source_properties = schemas["SourceMetadata"]["properties"]
    assert {
        "cache_status",
        "cache_key",
        "cache_age_seconds",
        "cache_ttl_seconds",
        "cache_expires_at",
        "cache_stale",
        "document_cache_status",
        "document_cache_key",
        "document_cache_age_seconds",
        "document_cache_ttl_seconds",
        "document_cache_expires_at",
        "document_cache_stale",
    }.issubset(source_properties)
    assert {
        "SourceMetadata",
        "ResearchWarning",
        "ResearchError",
        "ResearchRunListResponse",
        "ResearchRunSummary",
        "ResearchProgressResponse",
        "AgentStepResponse",
        "LLMCallEventResponse",
        "LLMUsageSummaryResponse",
    }.issubset(schemas)
    progress_properties = schemas["ResearchProgressResponse"]["properties"]
    assert {
        "run_id",
        "status",
        "total_steps",
        "completed_steps",
        "failed_steps",
        "latest_step",
        "workflow_started_at",
        "workflow_completed_at",
        "workflow_duration_seconds",
    }.issubset(progress_properties)
    assert progress_properties["latest_step"]["anyOf"][0]["$ref"] == (
        "#/components/schemas/AgentStepResponse"
    )
    assert_openapi_datetime_property(progress_properties["workflow_started_at"])
    assert_openapi_datetime_property(progress_properties["workflow_completed_at"])
    assert_openapi_number_property(progress_properties["workflow_duration_seconds"])
    list_properties = schemas["ResearchRunListResponse"]["properties"]
    assert list_properties["items"]["items"]["$ref"] == (
        "#/components/schemas/ResearchRunSummary"
    )
    assert {"items", "next_cursor", "has_more"}.issubset(list_properties)
    assert "compact" in list_properties["items"]["description"].lower()
    assert "next page" in list_properties["next_cursor"]["description"].lower()
    assert "another page" in list_properties["has_more"]["description"].lower()
    summary_properties = schemas["ResearchRunSummary"]["properties"]
    assert {
        "run_id",
        "retried_from_run_id",
        "query",
        "status",
        "created_at",
        "completed_at",
        "duration_seconds",
        "ticker",
        "company_name",
        "warnings_count",
        "errors_count",
        "has_report",
    }.issubset(summary_properties)
    assert "warning" in summary_properties["warnings_count"]["description"].lower()
    assert "error" in summary_properties["errors_count"]["description"].lower()
    assert "final report" in summary_properties["has_report"]["description"].lower()


def test_get_research_returns_404_for_unknown_run_id(client: TestClient) -> None:
    repository = FakeResearchRepository()
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.get(f"/research/{uuid4()}")

    assert response.status_code == 404


def test_get_research_steps_returns_404_for_unknown_run_id(client: TestClient) -> None:
    repository = FakeResearchRepository()
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.get(f"/research/{uuid4()}/steps")

    assert response.status_code == 404


def test_get_research_llm_calls_returns_404_for_unknown_run_id(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.get(f"/research/{uuid4()}/llm-calls")

    assert response.status_code == 404


def test_get_research_llm_usage_returns_404_for_unknown_run_id(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.get(f"/research/{uuid4()}/llm-usage")

    assert response.status_code == 404


def test_get_research_progress_returns_404_for_unknown_run_id(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.get(f"/research/{uuid4()}/progress")

    assert response.status_code == 404


def assert_datetime_matches(value: str, expected: datetime) -> None:
    assert datetime.fromisoformat(value.replace("Z", "+00:00")) == expected


def assert_openapi_datetime_property(schema: dict) -> None:
    if schema.get("format") == "date-time":
        return

    assert any(option.get("format") == "date-time" for option in schema.get("anyOf", []))


def assert_openapi_number_property(schema: dict) -> None:
    if schema.get("type") == "number":
        return

    assert any(option.get("type") == "number" for option in schema.get("anyOf", []))


def assert_openapi_integer_property(schema: dict) -> None:
    if schema.get("type") == "integer":
        return

    assert any(option.get("type") == "integer" for option in schema.get("anyOf", []))


def assert_openapi_uuid_property(schema: dict) -> None:
    if schema.get("format") == "uuid":
        return

    assert any(option.get("format") == "uuid" for option in schema.get("anyOf", []))


def assert_summary_excludes_detail_fields(summary: dict) -> None:
    assert {
        "report",
        "financial_metrics",
        "filing_text_excerpt",
        "risk_factors",
        "risk_themes",
        "research_insights",
        "warnings",
        "errors",
        "sources",
    }.isdisjoint(summary)
