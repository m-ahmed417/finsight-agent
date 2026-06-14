import json
from datetime import date
from pathlib import Path

from finsight_agent.app.services.filing_parser import (
    FilingRecord,
    extract_risk_factors_section,
    find_latest_filing,
    get_recent_filings,
    normalize_accession_number,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_sample_submissions() -> dict:
    return json.loads((FIXTURES_DIR / "sample_submissions.json").read_text())


def load_text_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


def test_get_recent_filings_converts_sec_parallel_arrays_to_records() -> None:
    submissions = load_sample_submissions()

    filings = get_recent_filings(submissions)

    assert len(filings) == 5
    assert filings[0] == FilingRecord(
        form="10-K",
        accession_number="0000320193-24-000123",
        filing_date=date(2024, 11, 1),
        report_date=date(2024, 9, 28),
        primary_document="aapl-20240928.htm",
        primary_doc_description="10-K",
    )


def test_find_latest_filing_returns_latest_exact_10k() -> None:
    submissions = load_sample_submissions()

    filing = find_latest_filing(submissions, form_type="10-K")

    assert filing is not None
    assert filing.form == "10-K"
    assert filing.accession_number == "0000320193-24-000123"
    assert filing.filing_date == date(2024, 11, 1)
    assert filing.primary_document == "aapl-20240928.htm"


def test_find_latest_filing_returns_latest_exact_10q() -> None:
    submissions = load_sample_submissions()

    filing = find_latest_filing(submissions, form_type="10-Q")

    assert filing is not None
    assert filing.form == "10-Q"
    assert filing.accession_number == "0000320193-24-000099"
    assert filing.filing_date == date(2024, 8, 2)


def test_find_latest_filing_does_not_treat_amendment_as_exact_form() -> None:
    submissions = load_sample_submissions()
    recent = submissions["filings"]["recent"]
    recent["form"] = ["10-K/A"]
    recent["accessionNumber"] = ["0000320193-24-000050"]
    recent["filingDate"] = ["2024-07-01"]
    recent["reportDate"] = ["2024-03-30"]
    recent["primaryDocument"] = ["aapl-20240330x10ka.htm"]
    recent["primaryDocDescription"] = ["10-K/A"]

    filing = find_latest_filing(submissions, form_type="10-K")

    assert filing is None


def test_find_latest_filing_returns_none_when_form_is_missing() -> None:
    submissions = load_sample_submissions()

    filing = find_latest_filing(submissions, form_type="S-1")

    assert filing is None


def test_get_recent_filings_handles_missing_recent_filings_safely() -> None:
    assert get_recent_filings({}) == []
    assert find_latest_filing({}, form_type="10-K") is None


def test_get_recent_filings_skips_malformed_rows() -> None:
    submissions = {
        "filings": {
            "recent": {
                "form": ["10-K", "10-Q"],
                "accessionNumber": ["bad-accession", "0000320193-24-000099"],
                "filingDate": ["not-a-date", "2024-08-02"],
                "reportDate": ["2024-09-28", "2024-06-29"],
                "primaryDocument": ["bad.htm", "aapl-20240629.htm"],
                "primaryDocDescription": ["10-K", "10-Q"],
            }
        }
    }

    filings = get_recent_filings(submissions)

    assert len(filings) == 1
    assert filings[0].form == "10-Q"


def test_normalize_accession_number_removes_dashes_for_sec_document_paths() -> None:
    assert normalize_accession_number("0000320193-24-000123") == "000032019324000123"


def test_extract_risk_factors_section_returns_item_1a_text() -> None:
    section = extract_risk_factors_section(load_text_fixture("sample_10k_excerpt.txt"))

    assert section is not None
    assert section.item == "1A"
    assert "The Company faces intense competition" in section.text
    assert "Item 1B. Unresolved Staff Comments" not in section.text


def test_extract_risk_factors_section_returns_none_when_missing() -> None:
    section = extract_risk_factors_section("Item 1. Business\n\nNo risk section here.")

    assert section is None
