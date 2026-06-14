from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


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


class ResearchResponse(BaseModel):
    run_id: UUID
    query: str | None = None
    status: str
    ticker: str | None = None
    company_name: str | None = None
    report: str | None = None
    financial_metrics: dict[str, Any] | None = None
    filing_text_excerpt: str | None = None
    risk_factors: list[dict[str, Any]] = Field(default_factory=list)
    risk_themes: list[dict[str, Any]] = Field(default_factory=list)
    research_insights: dict[str, Any] | None = None
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)


class AgentStepResponse(BaseModel):
    id: int
    research_run_id: str
    node_name: str
    status: str
    message: str | None = None
    error_message: str | None = None
