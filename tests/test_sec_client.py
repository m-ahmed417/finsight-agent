import httpx
import pytest
import respx

from finsight_agent.app.services.sec_client import SECClient, SECClientError


@respx.mock
def test_fetch_company_tickers_returns_json_mapping() -> None:
    route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "0": {
                    "cik_str": 320193,
                    "ticker": "AAPL",
                    "title": "Apple Inc.",
                }
            },
        )
    )
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    result = client.fetch_company_tickers()

    assert route.called
    assert result["0"]["ticker"] == "AAPL"
    assert result["0"]["cik_str"] == 320193


@respx.mock
def test_fetch_company_tickers_sends_configured_user_agent() -> None:
    route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json={})
    )
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    client.fetch_company_tickers()

    request = route.calls.last.request
    assert request.headers["User-Agent"] == "FinSightTest/0.1 test@example.com"
    assert request.headers["Accept"] == "application/json"


@respx.mock
def test_fetch_company_tickers_raises_clear_error_on_http_failure() -> None:
    respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(404, text="Not found")
    )
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    with pytest.raises(SECClientError, match="status 404"):
        client.fetch_company_tickers()


@respx.mock
def test_fetch_company_tickers_raises_clear_error_on_malformed_json() -> None:
    respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, text="not-json")
    )
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    with pytest.raises(SECClientError, match="malformed JSON"):
        client.fetch_company_tickers()


def test_sec_client_rejects_empty_user_agent() -> None:
    with pytest.raises(ValueError, match="SEC user agent cannot be empty"):
        SECClient(user_agent=" ")


@respx.mock
def test_fetch_company_submissions_normalizes_cik_and_returns_json() -> None:
    route = respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "cik": "0000320193",
                "name": "Apple Inc.",
                "filings": {"recent": {"form": ["10-K"]}},
            },
        )
    )
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    result = client.fetch_company_submissions("320193")

    assert route.called
    assert result["cik"] == "0000320193"
    assert result["filings"]["recent"]["form"] == ["10-K"]


@respx.mock
def test_fetch_company_facts_normalizes_cik_and_returns_json() -> None:
    route = respx.get(
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "cik": 789019,
                "entityName": "MICROSOFT CORPORATION",
                "facts": {"us-gaap": {}},
            },
        )
    )
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    result = client.fetch_company_facts("0000789019")

    assert route.called
    assert result["entityName"] == "MICROSOFT CORPORATION"
    assert result["facts"] == {"us-gaap": {}}


def test_fetch_company_submissions_rejects_invalid_cik() -> None:
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    with pytest.raises(ValueError, match="CIK must contain at least one digit"):
        client.fetch_company_submissions("not-a-cik")


def test_fetch_company_facts_rejects_invalid_cik() -> None:
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    with pytest.raises(ValueError, match="CIK must contain at least one digit"):
        client.fetch_company_facts("not-a-cik")


@respx.mock
def test_fetch_company_submissions_raises_clear_error_on_http_failure() -> None:
    respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(500, text="SEC unavailable")
    )
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    with pytest.raises(SECClientError, match="status 500"):
        client.fetch_company_submissions("320193")


@respx.mock
def test_fetch_company_facts_raises_clear_error_on_malformed_json() -> None:
    respx.get("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json").mock(
        return_value=httpx.Response(200, text="not-json")
    )
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    with pytest.raises(SECClientError, match="malformed JSON"):
        client.fetch_company_facts("320193")
