import json
from typing import Any, Protocol

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field, ValidationError, field_validator

from finsight_agent.app.config import Settings, get_settings
from finsight_agent.app.services.risk_analyzer import analyze_risk_factors

MAX_RISK_FACTOR_TEXT_CHARS = 12000
RISK_ANALYSIS_PROMPT_VERSION = "risk_analysis:v1"
REPORT_DRAFT_PROMPT_VERSION = "report_drafting:v1"
SENSITIVE_PROMPT_KEY_FRAGMENTS = (
    "api_key",
    "secret",
    "password",
    "token",
    "database_url",
    "local_file_path",
    "local_path",
    "environment",
)


class LLMClient(Protocol):
    def summarize_risks(self, risk_factors: list[dict[str, Any]]) -> dict[str, Any]:
        """Return structured risk themes from extracted risk-factor text."""

    def draft_report(self, evidence: dict[str, Any]) -> dict[str, Any]:
        """Return structured report sections from validated research evidence."""


class LLMClientError(RuntimeError):
    """Raised when an LLM provider returns unusable output."""


class RiskThemeLLMOutput(BaseModel):
    title: str
    summary: str

    @field_validator("title", "summary")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            msg = "Risk theme fields cannot be blank."
            raise ValueError(msg)
        return normalized


class RiskSummaryLLMResponse(BaseModel):
    themes: list[RiskThemeLLMOutput] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)


class ReportDraftLLMResponse(BaseModel):
    executive_summary: list[str] = Field(min_length=1)
    financial_performance: str
    risk_factors: list[str] = Field(min_length=1)
    bull_case: list[str] = Field(min_length=1)
    bear_case: list[str] = Field(min_length=1)
    open_questions: list[str] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("financial_performance")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            msg = "Report draft text cannot be blank."
            raise ValueError(msg)
        return normalized

    @field_validator(
        "executive_summary",
        "risk_factors",
        "bull_case",
        "bear_case",
        "open_questions",
    )
    @classmethod
    def list_items_must_not_be_blank(cls, value: list[str]) -> list[str]:
        normalized_items = [" ".join(item.strip().split()) for item in value]
        if any(not item for item in normalized_items):
            msg = "Report draft list items cannot be blank."
            raise ValueError(msg)
        return normalized_items


class MockLLMClient:
    provider = "mock"
    model_name = "mock"

    def __init__(self) -> None:
        self.last_call_metadata: dict[str, Any] = {}

    def summarize_risks(self, risk_factors: list[dict[str, Any]]) -> dict[str, Any]:
        return analyze_risk_factors(risk_factors)

    def draft_report(self, evidence: dict[str, Any]) -> dict[str, Any]:
        insights = evidence.get("research_insights") or {}
        periods = (evidence.get("financial_metrics") or {}).get("periods", [])
        latest_period = periods[-1] if periods else {}
        fiscal_year = latest_period.get("fy", "latest available period")
        revenue = latest_period.get("revenue", "N/A")
        free_cash_flow = latest_period.get("free_cash_flow", "N/A")
        risk_themes = evidence.get("risk_themes") or []

        return {
            "sections": {
                "executive_summary": insights.get("executive_summary")
                or [
                    f"{evidence.get('company_name', 'The company')} ({evidence.get('ticker', 'UNKNOWN')}) was reviewed using available SEC-derived evidence."
                ],
                "financial_performance": (
                    f"For fiscal {fiscal_year}, extracted revenue was {revenue} "
                    f"and free cash flow was {free_cash_flow}. [sec_company_facts]"
                ),
                "risk_factors": [
                    (
                        f"{theme.get('title', 'Risk theme')}: "
                        f"{theme.get('summary', 'No summary available.')}"
                        f"{_citation_suffix(theme.get('source_ids'))}"
                    )
                    for theme in risk_themes
                ]
                or ["No source-grounded risk themes were available."],
                "bull_case": [
                    _research_point_to_text(point)
                    for point in insights.get("bull_case", [])
                ]
                or ["No deterministic bull-case points were available."],
                "bear_case": [
                    _research_point_to_text(point)
                    for point in insights.get("bear_case", [])
                ]
                or ["No deterministic bear-case points were available."],
                "open_questions": insights.get("open_questions")
                or ["Which additional source evidence should be reviewed?"],
            },
            "warnings": [],
        }


