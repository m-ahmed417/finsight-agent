import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class EvalStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class StrictEvalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvalExpectations(StrictEvalModel):
    status: str = "completed"
    report_quality_status: str = "passed"
    compliance_status: str = "allowed"
    citation_audit_status: str = "passed"
    required_citations: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    required_warning_codes: list[str] = Field(default_factory=list)
    forbidden_warning_codes: list[str] = Field(default_factory=list)
    allowed_missing_citation_sections: list[str] = Field(default_factory=list)

    @field_validator(
        "status",
        "report_quality_status",
        "compliance_status",
        "citation_audit_status",
    )
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            msg = "Eval expectation field cannot be empty."
            raise ValueError(msg)
        return text

    @field_validator(
        "required_citations",
        "forbidden_phrases",
        "required_warning_codes",
        "forbidden_warning_codes",
        "allowed_missing_citation_sections",
    )
    @classmethod
    def list_values_must_not_be_blank(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            text = value.strip()
            if not text:
                msg = "Eval expectation list values cannot be empty."
                raise ValueError(msg)
            normalized.append(text)
        return normalized


class EvalCase(StrictEvalModel):
    id: str
    query: str
    description: str
    sec_fixture: str
    llm_fixture: str
    expected: EvalExpectations

    @field_validator("id", "query", "description", "sec_fixture", "llm_fixture")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            msg = "Eval case field cannot be empty."
            raise ValueError(msg)
        return text

    @field_validator("id")
    @classmethod
    def id_must_be_stable(cls, value: str) -> str:
        if not CASE_ID_PATTERN.fullmatch(value):
            msg = (
                "Eval case id must be stable: use lowercase letters, numbers, "
                "underscores, or hyphens."
            )
            raise ValueError(msg)
        return value


class EvalCheckResult(StrictEvalModel):
    name: str
    status: EvalStatus
    expected: Any | None = None
    actual: Any | None = None
    message: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            msg = "Eval check name cannot be empty."
            raise ValueError(msg)
        return text

    @field_validator("message")
    @classmethod
    def blank_message_becomes_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class EvalCaseResult(StrictEvalModel):
    case_id: str
    checks: list[EvalCheckResult] = Field(min_length=1)
    metrics: dict[str, bool | int | float | str | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("case_id")
    @classmethod
    def case_id_must_be_stable(cls, value: str) -> str:
        case_id = value.strip()
        if not case_id:
            msg = "Eval case result id cannot be empty."
            raise ValueError(msg)
        if not CASE_ID_PATTERN.fullmatch(case_id):
            msg = (
                "Eval case result id must be stable: use lowercase letters, numbers, "
                "underscores, or hyphens."
            )
            raise ValueError(msg)
        return case_id

    @field_validator("warnings")
    @classmethod
    def warnings_must_not_be_blank(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            warning = value.strip()
            if not warning:
                msg = "Eval case result warnings cannot be empty."
                raise ValueError(msg)
            normalized.append(warning)
        return normalized

    @computed_field
    @property
    def status(self) -> EvalStatus:
        if any(check.status == EvalStatus.FAILED for check in self.checks):
            return EvalStatus.FAILED
        return EvalStatus.PASSED


class EvalSuiteResult(StrictEvalModel):
    suite: str
    cases: list[EvalCaseResult] = Field(default_factory=list)

    @field_validator("suite")
    @classmethod
    def suite_must_not_be_blank(cls, value: str) -> str:
        suite = value.strip()
        if not suite:
            msg = "Eval suite name cannot be empty."
            raise ValueError(msg)
        if not CASE_ID_PATTERN.fullmatch(suite):
            msg = (
                "Eval suite name must be stable: use lowercase letters, numbers, "
                "underscores, or hyphens."
            )
            raise ValueError(msg)
        return suite

    @computed_field
    @property
    def case_count(self) -> int:
        return len(self.cases)

    @computed_field
    @property
    def passed(self) -> int:
        return sum(1 for case in self.cases if case.status == EvalStatus.PASSED)

    @computed_field
    @property
    def failed(self) -> int:
        return sum(1 for case in self.cases if case.status == EvalStatus.FAILED)

    @computed_field
    @property
    def pass_rate(self) -> float:
        if not self.cases:
            return 0.0
        return self.passed / self.case_count
