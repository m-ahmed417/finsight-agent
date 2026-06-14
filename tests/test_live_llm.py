import os

import pytest

from finsight_agent.app.config import get_settings
from finsight_agent.app.services.llm_client import get_llm_client


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
