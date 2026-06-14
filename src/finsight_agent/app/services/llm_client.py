from typing import Any, Protocol

from finsight_agent.app.config import Settings, get_settings
from finsight_agent.app.services.risk_analyzer import analyze_risk_factors


class LLMClient(Protocol):
    def summarize_risks(self, risk_factors: list[dict[str, Any]]) -> dict[str, Any]:
        """Return structured risk themes from extracted risk-factor text."""


class MockLLMClient:
    def summarize_risks(self, risk_factors: list[dict[str, Any]]) -> dict[str, Any]:
        return analyze_risk_factors(risk_factors)


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    configured_settings = settings or get_settings()
    provider = configured_settings.llm_provider.strip().casefold()
    if provider == "mock":
        return MockLLMClient()

    msg = f"Unsupported LLM provider: {configured_settings.llm_provider}"
    raise ValueError(msg)
