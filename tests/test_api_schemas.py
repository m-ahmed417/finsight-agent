from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from finsight_agent.app.api.schemas import (
    AgentStep,
    LLMCallEvent,
    LLMUsageSummary,
    LLMUsageSummaryResponse,
    ResearchError,
    ResearchProgressResponse,
    ResearchResponse,
    ResearchRunListResponse,
    ResearchRunSummary,
    ResearchWarning,
    SourceMetadata,
)


def test_source_metadata_preserves_rich_sec_provenance() -> None:
    source = SourceMetadata.model_validate(
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
            "cache_key": "company_submissions:0000320193",
            "cache_age_seconds": 120.5,
            "cache_ttl_seconds": 86400.0,
            "cache_expires_at": "2026-06-17T10:00:00+00:00",
            "cache_stale": False,
            "document_cache_status": "miss",
            "document_cache_key": (
                "filing_document:0000320193:"
                "000032019324000123:aapl-20240928.htm"
            ),
            "document_cache_age_seconds": 0.25,
            "document_cache_ttl_seconds": 604800.0,
            "document_cache_expires_at": "2026-06-23T10:00:00+00:00",
            "document_cache_stale": False,
        }
    )

    assert source.source_id == "latest_10k"
    assert source.form == "10-K"
    assert source.metadata_source_ids == ["sec_submissions"]
    assert source.extracted_sections == ["Item 1A Risk Factors"]
    assert source.cache_status == "hit"
    assert source.cache_age_seconds == 120.5
    assert source.cache_stale is False
    assert source.document_cache_status == "miss"
    assert source.document_cache_age_seconds == 0.25
    assert source.document_cache_stale is False


def test_source_metadata_defines_cache_diagnostic_fields() -> None:
    expected_fields = {
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
    }

    assert expected_fields.issubset(SourceMetadata.model_fields)


def test_source_metadata_rejects_blank_source_id() -> None:
    with pytest.raises(ValidationError, match="Source ID cannot be empty"):
        SourceMetadata.model_validate({"source_id": "   "})


def test_agent_step_validates_required_fields_and_preserves_extra_metadata() -> None:
    step = AgentStep.model_validate(
        {
            "node_name": " fetch_sec_data ",
            "status": " completed ",
            "message": "Fetched SEC submissions and company facts.",
            "started_at": "2026-06-16T13:00:00+00:00",
            "completed_at": "2026-06-16T13:00:02+00:00",
            "duration_seconds": 2.0,
            "llm_provider": "openai",
            "llm_model": "gpt-test-model",
            "llm_used": True,
            "llm_fallback_reason": None,
            "duration_ms": 125,
        }
    )

    assert step.node_name == "fetch_sec_data"
    assert step.status == "completed"
    assert step.started_at == datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)
    assert step.completed_at == datetime(2026, 6, 16, 13, 0, 2, tzinfo=timezone.utc)
    assert step.duration_seconds == 2.0
    assert step.llm_provider == "openai"
    assert step.llm_model == "gpt-test-model"
    assert step.llm_used is True
    assert step.llm_fallback_reason is None
    assert step.model_dump()["duration_ms"] == 125


def test_agent_step_rejects_blank_required_fields() -> None:
    with pytest.raises(ValidationError, match="Agent step field cannot be empty"):
        AgentStep.model_validate({"node_name": "resolve_company", "status": " "})


def test_agent_step_rejects_negative_duration() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        AgentStep.model_validate(
            {
                "node_name": "resolve_company",
                "status": "completed",
                "duration_seconds": -0.01,
            }
        )


def test_llm_call_event_validates_and_preserves_usage_metadata() -> None:
    event = LLMCallEvent.model_validate(
        {
            "node_name": "analyze_risks",
            "task": "risk_analysis",
            "status": "completed",
            "llm_provider": "openai",
            "llm_model": "gpt-test-model",
            "prompt_version": "risk_analysis:v1",
            "started_at": "2026-06-16T13:00:00+00:00",
            "completed_at": "2026-06-16T13:00:01+00:00",
            "duration_seconds": 1.0,
            "input_tokens": 120,
            "output_tokens": 42,
            "total_tokens": 162,
            "provider_request_id": "req_123",
            "fallback_used": False,
            "trace_id": "custom-trace-id",
        }
    )

    assert event.node_name == "analyze_risks"
    assert event.task == "risk_analysis"
    assert event.status == "completed"
    assert event.llm_provider == "openai"
    assert event.llm_model == "gpt-test-model"
    assert event.prompt_version == "risk_analysis:v1"
    assert event.input_tokens == 120
    assert event.output_tokens == 42
    assert event.total_tokens == 162
    assert event.provider_request_id == "req_123"
    assert event.fallback_used is False
    assert event.model_dump()["trace_id"] == "custom-trace-id"


