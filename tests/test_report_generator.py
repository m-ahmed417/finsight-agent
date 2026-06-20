from finsight_agent.app.services.report_generator import (
    RESEARCH_ONLY_NOTICE,
    generate_research_report,
)
from finsight_agent.app.services.report_validator import (
    ReportQualityStatus,
    validate_report_quality,
)


SCAFFOLD_MARKERS = (
    "mvp draft",
    "future versions will",
    "pending deterministic synthesis",
    "not been generated yet",
    "future llm-assisted step",
    "no sources were recorded",
    "this draft is generated",
    "has not been performed yet",
)


COMPLETE_SOURCES = [
    {
        "source_id": "sec_submissions",
        "label": "SEC submissions",
        "url": "https://data.sec.gov/submissions/CIK0000320193.json",
    },
    {
        "source_id": "sec_company_facts",
        "label": "SEC company facts",
        "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
    },
    {
        "source_id": "latest_10k",
        "label": "Latest 10-K filing",
        "url": "https://www.sec.gov/Archives/example-10k.htm",
        "form": "10-K",
        "filing_date": "2024-11-01",
        "accession_number": "abc",
    },
]


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
    assert (
        "For fiscal year 2024, extracted revenue was 1250000000, "
        "net income was 250000000, and free cash flow was 280000000. "
        "[sec_company_facts]"
    ) in report


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
                "source_id": "sec_company_facts",
                "label": "SEC company facts",
                "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            }
        ],
    )

    assert (
        "- [sec_company_facts] SEC company facts: "
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    ) in report


def test_generate_research_report_includes_source_metadata_details() -> None:
    report = generate_research_report(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={"periods": []},
        latest_10k={"filing_date": "2024-11-01", "accession_number": "abc"},
        latest_10q=None,
        warnings=[],
        sources=[
            {
                "source_id": "sec_company_facts",
                "label": "SEC company facts",
                "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                "metric_fiscal_years": [2023, 2024],
                "xbrl_tags_used": ["RevenueFromContractWithCustomerExcludingAssessedTax"],
                "retrieved_at": "2026-06-15T10:00:00+00:00",
            },
            {
                "source_id": "latest_10k",
                "label": "Latest 10-K filing",
                "url": "https://www.sec.gov/Archives/example.htm",
                "form": "10-K",
                "filing_date": "2024-11-01",
                "report_date": "2024-09-28",
                "accession_number": "abc",
                "primary_document": "aapl.htm",
                "extracted_sections": ["Item 1A Risk Factors"],
                "extraction_status": "risk_factors_extracted",
                "document_retrieved_at": "2026-06-15T10:01:00+00:00",
            },
        ],
    )

    assert (
        "- [sec_company_facts] SEC company facts: "
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json "
        "(metric fiscal years 2023, 2024; XBRL tags used: "
        "RevenueFromContractWithCustomerExcludingAssessedTax; "
        "retrieved 2026-06-15T10:00:00+00:00)"
    ) in report
    assert (
        "- [latest_10k] Latest 10-K filing: "
        "https://www.sec.gov/Archives/example.htm "
        "(10-K filed 2024-11-01; report date 2024-09-28; accession abc; "
        "primary document aapl.htm; extracted sections: Item 1A Risk Factors; "
        "risk factors extracted; document retrieved 2026-06-15T10:01:00+00:00)"
    ) in report
    assert report.count("- [latest_10k]") == 1


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
                "source_ids": ["latest_10k"],
            }
        ],
    )

    assert (
        "- **Competitive pressure**: The filing describes competition as a material "
        "business risk that could pressure operating performance. "
        "(10-K filed 2024-11-01, accession abc) [latest_10k]"
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
                    "source_ids": ["sec_company_facts"],
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
                    "source_ids": ["latest_10k"],
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
        "in fiscal 2024. (Source: SEC company facts) [sec_company_facts]"
    ) in report
    assert (
        "- **Competitive pressure**: The bear case includes this source-grounded "
        "risk theme: competition could pressure operating performance. "
        "(Source: 10-K filed 2024-11-01, accession abc) [latest_10k]"
    ) in report
    assert "- What changed in the latest annual filing compared with prior years?" in report


