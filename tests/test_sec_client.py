import os

import httpx
import pytest
import respx

from finsight_agent.app.services.sec_client import SECClient, SECClientError


class ManualClock:
    def __init__(self, start: float = 100.0) -> None:
        self.current = start
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += seconds

    def advance(self, seconds: float) -> None:
        self.current += seconds


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
    route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(404, text="Not found")
    )
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    with pytest.raises(SECClientError, match="status 404"):
        client.fetch_company_tickers()
    assert route.call_count == 1


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
def test_fetch_filing_document_builds_archive_url_and_returns_text() -> None:
    route = respx.get(
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019324000123/aapl-20240928.htm"
    ).mock(return_value=httpx.Response(200, text="<html>10-K text</html>"))
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    result = client.fetch_filing_document(
        cik="0000320193",
        accession_number="0000320193-24-000123",
        primary_document="aapl-20240928.htm",
    )

    assert route.called
    assert result == "<html>10-K text</html>"


def test_fetch_filing_document_rejects_missing_primary_document() -> None:
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    with pytest.raises(ValueError, match="Primary document cannot be empty"):
        client.fetch_filing_document(
            cik="0000320193",
            accession_number="0000320193-24-000123",
            primary_document=" ",
        )


@respx.mock
def test_fetch_company_submissions_raises_clear_error_on_http_failure() -> None:
    route = respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(500, text="SEC unavailable")
    )
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    with pytest.raises(SECClientError, match="status 500.*after 3 attempts"):
        client.fetch_company_submissions("320193")
    assert route.call_count == 3


@respx.mock
def test_fetch_company_facts_raises_clear_error_on_malformed_json() -> None:
    respx.get("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json").mock(
        return_value=httpx.Response(200, text="not-json")
    )
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    with pytest.raises(SECClientError, match="malformed JSON"):
        client.fetch_company_facts("320193")


@respx.mock
def test_fetch_company_submissions_retries_transient_5xx_then_succeeds() -> None:
    route = respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        side_effect=[
            httpx.Response(503, text="SEC temporarily unavailable"),
            httpx.Response(
                200,
                json={
                    "cik": "0000320193",
                    "name": "Apple Inc.",
                },
            ),
        ]
    )
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    result = client.fetch_company_submissions("320193")

    assert route.call_count == 2
    assert result["name"] == "Apple Inc."


@respx.mock
def test_fetch_company_facts_retries_timeout_then_succeeds() -> None:
    route = respx.get(
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    ).mock(
        side_effect=[
            httpx.TimeoutException("Request timed out."),
            httpx.Response(
                200,
                json={
                    "cik": 320193,
                    "facts": {"us-gaap": {}},
                },
            ),
        ]
    )
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    result = client.fetch_company_facts("320193")

    assert route.call_count == 2
    assert result["facts"] == {"us-gaap": {}}


@respx.mock
def test_fetch_company_facts_raises_clear_error_when_timeout_retries_are_exhausted() -> None:
    route = respx.get(
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    ).mock(side_effect=httpx.TimeoutException("Request timed out."))
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    with pytest.raises(SECClientError, match="after 3 attempts"):
        client.fetch_company_facts("320193")
    assert route.call_count == 3


def test_sec_client_rejects_negative_max_retries() -> None:
    with pytest.raises(ValueError, match="max_retries cannot be negative"):
        SECClient(user_agent="FinSightTest/0.1 test@example.com", max_retries=-1)


def test_sec_client_rejects_negative_min_request_interval() -> None:
    with pytest.raises(
        ValueError,
        match="min_request_interval_seconds cannot be negative",
    ):
        SECClient(
            user_agent="FinSightTest/0.1 test@example.com",
            min_request_interval_seconds=-0.1,
        )


def test_sec_client_rejects_negative_cache_ttl() -> None:
    with pytest.raises(ValueError, match="cache_ttl_seconds cannot be negative"):
        SECClient(
            user_agent="FinSightTest/0.1 test@example.com",
            cache_ttl_seconds=-1,
        )