def test_llm_call_event_rejects_negative_usage_values() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        LLMCallEvent.model_validate(
            {
                "node_name": "analyze_risks",
                "task": "risk_analysis",
                "status": "completed",
                "input_tokens": -1,
            }
        )


def test_llm_usage_summary_validates_rollup_fields() -> None:
    summary = LLMUsageSummary.model_validate(
        {
            "total_calls": 3,
            "completed_calls": 1,
            "failed_calls": 1,
            "skipped_calls": 1,
            "fallback_count": 2,
            "total_duration_seconds": 2.5,
            "total_input_tokens": 120,
            "total_output_tokens": 42,
            "total_tokens": 162,
            "providers": ["openai"],
            "models": ["gpt-test-model"],
        }
    )

    assert summary.total_calls == 3
    assert summary.completed_calls == 1
    assert summary.failed_calls == 1
    assert summary.skipped_calls == 1
    assert summary.fallback_count == 2
    assert summary.total_duration_seconds == 2.5
    assert summary.total_input_tokens == 120
    assert summary.total_output_tokens == 42
    assert summary.total_tokens == 162
    assert summary.providers == ["openai"]
    assert summary.models == ["gpt-test-model"]


def test_llm_usage_summary_response_adds_run_context() -> None:
    response = LLMUsageSummaryResponse.model_validate(
        {
            "run_id": "00000000-0000-0000-0000-000000000001",
            "status": "completed",
            "total_calls": 0,
            "completed_calls": 0,
            "failed_calls": 0,
            "skipped_calls": 0,
            "fallback_count": 0,
            "total_duration_seconds": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "providers": [],
            "models": [],
        }
    )

    assert str(response.run_id) == "00000000-0000-0000-0000-000000000001"
    assert response.status == "completed"


def test_llm_usage_summary_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        LLMUsageSummary.model_validate(
            {
                "total_calls": -1,
                "completed_calls": 0,
                "failed_calls": 0,
                "skipped_calls": 0,
                "fallback_count": 0,
                "total_duration_seconds": 0.0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
            }
        )


def test_research_warning_validates_core_fields_and_preserves_details() -> None:
    warning = ResearchWarning.model_validate(
        {
            "code": " report_quality_warning ",
            "message": "Report section is missing source_id citations.",
            "severity": " warning ",
            "details": {"validator_code": "missing_section_citation"},
            "source_id": "latest_10k",
        }
    )

    assert warning.code == "report_quality_warning"
    assert warning.severity == "warning"
    assert warning.details == {"validator_code": "missing_section_citation"}
    assert warning.model_dump()["source_id"] == "latest_10k"


def test_research_error_defaults_to_error_severity() -> None:
    error = ResearchError.model_validate(
        {
            "code": "company_not_found",
            "message": "Could not confidently resolve the company.",
        }
    )

    assert error.severity == "error"


def test_research_warning_and_error_reject_blank_messages() -> None:
    with pytest.raises(ValidationError, match="Research warning field cannot be empty"):
        ResearchWarning.model_validate({"code": "metric_warning", "message": " "})

    with pytest.raises(ValidationError, match="Research error field cannot be empty"):
        ResearchError.model_validate({"code": "company_not_found", "message": " "})


@pytest.mark.parametrize("status", ["queued", "running", "completed", "failed"])
def test_research_response_accepts_known_lifecycle_statuses(status: str) -> None:
    response = ResearchResponse.model_validate(
        {
            "run_id": "00000000-0000-0000-0000-000000000001",
            "status": status,
        }
    )

    assert response.status == status


def test_research_response_exposes_report_quality_details() -> None:
    response = ResearchResponse.model_validate(
        {
            "run_id": "00000000-0000-0000-0000-000000000001",
            "status": "completed",
            "report_quality_status": "passed",
            "report_quality_details": {
                "citation_audit": {
                    "status": "passed",
                    "known_source_ids": ["sec_company_facts"],
                    "unknown_citations": [],
                }
            },
        }
    )

    assert response.report_quality_details == {
        "citation_audit": {
            "status": "passed",
            "known_source_ids": ["sec_company_facts"],
            "unknown_citations": [],
        }
    }


