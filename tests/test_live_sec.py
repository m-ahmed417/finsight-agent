import os
from typing import Any

import pytest

from finsight_agent.app.config import get_settings
from finsight_agent.app.services.sec_client import SECClient

AAPL_CIK = "0000320193"


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_SEC_TESTS") != "1",
    reason="Live SEC smoke tests are opt-in.",
)
def test_live_sec_client_smoke_fetches_apple_data(tmp_path) -> None:
    get_settings.cache_clear()
    settings = get_settings()
    if _uses_placeholder_sec_user_agent(settings.sec_user_agent):
        pytest.fail(
            "Set SEC_USER_AGENT to a descriptive value before running live SEC tests."
        )

    cache_dir = tmp_path / "sec-cache"
    client = SECClient(
        user_agent=settings.sec_user_agent,
        cache_dir=cache_dir,
        min_request_interval_seconds=settings.sec_request_interval_seconds,
        timeout=20.0,
    )

    tickers = client.fetch_company_tickers()
    submissions = client.fetch_company_submissions(AAPL_CIK)
    company_facts = client.fetch_company_facts(AAPL_CIK)

    assert _contains_apple_ticker_record(tickers)
    assert submissions.get("cik") in {AAPL_CIK, "320193", 320193}
    recent_filings = submissions.get("filings", {}).get("recent", {})
    assert isinstance(recent_filings.get("form"), list)
    assert any(form in {"10-K", "10-Q"} for form in recent_filings["form"])
    assert company_facts.get("cik") in {AAPL_CIK, "320193", 320193}
    assert isinstance(company_facts.get("facts", {}).get("us-gaap"), dict)
    assert company_facts["facts"]["us-gaap"]
    assert any(cache_dir.iterdir())

    cached_tickers = client.fetch_company_tickers()

    assert cached_tickers == tickers

    get_settings.cache_clear()


def _uses_placeholder_sec_user_agent(user_agent: str) -> bool:
    normalized = user_agent.casefold()
    return (
        "configured-via-env" in normalized
        or "your-email@example.com" in normalized
    )


def _contains_apple_ticker_record(tickers: dict[str, Any]) -> bool:
    return any(
        isinstance(record, dict)
        and str(record.get("ticker", "")).upper() == "AAPL"
        and str(record.get("cik_str", "")).zfill(10) == AAPL_CIK
        for record in tickers.values()
    )
