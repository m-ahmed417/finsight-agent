from types import SimpleNamespace

import pytest

from finsight_agent.app.services.llm_client import (
    MockLLMClient,
    get_llm_client,
)


def sample_risk_factors() -> list[dict]:
    return [
        {
            "form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "0000320193-24-000123",
            "source_url": "https://www.sec.gov/filing.htm",
            "text": (
                "The Company faces intense competition. Supply chain disruption "
                "and component shortages could affect operations."
            ),
        }
    ]


def test_mock_llm_client_returns_deterministic_structured_risk_themes() -> None:
    client = MockLLMClient()

    result = client.summarize_risks(sample_risk_factors())

    assert result["warnings"] == []
    assert [theme["title"] for theme in result["themes"]] == [
        "Competitive pressure",
        "Supply chain and manufacturing disruption",
    ]
    assert result["themes"][0]["source_form"] == "10-K"
    assert result["themes"][0]["accession_number"] == "0000320193-24-000123"


def test_get_llm_client_returns_mock_provider_by_default() -> None:
    client = get_llm_client(SimpleNamespace(llm_provider="mock"))

    assert isinstance(client, MockLLMClient)


def test_get_llm_client_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        get_llm_client(SimpleNamespace(llm_provider="not-real"))
