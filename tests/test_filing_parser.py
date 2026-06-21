import json
from datetime import date
from pathlib import Path

from finsight_agent.app.services.filing_parser import (
    FilingRecord,
    extract_business_section,
    extract_business_section_with_diagnostics,
    extract_risk_factors_section,
    extract_risk_factors_section_with_diagnostics,
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


def test_extract_business_section_returns_item_1_text() -> None:
    section = extract_business_section(load_text_fixture("sample_10k_excerpt.txt"))

    assert section is not None
    assert section.item == "1"
    assert section.section_label == "Business"
    assert "Apple Inc. designs, manufactures, and markets smartphones" in section.text
    assert "Item 1A. Risk Factors" not in section.text
    assert "The Company faces intense competition" not in section.text
    assert "Item 1B. Unresolved Staff Comments" not in section.text


def test_extract_business_section_handles_html_and_spacing_variants() -> None:
    filing_text = """
    <html><body>
    <h2>ITEM&nbsp;1&nbsp;&nbsp; BUSINESS</h2>
    <p>The Company provides cloud software and support services.</p>
    <h2>Item&nbsp;1A. Risk Factors</h2>
    <p>Risk text should not be included.</p>
    </body></html>
    """

    section = extract_business_section(filing_text)

    assert section is not None
    assert section.item == "1"
    assert section.text == "The Company provides cloud software and support services."


def test_extract_business_section_handles_punctuation_and_part_i_fixture() -> None:
    section = extract_business_section(
        load_text_fixture("filing_heading_variants_10k.txt")
    )

    assert section is not None
    assert section.item == "1"
    assert section.section_label == "Business"
    assert "compliance workflow software" in section.text
    assert "support\nservices" in section.text
    assert "ITEM 1A" not in section.text
    assert "implementation risk" not in section.text


def test_extract_business_section_skips_table_of_contents_noise() -> None:
    section = extract_business_section(load_text_fixture("filing_toc_noise_10k.html"))

    assert section is not None
    assert section.item == "1"
    assert "Actual Cloud Corp. delivers cloud infrastructure products" in section.text
    assert "Table of Contents" not in section.text
    assert "Actual risk text" not in section.text
    assert section.text != "5"


def test_extract_business_section_diagnostics_describe_successful_extraction() -> None:
    result = extract_business_section_with_diagnostics(
        load_text_fixture("filing_toc_noise_10k.html")
    )

    assert result.section is not None
    assert result.diagnostics.model_dump() == {
        "status": "extracted",
        "section": "Item 1 Business",
        "candidate_count": 2,
        "text_character_count": len(result.section.text),
        "selection_reason": "selected plausible body after PART I heading",
        "warning_reason": None,
    }


def test_extract_business_section_prefers_body_after_part_i_over_long_toc_entry() -> None:
    filing_text = """
    Table of Contents

    Item 1. Business
    This table-of-contents description lists the business section location,
    page number, and navigation details but is not the actual business
    discussion body.

    Item 1A. Risk Factors
    This table-of-contents description lists risk section navigation details.

    PART I

    Item 1. Business
    Actual Robotics Corp. sells warehouse automation systems.

    Item 1A. Risk Factors
    Demand risk should not be included in business.
    """

    section = extract_business_section(filing_text)

    assert section is not None
    assert section.text == "Actual Robotics Corp. sells warehouse automation systems."


def test_extract_business_section_stops_at_item_1b_when_item_1a_is_absent() -> None:
    filing_text = """
    Item 1. Business
    The company provides regulated utility services in regional markets.

    Item 1B. Unresolved Staff Comments
    None.

    Item 2. Properties
    Property details should not be included.
    """

    section = extract_business_section(filing_text)

    assert section is not None
    assert "regulated utility services" in section.text
    assert "Unresolved Staff Comments" not in section.text
    assert "Property details" not in section.text


def test_extract_business_section_returns_none_for_implausibly_short_body() -> None:
    section = extract_business_section(
        "Item 1. Business\nSee page 5.\nItem 1A. Risk Factors\nRisk body."
    )

    assert section is None


def test_extract_business_section_diagnostics_describe_unavailable_extraction() -> None:
    result = extract_business_section_with_diagnostics(
        "Item 1. Business\nSee page 5.\nItem 1A. Risk Factors\nRisk body."
    )

    assert result.section is None
    assert result.diagnostics.model_dump() == {
        "status": "unavailable",
        "section": "Item 1 Business",
        "candidate_count": 1,
        "text_character_count": None,
        "selection_reason": None,
        "warning_reason": "No plausible Item 1 Business body could be extracted.",
    }


def test_extract_business_section_returns_none_when_missing() -> None:
    section = extract_business_section(
        "Item 1A. Risk Factors\n\nOnly risk text is available."
    )

    assert section is None


def test_extract_risk_factors_section_returns_item_1a_text() -> None:
    section = extract_risk_factors_section(load_text_fixture("sample_10k_excerpt.txt"))

    assert section is not None
    assert section.item == "1A"
    assert "The Company faces intense competition" in section.text
    assert "Item 1B. Unresolved Staff Comments" not in section.text


def test_extract_risk_factors_section_handles_punctuation_fixture() -> None:
    section = extract_risk_factors_section(
        load_text_fixture("filing_heading_variants_10k.txt")
    )

    assert section is not None
    assert section.item == "1A"
    assert "implementation risk, customer renewal risk" in section.text
    assert "ITEM 2" not in section.text
    assert "office space" not in section.text


def test_extract_risk_factors_section_skips_table_of_contents_noise() -> None:
    section = extract_risk_factors_section(
        load_text_fixture("filing_toc_noise_10k.html")
    )

    assert section is not None
    assert section.item == "1A"
    assert "Actual risk text describes cybersecurity incidents" in section.text
    assert "Table of Contents" not in section.text
    assert "UNRESOLVED STAFF COMMENTS" not in section.text
    assert section.text != "14"


def test_extract_risk_factors_section_diagnostics_describe_successful_extraction() -> None:
    result = extract_risk_factors_section_with_diagnostics(
        load_text_fixture("filing_toc_noise_10k.html")
    )

    assert result.section is not None
    assert result.diagnostics.model_dump() == {
        "status": "extracted",
        "section": "Item 1A Risk Factors",
        "candidate_count": 2,
        "text_character_count": len(result.section.text),
        "selection_reason": "selected plausible body after PART I heading",
        "warning_reason": None,
    }


def test_extract_risk_factors_section_prefers_body_after_part_i_over_long_toc_entry() -> None:
    filing_text = """
    Table of Contents

    Item 1A. Risk Factors
    This table-of-contents description lists risk-factor page numbers,
    navigation links, and cross references but is not the actual risk-factor
    discussion body.

    Item 1B. Unresolved Staff Comments
    This table-of-contents description lists staff comment page numbers.

    PART I

    Item 1A. Risk Factors
    Actual risk text discusses supplier concentration and cybersecurity events.

    Item 1B. Unresolved Staff Comments
    None.
    """

    section = extract_risk_factors_section(filing_text)

    assert section is not None
    assert (
        section.text
        == "Actual risk text discusses supplier concentration and cybersecurity events."
    )


def test_extract_risk_factors_section_stops_at_item_2_when_item_1b_is_absent() -> None:
    filing_text = """
    Item 1A. Risk Factors
    The company faces commodity price risk and project execution risk.

    Item 2. Properties
    Property details should not be included.
    """

    section = extract_risk_factors_section(filing_text)

    assert section is not None
    assert "commodity price risk" in section.text
    assert "Properties" not in section.text
    assert "Property details" not in section.text


def test_extract_risk_factors_section_returns_none_for_implausibly_short_body() -> None:
    section = extract_risk_factors_section(
        "Item 1A. Risk Factors\nSee page 8.\nItem 1B. Unresolved Staff Comments\nNone."
    )

    assert section is None


def test_extract_risk_factors_section_diagnostics_describe_unavailable_extraction() -> None:
    result = extract_risk_factors_section_with_diagnostics(
        "Item 1A. Risk Factors\nSee page 8.\nItem 1B. Unresolved Staff Comments\nNone."
    )

    assert result.section is None
    assert result.diagnostics.model_dump() == {
        "status": "unavailable",
        "section": "Item 1A Risk Factors",
        "candidate_count": 1,
        "text_character_count": None,
        "selection_reason": None,
        "warning_reason": "No plausible Item 1A Risk Factors body could be extracted.",
    }


def test_extract_risk_factors_section_returns_none_when_missing() -> None:
    section = extract_risk_factors_section("Item 1. Business\n\nNo risk section here.")

    assert section is None
