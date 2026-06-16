import pytest
from pydantic import ValidationError

from finsight_agent.app.api.schemas import (
    AgentStep,
    ResearchError,
    ResearchResponse,
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
            "duration_ms": 125,
        }
    )

    assert step.node_name == "fetch_sec_data"
    assert step.status == "completed"
    assert step.model_dump()["duration_ms"] == 125


def test_agent_step_rejects_blank_required_fields() -> None:
    with pytest.raises(ValidationError, match="Agent step field cannot be empty"):
        AgentStep.model_validate({"node_name": "resolve_company", "status": " "})


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


def test_research_response_rejects_unknown_lifecycle_status() -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        ResearchResponse.model_validate(
            {
                "run_id": "00000000-0000-0000-0000-000000000001",
                "status": "cancelled",
            }
        )
