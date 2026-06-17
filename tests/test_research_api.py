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

    def create_pending_run(self, *, run_id: UUID, query: str) -> SimpleNamespace:
        self.pending_runs.append({"run_id": run_id, "query": query})
        run = _make_run(run_id=run_id, query=query, status="queued")
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
    ) -> list[SimpleNamespace]:
        self.list_recent_calls.append({"status": status, "limit": limit})
        runs = list(self.runs.values())
        if status is not None:
            runs = [run for run in runs if run.status == status]

        return sorted(
            runs,
            key=lambda run: (run.created_at, run.id),
            reverse=True,
        )[:limit]

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
            )
            for index, step in enumerate(run.agent_steps, start=1)
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
) -> SimpleNamespace:
    result = graph_result or {}
    return SimpleNamespace(
        id=str(run_id),
        query=query,
        status=status,
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
    assert [run["run_id"] for run in body] == [str(newest_id), str(middle_id)]
    assert [run["query"] for run in body] == ["MSFT", "NVDA"]
    assert str(oldest_id) not in [run["run_id"] for run in body]
    assert repository.list_recent_calls == [{"status": None, "limit": 2}]


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
    )
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.get("/research?status=failed&limit=10")

    assert response.status_code == 200
    body = response.json()
    assert [run["run_id"] for run in body] == [
        str(newer_failed_id),
        str(older_failed_id),
    ]
    assert [run["status"] for run in body] == ["failed", "failed"]
    assert str(completed_id) not in [run["run_id"] for run in body]
    assert repository.list_recent_calls == [{"status": "failed", "limit": 10}]


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
    assert body["completed_at"] is None
    assert body["duration_seconds"] is None
    assert body["errors"] == []
    assert repository.runs[failed_run_id].status == "failed"
    assert repository.pending_runs == [{"run_id": retry_run_id, "query": "AAPL"}]
    assert job_executor.invocations == [{"run_id": retry_run_id, "query": "AAPL"}]


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
        },
        {
            "id": 2,
            "research_run_id": run_id,
            "node_name": "fetch_sec_data",
            "status": "completed",
            "message": "Fetched SEC submissions and company facts.",
            "error_message": None,
        },
    ]


def test_research_openapi_uses_typed_output_schemas(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi = response.json()
    schemas = openapi["components"]["schemas"]
    research_properties = schemas["ResearchResponse"]["properties"]
    list_response_schema = openapi["paths"]["/research"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    post_response_schema = openapi["paths"]["/research"]["post"]["responses"]["202"][
        "content"
    ]["application/json"]["schema"]
    steps_response_schema = openapi["paths"]["/research/{run_id}/steps"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    retry_response_schema = openapi["paths"]["/research/{run_id}/retry"]["post"][
        "responses"
    ]["202"]["content"]["application/json"]["schema"]

    assert list_response_schema["items"]["$ref"] == "#/components/schemas/ResearchResponse"
    assert post_response_schema["$ref"] == "#/components/schemas/ResearchResponse"
    assert retry_response_schema["$ref"] == "#/components/schemas/ResearchResponse"
    assert research_properties["status"]["enum"] == [
        "queued",
        "running",
        "completed",
        "failed",
    ]
    assert_openapi_datetime_property(research_properties["created_at"])
    assert_openapi_datetime_property(research_properties["completed_at"])
    assert_openapi_number_property(research_properties["duration_seconds"])
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
    assert schemas["AgentStepResponse"]["properties"]["node_name"]["type"] == "string"
    assert schemas["AgentStepResponse"]["properties"]["status"]["type"] == "string"
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
        "AgentStepResponse",
    }.issubset(schemas)


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
