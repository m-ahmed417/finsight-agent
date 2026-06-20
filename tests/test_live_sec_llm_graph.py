from datetime import datetime
import os
from typing import Any

import pytest

from finsight_agent.app.config import get_settings
from finsight_agent.app.graph.builder import build_research_graph
from finsight_agent.app.services.compliance import find_forbidden_terms
from finsight_agent.app.services.llm_client import get_llm_client
from finsight_agent.app.services.llm_usage import summarize_llm_usage
from finsight_agent.app.services.report_generator import RESEARCH_ONLY_NOTICE
from finsight_agent.app.services.resolver_loader import build_static_company_resolver
from finsight_agent.app.services.sec_client import SECClient

AAPL_CIK = "0000320193"
LIVE_LLM_TASKS = {"risk_analysis", "report_drafting"}


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_SEC_LLM_GRAPH_TESTS") != "1",
    reason="Live SEC plus LLM graph smoke tests are opt-in.",
)
def test_live_sec_llm_graph_smoke_exercises_full_agent_path(tmp_path) -> None:
    get_settings.cache_clear()
    settings = get_settings()
    if _uses_placeholder_sec_user_agent(settings.sec_user_agent):
        pytest.fail(
            "Set SEC_USER_AGENT to a descriptive value before running live SEC plus LLM graph tests."
        )
    if settings.llm_provider.strip().casefold() == "mock":
        pytest.fail(
            "Set LLM_PROVIDER to openai or deepseek before running live SEC plus LLM graph tests."
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
        llm_client=get_llm_client(settings),
    )

    result = graph.invoke({"user_query": "AAPL"})

    assert result["ticker"] == "AAPL"
    assert result["company_name"] == "Apple Inc."
    assert result["cik"] == AAPL_CIK
    _assert_diagnostic_contract(result.get("warnings", []), "warning")
    _assert_diagnostic_contract(result.get("errors", []), "error")
    _assert_agent_steps_contract(result["agent_steps"])

    if result["errors"]:
        assert result["final_report"] is None
        return

    assert isinstance(result["final_report"], str)
    assert RESEARCH_ONLY_NOTICE in result["final_report"]
    assert "[sec_company_facts]" in result["final_report"]
    assert "[latest_10k]" in result["final_report"]
    assert find_forbidden_terms(result["final_report"]) == []
    assert result["compliance_status"] in {"allowed", "needs_rewrite"}
    assert result["report_quality_status"] in {"passed", "warning"}
    assert result["sources"]
    assert {"sec_submissions", "sec_company_facts", "latest_10k"}.issubset(
        {source["source_id"] for source in result["sources"]}
    )

    llm_events = result["llm_call_events"]
    assert {event["task"] for event in llm_events} == LIVE_LLM_TASKS
    for event in llm_events:
        assert event["status"] in {"completed", "failed"}
        assert event["llm_provider"] == settings.llm_provider.strip().casefold()
        assert event["llm_model"] == settings.llm_model.strip()
        assert event["prompt_version"] in {"risk_analysis:v1", "report_drafting:v1"}
        assert isinstance(event["fallback_used"], bool)
        if event["status"] == "failed":
            assert event["fallback_used"] is True
            assert event["fallback_reason"]
        if event.get("started_at"):
            assert datetime.fromisoformat(event["started_at"])
        if event.get("completed_at"):
            assert datetime.fromisoformat(event["completed_at"])

    usage_summary = summarize_llm_usage(llm_events)
    assert usage_summary["total_calls"] == len(llm_events)
    assert usage_summary["total_calls"] >= 2
    assert settings.llm_provider.strip().casefold() in usage_summary["providers"]
    assert settings.llm_model.strip() in usage_summary["models"]
    assert (
        usage_summary["completed_calls"]
        + usage_summary["failed_calls"]
        + usage_summary["skipped_calls"]
        == usage_summary["total_calls"]
    )
    if usage_summary["fallback_count"]:
        assert any(
            warning["code"]
            in {"llm_risk_analysis_unavailable", "llm_report_drafting_unavailable"}
            for warning in result["warnings"]
        )


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
    for step in steps:
        assert isinstance(step.get("node_name"), str)
        assert step["node_name"].strip()
        assert isinstance(step.get("status"), str)
        assert step["status"].strip()
        if step.get("started_at"):
            assert datetime.fromisoformat(step["started_at"])
        if step.get("completed_at"):
            assert datetime.fromisoformat(step["completed_at"])
        if step.get("duration_seconds") is not None:
            assert isinstance(step["duration_seconds"], int | float)
            assert step["duration_seconds"] >= 0.0
