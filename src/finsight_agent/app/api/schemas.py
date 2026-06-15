from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class ResearchResponse(BaseModel):
    run_id: UUID
    query: str | None = None
    status: str
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
