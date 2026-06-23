from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from finsight_agent.app.services.compliance import find_forbidden_terms
from finsight_agent.app.services.report_generator import RESEARCH_ONLY_NOTICE
from finsight_agent.app.services.report_validator import (
    REQUIRED_SECTIONS,
    WEAK_SECTION_MARKERS,
)
from finsight_agent.evals.models import EvalCheckResult, EvalExpectations, EvalStatus


def evaluate_report_sections(report: str | None) -> EvalCheckResult:
    report_text = report or ""
    missing_sections = [
        section for section in REQUIRED_SECTIONS if section not in report_text
    ]

    return _check(
        name="required_report_sections",
        passed=not missing_sections,
        expected=list(REQUIRED_SECTIONS),
        actual=missing_sections,
        message="Report is missing required sections." if missing_sections else None,
    )


def evaluate_research_only_disclaimer(report: str | None) -> EvalCheckResult:
    actual = RESEARCH_ONLY_NOTICE in (report or "")
    return _check(
        name="research_only_disclaimer",
        passed=actual,
        expected=True,
        actual=actual,
        message="Report is missing the required research-only disclaimer."
        if not actual
        else None,
    )


def evaluate_forbidden_language(
    report: str | None,
    *,
    forbidden_phrases: Iterable[str] = (),
) -> EvalCheckResult:
    report_text = report or ""
    found_terms = list(find_forbidden_terms(report_text))
    normalized_report = report_text.casefold()
    for phrase in _normalized_list(forbidden_phrases):
        if phrase.casefold() in normalized_report and phrase not in found_terms:
            found_terms.append(phrase)

    return _check(
        name="forbidden_language",
        passed=not found_terms,
        expected=[],
        actual=found_terms,
        message="Report contains forbidden language." if found_terms else None,
    )


def evaluate_scaffold_language(report: str | None) -> EvalCheckResult:
    normalized_report = (report or "").casefold()
    found_markers = [
        marker for marker in WEAK_SECTION_MARKERS if marker in normalized_report
    ]

    return _check(
        name="scaffold_language",
        passed=not found_markers,
        expected=[],
        actual=found_markers,
        message="Report contains scaffold or placeholder language."
        if found_markers
        else None,
    )


def evaluate_citation_audit(
    report_quality_details: Mapping[str, Any] | None,
    *,
    expected_status: str = "passed",
    required_citations: Iterable[str] = (),
    allowed_missing_required_citation_sections: Iterable[str] = (),
) -> list[EvalCheckResult]:
    citation_audit = _citation_audit_details(report_quality_details)
    status = _audit_value(citation_audit, "status")
    known_source_ids = _audit_list(citation_audit, "known_source_ids")
    unknown_citations = _audit_list(citation_audit, "unknown_citations")
    sections_missing_required_citations = _audit_list(
        citation_audit,
        "sections_missing_required_citations",
    )
    required_source_ids = _normalized_list(required_citations)
    missing_required_source_ids = [
        source_id for source_id in required_source_ids if source_id not in known_source_ids
    ]
    allowed_missing_sections = _normalized_list(
        allowed_missing_required_citation_sections
    )
    unexpected_missing_sections = [
        section
        for section in sections_missing_required_citations
        if section not in allowed_missing_sections
    ]

    return [
        _check(
            name="citation_audit_status",
            passed=status == expected_status,
            expected=expected_status,
            actual=status,
            message="Citation audit did not match expected status."
            if status != expected_status
            else None,
        ),
        _check(
            name="required_citations",
            passed=not missing_required_source_ids,
            expected=required_source_ids,
            actual=known_source_ids,
            message=_missing_required_citations_message(missing_required_source_ids),
        ),
        _check(
            name="unknown_citations",
            passed=not unknown_citations,
            expected=[],
            actual=unknown_citations,
            message="Citation audit includes unknown citations."
            if unknown_citations
            else None,
        ),
        _check(
            name="sections_missing_required_citations",
            passed=not unexpected_missing_sections,
            expected=allowed_missing_sections,
            actual=sections_missing_required_citations,
            message="Citation audit found sections missing required citations."
            if unexpected_missing_sections
            else None,
        ),
    ]


