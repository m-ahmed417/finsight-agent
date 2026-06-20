from collections.abc import Iterable, Mapping
from typing import Any


def summarize_llm_usage(events: Iterable[Any]) -> dict[str, Any]:
    providers: set[str] = set()
    models: set[str] = set()
    summary: dict[str, Any] = {
        "total_calls": 0,
        "completed_calls": 0,
        "failed_calls": 0,
        "skipped_calls": 0,
        "fallback_count": 0,
        "total_duration_seconds": 0.0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
    }

    for event in events:
        summary["total_calls"] += 1
        status = _optional_text(_event_value(event, "status"))
        if status == "completed":
            summary["completed_calls"] += 1
        elif status == "failed":
            summary["failed_calls"] += 1
        elif status == "skipped":
            summary["skipped_calls"] += 1

        if _event_value(event, "fallback_used") is True:
            summary["fallback_count"] += 1

        summary["total_duration_seconds"] += _optional_non_negative_float(
            _event_value(event, "duration_seconds")
        )
        summary["total_input_tokens"] += _optional_non_negative_int(
            _event_value(event, "input_tokens")
        )
        summary["total_output_tokens"] += _optional_non_negative_int(
            _event_value(event, "output_tokens")
        )
        summary["total_tokens"] += _optional_non_negative_int(
            _event_value(event, "total_tokens")
        )

        provider = _optional_text(_event_value(event, "llm_provider"))
        if provider is not None:
            providers.add(provider)
        model = _optional_text(_event_value(event, "llm_model"))
        if model is not None:
            models.add(model)

    return {
        **summary,
        "total_duration_seconds": round(summary["total_duration_seconds"], 6),
        "providers": sorted(providers),
        "models": sorted(models),
    }


def _event_value(event: Any, field_name: str) -> Any:
    if isinstance(event, Mapping):
        return event.get(field_name)
    return getattr(event, field_name, None)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_non_negative_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if parsed >= 0 else 0.0


def _optional_non_negative_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed >= 0 else 0