class ChatModelLLMClient:
    def __init__(
        self,
        chat_model: Any,
        model_name: str,
        provider: str = "unknown",
    ) -> None:
        self._chat_model = chat_model
        self.provider = provider
        self.model_name = model_name
        self.last_call_metadata: dict[str, Any] = {}

    def summarize_risks(self, risk_factors: list[dict[str, Any]]) -> dict[str, Any]:
        prepared_risk_factors, truncation_warnings = _prepare_risk_factors_for_llm(
            risk_factors
        )
        prompt_risk_factors = _sanitize_prompt_value(prepared_risk_factors)
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
                            "prompt_version": RISK_ANALYSIS_PROMPT_VERSION,
                            "required_schema": {
                                "themes": [
                                    {
                                        "title": "string",
                                        "summary": "string",
                                    }
                                ],
                                "warnings": ["optional string warnings"],
                            },
                            "risk_factors": prompt_risk_factors,
                        },
                        sort_keys=True,
                    ),
                },
            ]
        )
        self.last_call_metadata = _model_response_metadata(response)
        data = _parse_llm_json_response(response)
        result = _normalize_risk_theme_response(data, risk_factors)
        return {
            "themes": result["themes"],
            "warnings": [*truncation_warnings, *result["warnings"]],
        }

    def draft_report(self, evidence: dict[str, Any]) -> dict[str, Any]:
        response = self._chat_model.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a neutral equity research assistant. Draft "
                        "source-grounded research brief sections only from the "
                        "provided evidence. Do not provide financial advice, "
                        "recommendations, price predictions, or unsupported facts. "
                        "Do not invent citations. Only use source_id citation "
                        "markers present in the provided evidence. "
                        "Use source_id citation markers from the evidence where "
                        "available. Return only valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "Draft source-grounded research brief sections.",
                            "prompt_version": REPORT_DRAFT_PROMPT_VERSION,
                            "required_schema": {
                                "executive_summary": ["string"],
                                "financial_performance": "string",
                                "risk_factors": ["string"],
                                "bull_case": ["string"],
                                "bear_case": ["string"],
                                "open_questions": ["string"],
                                "warnings": ["optional string warnings"],
                            },
                            "evidence": _sanitize_prompt_value(evidence),
                        },
                        sort_keys=True,
                    ),
                },
            ]
        )
        self.last_call_metadata = _model_response_metadata(response)
        data = _parse_llm_json_response(response)
        return _normalize_report_draft_response(data)


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    configured_settings = settings or get_settings()
    provider = configured_settings.llm_provider.strip().casefold()
    if provider == "mock":
        return MockLLMClient()
    if provider in {"openai", "deepseek"}:
        api_key = _api_key_for_provider(configured_settings, provider)
        model_name = _model_name_for_provider(configured_settings, provider)
        chat_model = init_chat_model(
            model_name,
            model_provider=provider,
            api_key=api_key,
        )
        return ChatModelLLMClient(
            chat_model=chat_model,
            model_name=model_name,
            provider=provider,
        )

    msg = f"Unsupported LLM provider: {configured_settings.llm_provider}"
    raise ValueError(msg)


def _model_name_for_provider(settings: Settings, provider: str) -> str:
    model_name = str(settings.llm_model).strip()
    if not model_name:
        msg = f"LLM_MODEL must be configured when LLM_PROVIDER={provider}."
        raise ValueError(msg)
    return model_name


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


def _model_response_metadata(response: Any) -> dict[str, Any]:
    usage_metadata = getattr(response, "usage_metadata", None)
    response_metadata = getattr(response, "response_metadata", None) or {}
    if not isinstance(response_metadata, dict):
        response_metadata = {}
    if not isinstance(usage_metadata, dict):
        usage_metadata = _token_usage_metadata(response_metadata)

    metadata = {
        "input_tokens": _optional_non_negative_int(
            usage_metadata.get("input_tokens")
            or usage_metadata.get("prompt_tokens")
            or usage_metadata.get("input_token_count")
        ),
        "output_tokens": _optional_non_negative_int(
            usage_metadata.get("output_tokens")
            or usage_metadata.get("completion_tokens")
            or usage_metadata.get("output_token_count")
        ),
        "total_tokens": _optional_non_negative_int(
            usage_metadata.get("total_tokens")
            or usage_metadata.get("total_token_count")
        ),
        "provider_request_id": _optional_text(
            response_metadata.get("id")
            or response_metadata.get("request_id")
            or getattr(response, "id", None)
        ),
    }
    return {key: value for key, value in metadata.items() if value is not None}


