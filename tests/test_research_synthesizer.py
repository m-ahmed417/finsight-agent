from finsight_agent.app.services.research_synthesizer import synthesize_research_insights


def sample_metrics() -> dict:
    return {
        "periods": [
            {
                "fy": 2023,
                "revenue": 1000000000,
                "free_cash_flow": 200000000,
            },
            {
                "fy": 2024,
                "revenue": 1250000000,
                "revenue_growth": 0.25,
                "operating_margin": 0.24,
                "free_cash_flow": 280000000,
            },
        ]
    }


def sample_risk_themes() -> list[dict]:
    return [
        {
            "title": "Competitive pressure",
            "summary": (
                "The filing describes competition as a material business risk that "
                "could pressure operating performance."
            ),
            "source_form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "0000320193-24-000123",
            "source_ids": ["latest_10k"],
        }
    ]


def test_synthesize_research_insights_uses_positive_revenue_growth() -> None:
    insights = synthesize_research_insights(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics=sample_metrics(),
        risk_themes=[],
        warnings=[],
    )

    assert insights["bull_case"] == [
        {
            "title": "Revenue growth",
            "summary": (
                "Extracted revenue increased 25.00% year over year in fiscal 2024."
            ),
            "source": "SEC company facts",
            "source_ids": ["sec_company_facts"],
        },
        {
            "title": "Positive free cash flow",
            "summary": "Extracted free cash flow was 280000000 in fiscal 2024.",
            "source": "SEC company facts",
            "source_ids": ["sec_company_facts"],
        },
    ]


def test_synthesize_research_insights_uses_risk_themes_for_bear_case() -> None:
    insights = synthesize_research_insights(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics=sample_metrics(),
        risk_themes=sample_risk_themes(),
        warnings=[],
    )

    assert insights["bear_case"] == [
        {
            "title": "Competitive pressure",
            "summary": (
                "The bear case includes this source-grounded risk theme: The filing "
                "describes competition as a material business risk that could "
                "pressure operating performance."
            ),
            "source": "10-K filed 2024-11-01, accession 0000320193-24-000123",
            "source_ids": ["latest_10k"],
        }
    ]


def test_synthesize_research_insights_adds_open_question_for_missing_metrics() -> None:
    insights = synthesize_research_insights(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={"periods": []},
        risk_themes=[],
        warnings=[
            {
                "code": "metric_warning",
                "message": "Revenue could not be extracted.",
                "severity": "warning",
            }
        ],
    )

    assert insights["executive_summary"] == [
        "Apple Inc. (AAPL) was reviewed using available SEC-derived evidence."
    ]
    assert insights["bull_case"] == []
    assert insights["bear_case"] == []
    assert "Which missing SEC metrics are needed before drawing firmer research conclusions?" in insights[
        "open_questions"
    ]
