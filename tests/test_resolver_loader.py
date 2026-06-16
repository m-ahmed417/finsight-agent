import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from finsight_agent.app.services.company_resolver import ResolutionStatus
from finsight_agent.app.services import resolver_loader
from finsight_agent.app.services.resolver_loader import (
    CompanyResolverLoadError,
    build_company_resolver,
    build_sec_company_resolver,
    build_static_company_resolver,
    get_cached_company_resolver,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FakeSECClient:
    def __init__(self, mapping: dict) -> None:
        self.mapping = mapping
        self.calls = 0

    def fetch_company_tickers(self) -> dict:
        self.calls += 1
        return self.mapping


class FailingSECClient:
    def fetch_company_tickers(self) -> dict:
        raise RuntimeError("SEC unavailable")


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def test_build_sec_company_resolver_loads_sec_ticker_mapping() -> None:
    sec_client = FakeSECClient(load_fixture("sec_company_tickers.json"))

    resolver = build_sec_company_resolver(sec_client)
    result = resolver.resolve("AAPL")

    assert sec_client.calls == 1
    assert result.status == ResolutionStatus.EXACT_TICKER_MATCH
    assert result.company is not None
    assert result.company.company_name == "Apple Inc."
    assert result.company.cik == "0000320193"


def test_build_sec_company_resolver_rejects_empty_usable_mapping() -> None:
    sec_client = FakeSECClient(
        {
            "0": {"cik_str": "not-a-cik", "ticker": "BAD", "title": "Bad CIK Inc."},
            "1": {"cik_str": 123456, "ticker": "", "title": "Missing Ticker Inc."},
        }
    )

    with pytest.raises(CompanyResolverLoadError, match="no usable company records"):
        build_sec_company_resolver(sec_client)


def test_build_sec_company_resolver_rejects_malformed_top_level_mapping() -> None:
    sec_client = FakeSECClient([])

    with pytest.raises(CompanyResolverLoadError, match="SEC company ticker mapping"):
        build_sec_company_resolver(sec_client)


def test_build_company_resolver_falls_back_to_static_resolver_when_sec_load_fails() -> None:
    resolver = build_company_resolver(sec_client=FailingSECClient())

    result = resolver.resolve("NVDA")

    assert result.status == ResolutionStatus.EXACT_TICKER_MATCH
    assert result.company is not None
    assert result.company.cik == "0001045810"


def test_build_static_company_resolver_supports_mvp_tickers() -> None:
    resolver = build_static_company_resolver()

    apple = resolver.resolve("AAPL")
    microsoft = resolver.resolve("MSFT")
    tesla = resolver.resolve("TSLA")
    nvidia = resolver.resolve("NVDA")

    assert apple.company is not None
    assert apple.company.cik == "0000320193"
    assert microsoft.company is not None
    assert microsoft.company.cik == "0000789019"
    assert tesla.company is not None
    assert tesla.company.cik == "0001318605"
    assert nvidia.company is not None
    assert nvidia.company.cik == "0001045810"


def test_get_cached_company_resolver_reuses_loaded_resolver(monkeypatch) -> None:
    sec_client = FakeSECClient(load_fixture("sec_company_tickers.json"))

    monkeypatch.setattr(
        resolver_loader,
        "get_settings",
        lambda: SimpleNamespace(
            sec_user_agent="FinSightTest/0.1 test@example.com",
            sec_cache_dir=".tmp/sec-cache",
            sec_cache_ttl_seconds=3600.0,
            sec_request_interval_seconds=0.25,
        ),
    )
    monkeypatch.setattr(
        resolver_loader,
        "SECClient",
        lambda user_agent,
        cache_dir=None,
        cache_ttl_seconds=None,
        min_request_interval_seconds=0.0: sec_client,
    )
    get_cached_company_resolver.cache_clear()

    first_resolver = get_cached_company_resolver()
    second_resolver = get_cached_company_resolver()

    assert first_resolver is second_resolver
    assert sec_client.calls == 1

    get_cached_company_resolver.cache_clear()


def test_build_company_resolver_passes_sec_settings(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class CapturingSECClient(FakeSECClient):
        def __init__(
            self,
            user_agent: str,
            cache_dir: str | None = None,
            cache_ttl_seconds: float | None = None,
            min_request_interval_seconds: float = 0.0,
        ) -> None:
            super().__init__(load_fixture("sec_company_tickers.json"))
            captured["user_agent"] = user_agent
            captured["cache_dir"] = cache_dir
            captured["cache_ttl_seconds"] = cache_ttl_seconds
            captured["min_request_interval_seconds"] = min_request_interval_seconds

    monkeypatch.setattr(
        resolver_loader,
        "get_settings",
        lambda: SimpleNamespace(
            sec_user_agent="FinSightTest/0.1 test@example.com",
            sec_cache_dir=".tmp/sec-cache",
            sec_cache_ttl_seconds=3600.0,
            sec_request_interval_seconds=0.25,
        ),
    )
    monkeypatch.setattr(resolver_loader, "SECClient", CapturingSECClient)

    resolver = build_company_resolver()
    result = resolver.resolve("AAPL")

    assert captured == {
        "user_agent": "FinSightTest/0.1 test@example.com",
        "cache_dir": ".tmp/sec-cache",
        "cache_ttl_seconds": 3600.0,
        "min_request_interval_seconds": 0.25,
    }
    assert result.status == ResolutionStatus.EXACT_TICKER_MATCH
