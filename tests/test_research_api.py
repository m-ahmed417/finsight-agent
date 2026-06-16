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
            compliance_status=graph_result.get("compliance_status"),
            report_quality_status=graph_result.get("report_quality_status"),
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
            "warnings": [
                {
                    "code": "report_quality_warning",
                    "message": "Report section is missing source_id citations.",
                    "severity": "warning",
                    "details": {"validator_code": "missing_section_citation"},
                    "source_id": "latest_10k",
                }
            ],
            "errors": [],
            "sources": [
                {
                    "source_id": "sec_company_facts",
                    "source_type": "sec_company_facts",
                    "label": "SEC company facts",
                    "publisher": "U.S. Securities and Exchange Commission",
                    "cik": "0000320193",
                    "company_name": "Apple Inc.",
                    "ticker": "AAPL",
                    "url": (
                        "https://data.sec.gov/api/xbrl/companyfacts/"
                        "CIK0000320193.json"
                    ),
                    "retrieved_at": "2026-06-15T10:00:00+00:00",
                    "metric_fiscal_years": [2023, 2024],
                    "xbrl_tags_used": [
                        "RevenueFromContractWithCustomerExcludingAssessedTax"
                    ],
                    "cache_status": "hit",
                }
            ],
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
    assert body["compliance_status"] == "allowed"
    assert body["report_quality_status"] == "passed"
    assert body["financial_metrics"]["periods"][0]["revenue"] == 1250000000
    assert body["filing_text_excerpt"] == "Risk factor text from latest 10-K."
    assert body["risk_factors"] == [{"form": "10-K", "text": "Risk factor text."}]
    assert body["risk_themes"] == [{"title": "Competitive pressure"}]
    assert body["research_insights"]["bull_case"] == [{"title": "Revenue growth"}]
    assert body["report"] == "# FinSight Research Brief: Apple Inc. (AAPL)"
    assert body["warnings"] == [
        {
            "code": "report_quality_warning",
            "message": "Report section is missing source_id citations.",
            "severity": "warning",
            "details": {"validator_code": "missing_section_citation"},
            "source_id": "latest_10k",
        }
    ]
    assert body["errors"] == []
    assert len(body["sources"]) == 1
    source = body["sources"][0]
    assert source["source_id"] == "sec_company_facts"
    assert source["source_type"] == "sec_company_facts"
    assert source["label"] == "SEC company facts"
    assert source["company_name"] == "Apple Inc."
    assert source["metric_fiscal_years"] == [2023, 2024]
    assert source["xbrl_tags_used"] == [
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    ]
    assert source["cache_status"] == "hit"
    assert graph_runner.invocations == [{"user_query": "AAPL"}]
    assert repository.created_runs[0]["query"] == "AAPL"
    assert repository.created_runs[0]["status"] == "completed"


def test_post_research_persists_normalized_graph_result(client: TestClient) -> None:
    repository = FakeResearchRepository()
    graph_runner = FakeGraphRunner(
        {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "compliance_status": "allowed",
            "report_quality_status": "passed",
            "final_report": "# FinSight Research Brief: Apple Inc. (AAPL)",
            "financial_metrics": {"periods": []},
            "warnings": [
                {
                    "code": " metric_warning ",
                    "message": "Revenue could not be extracted.",
                }
            ],
            "errors": [],
            "sources": [
                {
                    "source_id": " sec_company_facts ",
                    "source_type": "sec_company_facts",
                    "cache_status": "hit",
                }
            ],
            "agent_steps": [
                {
                    "node_name": " fetch_sec_data ",
                    "status": " completed ",
                    "message": "Fetched SEC submissions and company facts.",
                }
            ],
        }
    )
    app.dependency_overrides[get_research_graph_runner] = lambda: graph_runner
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.post("/research", json={"query": "AAPL"})

    assert response.status_code == 200
    persisted_graph_result = repository.created_runs[0]["graph_result"]
    assert persisted_graph_result["warnings"] == [
        {
            "code": "metric_warning",
            "message": "Revenue could not be extracted.",
            "severity": "warning",
        }
    ]
    assert persisted_graph_result["sources"] == [
        {
            "source_id": "sec_company_facts",
            "source_type": "sec_company_facts",
            "cache_status": "hit",
        }
    ]
    assert persisted_graph_result["agent_steps"] == [
        {
            "node_name": "fetch_sec_data",
            "status": "completed",
            "message": "Fetched SEC submissions and company facts.",
        }
    ]