def test_generate_research_report_prefers_llm_report_sections() -> None:
    report = generate_research_report(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={"periods": []},
        latest_10k=None,
        latest_10q=None,
        warnings=[],
        sources=[],
        research_insights={
            "executive_summary": ["Deterministic summary should be replaced."],
            "bull_case": [{"title": "Deterministic point", "summary": "Replaced."}],
            "bear_case": [],
            "open_questions": [],
        },
        llm_report_sections={
            "executive_summary": ["LLM-written summary."],
            "financial_performance": "LLM-written financial performance.",
            "risk_factors": ["LLM-written risk factor."],
            "bull_case": ["LLM-written bull case."],
            "bear_case": ["LLM-written bear case."],
            "open_questions": ["LLM-written open question."],
        },
    )

    assert "- LLM-written summary." in report
    assert "LLM-written financial performance." in report
    assert "- LLM-written risk factor." in report
    assert "- LLM-written bull case." in report
    assert "- LLM-written bear case." in report
    assert "- LLM-written open question." in report
    assert "Deterministic summary should be replaced." not in report


def test_generate_research_report_omits_scaffold_language_with_partial_data() -> None:
    report = generate_research_report(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={"periods": []},
        latest_10k=None,
        latest_10q=None,
        warnings=[],
        sources=[],
    )

    normalized_report = report.casefold()
    assert not any(marker in normalized_report for marker in SCAFFOLD_MARKERS)


def test_generate_research_report_includes_grounded_company_overview() -> None:
    report = generate_research_report(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={"periods": []},
        latest_10k={
            "form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "abc",
        },
        latest_10q=None,
        warnings=[],
        sources=COMPLETE_SOURCES,
    )

    overview = _extract_section(report, "## 3. Company Overview")

    assert "Apple Inc. (AAPL)" in overview
    assert "available SEC source records" in overview
    assert "[sec_submissions]" in overview
    assert "[sec_company_facts]" in overview
    assert "[latest_10k]" in overview
    assert "business overview has not been generated" not in overview.casefold()


def test_generate_research_report_uses_professional_no_source_language() -> None:
    report = generate_research_report(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={"periods": []},
        latest_10k=None,
        latest_10q=None,
        warnings=[],
        sources=[],
    )

    sources_section = _extract_section(report, "## 10. Sources Used")

    assert "No sources were recorded" not in sources_section
    assert "No source records were available for this run." in sources_section


def test_generate_research_report_includes_baseline_limitations_without_warnings() -> None:
    report = generate_research_report(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={"periods": []},
        latest_10k=None,
        latest_10q=None,
        warnings=[],
        sources=[],
    )

    limitations = _extract_section(report, "## 11. Limitations")

    assert "MVP draft" not in limitations
    assert "limited to the SEC-derived evidence available in this run" in limitations


def test_generate_research_report_passes_quality_validation_with_full_evidence() -> None:
    report = generate_research_report(
        company_name="Apple Inc.",
        ticker="AAPL",
        financial_metrics={
            "periods": [
                {
                    "fy": 2023,
                    "revenue": 1000000000,
                    "net_income": 150000000,
                    "free_cash_flow": 200000000,
                },
                {
                    "fy": 2024,
                    "revenue": 1250000000,
                    "revenue_growth": 0.25,
                    "operating_margin": 0.24,
                    "net_income": 250000000,
                    "net_margin": 0.2,
                    "free_cash_flow": 280000000,
                },
            ]
        },
        latest_10k={
            "form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "abc",
        },
        latest_10q=None,
        warnings=[],
        sources=COMPLETE_SOURCES,
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
                "source_ids": ["latest_10k"],
            }
        ],
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
                    "source_ids": ["sec_company_facts"],
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
                    "source_ids": ["latest_10k"],
                }
            ],
            "open_questions": [
                "What changed in the latest annual filing compared with prior years?"
            ],
        },
    )

    result = validate_report_quality(report, sources=COMPLETE_SOURCES)

    assert result.status == ReportQualityStatus.PASSED
    assert result.warnings == []


def _extract_section(report: str, heading: str) -> str:
    start = report.find(heading)
    assert start != -1
    next_heading = report.find("\n## ", start + len(heading))
    if next_heading == -1:
        return report[start:]
    return report[start:next_heading]
