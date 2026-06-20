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


class BusinessSection(BaseModel):
    item: str
    section_label: str
    text: str


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
    section_text = _extract_item_section(
        filing_text,
        start_pattern=r"\bitem\s+1\.?\s+business\b",
        end_pattern=r"\bitem\s+1a\.?\s+risk\s+factors\b",
    )
    if section_text is None:
        return None

    return BusinessSection(item="1", section_label="Business", text=section_text)


def extract_risk_factors_section(filing_text: str) -> RiskFactorsSection | None:
    section_text = _extract_item_section(
        filing_text,
        start_pattern=r"\bitem\s+1a\.?\s+risk\s+factors\b",
        end_pattern=r"\bitem\s+(?:1b|2)\.?\b",
    )
    if section_text is None:
        return None

    return RiskFactorsSection(item="1A", text=section_text)


def _extract_item_section(
    filing_text: str,
    *,
    start_pattern: str,
    end_pattern: str,
) -> str | None:
    plain_text = _to_plain_text(filing_text)
    start_match = re.search(
        start_pattern,
        plain_text,
        flags=re.IGNORECASE,
    )
    if start_match is None:
        return None

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
    if not section_text:
        return None
    return section_text


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