def test_post_research_rejects_invalid_graph_result_before_persistence(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    graph_runner = FakeGraphRunner(
        {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "warnings": [],
            "errors": [],
            "sources": [{"source_id": " "}],
            "agent_steps": [],
        }
    )
    app.dependency_overrides[get_research_graph_runner] = lambda: graph_runner
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.post("/research", json={"query": "AAPL"})

    assert response.status_code == 500
    assert response.json()["detail"].startswith("Graph result validation failed:")
    assert "sources" in response.json()["detail"]
    assert repository.created_runs == []


@pytest.mark.parametrize(
    ("graph_result", "expected_detail_parts"),
    [
        ([], ["Graph result validation failed", "must be a mapping"]),
        (
            {"warnings": {}},
            ["Graph result validation failed", "field 'warnings' must be a list"],
        ),
        (
            {"warnings": [{"code": "metric_warning", "message": " "}]},
            ["Graph result validation failed", "'warnings' item 0", "message"],
        ),
        (
            {"errors": [{"message": "Could not confidently resolve the company."}]},
            ["Graph result validation failed", "'errors' item 0", "code"],
        ),
        (
            {"agent_steps": [{"node_name": "resolve_company", "status": " "}]},
            ["Graph result validation failed", "'agent_steps' item 0", "status"],
        ),
    ],
)
def test_post_research_rejects_invalid_graph_contract_fields_before_persistence(
    client: TestClient,
    graph_result: object,
    expected_detail_parts: list[str],
) -> None:
    repository = FakeResearchRepository()
    graph_runner = FakeGraphRunner(graph_result)
    app.dependency_overrides[get_research_graph_runner] = lambda: graph_runner
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.post("/research", json={"query": "AAPL"})

    assert response.status_code == 500
    detail = response.json()["detail"]
    for expected_part in expected_detail_parts:
        assert expected_part in detail
    assert repository.created_runs == []


def test_post_research_returns_failed_result_when_graph_has_errors(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    graph_runner = FakeGraphRunner(
        {
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
    )
    app.dependency_overrides[get_research_graph_runner] = lambda: graph_runner
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.post("/research", json={"query": "UNKNOWN"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["ticker"] is None
    assert body["company_name"] is None
    assert body["compliance_status"] is None
    assert body["report_quality_status"] is None
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
            "compliance_status": "needs_rewrite",
            "report_quality_status": "warning",
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
    assert body["compliance_status"] == "needs_rewrite"
    assert body["report_quality_status"] == "warning"
    assert body["filing_text_excerpt"] == "Risk factor text from latest 10-K."
    assert body["risk_themes"] == [{"title": "Competitive pressure"}]
    assert body["research_insights"]["bear_case"] == [{"title": "Competitive pressure"}]


def test_get_research_preserves_typed_output_metadata_from_stored_run(
    client: TestClient,
) -> None:
    repository = FakeResearchRepository()
    graph_runner = FakeGraphRunner(
        {
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
    )
    app.dependency_overrides[get_research_graph_runner] = lambda: graph_runner
    app.dependency_overrides[get_research_repository] = lambda: repository

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
    graph_runner = FakeGraphRunner(
        {
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
    )
    app.dependency_overrides[get_research_graph_runner] = lambda: graph_runner
    app.dependency_overrides[get_research_repository] = lambda: repository

    response = client.post("/research", json={"query": "UNKNOWN"})

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


def test_research_openapi_uses_typed_output_schemas(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi = response.json()
    schemas = openapi["components"]["schemas"]
    research_properties = schemas["ResearchResponse"]["properties"]
    steps_response_schema = openapi["paths"]["/research/{run_id}/steps"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]

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
