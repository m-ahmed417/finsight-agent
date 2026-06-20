import os

import pytest

from finsight_agent.app.config import get_settings
from finsight_agent.app.services.llm_client import get_llm_client


KNOWN_LIVE_SOURCE_IDS = ("sec_company_facts", "latest_10k")


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_LLM_TESTS") != "1",
    reason="Live LLM smoke tests are opt-in.",
)
def test_live_llm_risk_summary_smoke() -> None:
    get_settings.cache_clear()
    client = get_llm_client(get_settings())

    result = client.summarize_risks(
        [
            {
                "form": "10-K",
                "filing_date": "2024-11-01",
                "accession_number": "live-test",
                "source_url": "https://example.com/live-test",
                "source_ids": ["latest_10k"],
                "text": (
                    "The company faces intense competition and possible supply "
                    "chain disruption that could affect operations."
                ),
            }
        ]
    )

    assert result["themes"]
    assert result["themes"][0]["title"]
    assert result["themes"][0]["summary"]
    assert result["themes"][0]["source_ids"] == ["latest_10k"]


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_LLM_TESTS") != "1",
    reason="Live LLM smoke tests are opt-in.",
)
def test_live_llm_report_drafting_smoke() -> None:
    get_settings.cache_clear()
    client = get_llm_client(get_settings())

    result = client.draft_report(
        {
            "company_name": "Apple Inc.",
            "ticker": "AAPL",
            "latest_10k": {
                "form": "10-K",
                "filing_date": "2024-11-01",
                "accession_number": "live-test",
            },
            "financial_metrics": {
                "periods": [
                    {
                        "fy": 2024,
                        "revenue": 1250000000,
                        "free_cash_flow": 280000000,
                    }
                ]
            },
            "risk_themes": [
                {
                    "title": "Competitive pressure",
                    "summary": "Competition could pressure operating performance.",
                    "source_ids": ["latest_10k"],
                }
            ],
            "research_insights": {
                "executive_summary": [
                    "Apple Inc. (AAPL) was reviewed using SEC-derived evidence."
                ],
                "bull_case": [
                    {
                        "title": "Revenue growth",
                        "summary": "Extracted revenue increased in the sample period.",
                        "source_ids": ["sec_company_facts"],
                    }
                ],
                "bear_case": [
                    {
                        "title": "Competitive pressure",
                        "summary": "Competition remains a source-grounded risk theme.",
                        "source_ids": ["latest_10k"],
                    }
                ],
                "open_questions": ["Are revenue growth and cash flow durable?"],
            },
            "business_overview": {
                "status": "available",
                "summary": "Item 1 Business evidence is available for overview context.",
                "source_ids": ["latest_10k"],
            },
            "sources": [
                {"source_id": "sec_company_facts", "label": "SEC company facts"},
                {"source_id": "latest_10k", "label": "Latest 10-K filing"},
            ],
            "warnings": [],
        }
    )

    sections = result["sections"]

    assert sections["executive_summary"]
    assert sections["financial_performance"].strip()
    assert sections["risk_factors"]
    assert sections["bull_case"]
    assert sections["bear_case"]
    assert sections["open_questions"]
    assert any(
        f"[{source_id}]" in sections["financial_performance"]
        or any(f"[{source_id}]" in item for item in sections["risk_factors"])
        or any(f"[{source_id}]" in item for item in sections["bull_case"])
        or any(f"[{source_id}]" in item for item in sections["bear_case"])
        for source_id in KNOWN_LIVE_SOURCE_IDS
    )