@respx.mock
def test_sec_client_applies_request_interval_between_live_requests() -> None:
    clock = ManualClock()
    respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.get(
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    ).mock(return_value=httpx.Response(200, json={"facts": {"us-gaap": {}}}))
    client = SECClient(
        user_agent="FinSightTest/0.1 test@example.com",
        min_request_interval_seconds=0.5,
        clock=clock.now,
        sleep=clock.sleep,
    )

    client.fetch_company_tickers()
    client.fetch_company_facts("320193")

    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(0.5)


@respx.mock
def test_sec_client_rate_limit_accounts_for_elapsed_time() -> None:
    clock = ManualClock()
    respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json={"cik": "0000320193"})
    )
    client = SECClient(
        user_agent="FinSightTest/0.1 test@example.com",
        min_request_interval_seconds=0.5,
        clock=clock.now,
        sleep=clock.sleep,
    )

    client.fetch_company_tickers()
    clock.advance(0.3)
    client.fetch_company_submissions("320193")

    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(0.2)


@respx.mock
def test_fetch_company_tickers_uses_filesystem_cache(tmp_path) -> None:
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
    client = SECClient(
        user_agent="FinSightTest/0.1 test@example.com",
        cache_dir=tmp_path,
    )

    first_result = client.fetch_company_tickers()
    second_result = client.fetch_company_tickers()

    assert route.call_count == 1
    assert first_result == second_result
    assert any(tmp_path.iterdir())


@respx.mock
def test_fetch_company_tickers_with_metadata_reports_cache_miss_and_hit(
    tmp_path,
) -> None:
    route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json={"0": {"ticker": "AAPL"}})
    )
    client = SECClient(
        user_agent="FinSightTest/0.1 test@example.com",
        cache_dir=tmp_path,
    )

    first_result = client.fetch_company_tickers_with_metadata()
    second_result = client.fetch_company_tickers_with_metadata()

    assert route.call_count == 1
    assert first_result.data == {"0": {"ticker": "AAPL"}}
    assert second_result.data == first_result.data
    assert first_result.metadata.cache_status == "miss"
    assert second_result.metadata.cache_status == "hit"
    assert first_result.metadata.url == SECClient.COMPANY_TICKERS_URL
    assert second_result.metadata.url == SECClient.COMPANY_TICKERS_URL


@respx.mock
def test_fetch_company_tickers_with_metadata_reports_fresh_cache_age_and_expiry(
    tmp_path,
) -> None:
    clock = ManualClock(start=100.0)
    route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json={"0": {"ticker": "AAPL"}})
    )
    client = SECClient(
        user_agent="FinSightTest/0.1 test@example.com",
        cache_dir=tmp_path,
        cache_ttl_seconds=60.0,
        wall_clock=clock.now,
    )

    client.fetch_company_tickers_with_metadata()
    cache_path = next(tmp_path.iterdir())
    os.utime(cache_path, (90.0, 90.0))

    result = client.fetch_company_tickers_with_metadata()

    assert route.call_count == 1
    assert result.metadata.cache_status == "hit"
    assert result.metadata.cache_age_seconds == pytest.approx(10.0)
    assert result.metadata.cache_ttl_seconds == 60.0
    assert result.metadata.cache_expires_at == "1970-01-01T00:02:30+00:00"
    assert result.metadata.cache_stale is False


@respx.mock
def test_fetch_company_tickers_with_metadata_refetches_stale_cache(
    tmp_path,
) -> None:
    clock = ManualClock(start=100.0)
    route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        side_effect=[
            httpx.Response(200, json={"0": {"ticker": "AAPL"}}),
            httpx.Response(200, json={"0": {"ticker": "MSFT"}}),
        ]
    )
    client = SECClient(
        user_agent="FinSightTest/0.1 test@example.com",
        cache_dir=tmp_path,
        cache_ttl_seconds=60.0,
        wall_clock=clock.now,
    )

    client.fetch_company_tickers_with_metadata()
    cache_path = next(tmp_path.iterdir())
    os.utime(cache_path, (20.0, 20.0))

    result = client.fetch_company_tickers_with_metadata()

    assert route.call_count == 2
    assert result.data == {"0": {"ticker": "MSFT"}}
    assert result.metadata.cache_status == "miss"
    assert result.metadata.cache_ttl_seconds == 60.0
    assert result.metadata.cache_stale is False


