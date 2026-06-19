from typing import get_args

from finsight_agent.app.api.schemas import ResearchResponse, ResearchRunSummary
from finsight_agent.app.research_status import (
    IN_PROGRESS_RESEARCH_STATUSES,
    RESEARCH_STATUS_COMPLETED,
    RESEARCH_STATUS_FAILED,
    RESEARCH_STATUS_QUEUED,
    RESEARCH_STATUS_RUNNING,
    RESEARCH_STATUSES,
    TERMINAL_RESEARCH_STATUSES,
    ResearchStatus,
)


def test_research_status_constants_define_api_lifecycle_contract() -> None:
    assert RESEARCH_STATUS_QUEUED == "queued"
    assert RESEARCH_STATUS_RUNNING == "running"
    assert RESEARCH_STATUS_COMPLETED == "completed"
    assert RESEARCH_STATUS_FAILED == "failed"
    assert RESEARCH_STATUSES == (
        "queued",
        "running",
        "completed",
        "failed",
    )
    assert TERMINAL_RESEARCH_STATUSES == ("completed", "failed")
    assert IN_PROGRESS_RESEARCH_STATUSES == ("queued", "running")


def test_research_response_status_uses_shared_lifecycle_contract() -> None:
    assert get_args(ResearchStatus) == RESEARCH_STATUSES
    assert get_args(ResearchResponse.model_fields["status"].annotation) == (
        RESEARCH_STATUSES
    )
    assert get_args(ResearchRunSummary.model_fields["status"].annotation) == (
        RESEARCH_STATUSES
    )
