import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from finsight_agent.app.services.company_resolver import (
    CompanyRecord,
    CompanyResolver,
    ResolutionStatus,
    load_sec_company_tickers,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def resolver() -> CompanyResolver:
    return CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
            CompanyRecord(
                ticker="APLE",
                company_name="Apple Hospitality REIT, Inc.",
                cik="1418121",
            ),
            CompanyRecord(
                ticker="MSFT",
                company_name="Microsoft Corporation",
                cik="789019",
            ),
            CompanyRecord(ticker="TSLA", company_name="Tesla, Inc.", cik="1318605"),
        ]
    )


def test_exact_ticker_match_is_case_insensitive(resolver: CompanyResolver) -> None:
    result = resolver.resolve("aapl")

    assert result.status == ResolutionStatus.EXACT_TICKER_MATCH
    assert result.company is not None
    assert result.company.ticker == "AAPL"
    assert result.company.company_name == "Apple Inc."
    assert result.company.cik == "0000320193"
    assert result.confidence == 1.0


def test_exact_company_name_match_is_case_insensitive(resolver: CompanyResolver) -> None:
    result = resolver.resolve("microsoft corporation")

    assert result.status == ResolutionStatus.EXACT_COMPANY_MATCH
    assert result.company is not None
    assert result.company.ticker == "MSFT"
    assert result.company.cik == "0000789019"


def test_company_record_normalizes_input_values() -> None:
    company = CompanyRecord(
        ticker=" msft ",
        company_name=" Microsoft   Corporation ",
        cik="789019",
    )

    assert company.ticker == "MSFT"
    assert company.company_name == "Microsoft Corporation"
    assert company.cik == "0000789019"


def test_empty_query_returns_not_found(resolver: CompanyResolver) -> None:
    result = resolver.resolve("   ")

    assert result.status == ResolutionStatus.NOT_FOUND
    assert result.company is None
    assert result.matches == []
    assert result.message == "Company query cannot be empty."


def test_unknown_query_returns_not_found(resolver: CompanyResolver) -> None:
    result = resolver.resolve("Definitely Not A Listed Company")

    assert result.status == ResolutionStatus.NOT_FOUND
    assert result.company is None
    assert result.matches == []
    assert result.message == "Could not confidently resolve the company."


def test_single_partial_company_match_returns_fuzzy_match(
    resolver: CompanyResolver,
) -> None:
    result = resolver.resolve("Tesla")

    assert result.status == ResolutionStatus.FUZZY_COMPANY_MATCH
    assert result.company is not None
    assert result.company.ticker == "TSLA"
    assert result.matches[0].company.ticker == "TSLA"
    assert result.confidence == 0.75


def test_multiple_partial_company_matches_return_ambiguous(
    resolver: CompanyResolver,
) -> None:
    result = resolver.resolve("Apple")

    assert result.status == ResolutionStatus.AMBIGUOUS
    assert result.company is None
    assert {match.company.ticker for match in result.matches} == {"AAPL", "APLE"}
    assert result.message == "Multiple companies matched the query."


def test_company_record_rejects_cik_without_digits() -> None:
    with pytest.raises(ValidationError):
        CompanyRecord(ticker="BAD", company_name="Bad Data Inc.", cik="not-a-cik")


def test_search_returns_ticker_and_company_name_matches(resolver: CompanyResolver) -> None:
    matches = resolver.search("apple")

    assert [company.ticker for company in matches] == ["AAPL", "APLE"]


def test_search_is_case_insensitive(resolver: CompanyResolver) -> None:
    matches = resolver.search("mIcRoSoFt")

    assert [company.ticker for company in matches] == ["MSFT"]


def test_search_returns_exact_ticker_match_first(resolver: CompanyResolver) -> None:
    matches = resolver.search("AAPL")

    assert [company.ticker for company in matches] == ["AAPL"]


def test_search_respects_limit(resolver: CompanyResolver) -> None:
    matches = resolver.search("Apple", limit=1)

    assert [company.ticker for company in matches] == ["AAPL"]


def test_search_empty_query_returns_empty_list(resolver: CompanyResolver) -> None:
    assert resolver.search("   ") == []


def test_load_sec_company_tickers_converts_sec_mapping_fixture() -> None:
    fixture_data = json.loads((FIXTURES_DIR / "sec_company_tickers.json").read_text())

    companies = load_sec_company_tickers(fixture_data)

    assert [(company.ticker, company.company_name, company.cik) for company in companies] == [
        ("AAPL", "Apple Inc.", "0000320193"),
        ("APLE", "Apple Hospitality REIT, Inc.", "0001418121"),
        ("MSFT", "MICROSOFT CORP", "0000789019"),
    ]


def test_load_sec_company_tickers_skips_malformed_records() -> None:
    sec_mapping = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": "not-a-cik", "ticker": "BAD", "title": "Bad CIK Inc."},
        "2": {"cik_str": 123456, "ticker": "", "title": "Missing Ticker Inc."},
        "3": {"cik_str": 654321, "ticker": "MISS", "title": ""},
    }

    companies = load_sec_company_tickers(sec_mapping)

    assert [company.ticker for company in companies] == ["AAPL"]


def test_partial_company_matches_are_returned_in_deterministic_order() -> None:
    resolver = CompanyResolver(
        companies=[
            CompanyRecord(ticker="APLE", company_name="Apple Hospitality REIT, Inc.", cik="1418121"),
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
        ]
    )

    result = resolver.resolve("Apple")

    assert result.status == ResolutionStatus.AMBIGUOUS
    assert [match.company.ticker for match in result.matches] == ["AAPL", "APLE"]


def test_ambiguous_result_includes_candidate_match_details(resolver: CompanyResolver) -> None:
    result = resolver.resolve("Apple")

    assert result.status == ResolutionStatus.AMBIGUOUS
    assert all(match.match_type == ResolutionStatus.FUZZY_COMPANY_MATCH for match in result.matches)
    assert all(match.confidence == 0.6 for match in result.matches)
    assert all(match.company.cik.startswith("000") for match in result.matches)