def test_research_response_exposes_lifecycle_timestamps() -> None:
    created_at = datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)
    completed_at = datetime(2026, 6, 16, 13, 2, 30, tzinfo=timezone.utc)

    response = ResearchResponse.model_validate(
        {
            "run_id": "00000000-0000-0000-0000-000000000001",
            "status": "completed",
            "created_at": created_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_seconds": 150.0,
        }
    )

    assert response.created_at == created_at
    assert response.completed_at == completed_at
    assert response.duration_seconds == 150.0


def test_research_response_exposes_retry_lineage() -> None:
    response = ResearchResponse.model_validate(
        {
            "run_id": "00000000-0000-0000-0000-000000000002",
            "retried_from_run_id": "00000000-0000-0000-0000-000000000001",
            "status": "queued",
        }
    )

    assert str(response.retried_from_run_id) == (
        "00000000-0000-0000-0000-000000000001"
    )


def test_research_run_summary_exposes_compact_list_metadata() -> None:
    created_at = datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)
    completed_at = datetime(2026, 6, 16, 13, 2, 30, tzinfo=timezone.utc)

    summary = ResearchRunSummary.model_validate(
        {
            "run_id": "00000000-0000-0000-0000-000000000002",
            "retried_from_run_id": "00000000-0000-0000-0000-000000000001",
            "query": "AAPL",
            "status": "completed",
            "created_at": created_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_seconds": 150.0,
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "warnings_count": 2,
            "errors_count": 1,
            "has_report": True,
        }
    )

    assert summary.status == "completed"
    assert summary.created_at == created_at
    assert summary.completed_at == completed_at
    assert summary.duration_seconds == 150.0
    assert summary.warnings_count == 2
    assert summary.errors_count == 1
    assert summary.has_report is True


def test_research_run_summary_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        ResearchRunSummary.model_validate(
            {
                "run_id": "00000000-0000-0000-0000-000000000001",
                "query": "AAPL",
                "status": "failed",
                "warnings_count": -1,
                "errors_count": 0,
                "has_report": False,
            }
        )


def test_research_run_list_response_wraps_items_with_cursor_metadata() -> None:
    response = ResearchRunListResponse.model_validate(
        {
            "items": [
                {
                    "run_id": "00000000-0000-0000-0000-000000000001",
                    "query": "AAPL",
                    "status": "queued",
                    "warnings_count": 0,
                    "errors_count": 0,
                    "has_report": False,
                }
            ],
            "next_cursor": "opaque-cursor",
            "has_more": True,
        }
    )

    assert len(response.items) == 1
    assert response.next_cursor == "opaque-cursor"
    assert response.has_more is True


def test_research_progress_response_summarizes_stored_steps() -> None:
    response = ResearchProgressResponse.model_validate(
        {
            "run_id": "00000000-0000-0000-0000-000000000001",
            "status": "completed",
            "total_steps": 2,
            "completed_steps": 2,
            "failed_steps": 0,
            "workflow_started_at": "2026-06-16T13:00:00+00:00",
            "workflow_completed_at": "2026-06-16T13:00:03+00:00",
            "workflow_duration_seconds": 3.0,
            "latest_step": {
                "id": 2,
                "research_run_id": "00000000-0000-0000-0000-000000000001",
                "node_name": "fetch_sec_data",
                "status": "completed",
                "message": "Fetched SEC submissions and company facts.",
                "completed_at": "2026-06-16T13:00:03+00:00",
                "duration_seconds": 2.0,
            },
        }
    )

    assert response.total_steps == 2
    assert response.completed_steps == 2
    assert response.failed_steps == 0
    assert response.workflow_duration_seconds == 3.0
    assert response.latest_step is not None
    assert response.latest_step.node_name == "fetch_sec_data"


def test_research_progress_response_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        ResearchProgressResponse.model_validate(
            {
                "run_id": "00000000-0000-0000-0000-000000000001",
                "status": "failed",
                "total_steps": -1,
                "completed_steps": 0,
                "failed_steps": 0,
            }
        )


def test_research_response_rejects_unknown_lifecycle_status() -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        ResearchResponse.model_validate(
            {
                "run_id": "00000000-0000-0000-0000-000000000001",
                "status": "cancelled",
            }
        )
