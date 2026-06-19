from datetime import datetime
import os
from typing import Any

import pytest

from finsight_agent.app.config import get_settings
from finsight_agent.app.graph.builder import build_research_graph
from finsight_agent.app.services.compliance import find_forbidden_terms
from finsight_agent.app.services.llm_client import MockLLMClient
from finsight_agent.app.services.report_generator import RESEARCH_ONLY_NOTICE
from finsight_agent.app.services.resolver_loader import build_static_company_resolver
from finsight_agent.app.services.sec_client import SECClient

AAPL_CIK = "0000320193"
CACHE_STATUSES = {"hit", "miss", "disabled"}


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_SEC_GRAPH_TESTS") != "1",
    reason="Live SEC graph smoke tests are opt-in.",
)
def test_live_sec_graph_smoke_generates_apple_research_state(tmp_path) -> None:
    get_settings.cache_clear()
    settings = get_settings()
    if _uses_placeholder_sec_user_agent(settings.sec_user_agent):
        pytest.fail(
            "Set SEC_USER_AGENT to a descriptive value before running live SEC graph tests."
        )

    sec_client = SECClient(
        user_agent=settings.sec_user_agent,
        cache_dir=tmp_path / "sec-cache",
        min_request_interval_seconds=settings.sec_request_interval_seconds,
        timeout=20.0,
    )
    graph = build_research_graph(
        resolver=build_static_company_resolver(),
        sec_client=sec_client,
        llm_client=MockLLMClient(),
    )

    result = graph.invoke({"user_query": "AAPL"})

    assert result["ticker"] == "AAPL"
    assert result["company_name"] == "Apple Inc."
    assert result["cik"] == AAPL_CIK
    assert result["errors"] == []
    assert result["compliance_status"] in {"allowed", "needs_rewrite"}
    assert result["report_quality_status"] in {"passed", "warning"}
    assert isinstance(result["final_report"], str)
    assert RESEARCH_ONLY_NOTICE in result["final_report"]
    assert find_forbidden_terms(result["final_report"]) == []

    metrics = result["financial_metrics"]
    assert isinstance(metrics, dict)
    assert isinstance(metrics.get("periods"), list)
    assert metrics["periods"]
    assert all(isinstance(period.get("fy"), int) for period in metrics["periods"])

    latest_10k = result["latest_10k"]
    latest_10q = result["latest_10q"]
    assert isinstance(latest_10k, dict)
    assert latest_10k.get("form") == "10-K"
    assert latest_10k.get("accession_number")
    assert isinstance(latest_10q, dict)
    assert latest_10q.get("form") == "10-Q"
    assert latest_10q.get("accession_number")

    _assert_diagnostic_contract(result.get("warnings", []), "warning")
    _assert_diagnostic_contract(result.get("errors", []), "error")
    _assert_agent_steps_contract(result["agent_steps"])
    _assert_sources_contract(result["sources"])

    source_ids = {source["source_id"] for source in result["sources"]}
    assert {"sec_submissions", "sec_company_facts", "latest_10k"}.issubset(source_ids)

    source_by_id = {source["source_id"]: source for source in result["sources"]}
    assert source_by_id["sec_submissions"]["cache_status"] in CACHE_STATUSES
    assert source_by_id["sec_company_facts"]["cache_status"] in CACHE_STATUSES
    assert source_by_id["sec_submissions"]["cache_key"]
    assert source_by_id["sec_company_facts"]["cache_key"]

    latest_10k_source = source_by_id["latest_10k"]
    assert latest_10k_source["url"]
    if latest_10k_source.get("document_cache_status") is not None:
        assert latest_10k_source["document_cache_status"] in CACHE_STATUSES
        assert latest_10k_source["document_cache_key"]


def _uses_placeholder_sec_user_agent(user_agent: str) -> bool:
    normalized = user_agent.casefold()
    return (
        "configured-via-env" in normalized
        or "your-email@example.com" in normalized
    )


def _assert_diagnostic_contract(items: list[dict[str, Any]], severity: str) -> None:
    for item in items:
        assert isinstance(item.get("code"), str)
        assert item["code"].strip()
        assert isinstance(item.get("message"), str)
        assert item["message"].strip()
        assert item.get("severity") == severity


def _assert_agent_steps_contract(steps: list[dict[str, Any]]) -> None:
    assert steps
    step_names = [step.get("node_name") for step in steps]
    assert step_names[:4] == [
        "resolve_company",
        "fetch_sec_data",
        "identify_filings",
        "fetch_filing_text",
    ]
    for step in steps:
        assert isinstance(step.get("node_name"), str)
        assert step["node_name"].strip()
        assert isinstance(step.get("status"), str)
        assert step["status"].strip()
        assert isinstance(step.get("started_at"), str)
        assert datetime.fromisoformat(step["started_at"])
        assert isinstance(step.get("completed_at"), str)
        assert datetime.fromisoformat(step["completed_at"])
        assert isinstance(step.get("duration_seconds"), int | float)
        assert step["duration_seconds"] >= 0.0


def _assert_sources_contract(sources: list[dict[str, Any]]) -> None:
    assert sources
    for source in sources:
        assert isinstance(source.get("source_id"), str)
        assert source["source_id"].strip()
        assert source.get("publisher") in {
            "U.S. Securities and Exchange Commission",
            None,
        }
