from functools import lru_cache
from typing import Any

from finsight_agent.app.config import get_settings
from finsight_agent.app.services.company_resolver import (
    CompanyRecord,
    CompanyResolver,
    load_sec_company_tickers,
)
from finsight_agent.app.services.sec_client import SECClient


class CompanyResolverLoadError(RuntimeError):
    """Raised when a resolver cannot be built from SEC ticker data."""


def build_static_company_resolver() -> CompanyResolver:
    return CompanyResolver(
        companies=[
            CompanyRecord(ticker="AAPL", company_name="Apple Inc.", cik="320193"),
            CompanyRecord(
                ticker="MSFT",
                company_name="Microsoft Corporation",
                cik="789019",
            ),
            CompanyRecord(ticker="TSLA", company_name="Tesla, Inc.", cik="1318605"),
            CompanyRecord(
                ticker="NVDA",
                company_name="NVIDIA Corporation",
                cik="1045810",
            ),
        ]
    )


def build_sec_company_resolver(sec_client: Any) -> CompanyResolver:
    sec_mapping = sec_client.fetch_company_tickers()
    if not isinstance(sec_mapping, dict):
        msg = "SEC company ticker mapping must be a JSON object."
        raise CompanyResolverLoadError(msg)

    companies = load_sec_company_tickers(sec_mapping)
    if not companies:
        msg = "SEC company ticker mapping contained no usable company records."
        raise CompanyResolverLoadError(msg)

    return CompanyResolver(companies=companies)


def build_company_resolver(sec_client: Any | None = None) -> CompanyResolver:
    configured_sec_client = sec_client
    if configured_sec_client is None:
        settings = get_settings()
        configured_sec_client = SECClient(user_agent=settings.sec_user_agent)

    try:
        return build_sec_company_resolver(configured_sec_client)
    except (AttributeError, CompanyResolverLoadError, RuntimeError, TypeError, ValueError):
        return build_static_company_resolver()


@lru_cache
def get_cached_company_resolver() -> CompanyResolver:
    return build_company_resolver()
