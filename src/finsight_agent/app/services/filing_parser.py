from datetime import date
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
