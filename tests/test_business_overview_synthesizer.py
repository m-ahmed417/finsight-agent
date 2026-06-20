import json

from finsight_agent.app.services.business_overview_synthesizer import (
    synthesize_business_overview,
)


RAW_BUSINESS_TEXT = (
    "Apple Inc. designs, manufactures, and markets smartphones, personal computers,\n"
    "tablets, wearables, and accessories."
)


def test_synthesize_business_overview_uses_business_section_metadata() -> None:
    overview = synthesize_business_overview(
        company_name="Apple Inc.",
        ticker="AAPL",
        business_sections=[
            {
                "source_id": "latest_10k",
                "source_type": "sec_business_section",
                "form": "10-K",
                "filing_date": "2024-11-01",
                "accession_number": "0000320193-24-000123",
                "source_url": "https://www.sec.gov/Archives/example.htm",
                "source_ids": ["latest_10k"],
                "section": "Item 1",
                "section_label": "Business",
                "text_character_count": len(RAW_BUSINESS_TEXT),
                "text": RAW_BUSINESS_TEXT,
            }
        ],
        warnings=[],
    )

    assert overview == {
        "status": "available",
        "summary": (
            "Apple Inc. (AAPL) has Item 1 Business evidence from the latest "
            "10-K filed 2024-11-01. Use this SEC filing evidence for company "
            "overview context without adding external company descriptions."
        ),
        "source": "10-K filed 2024-11-01, accession 0000320193-24-000123",
        "source_ids": ["latest_10k"],
        "source_form": "10-K",
        "filing_date": "2024-11-01",
        "accession_number": "0000320193-24-000123",
        "source_url": "https://www.sec.gov/Archives/example.htm",
        "section": "Item 1",
        "section_label": "Business",
        "text_character_count": len(RAW_BUSINESS_TEXT),
        "limitations": [],
    }
    serialized = json.dumps(overview)
    assert RAW_BUSINESS_TEXT not in serialized
    assert "smartphones" not in serialized


def test_synthesize_business_overview_falls_back_when_business_section_is_missing() -> None:
    overview = synthesize_business_overview(
        company_name="Apple Inc.",
        ticker="AAPL",
        business_sections=[],
        warnings=[
            {
                "code": "business_section_unavailable",
                "message": "Item 1 business section could not be extracted.",
                "severity": "warning",
            }
        ],
    )

    assert overview == {
        "status": "limited",
        "summary": (
            "Apple Inc. (AAPL) business overview is limited to resolved company "
            "identity because Item 1 Business evidence was not available in this run."
        ),
        "source_ids": [],
        "limitations": ["Item 1 business section could not be extracted."],
    }


def test_synthesize_business_overview_uses_source_id_when_source_ids_are_missing() -> None:
    overview = synthesize_business_overview(
        company_name="Apple Inc.",
        ticker="AAPL",
        business_sections=[
            {
                "source_id": "latest_10k",
                "form": "10-K",
                "filing_date": "2024-11-01",
                "accession_number": "abc",
                "section": "Item 1",
                "section_label": "Business",
                "text": RAW_BUSINESS_TEXT,
            }
        ],
        warnings=[],
    )

    assert overview["source_ids"] == ["latest_10k"]
