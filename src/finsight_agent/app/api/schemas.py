from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from finsight_agent.app.research_status import ResearchStatus


class HealthResponse(BaseModel):
    status: str


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=120)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        query = value.strip()
        if not query:
            msg = "Research query cannot be empty."
            raise ValueError(msg)
        return query


class CompanySearchResult(BaseModel):
    ticker: str
    company_name: str
    cik: str
    exchange: str | None = None


class SourceMetadata(BaseModel):
    """Flexible source provenance returned with research outputs."""

    source_id: str
    source_type: str | None = None
    label: str | None = None
    publisher: str | None = None
    cik: str | None = None
    company_name: str | None = None
    ticker: str | None = None
    url: str | None = None
    data_format: str | None = None
    retrieval_method: str | None = None
    description: str | None = None
    retrieved_at: str | None = None
    form: str | None = None
    filing_date: str | None = None
    report_date: str | None = None
    accession_number: str | None = None
    accession_path: str | None = None
    primary_document: str | None = None
    metadata_source_ids: list[str] | None = None
    metadata_retrieved_at: str | None = None
    document_retrieved_at: str | None = None
    document_character_count: int | None = None
    extraction_status: str | None = None
    extracted_sections: list[str] | None = None
    risk_factor_text_character_count: int | None = None
    metric_extracted_at: str | None = None
    metric_extraction_status: str | None = None
    metric_fiscal_years: list[int] | None = None
    xbrl_tags_used: list[str] | None = None
    filing_forms_used: list[str] | None = None
    cache_status: str | None = None
    cache_key: str | None = None
    cache_age_seconds: float | None = None
    cache_ttl_seconds: float | None = None
    cache_expires_at: str | None = None
    cache_stale: bool | None = None
    document_cache_status: str | None = None
    document_cache_key: str | None = None
    document_cache_age_seconds: float | None = None
    document_cache_ttl_seconds: float | None = None
    document_cache_expires_at: str | None = None
    document_cache_stale: bool | None = None

    model_config = ConfigDict(extra="allow")

    @field_validator("source_id")
    @classmethod
    def source_id_must_not_be_blank(cls, value: str) -> str:
        source_id = value.strip()
        if not source_id:
            msg = "Source ID cannot be empty."
            raise ValueError(msg)
        return source_id


class AgentStep(BaseModel):
    node_name: str
    status: str
    message: str | None = None
    error_message: str | None = None
    started_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when this workflow step started, if captured.",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when this workflow step completed, if captured.",
    )
    duration_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Elapsed seconds for this workflow step, if captured.",
    )

    model_config = ConfigDict(extra="allow")

    @field_validator("node_name", "status")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            msg = "Agent step field cannot be empty."
            raise ValueError(msg)
        return text


class ResearchWarning(BaseModel):
    code: str
    message: str
    severity: str = "warning"
    details: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")

    @field_validator("code", "message", "severity")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            msg = "Research warning field cannot be empty."
            raise ValueError(msg)
        return text


class ResearchError(BaseModel):
    code: str
    message: str
    severity: str = "error"
    details: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")

    @field_validator("code", "message", "severity")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            msg = "Research error field cannot be empty."
            raise ValueError(msg)
        return text


class ResearchRunSummary(BaseModel):
    run_id: UUID
    retried_from_run_id: UUID | None = Field(
        default=None,
        description=(
            "Original failed research run ID when this run was created by a retry, "
            "or null for first-attempt runs."
        ),
    )
    query: str = Field(description="Original research query submitted for the run.")
    status: ResearchStatus = Field(
        description=(
            "Lifecycle status for scanning research runs: queued, running, "
            "completed, or failed."
        )
    )
    created_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the research run was created.",
    )
    completed_at: datetime | None = Field(
        default=None,
        description=(
            "UTC timestamp when the research run reached a terminal status, "
            "or null while it is queued or running."
        ),
    )
    duration_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Elapsed seconds between created_at and completed_at, or null while "
            "the run is queued or running."
        ),
    )
    ticker: str | None = Field(default=None, description="Resolved ticker, if available.")
    company_name: str | None = Field(
        default=None,
        description="Resolved company name, if available.",
    )
    warnings_count: int = Field(
        default=0,
        ge=0,
        description="Number of warning diagnostics persisted on the run.",
    )
    errors_count: int = Field(
        default=0,
        ge=0,
        description="Number of error diagnostics persisted on the run.",
    )
    has_report: bool = Field(
        default=False,
        description="Whether the detailed run resource includes a final report.",
    )


class ResearchRunListResponse(BaseModel):
    items: list[ResearchRunSummary] = Field(
        default_factory=list,
        description="Compact research run summaries for this page.",
    )
    next_cursor: str | None = Field(
        default=None,
        description="Opaque cursor to request the next page, or null at the end.",
    )
    has_more: bool = Field(
        default=False,
        description="Whether another page is available after this response.",
    )


class ResearchResponse(BaseModel):
    run_id: UUID
    retried_from_run_id: UUID | None = Field(
        default=None,
        description=(
            "Original failed research run ID when this run was created by a retry, "
            "or null for first-attempt runs."
        ),
    )
    query: str | None = None
    status: ResearchStatus = Field(
        description=(
            "Lifecycle status for polling research runs: queued, running, "
            "completed, or failed."
        )
    )
    created_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the research run was created.",
    )
    completed_at: datetime | None = Field(
        default=None,
        description=(
            "UTC timestamp when the research run reached a terminal status, "
            "or null while it is queued or running."
        ),
    )
    duration_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Elapsed seconds between created_at and completed_at, or null while "
            "the run is queued or running."
        ),
    )
    ticker: str | None = None
    company_name: str | None = None
    compliance_status: str | None = None
    report_quality_status: str | None = None
    report: str | None = None
    financial_metrics: dict[str, Any] | None = None
    filing_text_excerpt: str | None = None
    risk_factors: list[dict[str, Any]] = Field(default_factory=list)
    risk_themes: list[dict[str, Any]] = Field(default_factory=list)
    research_insights: dict[str, Any] | None = None
    warnings: list[ResearchWarning] = Field(default_factory=list)
    errors: list[ResearchError] = Field(default_factory=list)
    sources: list[SourceMetadata] = Field(default_factory=list)


class AgentStepResponse(AgentStep):
    id: int
    research_run_id: str


class ResearchProgressResponse(BaseModel):
    run_id: UUID = Field(description="Research run ID for this progress summary.")
    status: ResearchStatus = Field(
        description="Current lifecycle status for the research run.",
    )
    total_steps: int = Field(
        default=0,
        ge=0,
        description="Total number of stored workflow steps for the run.",
    )
    completed_steps: int = Field(
        default=0,
        ge=0,
        description="Number of stored workflow steps with status completed.",
    )
    failed_steps: int = Field(
        default=0,
        ge=0,
        description="Number of stored workflow steps with status failed.",
    )
    latest_step: AgentStepResponse | None = Field(
        default=None,
        description="Most recently stored workflow step, or null when no step exists.",
    )
    workflow_started_at: datetime | None = Field(
        default=None,
        description="Earliest captured step start timestamp for the run.",
    )
    workflow_completed_at: datetime | None = Field(
        default=None,
        description="Latest captured step completion timestamp for the run.",
    )
    workflow_duration_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Elapsed seconds between workflow_started_at and "
            "workflow_completed_at when both are available."
        ),
    )
