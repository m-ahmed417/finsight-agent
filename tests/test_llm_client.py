from types import SimpleNamespace

import pytest

from finsight_agent.app.services.llm_client import (
    ChatModelLLMClient,
    LLMClientError,
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
    client = get_llm_client(SimpleNamespace(llm_provider="mock", llm_model="mock"))

    assert isinstance(client, MockLLMClient)


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChatModel:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages = None

    def invoke(self, messages: list[dict[str, str]]) -> FakeMessage:
        self.messages = messages
        return FakeMessage(self.content)


def test_chat_model_llm_client_parses_structured_risk_themes() -> None:
    chat_model = FakeChatModel(
        """
        {
          "themes": [
            {
              "title": "Customer concentration",
              "summary": "The filing describes dependence on major customers."
            }
          ]
        }
        """
    )
    client = ChatModelLLMClient(chat_model=chat_model, model_name="fake-model")

    result = client.summarize_risks(sample_risk_factors())

    assert result == {
        "themes": [
            {
                "title": "Customer concentration",
                "summary": "The filing describes dependence on major customers.",
                "source_form": "10-K",
                "filing_date": "2024-11-01",
                "accession_number": "0000320193-24-000123",
                "source_url": "https://www.sec.gov/filing.htm",
            }
        ],
        "warnings": [],
    }
    assert chat_model.messages is not None
    assert chat_model.messages[0]["role"] == "system"
    assert "neutral equity research" in chat_model.messages[0]["content"]


def test_chat_model_llm_client_rejects_invalid_json() -> None:
    client = ChatModelLLMClient(
        chat_model=FakeChatModel("not-json"),
        model_name="fake-model",
    )

    with pytest.raises(LLMClientError, match="valid JSON"):
        client.summarize_risks(sample_risk_factors())


def test_get_llm_client_builds_openai_provider(monkeypatch) -> None:
    calls = []

    def fake_init_chat_model(model: str, model_provider: str, api_key: str):
        calls.append(
            {"model": model, "model_provider": model_provider, "api_key": api_key}
        )
        return FakeChatModel('{"themes": []}')

    monkeypatch.setattr(
        "finsight_agent.app.services.llm_client.init_chat_model",
        fake_init_chat_model,
    )

    client = get_llm_client(
        SimpleNamespace(
            llm_provider="openai",
            llm_model="gpt-test-model",
            openai_api_key="openai-test-key",
        )
    )

    assert isinstance(client, ChatModelLLMClient)
    assert calls == [
        {
            "model": "gpt-test-model",
            "model_provider": "openai",
            "api_key": "openai-test-key",
        }
    ]


def test_get_llm_client_builds_deepseek_provider(monkeypatch) -> None:
    calls = []

    def fake_init_chat_model(model: str, model_provider: str, api_key: str):
        calls.append(
            {"model": model, "model_provider": model_provider, "api_key": api_key}
        )
        return FakeChatModel('{"themes": []}')

    monkeypatch.setattr(
        "finsight_agent.app.services.llm_client.init_chat_model",
        fake_init_chat_model,
    )

    client = get_llm_client(
        SimpleNamespace(
            llm_provider="deepseek",
            llm_model="deepseek-test-model",
            deepseek_api_key="deepseek-test-key",
        )
    )

    assert isinstance(client, ChatModelLLMClient)
    assert calls == [
        {
            "model": "deepseek-test-model",
            "model_provider": "deepseek",
            "api_key": "deepseek-test-key",
        }
    ]


def test_get_llm_client_rejects_missing_provider_api_key() -> None:
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY must be configured"):
        get_llm_client(
            SimpleNamespace(
                llm_provider="deepseek",
                llm_model="deepseek-test-model",
                deepseek_api_key="",
            )
        )


def test_get_llm_client_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        get_llm_client(SimpleNamespace(llm_provider="not-real", llm_model="mock"))
