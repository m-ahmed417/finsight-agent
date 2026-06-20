import json
from types import SimpleNamespace

import pytest

from finsight_agent.app.services.llm_client import (
    ChatModelLLMClient,
    LLMClientError,
    MAX_RISK_FACTOR_TEXT_CHARS,
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
            "source_ids": ["latest_10k"],
            "text": (
                "The Company faces intense competition. Supply chain disruption "
                "and component shortages could affect operations."
            ),
        }
    ]


def test_mock_llm_client_returns_deterministic_structured_risk_themes() -> None:
    client = MockLLMClient()

    result = client.summarize_risks(sample_risk_factors())

    assert client.provider == "mock"
    assert client.model_name == "mock"
    assert result["warnings"] == []
    assert [theme["title"] for theme in result["themes"]] == [
        "Competitive pressure",
        "Supply chain and manufacturing disruption",
    ]
    assert result["themes"][0]["source_form"] == "10-K"
    assert result["themes"][0]["accession_number"] == "0000320193-24-000123"
    assert result["themes"][0]["source_ids"] == ["latest_10k"]


def sample_report_evidence() -> dict:
    return {
        "company_name": "Apple Inc.",
        "ticker": "AAPL",
        "financial_metrics": {
            "periods": [
                {
                    "fy": 2024,
                    "revenue": 1250000000,
                    "revenue_growth": 0.25,
                    "free_cash_flow": 280000000,
                }
            ]
        },
        "risk_themes": [
            {
                "title": "Competitive pressure",
                "summary": "Competition could pressure operating performance.",
                "source_ids": ["latest_10k"],
            }
        ],
        "research_insights": {
            "executive_summary": [
                "Apple Inc. (AAPL) was reviewed using available SEC-derived evidence."
            ],
            "bull_case": [
                {
                    "title": "Revenue growth",
                    "summary": "Revenue increased.",
                    "source_ids": ["sec_company_facts"],
                }
            ],
            "bear_case": [
                {
                    "title": "Competitive pressure",
                    "summary": "Competition is a risk.",
                    "source_ids": ["latest_10k"],
                }
            ],
            "open_questions": ["Are revenue growth and cash flow durable?"],
        },
        "sources": [
            {
                "source_id": "sec_company_facts",
                "label": "SEC company facts",
                "url": "https://example.com",
            }
        ],
        "warnings": [],
    }


def test_mock_llm_client_returns_deterministic_report_sections() -> None:
    client = MockLLMClient()

    result = client.draft_report(sample_report_evidence())

    assert result["warnings"] == []
    assert result["sections"]["executive_summary"] == [
        "Apple Inc. (AAPL) was reviewed using available SEC-derived evidence."
    ]
    assert result["sections"]["financial_performance"] == (
        "For fiscal 2024, extracted revenue was 1250000000 "
        "and free cash flow was 280000000. [sec_company_facts]"
    )
    assert result["sections"]["risk_factors"] == [
        "Competitive pressure: Competition could pressure operating performance. [latest_10k]"
    ]


def test_get_llm_client_returns_mock_provider_by_default() -> None:
    client = get_llm_client(SimpleNamespace(llm_provider="mock", llm_model="mock"))

    assert isinstance(client, MockLLMClient)


class FakeMessage:
    def __init__(
        self,
        content: str,
        *,
        usage_metadata: dict | None = None,
        response_metadata: dict | None = None,
        message_id: str | None = None,
    ) -> None:
        self.content = content
        self.usage_metadata = usage_metadata
        self.response_metadata = response_metadata or {}
        self.id = message_id


class FakeChatModel:
    def __init__(
        self,
        content: str,
        *,
        usage_metadata: dict | None = None,
        response_metadata: dict | None = None,
        message_id: str | None = None,
    ) -> None:
        self.content = content
        self.usage_metadata = usage_metadata
        self.response_metadata = response_metadata
        self.message_id = message_id
        self.messages = None

    def invoke(self, messages: list[dict[str, str]]) -> FakeMessage:
        self.messages = messages
        return FakeMessage(
            self.content,
            usage_metadata=self.usage_metadata,
            response_metadata=self.response_metadata,
            message_id=self.message_id,
        )


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
                "source_ids": ["latest_10k"],
            }
        ],
        "warnings": [],
    }
    assert chat_model.messages is not None
    assert chat_model.messages[0]["role"] == "system"
    assert "neutral equity research" in chat_model.messages[0]["content"]


