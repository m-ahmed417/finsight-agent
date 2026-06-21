from finsight_agent.app.services.financial_presentation import (
    build_period_analysis,
    format_percentage_value,
    format_usd_value,
)


def test_format_usd_value_uses_readable_units() -> None:
    assert format_usd_value(1_250_000_000) == "$1.25B"
    assert format_usd_value(280_000_000) == "$280.0M"
    assert format_usd_value(950_000) == "$950.0K"
    assert format_usd_value(999) == "$999"


def test_format_usd_value_handles_negative_values() -> None:
    assert format_usd_value(-45_000_000) == "-$45.0M"
    assert format_usd_value(-999) == "-$999"


def test_format_usd_value_handles_none() -> None:
    assert format_usd_value(None) == "N/A"


def test_format_percentage_value_uses_one_decimal_place() -> None:
    assert format_percentage_value(0.25) == "25.0%"
    assert format_percentage_value(-0.035) == "-3.5%"


def test_format_percentage_value_handles_none() -> None:
    assert format_percentage_value(None) == "N/A"


def test_build_period_analysis_describes_latest_period_improvement() -> None:
    analysis = build_period_analysis(
        [
            {
                "fy": 2023,
                "revenue": 1_000_000_000,
                "operating_margin": 0.20,
                "net_margin": 0.15,
                "free_cash_flow": 200_000_000,
            },
            {
                "fy": 2024,
                "revenue": 1_250_000_000,
                "revenue_growth": 0.25,
                "operating_margin": 0.24,
                "net_margin": 0.20,
                "free_cash_flow": 280_000_000,
            },
        ]
    )

    assert analysis == [
        "Revenue increased 25.0% from fiscal year 2023 to 2024.",
        (
            "Operating margin expanded by 4.0 percentage points from fiscal "
            "year 2023 to 2024."
        ),
        (
            "Net margin expanded by 5.0 percentage points from fiscal year "
            "2023 to 2024."
        ),
        (
            "Free cash flow increased from $200.0M in fiscal year 2023 to "
            "$280.0M in fiscal year 2024."
        ),
    ]


def test_build_period_analysis_describes_revenue_decline_and_cash_flow_decline() -> None:
    analysis = build_period_analysis(
        [
            {"fy": 2023, "revenue": 1_000_000_000, "free_cash_flow": 200_000_000},
            {"fy": 2024, "revenue": 900_000_000, "free_cash_flow": 125_000_000},
        ]
    )

    assert "Revenue decreased 10.0% from fiscal year 2023 to 2024." in analysis
    assert (
        "Free cash flow decreased from $200.0M in fiscal year 2023 to "
        "$125.0M in fiscal year 2024."
    ) in analysis


def test_build_period_analysis_describes_flat_revenue() -> None:
    analysis = build_period_analysis(
        [
            {"fy": 2023, "revenue": 1_000_000_000},
            {"fy": 2024, "revenue": 1_000_000_000},
        ]
    )

    assert analysis == ["Revenue was flat from fiscal year 2023 to 2024."]


def test_build_period_analysis_handles_single_period_without_inventing_trend() -> None:
    analysis = build_period_analysis([{"fy": 2024, "revenue": 1_250_000_000}])

    assert analysis == [
        "Only one fiscal year was available, so year-over-year comparisons are limited."
    ]


def test_build_period_analysis_avoids_percentage_growth_when_prior_revenue_is_zero() -> None:
    analysis = build_period_analysis(
        [
            {"fy": 2023, "revenue": 0},
            {"fy": 2024, "revenue": 100_000_000},
        ]
    )

    assert analysis == [
        (
            "Revenue increased from $0 in fiscal year 2023 to $100.0M in fiscal "
            "year 2024; percentage growth is not meaningful because prior "
            "revenue was zero."
        )
    ]


def test_build_period_analysis_describes_margin_contraction() -> None:
    analysis = build_period_analysis(
        [
            {"fy": 2023, "revenue": 1_000_000_000, "operating_margin": 0.24},
            {"fy": 2024, "revenue": 1_000_000_000, "operating_margin": 0.20},
        ]
    )

    assert (
        "Operating margin contracted by 4.0 percentage points from fiscal year "
        "2023 to 2024."
    ) in analysis
