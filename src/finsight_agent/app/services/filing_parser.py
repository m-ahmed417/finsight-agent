from datetime import date
from html import unescape
import re
from typing import Any

from pydantic import BaseModel, ValidationError, field_validator


class FilingRecord(BaseModel):
    form: str
    accession_number: str
    filing_date: date
    report_date: date | None = None
    primary_document: str | None = None
    primary_doc_description: str | None = None

    @field_validator("form")
    @classmethod
    def normalize_form(cls, value: str) -> str:
        form = value.strip().upper()
        if not form:
            msg = "Filing form cannot be empty."
            raise ValueError(msg)
        return form

    @field_validator("accession_number")
    @classmethod
    def validate_accession_number(cls, value: str) -> str:
        accession_number = value.strip()
        if not accession_number:
            msg = "Accession number cannot be empty."
            raise ValueError(msg)
        if not normalize_accession_number(accession_number).isdigit():
            msg = "Accession number must contain digits."
            raise ValueError(msg)
        return accession_number

    @field_validator("primary_document", "primary_doc_description")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class RiskFactorsSection(BaseModel):
    item: str
    text: str
    extraction_diagnostics: dict[str, Any] | None = None


class BusinessSection(BaseModel):
    item: str
    section_label: str
    text: str
    extraction_diagnostics: dict[str, Any] | None = None


class SectionExtractionDiagnostics(BaseModel):
    status: str
    section: str
    candidate_count: int
    text_character_count: int | None = None
    selection_reason: str | None = None
    warning_reason: str | None = None


class SectionExtractionResult(BaseModel):
    section: BusinessSection | RiskFactorsSection | None
    diagnostics: SectionExtractionDiagnostics


def get_recent_filings(submissions: dict[str, Any]) -> list[FilingRecord]:
    recent = _get_recent_filings_data(submissions)
    if not recent:
        return []

    forms = recent.get("form")
    if not isinstance(forms, list):
        return []

    filings: list[FilingRecord] = []
    for index in range(len(forms)):
        try:
            filings.append(
                FilingRecord(
                    form=_get_indexed_value(recent, "form", index),
                    accession_number=_get_indexed_value(
                        recent,
                        "accessionNumber",
                        index,
                    ),
                    filing_date=_get_indexed_value(recent, "filingDate", index),
                    report_date=_get_indexed_value(recent, "reportDate", index),
                    primary_document=_get_indexed_value(
                        recent,
                        "primaryDocument",
                        index,
                    ),
                    primary_doc_description=_get_indexed_value(
                        recent,
                        "primaryDocDescription",
                        index,
                    ),
                )
            )
        except (IndexError, TypeError, ValidationError):
            continue

    return filings


def find_latest_filing(
    submissions: dict[str, Any],
    form_type: str,
) -> FilingRecord | None:
    normalized_form_type = form_type.strip().upper()
    if not normalized_form_type:
        return None

    matches = [
        filing
        for filing in get_recent_filings(submissions)
        if filing.form == normalized_form_type
    ]
    if not matches:
        return None

    return max(matches, key=lambda filing: (filing.filing_date, filing.accession_number))


def normalize_accession_number(accession_number: str) -> str:
    return accession_number.strip().replace("-", "")


def extract_business_section(filing_text: str) -> BusinessSection | None:
    return extract_business_section_with_diagnostics(filing_text).section


def extract_business_section_with_diagnostics(
    filing_text: str,
) -> SectionExtractionResult:
    extraction = _extract_item_section(
        filing_text,
        section_label="Item 1 Business",
        start_pattern=r"\bitem\s+1\s*(?:[.\-:])?\s*business\b",
        end_pattern=(
            r"\bitem\s+(?:1a\s*(?:[.\-:])?\s*risk\s+factors|"
            r"1b\s*(?:[.\-:])?|2\s*(?:[.\-:])?)\b"
        ),
    )
    if extraction["section_text"] is None:
        return SectionExtractionResult(
            section=None,
            diagnostics=extraction["diagnostics"],
        )

    diagnostics = extraction["diagnostics"]
    return SectionExtractionResult(
        section=BusinessSection(
            item="1",
            section_label="Business",
            text=extraction["section_text"],
            extraction_diagnostics=diagnostics.model_dump(),
        ),
        diagnostics=diagnostics,
    )


def extract_risk_factors_section(filing_text: str) -> RiskFactorsSection | None:
    return extract_risk_factors_section_with_diagnostics(filing_text).section


