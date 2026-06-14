import json
from typing import Any, Protocol

from langchain.chat_models import init_chat_model

from finsight_agent.app.config import Settings, get_settings
from finsight_agent.app.services.risk_analyzer import analyze_risk_factors


class LLMClient(Protocol):
    def summarize_risks(self, risk_factors: list[dict[str, Any]]) -> dict[str, Any]:
        """Return structured risk themes from extracted risk-factor text."""


class LLMClientError(RuntimeError):
    """Raised when an LLM provider returns unusable output."""


class MockLLMClient:
    def summarize_risks(self, risk_factors: list[dict[str, Any]]) -> dict[str, Any]:
        return analyze_risk_factors(risk_factors)


class ChatModelLLMClient:
    def __init__(self, chat_model: Any, model_name: str) -> None:
        self._chat_model = chat_model
        self._model_name = model_name

    def summarize_risks(self, risk_factors: list[dict[str, Any]]) -> dict[str, Any]:
        response = self._chat_model.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a neutral equity research assistant. Summarize "
                        "risk-factor evidence into structured, source-grounded "
                        "themes. Do not provide financial advice or recommendations. "
                        "Return only valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "Summarize extracted SEC risk-factor text.",
                            "required_schema": {
                                "themes": [
                                    {
                                        "title": "string",
                                        "summary": "string",
                                    }
                                ],
                                "warnings": ["optional string warnings"],
                            },
                            "risk_factors": risk_factors,
                        },
                        sort_keys=True,
                    ),
                },
            ]
        )
        data = _parse_llm_json_response(response)
        return _normalize_risk_theme_response(data, risk_factors)


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    configured_settings = settings or get_settings()
    provider = configured_settings.llm_provider.strip().casefold()
    if provider == "mock":
        return MockLLMClient()
    if provider in {"openai", "deepseek"}:
        api_key = _api_key_for_provider(configured_settings, provider)
        chat_model = init_chat_model(
            configured_settings.llm_model,
            model_provider=provider,
            api_key=api_key,
        )
        return ChatModelLLMClient(
            chat_model=chat_model,
            model_name=configured_settings.llm_model,
        )

    msg = f"Unsupported LLM provider: {configured_settings.llm_provider}"
    raise ValueError(msg)


def _api_key_for_provider(settings: Settings, provider: str) -> Any:
    api_key = getattr(settings, f"{provider}_api_key", None)
    if api_key is None or not _api_key_value(api_key).strip():
        env_var = f"{provider.upper()}_API_KEY"
        msg = f"{env_var} must be configured when LLM_PROVIDER={provider}."
        raise ValueError(msg)
    return api_key


def _api_key_value(api_key: Any) -> str:
    if hasattr(api_key, "get_secret_value"):
        return str(api_key.get_secret_value())
    return str(api_key)


def _parse_llm_json_response(response: Any) -> dict[str, Any]:
    content = getattr(response, "content", response)
    if not isinstance(content, str):
        msg = "LLM response content must be a string containing valid JSON."
        raise LLMClientError(msg)

    try:
        data = json.loads(_strip_json_code_fence(content))
    except json.JSONDecodeError as exc:
        msg = "LLM response must contain valid JSON."
        raise LLMClientError(msg) from exc

    if not isinstance(data, dict):
        msg = "LLM response JSON must be an object."
        raise LLMClientError(msg)

    return data


def _strip_json_code_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _normalize_risk_theme_response(
    data: dict[str, Any],
    risk_factors: list[dict[str, Any]],
) -> dict[str, Any]:
    themes = data.get("themes")
    warnings = data.get("warnings", [])
    if not isinstance(themes, list):
        msg = "LLM risk response must include a themes list."
        raise LLMClientError(msg)
    if not isinstance(warnings, list):
        msg = "LLM risk response warnings must be a list."
        raise LLMClientError(msg)

    source = risk_factors[0] if risk_factors else {}
    normalized_themes = [
        _normalize_theme(theme, source)
        for theme in themes
        if isinstance(theme, dict)
    ]

    return {"themes": normalized_themes, "warnings": warnings}


def _normalize_theme(theme: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(theme.get("title", "Risk theme")),
        "summary": str(theme.get("summary", "No summary available.")),
        "source_form": theme.get("source_form") or source.get("form"),
        "filing_date": theme.get("filing_date") or source.get("filing_date"),
        "accession_number": theme.get("accession_number")
        or source.get("accession_number"),
        "source_url": theme.get("source_url") or source.get("source_url"),
    }
