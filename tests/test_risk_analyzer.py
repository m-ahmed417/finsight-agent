from finsight_agent.app.services.risk_analyzer import analyze_risk_factors


def test_analyze_risk_factors_returns_grounded_themes() -> None:
    result = analyze_risk_factors(
        [
            {
                "form": "10-K",
                "filing_date": "2024-11-01",
                "accession_number": "0000320193-24-000123",
                "source_url": "https://www.sec.gov/filing.htm",
                "text": (
                    "The Company faces intense competition in all markets in which it operates.\n"
                    "Supply chain disruption, component shortages, or manufacturing delays could "
                    "adversely affect results of operations.\n"
                    "The Company's business also depends on continued access to third-party "
                    "software, services, and distribution channels."
                ),
            }
        ]
    )

    assert result["warnings"] == []
    assert result["themes"] == [
        {
            "title": "Competitive pressure",
            "summary": (
                "The filing describes competition as a material business risk that "
                "could pressure operating performance."
            ),
            "source_form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "0000320193-24-000123",
            "source_url": "https://www.sec.gov/filing.htm",
        },
        {
            "title": "Supply chain and manufacturing disruption",
            "summary": (
                "The filing indicates that supply chain disruption, component "
                "availability, or manufacturing delays could affect operations."
            ),
            "source_form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "0000320193-24-000123",
            "source_url": "https://www.sec.gov/filing.htm",
        },
        {
            "title": "Third-party platform and distribution dependence",
            "summary": (
                "The filing notes dependence on third-party software, services, or "
                "distribution channels as an operating risk."
            ),
            "source_form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "0000320193-24-000123",
            "source_url": "https://www.sec.gov/filing.htm",
        },
    ]


def test_analyze_risk_factors_deduplicates_themes() -> None:
    result = analyze_risk_factors(
        [
            {
                "form": "10-K",
                "filing_date": "2024-11-01",
                "accession_number": "abc",
                "source_url": "https://www.sec.gov/filing.htm",
                "text": "Competition and intense competitive pressure are discussed.",
            }
        ]
    )

    assert [theme["title"] for theme in result["themes"]] == ["Competitive pressure"]


def test_analyze_risk_factors_returns_warning_when_text_is_missing() -> None:
    result = analyze_risk_factors([])

    assert result["themes"] == []
    assert result["warnings"] == [
        {
            "code": "risk_analysis_unavailable",
            "message": "Risk-factor text was unavailable for analysis.",
            "severity": "warning",
        }
    ]