def extract_risk_factors_section_with_diagnostics(
    filing_text: str,
) -> SectionExtractionResult:
    extraction = _extract_item_section(
        filing_text,
        section_label="Item 1A Risk Factors",
        start_pattern=r"\bitem\s+1a\s*(?:[.\-:])?\s*risk\s+factors\b",
        end_pattern=r"\bitem\s+(?:1b\s*(?:[.\-:])?|2\s*(?:[.\-:])?)\b",
    )
    if extraction["section_text"] is None:
        return SectionExtractionResult(
            section=None,
            diagnostics=extraction["diagnostics"],
        )

    diagnostics = extraction["diagnostics"]
    return SectionExtractionResult(
        section=RiskFactorsSection(
            item="1A",
            text=extraction["section_text"],
            extraction_diagnostics=diagnostics.model_dump(),
        ),
        diagnostics=diagnostics,
    )


def _extract_item_section(
    filing_text: str,
    *,
    section_label: str,
    start_pattern: str,
    end_pattern: str,
) -> dict[str, Any]:
    plain_text = _to_plain_text(filing_text)
    part_i_positions = _part_i_positions(plain_text)
    candidates: list[tuple[tuple[int, int, int], str]] = []
    candidate_count = 0
    for start_match in re.finditer(
        start_pattern,
        plain_text,
        flags=re.IGNORECASE,
    ):
        candidate_count += 1
        end_match = re.search(
            end_pattern,
            plain_text[start_match.end() :],
            flags=re.IGNORECASE,
        )
        section_end = (
            start_match.end() + end_match.start()
            if end_match is not None
            else len(plain_text)
        )
        section_text = _clean_section_text(plain_text[start_match.end() : section_end])
        if _is_plausible_section_text(section_text):
            candidates.append(
                (
                    _section_candidate_score(
                        section_text,
                        starts_after_part_i=_starts_after_part_i(
                            start_match.start(),
                            part_i_positions,
                        ),
                    ),
                    section_text,
                )
            )

    if not candidates:
        return {
            "section_text": None,
            "diagnostics": _unavailable_diagnostics(
                section_label,
                candidate_count=candidate_count,
            ),
        }

    selected_score, section_text = max(candidates, key=lambda candidate: candidate[0])
    starts_after_part_i = selected_score[0] == 1
    diagnostics = SectionExtractionDiagnostics(
        status="extracted",
        section=section_label,
        candidate_count=candidate_count,
        text_character_count=len(section_text),
        selection_reason=(
            "selected plausible body after PART I heading"
            if starts_after_part_i
            else "selected longest plausible body"
        ),
        warning_reason=None,
    )
    return {
        "section_text": section_text,
        "diagnostics": diagnostics,
    }


def _get_recent_filings_data(submissions: dict[str, Any]) -> dict[str, Any]:
    filings = submissions.get("filings")
    if not isinstance(filings, dict):
        return {}

    recent = filings.get("recent")
    if not isinstance(recent, dict):
        return {}

    return recent


def _get_indexed_value(data: dict[str, Any], key: str, index: int) -> Any:
    values = data.get(key)
    if not isinstance(values, list):
        return None
    return values[index]


def _to_plain_text(filing_text: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", filing_text)
    return unescape(without_tags)


def _clean_section_text(text: str) -> str:
    lines = [" ".join(line.strip().split()) for line in text.strip().splitlines()]
    return "\n".join(line for line in lines if line)


def _is_plausible_section_text(text: str) -> bool:
    if not text:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    return len(words) >= 5 and sum(len(word) for word in words) >= 25


def _unavailable_diagnostics(
    section_label: str,
    *,
    candidate_count: int,
) -> SectionExtractionDiagnostics:
    if candidate_count == 0:
        warning_reason = f"No {section_label} heading candidates found."
    else:
        warning_reason = f"No plausible {section_label} body could be extracted."
    return SectionExtractionDiagnostics(
        status="unavailable",
        section=section_label,
        candidate_count=candidate_count,
        text_character_count=None,
        selection_reason=None,
        warning_reason=warning_reason,
    )


def _part_i_positions(text: str) -> list[int]:
    return [
        match.end()
        for match in re.finditer(r"\bpart\s+i\b", text, flags=re.IGNORECASE)
    ]


def _starts_after_part_i(start_index: int, part_i_positions: list[int]) -> bool:
    return any(position <= start_index for position in part_i_positions)


def _section_candidate_score(
    text: str,
    *,
    starts_after_part_i: bool,
) -> tuple[int, int, int]:
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    return int(starts_after_part_i), len(words), len(text)