def _token_usage_metadata(response_metadata: dict[str, Any]) -> dict[str, Any]:
    token_usage = response_metadata.get("token_usage")
    if isinstance(token_usage, dict):
        return token_usage
    return {}


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
    try:
        parsed = RiskSummaryLLMResponse.model_validate(data)
    except ValidationError as exc:
        if data.get("themes") == []:
            msg = "LLM risk analysis must include at least one theme."
        else:
            msg = "LLM risk response must include valid risk themes."
        raise LLMClientError(msg) from exc

    source = risk_factors[0] if risk_factors else {}
    normalized_themes = [_normalize_theme(theme, source) for theme in parsed.themes]

    return {
        "themes": normalized_themes,
        "warnings": [_llm_warning(warning) for warning in parsed.warnings],
    }


def _normalize_report_draft_response(data: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = ReportDraftLLMResponse.model_validate(data)
    except ValidationError as exc:
        msg = "LLM report draft must include valid report sections."
        raise LLMClientError(msg) from exc

    return {
        "sections": {
            "executive_summary": parsed.executive_summary,
            "financial_performance": parsed.financial_performance,
            "risk_factors": parsed.risk_factors,
            "bull_case": parsed.bull_case,
            "bear_case": parsed.bear_case,
            "open_questions": parsed.open_questions,
        },
        "warnings": [_llm_warning(warning) for warning in parsed.warnings],
    }


def _normalize_theme(
    theme: RiskThemeLLMOutput,
    source: dict[str, Any],
) -> dict[str, Any]:
    return {
        "title": theme.title,
        "summary": theme.summary,
        "source_form": source.get("form"),
        "filing_date": source.get("filing_date"),
        "accession_number": source.get("accession_number"),
        "source_url": source.get("source_url"),
        "source_ids": _source_ids(source),
    }


def _prepare_risk_factors_for_llm(
    risk_factors: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    prepared: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    truncated = False
    for risk_factor in risk_factors:
        prepared_risk_factor = dict(risk_factor)
        text = str(prepared_risk_factor.get("text", ""))
        if len(text) > MAX_RISK_FACTOR_TEXT_CHARS:
            prepared_risk_factor["text"] = text[:MAX_RISK_FACTOR_TEXT_CHARS]
            truncated = True
        prepared.append(prepared_risk_factor)

    if truncated:
        warnings.append(
            {
                "code": "llm_input_truncated",
                "message": (
                    "Risk-factor text was truncated to "
                    f"{MAX_RISK_FACTOR_TEXT_CHARS} characters before LLM analysis."
                ),
                "severity": "warning",
            }
        )

    return prepared, warnings


def _sanitize_prompt_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_prompt_value(item)
            for key, item in value.items()
            if not _is_sensitive_prompt_key(key)
        }
    if isinstance(value, list):
        return [_sanitize_prompt_value(item) for item in value]
    return value


def _is_sensitive_prompt_key(key: Any) -> bool:
    normalized = str(key).strip().casefold()
    return any(fragment in normalized for fragment in SENSITIVE_PROMPT_KEY_FRAGMENTS)


def _llm_warning(message: str) -> dict[str, str]:
    return {
        "code": "llm_risk_analysis_warning",
        "message": message,
        "severity": "warning",
    }


def _research_point_to_text(point: dict[str, Any]) -> str:
    title = point.get("title", "Research point")
    summary = point.get("summary", "No summary available.")
    return f"{title}: {summary}{_citation_suffix(point.get('source_ids'))}"


def _source_ids(source: dict[str, Any]) -> list[str]:
    values = source.get("source_ids")
    if not isinstance(values, list):
        return []

    return [
        normalized
        for value in values
        if (normalized := str(value).strip())
    ]


def _citation_suffix(source_ids: Any) -> str:
    citations = [f"[{source_id}]" for source_id in _source_ids({"source_ids": source_ids})]
    return f" {' '.join(citations)}" if citations else ""