def evaluate_warning_codes(
    warnings: Sequence[Mapping[str, Any] | str] | None,
    *,
    required_warning_codes: Iterable[str] = (),
    forbidden_warning_codes: Iterable[str] = (),
) -> list[EvalCheckResult]:
    warning_codes = _warning_codes(warnings or [])
    required_codes = _normalized_list(required_warning_codes)
    forbidden_codes = _normalized_list(forbidden_warning_codes)
    missing_required_codes = [
        code for code in required_codes if code not in warning_codes
    ]
    present_forbidden_codes = [
        code for code in forbidden_codes if code in warning_codes
    ]

    return [
        _check(
            name="required_warning_codes",
            passed=not missing_required_codes,
            expected=required_codes,
            actual=warning_codes,
            message=_missing_required_warning_codes_message(missing_required_codes),
        ),
        _check(
            name="forbidden_warning_codes",
            passed=not present_forbidden_codes,
            expected=[],
            actual=present_forbidden_codes,
            message="Forbidden warning codes were present."
            if present_forbidden_codes
            else None,
        ),
    ]


def evaluate_report_quality_checks(
    *,
    report: str | None,
    report_quality_details: Mapping[str, Any] | None,
    warnings: Sequence[Mapping[str, Any] | str] | None,
    expectations: EvalExpectations,
) -> list[EvalCheckResult]:
    return [
        evaluate_report_sections(report),
        evaluate_research_only_disclaimer(report),
        evaluate_forbidden_language(
            report,
            forbidden_phrases=expectations.forbidden_phrases,
        ),
        evaluate_scaffold_language(report),
        *evaluate_citation_audit(
            report_quality_details,
            expected_status=expectations.citation_audit_status,
            required_citations=expectations.required_citations,
            allowed_missing_required_citation_sections=(
                expectations.allowed_missing_citation_sections
            ),
        ),
        *evaluate_warning_codes(
            warnings,
            required_warning_codes=expectations.required_warning_codes,
            forbidden_warning_codes=expectations.forbidden_warning_codes,
        ),
    ]


def _check(
    *,
    name: str,
    passed: bool,
    expected: Any,
    actual: Any,
    message: str | None,
) -> EvalCheckResult:
    return EvalCheckResult(
        name=name,
        status=EvalStatus.PASSED if passed else EvalStatus.FAILED,
        expected=expected,
        actual=actual,
        message=message,
    )


def _citation_audit_details(
    report_quality_details: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if not isinstance(report_quality_details, Mapping):
        return None
    citation_audit = report_quality_details.get("citation_audit")
    if not isinstance(citation_audit, Mapping):
        return None
    return citation_audit


def _audit_value(
    citation_audit: Mapping[str, Any] | None,
    key: str,
) -> str | None:
    if citation_audit is None:
        return None
    value = citation_audit.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _audit_list(
    citation_audit: Mapping[str, Any] | None,
    key: str,
) -> list[str]:
    if citation_audit is None:
        return []
    value = citation_audit.get(key)
    if not isinstance(value, list):
        return []
    return _normalized_list(str(item) for item in value)


def _warning_codes(warnings: Sequence[Mapping[str, Any] | str]) -> list[str]:
    codes: list[str] = []
    for warning in warnings:
        raw_code: Any
        if isinstance(warning, Mapping):
            raw_code = warning.get("code")
        else:
            raw_code = warning
        if raw_code is None:
            continue
        code = str(raw_code).strip()
        if code and code not in codes:
            codes.append(code)
    return codes


def _normalized_list(values: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _missing_required_citations_message(missing_source_ids: list[str]) -> str | None:
    if not missing_source_ids:
        return None
    missing = ", ".join(missing_source_ids)
    return f"Citation audit is missing required known source IDs: {missing}."


def _missing_required_warning_codes_message(missing_codes: list[str]) -> str | None:
    if not missing_codes:
        return None
    missing = ", ".join(missing_codes)
    return f"Missing required warning codes: {missing}."
