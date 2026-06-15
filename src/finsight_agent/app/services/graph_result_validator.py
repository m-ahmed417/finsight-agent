from collections.abc import Mapping
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from finsight_agent.app.api.schemas import (
    AgentStep,
    ResearchError,
    ResearchWarning,
    SourceMetadata,
)


class GraphResultValidationError(ValueError):
    """Raised when graph output does not match the persisted/API contract."""


ModelT = TypeVar("ModelT", bound=BaseModel)


def validate_graph_result(graph_result: Mapping[str, Any]) -> dict[str, Any]:
    """Return a normalized copy of graph output for persistence/API use."""
    if not isinstance(graph_result, Mapping):
        msg = "Graph result must be a mapping."
        raise GraphResultValidationError(msg)

    normalized = dict(graph_result)
    normalized["warnings"] = _validate_list_field(
        graph_result,
        field_name="warnings",
        model=ResearchWarning,
    )
    normalized["errors"] = _validate_list_field(
        graph_result,
        field_name="errors",
        model=ResearchError,
    )
    normalized["sources"] = _validate_list_field(
        graph_result,
        field_name="sources",
        model=SourceMetadata,
    )
    normalized["agent_steps"] = _validate_list_field(
        graph_result,
        field_name="agent_steps",
        model=AgentStep,
    )
    return normalized


def _validate_list_field(
    graph_result: Mapping[str, Any],
    *,
    field_name: str,
    model: type[ModelT],
) -> list[dict[str, Any]]:
    values = graph_result.get(field_name, [])
    if not isinstance(values, list):
        msg = f"Graph result field '{field_name}' must be a list."
        raise GraphResultValidationError(msg)

    normalized: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        try:
            parsed = model.model_validate(value)
        except ValidationError as exc:
            msg = (
                f"Invalid graph result field '{field_name}' item {index}: "
                f"{_validation_error_summary(exc)}"
            )
            raise GraphResultValidationError(msg) from exc
        normalized.append(parsed.model_dump(exclude_none=True))

    return normalized


def _validation_error_summary(exc: ValidationError) -> str:
    first_error = exc.errors()[0]
    location = ".".join(str(part) for part in first_error.get("loc", ()))
    message = first_error.get("msg", "Validation failed.")
    if location:
        return f"{location}: {message}"
    return message
