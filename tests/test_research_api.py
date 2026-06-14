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
            filing_text_excerpt=(
                graph_result.get("filing_text", "")[:2000]
                if graph_result.get("filing_text")
                else None
            ),
            risk_factors_json=graph_result.get("risk_factors", []),
            risk_themes_json=graph_result.get("risk_themes", []),
            research_insights_json=graph_result.get("research_insights"),
            warnings_json=graph_result.get("warnings", []),
            errors_json=graph_result.get("errors", []),
            sources_json=graph_result.get("sources", []),
            agent_steps=graph_result.get("agent_steps", []),
        )
        self.runs[run_id] = run
        return run

    def get_by_id(self, run_id: UUID) -> SimpleNamespace | None:
        return self.runs.get(run_id)

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
    assert body["filing_text_excerpt"] == "Risk factor text from latest 10-K."
    assert body["risk_factors"] == [{"form": "10-K", "text": "Risk factor text."}]
    assert body["risk_themes"] == [{"title": "Competitive pressure"}]
    assert body["research_insights"]["bull_case"] == [{"title": "Revenue growth"}]
    assert body["report"] == "# FinSight Research Brief: Apple Inc. (AAPL)"
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
    assert body["filing_text_excerpt"] == "Risk factor text from latest 10-K."
    assert body["risk_themes"] == [{"title": "Competitive pressure"}]
    assert body["research_insights"]["bear_case"] == [{"title": "Competitive pressure"}]


def test_get_research_steps_returns_stored_steps(client: TestClient) -> None:
    repository = FakeResearchRepository()
    graph_runner = FakeGraphRunner(
        {
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
    )
    app.dependency_overrides[get_research_graph_runner] = lambda: graph_runner
    app.dependency_overrides[get_research_repository] = lambda: repository

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
