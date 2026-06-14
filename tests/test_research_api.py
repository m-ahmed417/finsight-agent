from collections.abc import Iterator
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from finsight_agent.app.api.dependencies import (
    get_research_graph_runner,
    get_research_repository,
)
from finsight_agent.app.main import app


class FakeGraphRunner:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.invocations: list[dict] = []

    def invoke(self, state: dict) -> dict:
        self.invocations.append(state)
        return self.result


class FakeResearchRepository:
    def __init__(self) -> None:
        self.created_runs: list[dict] = []
        self.runs: dict[UUID, SimpleNamespace] = {}

    def create_from_graph_result(
        self,
        *,
        run_id: UUID,
        query: str,
        status: str,
        graph_result: dict,
    ) -> SimpleNamespace:
        self.created_runs.append(
            {
                "run_id": run_id,
                "query": query,
                "status": status,
                "graph_result": graph_result,
            }
        )
        run = SimpleNamespace(
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
        )
        self.runs[run_id] = run
        return run

    def get_by_id(self, run_id: UUID) -> SimpleNamespace | None:
        return self.runs.get(run_id)


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_post_research_returns_completed_result(client: TestClient) -> None:
    repository = FakeResearchRepository()
    graph_runner = FakeGraphRunner(
        {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "financial_metrics": {"periods": [{"fy": 2024, "revenue": 1250000000}]},
            "warnings": [],
            "errors": [],
            "sources": [],
        }
    )
    app.dependency_overrides[get_research_graph_runner] = lambda: graph_runner
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.post("/research", json={"query": "AAPL"})

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"]
    assert body["status"] == "completed"
    assert body["ticker"] == "AAPL"
    assert body["company_name"] == "Apple Inc."
    assert body["financial_metrics"]["periods"][0]["revenue"] == 1250000000
    assert body["report"] is None
    assert body["warnings"] == []
    assert body["errors"] == []
    assert graph_runner.invocations == [{"user_query": "AAPL"}]
    assert repository.created_runs[0]["query"] == "AAPL"
    assert repository.created_runs[0]["status"] == "completed"


def test_post_research_returns_failed_result_when_graph_has_errors(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    graph_runner = FakeGraphRunner(
        {
            "ticker": None,
            "company_name": None,
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
    )
    app.dependency_overrides[get_research_graph_runner] = lambda: graph_runner
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.post("/research", json={"query": "UNKNOWN"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["ticker"] is None
    assert body["company_name"] is None
    assert body["financial_metrics"] is None
    assert body["errors"][0]["code"] == "company_not_found"
    assert repository.created_runs[0]["status"] == "failed"


def test_post_research_rejects_empty_query(client: TestClient) -> None:
    graph_runner = FakeGraphRunner({})
    app.dependency_overrides[get_research_graph_runner] = lambda: graph_runner
    app.dependency_overrides[get_research_repository] = lambda: FakeResearchRepository()

    response = client.post("/research", json={"query": "   "})

    assert response.status_code == 422


def test_post_research_rejects_missing_query(client: TestClient) -> None:
    graph_runner = FakeGraphRunner({})
    app.dependency_overrides[get_research_graph_runner] = lambda: graph_runner
    app.dependency_overrides[get_research_repository] = lambda: FakeResearchRepository()

    response = client.post("/research", json={})

    assert response.status_code == 422


def test_get_research_returns_stored_run(client: TestClient) -> None:
    repository = FakeResearchRepository()
    graph_runner = FakeGraphRunner(
        {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "financial_metrics": {"periods": [{"fy": 2024, "revenue": 1250000000}]},
            "warnings": [],
            "errors": [],
            "sources": [],
        }
    )
    app.dependency_overrides[get_research_graph_runner] = lambda: graph_runner
    app.dependency_overrides[get_research_repository] = lambda: repository

    post_response = client.post("/research", json={"query": "AAPL"})
    run_id = post_response.json()["run_id"]

    get_response = client.get(f"/research/{run_id}")

    assert get_response.status_code == 200
    body = get_response.json()
    assert body["run_id"] == run_id
    assert body["query"] == "AAPL"
    assert body["status"] == "completed"
    assert body["ticker"] == "AAPL"


def test_get_research_returns_404_for_unknown_run_id(client: TestClient) -> None:
    repository = FakeResearchRepository()
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.get(f"/research/{uuid4()}")

    assert response.status_code == 404