def test_chat_model_llm_client_captures_last_call_metadata() -> None:
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
        """,
        usage_metadata={
            "input_tokens": 120,
            "output_tokens": 42,
            "total_tokens": 162,
        },
        response_metadata={"id": "provider-response-id"},
        message_id="message-id",
    )
    client = ChatModelLLMClient(chat_model=chat_model, model_name="fake-model")

    client.summarize_risks(sample_risk_factors())
    user_payload = json.loads(chat_model.messages[1]["content"])

    assert user_payload["prompt_version"] == "risk_analysis:v1"
    assert client.last_call_metadata == {
        "input_tokens": 120,
        "output_tokens": 42,
        "total_tokens": 162,
        "provider_request_id": "provider-response-id",
    }


def test_chat_model_llm_client_risk_prompt_preserves_source_contract() -> None:
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
    risk_factors = [
        {
            **sample_risk_factors()[0],
            "openai_api_key": "sk-test-secret",
            "database_url": "sqlite:///C:/Users/Mohammed/Documents/private.db",
            "local_file_path": "C:/Users/Mohammed/Documents/private-filing.htm",
            "environment": {"DEEPSEEK_API_KEY": "deepseek-secret"},
        }
    ]

    client.summarize_risks(risk_factors)
    user_payload = json.loads(chat_model.messages[1]["content"])
    risk_payload_text = json.dumps(user_payload, sort_keys=True)

    assert user_payload["task"] == "Summarize extracted SEC risk-factor text."
    assert user_payload["prompt_version"] == "risk_analysis:v1"
    assert user_payload["required_schema"] == {
        "themes": [{"title": "string", "summary": "string"}],
        "warnings": ["optional string warnings"],
    }
    assert user_payload["risk_factors"][0]["source_ids"] == ["latest_10k"]
    assert user_payload["risk_factors"][0]["form"] == "10-K"
    assert user_payload["risk_factors"][0]["filing_date"] == "2024-11-01"
    assert user_payload["risk_factors"][0]["accession_number"] == (
        "0000320193-24-000123"
    )
    assert "sk-test-secret" not in risk_payload_text
    assert "deepseek-secret" not in risk_payload_text
    assert "private.db" not in risk_payload_text
    assert "private-filing.htm" not in risk_payload_text


def test_chat_model_llm_client_truncates_large_risk_factor_text() -> None:
    long_text = "A" * (MAX_RISK_FACTOR_TEXT_CHARS + 25)
    risk_factors = [
        {
            "form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "0000320193-24-000123",
            "source_url": "https://www.sec.gov/filing.htm",
            "source_ids": ["latest_10k"],
            "text": long_text,
        }
    ]
    chat_model = FakeChatModel(
        """
        {
          "themes": [
            {
              "title": "Large risk section",
              "summary": "The risk section was summarized from truncated input."
            }
          ]
        }
        """
    )
    client = ChatModelLLMClient(chat_model=chat_model, model_name="fake-model")

    result = client.summarize_risks(risk_factors)
    user_payload = json.loads(chat_model.messages[1]["content"])

    assert len(user_payload["risk_factors"][0]["text"]) == MAX_RISK_FACTOR_TEXT_CHARS
    assert user_payload["risk_factors"][0]["source_ids"] == ["latest_10k"]
    assert result["warnings"] == [
        {
            "code": "llm_input_truncated",
            "message": (
                "Risk-factor text was truncated to "
                f"{MAX_RISK_FACTOR_TEXT_CHARS} characters before LLM analysis."
            ),
            "severity": "warning",
        }
    ]


def test_chat_model_llm_client_rejects_invalid_json() -> None:
    client = ChatModelLLMClient(
        chat_model=FakeChatModel("not-json"),
        model_name="fake-model",
    )

    with pytest.raises(LLMClientError, match="valid JSON"):
        client.summarize_risks(sample_risk_factors())


def test_chat_model_llm_client_rejects_empty_themes() -> None:
    client = ChatModelLLMClient(
        chat_model=FakeChatModel('{"themes": []}'),
        model_name="fake-model",
    )

    with pytest.raises(LLMClientError, match="at least one theme"):
        client.summarize_risks(sample_risk_factors())


def test_chat_model_llm_client_rejects_blank_theme_fields() -> None:
    client = ChatModelLLMClient(
        chat_model=FakeChatModel('{"themes": [{"title": " ", "summary": ""}]}'),
        model_name="fake-model",
    )

    with pytest.raises(LLMClientError, match="valid risk themes"):
        client.summarize_risks(sample_risk_factors())


def test_chat_model_llm_client_parses_structured_report_sections() -> None:
    chat_model = FakeChatModel(
        """
        {
          "executive_summary": ["LLM-written summary."],
          "financial_performance": "LLM-written financial performance.",
          "risk_factors": ["LLM-written risk factor."],
          "bull_case": ["LLM-written bull case."],
          "bear_case": ["LLM-written bear case."],
          "open_questions": ["LLM-written open question."]
        }
        """
    )
    client = ChatModelLLMClient(chat_model=chat_model, model_name="fake-model")

    result = client.draft_report(sample_report_evidence())

    assert result == {
        "sections": {
            "executive_summary": ["LLM-written summary."],
            "financial_performance": "LLM-written financial performance.",
            "risk_factors": ["LLM-written risk factor."],
            "bull_case": ["LLM-written bull case."],
            "bear_case": ["LLM-written bear case."],
            "open_questions": ["LLM-written open question."],
        },
        "warnings": [],
    }
    assert chat_model.messages[0]["role"] == "system"
    assert "source-grounded research brief sections" in chat_model.messages[0]["content"]


def test_chat_model_llm_client_report_prompt_uses_sanitized_evidence_contract() -> None:
    chat_model = FakeChatModel(
        """
        {
          "executive_summary": ["LLM-written summary."],
          "financial_performance": "LLM-written financial performance. [sec_company_facts]",
          "risk_factors": ["LLM-written risk factor. [latest_10k]"],
          "bull_case": ["LLM-written bull case. [sec_company_facts]"],
          "bear_case": ["LLM-written bear case. [latest_10k]"],
          "open_questions": ["LLM-written open question."]
        }
        """
    )
    client = ChatModelLLMClient(chat_model=chat_model, model_name="fake-model")
    evidence = {
        **sample_report_evidence(),
        "business_overview": {
            "status": "available",
            "summary": "Item 1 Business evidence is available.",
            "source_ids": ["latest_10k"],
            "source": "10-K filed 2024-11-01, accession 0000320193-24-000123",
        },
        "latest_10k": {
            "form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "0000320193-24-000123",
        },
        "openai_api_key": "sk-test-secret",
        "database_url": "postgresql://user:pass@localhost/finsight",
        "local_file_path": "C:/Users/Mohammed/Documents/private-report.json",
        "environment": {"DEEPSEEK_API_KEY": "deepseek-secret"},
    }

    client.draft_report(evidence)
    system_prompt = chat_model.messages[0]["content"]
    user_payload = json.loads(chat_model.messages[1]["content"])
    evidence_payload = user_payload["evidence"]
    report_payload_text = json.dumps(user_payload, sort_keys=True)

    assert "Do not invent citations" in system_prompt
    assert "provided evidence" in system_prompt
    assert "price predictions" in system_prompt
    assert "financial advice" in system_prompt
    assert user_payload["task"] == "Draft source-grounded research brief sections."
    assert user_payload["prompt_version"] == "report_drafting:v1"
    assert user_payload["required_schema"] == {
        "executive_summary": ["string"],
        "financial_performance": "string",
        "risk_factors": ["string"],
        "bull_case": ["string"],
        "bear_case": ["string"],
        "open_questions": ["string"],
        "warnings": ["optional string warnings"],
    }
    assert evidence_payload["business_overview"]["source_ids"] == ["latest_10k"]
    assert evidence_payload["business_overview"]["summary"] == (
        "Item 1 Business evidence is available."
    )
    assert evidence_payload["sources"] == sample_report_evidence()["sources"]
    assert evidence_payload["research_insights"] == sample_report_evidence()[
        "research_insights"
    ]
    assert evidence_payload["financial_metrics"] == sample_report_evidence()[
        "financial_metrics"
    ]
    assert evidence_payload["risk_themes"] == sample_report_evidence()["risk_themes"]
    assert evidence_payload["warnings"] == []
    assert "sk-test-secret" not in report_payload_text
    assert "deepseek-secret" not in report_payload_text
    assert "localhost/finsight" not in report_payload_text
    assert "private-report.json" not in report_payload_text


def test_chat_model_llm_client_rejects_invalid_report_sections() -> None:
    client = ChatModelLLMClient(
        chat_model=FakeChatModel('{"executive_summary": []}'),
        model_name="fake-model",
    )

    with pytest.raises(LLMClientError, match="valid report sections"):
        client.draft_report(sample_report_evidence())


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
    assert client.provider == "openai"
    assert client.model_name == "gpt-test-model"
    assert calls == [
        {
            "model": "gpt-test-model",
            "model_provider": "openai",
            "api_key": "openai-test-key",
        }
    ]


def test_get_llm_client_normalizes_real_provider_model(monkeypatch) -> None:
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
            llm_provider=" OpenAI ",
            llm_model=" gpt-test-model ",
            openai_api_key="openai-test-key",
        )
    )

    assert isinstance(client, ChatModelLLMClient)
    assert client.provider == "openai"
    assert client.model_name == "gpt-test-model"
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
    assert client.provider == "deepseek"
    assert client.model_name == "deepseek-test-model"
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


def test_get_llm_client_rejects_missing_openai_api_key() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY must be configured"):
        get_llm_client(
            SimpleNamespace(
                llm_provider="openai",
                llm_model="gpt-test-model",
                openai_api_key=" ",
            )
        )


def test_get_llm_client_rejects_blank_real_provider_model(monkeypatch) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("init_chat_model should not be called")

    monkeypatch.setattr(
        "finsight_agent.app.services.llm_client.init_chat_model",
        fail_if_called,
    )

    with pytest.raises(
        ValueError,
        match="LLM_MODEL must be configured when LLM_PROVIDER=openai",
    ):
        get_llm_client(
            SimpleNamespace(
                llm_provider="openai",
                llm_model=" ",
                openai_api_key="openai-test-key",
            )
        )


def test_get_llm_client_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        get_llm_client(SimpleNamespace(llm_provider="not-real", llm_model="mock"))