@respx.mock
def test_fetch_company_facts_with_metadata_reports_cache_disabled() -> None:
    route = respx.get(
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    ).mock(return_value=httpx.Response(200, json={"facts": {"us-gaap": {}}}))
    client = SECClient(user_agent="FinSightTest/0.1 test@example.com")

    result = client.fetch_company_facts_with_metadata("320193")

    assert route.call_count == 1
    assert result.data == {"facts": {"us-gaap": {}}}
    assert result.metadata.cache_status == "disabled"
    assert result.metadata.url == (
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    )


@respx.mock
def test_fetch_filing_document_with_metadata_reports_cache_miss_and_hit(
    tmp_path,
) -> None:
    route = respx.get(
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019324000123/aapl-20240928.htm"
    ).mock(return_value=httpx.Response(200, text="<html>10-K text</html>"))
    client = SECClient(
        user_agent="FinSightTest/0.1 test@example.com",
        cache_dir=tmp_path,
    )

    first_result = client.fetch_filing_document_with_metadata(
        cik="0000320193",
        accession_number="0000320193-24-000123",
        primary_document="aapl-20240928.htm",
    )
    second_result = client.fetch_filing_document_with_metadata(
        cik="320193",
        accession_number="000032019324000123",
        primary_document="aapl-20240928.htm",
    )

    assert route.call_count == 1
    assert first_result.data == "<html>10-K text</html>"
    assert second_result.data == first_result.data
    assert first_result.metadata.cache_status == "miss"
    assert second_result.metadata.cache_status == "hit"


@respx.mock
def test_sec_client_does_not_rate_limit_cache_hits(tmp_path) -> None:
    clock = ManualClock()
    route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json={"0": {"ticker": "AAPL"}})
    )
    client = SECClient(
        user_agent="FinSightTest/0.1 test@example.com",
        cache_dir=tmp_path,
        min_request_interval_seconds=1.0,
        clock=clock.now,
        sleep=clock.sleep,
    )

    first_result = client.fetch_company_tickers()
    second_result = client.fetch_company_tickers()

    assert route.call_count == 1
    assert first_result == second_result
    assert clock.sleeps == []


@respx.mock
def test_fetch_company_submissions_uses_normalized_cik_cache_key(tmp_path) -> None:
    route = respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "cik": "0000320193",
                "name": "Apple Inc.",
            },
        )
    )
    client = SECClient(
        user_agent="FinSightTest/0.1 test@example.com",
        cache_dir=tmp_path,
    )

    first_result = client.fetch_company_submissions("320193")
    second_result = client.fetch_company_submissions("0000320193")

    assert route.call_count == 1
    assert first_result == second_result


@respx.mock
def test_fetch_filing_document_uses_filesystem_cache(tmp_path) -> None:
    route = respx.get(
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019324000123/aapl-20240928.htm"
    ).mock(return_value=httpx.Response(200, text="<html>10-K text</html>"))
    client = SECClient(
        user_agent="FinSightTest/0.1 test@example.com",
        cache_dir=tmp_path,
    )

    first_result = client.fetch_filing_document(
        cik="0000320193",
        accession_number="0000320193-24-000123",
        primary_document="aapl-20240928.htm",
    )
    second_result = client.fetch_filing_document(
        cik="320193",
        accession_number="000032019324000123",
        primary_document="aapl-20240928.htm",
    )

    assert route.call_count == 1
    assert first_result == second_result == "<html>10-K text</html>"


@respx.mock
def test_malformed_json_response_is_not_cached(tmp_path) -> None:
    route = respx.get(
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    ).mock(
        side_effect=[
            httpx.Response(200, text="not-json"),
            httpx.Response(
                200,
                json={
                    "cik": 320193,
                    "facts": {"us-gaap": {}},
                },
            ),
        ]
    )
    client = SECClient(
        user_agent="FinSightTest/0.1 test@example.com",
        cache_dir=tmp_path,
    )

    with pytest.raises(SECClientError, match="malformed JSON"):
        client.fetch_company_facts("320193")
    result = client.fetch_company_facts("320193")

    assert route.call_count == 2
    assert result["facts"] == {"us-gaap": {}}
