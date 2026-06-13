from collections import defaultdict
from datetime import date
from typing import Any

REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
NET_INCOME_TAGS = ("NetIncomeLoss",)


def extract_financial_metrics(company_facts: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []

    revenue_by_fy = _extract_metric_by_fiscal_year(company_facts, REVENUE_TAGS)
    net_income_by_fy = _extract_metric_by_fiscal_year(company_facts, NET_INCOME_TAGS)

    if not revenue_by_fy:
        warnings.append("Revenue could not be extracted from SEC company facts.")
        return {"periods": [], "warnings": warnings}

    if not net_income_by_fy:
        warnings.append("Net income could not be extracted from SEC company facts.")

    periods: list[dict[str, Any]] = []
    previous_revenue: int | float | None = None
    for fiscal_year in sorted(revenue_by_fy):
        revenue = revenue_by_fy[fiscal_year]["val"]
        net_income_fact = net_income_by_fy.get(fiscal_year)
        net_income = net_income_fact["val"] if net_income_fact is not None else None

        periods.append(
            {
                "fy": fiscal_year,
                "revenue": revenue,
                "revenue_growth": _calculate_growth(revenue, previous_revenue),
                "net_income": net_income,
                "net_margin": _calculate_margin(net_income, revenue),
            }
        )
        previous_revenue = revenue

    return {"periods": periods, "warnings": warnings}


def _extract_metric_by_fiscal_year(
    company_facts: dict[str, Any],
    tag_priority: tuple[str, ...],
) -> dict[int, dict[str, Any]]:
    us_gaap_facts = company_facts.get("facts", {}).get("us-gaap", {})
    if not isinstance(us_gaap_facts, dict):
        return {}

    for tag in tag_priority:
        tag_data = us_gaap_facts.get(tag)
        if not isinstance(tag_data, dict):
            continue

        usd_facts = tag_data.get("units", {}).get("USD", [])
        if not isinstance(usd_facts, list):
            continue

        selected = _select_annual_facts_by_fiscal_year(usd_facts)
        if selected:
            return selected

    return {}


def _select_annual_facts_by_fiscal_year(facts: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    candidates: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        fiscal_year = fact.get("fy")
        value = fact.get("val")
        if not isinstance(fiscal_year, int) or not isinstance(value, int | float):
            continue
        if fact.get("fp") not in {None, "FY"}:
            continue

        candidates[fiscal_year].append(fact)

    return {
        fiscal_year: _choose_best_fact(fiscal_year_facts)
        for fiscal_year, fiscal_year_facts in candidates.items()
    }


def _choose_best_fact(facts: list[dict[str, Any]]) -> dict[str, Any]:
    return max(facts, key=_fact_sort_key)


def _fact_sort_key(fact: dict[str, Any]) -> tuple[int, date]:
    form_priority = 1 if fact.get("form") == "10-K" else 0
    return form_priority, _parse_date(fact.get("filed"))


def _parse_date(value: Any) -> date:
    if not isinstance(value, str):
        return date.min
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.min


def _calculate_growth(
    current_value: int | float,
    previous_value: int | float | None,
) -> float | None:
    if previous_value in (None, 0):
        return None
    return (current_value - previous_value) / previous_value


def _calculate_margin(
    numerator: int | float | None,
    denominator: int | float | None,
) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator
