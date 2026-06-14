from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from finsight_agent.app.api.dependencies import get_company_resolver
from finsight_agent.app.main import app
from finsight_agent.app.services.company_resolver import CompanyRecord, CompanyResolver


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


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
            CompanyRecord(ticker="MSFT", company_name="Microsoft Corporation", cik="789019"),
        ]
    )


def test_companies_search_returns_matching_companies(
    client: TestClient,
    resolver: CompanyResolver,
) -> None:
    app.dependency_overrides[get_company_resolver] = lambda: resolver

    response = client.get("/companies/search", params={"q": "apple"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "cik": "0000320193",
            "exchange": None,
        },
        {
            "ticker": "APLE",
            "company_name": "Apple Hospitality REIT, Inc.",
            "cik": "0001418121",
            "exchange": None,
        },
    ]


def test_companies_search_supports_ticker_query(
    client: TestClient,
    resolver: CompanyResolver,
) -> None:
    app.dependency_overrides[get_company_resolver] = lambda: resolver

    response = client.get("/companies/search", params={"q": "msft"})

    assert response.status_code == 200
    assert response.json()[0]["ticker"] == "MSFT"


def test_companies_search_rejects_blank_query(
    client: TestClient,
    resolver: CompanyResolver,
) -> None:
    app.dependency_overrides[get_company_resolver] = lambda: resolver

    response = client.get("/companies/search", params={"q": "   "})

    assert response.status_code == 422
