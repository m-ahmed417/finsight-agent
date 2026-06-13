from enum import StrEnum

from pydantic import BaseModel, Field, ValidationError, field_validator


class ResolutionStatus(StrEnum):
    EXACT_TICKER_MATCH = "exact_ticker_match"
    EXACT_COMPANY_MATCH = "exact_company_match"
    FUZZY_COMPANY_MATCH = "fuzzy_company_match"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


class CompanyRecord(BaseModel):
    ticker: str
    company_name: str
    cik: str
    exchange: str | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        ticker = value.strip().upper()
        if not ticker:
            msg = "Ticker cannot be empty."
            raise ValueError(msg)
        return ticker

    @field_validator("company_name")
    @classmethod
    def normalize_company_name(cls, value: str) -> str:
        company_name = " ".join(value.strip().split())
        if not company_name:
            msg = "Company name cannot be empty."
            raise ValueError(msg)
        return company_name

    @field_validator("cik")
    @classmethod
    def normalize_cik(cls, value: str) -> str:
        digits = "".join(char for char in str(value).strip() if char.isdigit())
        if not digits:
            msg = "CIK must contain at least one digit."
            raise ValueError(msg)
        return digits.zfill(10)


class CompanyMatch(BaseModel):
    company: CompanyRecord
    match_type: ResolutionStatus
    confidence: float = Field(ge=0.0, le=1.0)


class CompanyResolution(BaseModel):
    query: str
    status: ResolutionStatus
    company: CompanyRecord | None = None
    matches: list[CompanyMatch] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    message: str | None = None


class CompanyResolver:
    def __init__(self, companies: list[CompanyRecord]) -> None:
        self._companies = companies

    def resolve(self, query: str) -> CompanyResolution:
        normalized_query = self._normalize_query(query)
        if not normalized_query:
            return CompanyResolution(
                query=query,
                status=ResolutionStatus.NOT_FOUND,
                message="Company query cannot be empty.",
            )

        ticker_match = self._find_exact_ticker(normalized_query)
        if ticker_match is not None:
            return CompanyResolution(
                query=query,
                status=ResolutionStatus.EXACT_TICKER_MATCH,
                company=ticker_match,
                confidence=1.0,
            )

        company_match = self._find_exact_company_name(normalized_query)
        if company_match is not None:
            return CompanyResolution(
                query=query,
                status=ResolutionStatus.EXACT_COMPANY_MATCH,
                company=company_match,
                confidence=1.0,
            )

        partial_matches = self._find_partial_company_matches(normalized_query)
        if len(partial_matches) == 1:
            return CompanyResolution(
                query=query,
                status=ResolutionStatus.FUZZY_COMPANY_MATCH,
                company=partial_matches[0],
                matches=[
                    CompanyMatch(
                        company=partial_matches[0],
                        match_type=ResolutionStatus.FUZZY_COMPANY_MATCH,
                        confidence=0.75,
                    )
                ],
                confidence=0.75,
            )
        if len(partial_matches) > 1:
            return CompanyResolution(
                query=query,
                status=ResolutionStatus.AMBIGUOUS,
                matches=[
                    CompanyMatch(
                        company=company,
                        match_type=ResolutionStatus.FUZZY_COMPANY_MATCH,
                        confidence=0.6,
                    )
                    for company in partial_matches
                ],
                message="Multiple companies matched the query.",
            )

        return CompanyResolution(
            query=query,
            status=ResolutionStatus.NOT_FOUND,
            message="Could not confidently resolve the company.",
        )

    @staticmethod
    def _normalize_query(query: str) -> str:
        return " ".join(query.strip().split()).casefold()

    def _find_exact_ticker(self, normalized_query: str) -> CompanyRecord | None:
        for company in self._companies:
            if company.ticker.casefold() == normalized_query:
                return company
        return None

    def _find_exact_company_name(self, normalized_query: str) -> CompanyRecord | None:
        for company in self._companies:
            if company.company_name.casefold() == normalized_query:
                return company
        return None

    def _find_partial_company_matches(self, normalized_query: str) -> list[CompanyRecord]:
        matches = [
            company
            for company in self._companies
            if normalized_query in company.company_name.casefold()
        ]
        return sorted(matches, key=lambda company: (company.ticker, company.company_name))


def load_sec_company_tickers(sec_mapping: dict[str, dict]) -> list[CompanyRecord]:
    companies: list[CompanyRecord] = []
    for record in sec_mapping.values():
        try:
            company = CompanyRecord(
                ticker=record.get("ticker", ""),
                company_name=record.get("title", ""),
                cik=str(record.get("cik_str", "")),
            )
        except (AttributeError, TypeError, ValidationError):
            continue

        companies.append(company)

    return sorted(companies, key=lambda company: (company.ticker, company.company_name))
