from finsight_agent.app.services.report_generator import (
    RESEARCH_ONLY_NOTICE,
    generate_research_report,
)


def test_generate_research_report_contains_required_sections() -> None:
    report = generate_research_report(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={"periods": [{"fy": 2024, "revenue": 1250000000}]},
        latest_10k={"filing_date": "2024-11-01", "accession_number": "abc"},
        latest_10q={"filing_date": "2024-08-02", "accession_number": "def"},
        warnings=[],
        sources=[],
    )

    assert "# FinSight Research Brief: Apple Inc. (AAPL)" in report
    assert "## 1. Research-Only Notice" in report
    assert "## 2. Executive Summary" in report
    assert "## 3. Company Overview" in report
    assert "## 4. Financial Performance" in report
    assert "## 5. Key Financial Metrics" in report
    assert "## 6. Risk Factors" in report
    assert "## 7. Bull Case" in report
    assert "## 8. Bear Case" in report
    assert "## 9. Open Questions for Further Research" in report
    assert "## 10. Sources Used" in report
    assert "## 11. Limitations" in report


def test_generate_research_report_includes_required_disclaimer() -> None:
    report = generate_research_report(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={"periods": []},
        latest_10k=None,
        latest_10q=None,
        warnings=[],
        sources=[],
    )

    assert RESEARCH_ONLY_NOTICE in report


def test_generate_research_report_includes_metrics_table() -> None:
    report = generate_research_report(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={
            "periods": [
                {
                    "fy": 2024,
                    "revenue": 1250000000,
                    "revenue_growth": 0.25,
                    "operating_income": 300000000,
                    "operating_margin": 0.24,
                    "net_income": 250000000,
                    "net_margin": 0.2,
                    "free_cash_flow": 280000000,
                }
            ]
        },
        latest_10k=None,
        latest_10q=None,
        warnings=[],
        sources=[],
    )

    assert "| Fiscal Year | Revenue | Revenue Growth | Operating Margin | Net Margin | Free Cash Flow |" in report
    assert "| 2024 | 1250000000 | 25.00% | 24.00% | 20.00% | 280000000 |" in report


def test_generate_research_report_includes_limitations_from_warnings() -> None:
    report = generate_research_report(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={"periods": []},
        latest_10k=None,
        latest_10q=None,
        warnings=[
            {
                "code": "metric_warning",
                "message": "Revenue could not be extracted.",
                "severity": "warning",
            }
        ],
        sources=[],
    )

    assert "- Revenue could not be extracted." in report


def test_generate_research_report_includes_source_labels_and_urls() -> None:
    report = generate_research_report(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={"periods": []},
        latest_10k=None,
        latest_10q=None,
        warnings=[],
        sources=[
            {
                "label": "SEC company facts",
                "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            }
        ],
    )

    assert (
        "- SEC company facts: "
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    ) in report


def test_generate_research_report_notes_available_risk_factor_text() -> None:
    report = generate_research_report(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={"periods": []},
        latest_10k={"filing_date": "2024-11-01", "accession_number": "abc"},
        latest_10q=None,
        warnings=[],
        sources=[],
        risk_factors=[
            {
                "form": "10-K",
                "filing_date": "2024-11-01",
                "accession_number": "abc",
                "text": "Raw filing risk text should not be copied into the report.",
            }
        ],
    )

    assert "Risk-factor text was retrieved from the latest 10-K filed 2024-11-01." in report
    assert "Raw filing risk text should not be copied into the report." not in report


def test_generate_research_report_includes_risk_themes() -> None:
    report = generate_research_report(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={"periods": []},
        latest_10k={"filing_date": "2024-11-01", "accession_number": "abc"},
        latest_10q=None,
        warnings=[],
        sources=[],
        risk_themes=[
            {
                "title": "Competitive pressure",
                "summary": (
                    "The filing describes competition as a material business risk that "
                    "could pressure operating performance."
                ),
                "source_form": "10-K",
                "filing_date": "2024-11-01",
                "accession_number": "abc",
            }
        ],
    )

    assert (
        "- **Competitive pressure**: The filing describes competition as a material "
        "business risk that could pressure operating performance. "
        "(10-K filed 2024-11-01, accession abc)"
    ) in report


def test_generate_research_report_includes_synthesized_research_sections() -> None:
    report = generate_research_report(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={"periods": []},
        latest_10k=None,
        latest_10q=None,
        warnings=[],
        sources=[],
        research_insights={
            "executive_summary": [
                "Apple Inc. (AAPL) was reviewed using available SEC-derived evidence."
            ],
            "bull_case": [
                {
                    "title": "Revenue growth",
                    "summary": (
                        "Extracted revenue increased 25.00% year over year in fiscal 2024."
                    ),
                    "source": "SEC company facts",
                }
            ],
            "bear_case": [
                {
                    "title": "Competitive pressure",
                    "summary": (
                        "The bear case includes this source-grounded risk theme: "
                        "competition could pressure operating performance."
                    ),
                    "source": "10-K filed 2024-11-01, accession abc",
                }
            ],
            "open_questions": [
                "What changed in the latest annual filing compared with prior years?"
            ],
        },
    )

    assert (
        "- Apple Inc. (AAPL) was reviewed using available SEC-derived evidence."
    ) in report
    assert (
        "- **Revenue growth**: Extracted revenue increased 25.00% year over year "
        "in fiscal 2024. (Source: SEC company facts)"
    ) in report
    assert (
        "- **Competitive pressure**: The bear case includes this source-grounded "
        "risk theme: competition could pressure operating performance. "
        "(Source: 10-K filed 2024-11-01, accession abc)"
    ) in report
    assert "- What changed in the latest annual filing compared with prior years?" in report
