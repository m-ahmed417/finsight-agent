from math import isfinite
from typing import Any


def build_period_analysis(periods: list[dict[str, Any]]) -> list[str]:
    comparable_periods = _sorted_periods(periods)
    if not comparable_periods:
        return []
    if len(comparable_periods) == 1:
        return [
            "Only one fiscal year was available, so year-over-year comparisons are limited."
        ]

    previous = comparable_periods[-2]
    current = comparable_periods[-1]
    previous_year = _format_fiscal_year(previous)
    current_year = _format_fiscal_year(current)

    analysis: list[str] = []
    revenue_analysis = _revenue_analysis(previous, current, previous_year, current_year)
    if revenue_analysis:
        analysis.append(revenue_analysis)

    for field, label in (
        ("operating_margin", "Operating margin"),
        ("net_margin", "Net margin"),
    ):
        margin_analysis = _margin_analysis(
            previous,
            current,
            field=field,
            label=label,
            previous_year=previous_year,
            current_year=current_year,
        )
        if margin_analysis:
            analysis.append(margin_analysis)

    free_cash_flow_analysis = _free_cash_flow_analysis(
        previous,
        current,
        previous_year,
        current_year,
    )
    if free_cash_flow_analysis:
        analysis.append(free_cash_flow_analysis)

    return analysis


def format_usd_value(value: Any) -> str:
    numeric_value = _finite_number(value)
    if numeric_value is None:
        return "N/A"

    sign = "-" if numeric_value < 0 else ""
    absolute_value = abs(numeric_value)

    if absolute_value >= 1_000_000_000_000:
        return f"{sign}${absolute_value / 1_000_000_000_000:.2f}T"
    if absolute_value >= 1_000_000_000:
        return f"{sign}${absolute_value / 1_000_000_000:.2f}B"
    if absolute_value >= 1_000_000:
        return f"{sign}${absolute_value / 1_000_000:.1f}M"
    if absolute_value >= 1_000:
        return f"{sign}${absolute_value / 1_000:.1f}K"
    if absolute_value.is_integer():
        return f"{sign}${absolute_value:.0f}"
    return f"{sign}${absolute_value:.2f}"


def format_percentage_value(value: Any) -> str:
    numeric_value = _finite_number(value)
    if numeric_value is None:
        return "N/A"

    percentage = round(numeric_value * 100, 1)
    if percentage == 0:
        percentage = 0.0
    return f"{percentage:.1f}%"


def _revenue_analysis(
    previous: dict[str, Any],
    current: dict[str, Any],
    previous_year: str,
    current_year: str,
) -> str:
    previous_revenue = _finite_number(previous.get("revenue"))
    current_revenue = _finite_number(current.get("revenue"))
    if previous_revenue is None or current_revenue is None:
        return ""

    if current_revenue == previous_revenue:
        return f"Revenue was flat from fiscal year {previous_year} to {current_year}."

    direction = "increased" if current_revenue > previous_revenue else "decreased"
    if previous_revenue == 0:
        return (
            f"Revenue {direction} from {format_usd_value(previous_revenue)} in fiscal "
            f"year {previous_year} to {format_usd_value(current_revenue)} in fiscal "
            "year "
            f"{current_year}; percentage growth is not meaningful because prior "
            "revenue was zero."
        )

    revenue_growth = _finite_number(current.get("revenue_growth"))
    if revenue_growth is None:
        revenue_growth = (current_revenue - previous_revenue) / previous_revenue

    return (
        f"Revenue {direction} {format_percentage_value(abs(revenue_growth))} from "
        f"fiscal year {previous_year} to {current_year}."
    )


def _margin_analysis(
    previous: dict[str, Any],
    current: dict[str, Any],
    *,
    field: str,
    label: str,
    previous_year: str,
    current_year: str,
) -> str:
    previous_margin = _finite_number(previous.get(field))
    current_margin = _finite_number(current.get(field))
    if previous_margin is None or current_margin is None:
        return ""

    movement = round((current_margin - previous_margin) * 100, 1)
    if movement == 0:
        return f"{label} was flat from fiscal year {previous_year} to {current_year}."

    direction = "expanded" if movement > 0 else "contracted"
    return (
        f"{label} {direction} by {abs(movement):.1f} percentage points from fiscal "
        f"year {previous_year} to {current_year}."
    )


def _free_cash_flow_analysis(
    previous: dict[str, Any],
    current: dict[str, Any],
    previous_year: str,
    current_year: str,
) -> str:
    previous_free_cash_flow = _finite_number(previous.get("free_cash_flow"))
    current_free_cash_flow = _finite_number(current.get("free_cash_flow"))
    if previous_free_cash_flow is None or current_free_cash_flow is None:
        return ""

    if current_free_cash_flow == previous_free_cash_flow:
        return (
            "Free cash flow was flat from fiscal year "
            f"{previous_year} to {current_year}."
        )

    direction = (
        "increased" if current_free_cash_flow > previous_free_cash_flow else "decreased"
    )
    return (
        f"Free cash flow {direction} from {format_usd_value(previous_free_cash_flow)} "
        f"in fiscal year {previous_year} to {format_usd_value(current_free_cash_flow)} "
        f"in fiscal year {current_year}."
    )


def _sorted_periods(periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(periods, key=_period_sort_key)


def _period_sort_key(period: dict[str, Any]) -> tuple[int, float]:
    fiscal_year = _finite_number(period.get("fy"))
    if fiscal_year is None:
        return (0, 0)
    return (1, fiscal_year)


def _format_fiscal_year(period: dict[str, Any]) -> str:
    fiscal_year = period.get("fy")
    if isinstance(fiscal_year, int):
        return str(fiscal_year)
    return str(fiscal_year or "unknown")


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None

    numeric_value = float(value)
    if not isfinite(numeric_value):
        return None
    return numeric_value
