from collections import defaultdict
from datetime import date
from typing import Any

REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
NET_INCOME_TAGS = ("NetIncomeLoss",)
OPERATING_INCOME_TAGS = ("OperatingIncomeLoss",)
ASSETS_TAGS = ("Assets",)
LIABILITIES_TAGS = ("Liabilities",)
CASH_TAGS = (
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
)
DEBT_TAGS = ("LongTermDebt",)
DEBT_COMPONENT_TAGS = (
    "LongTermDebtCurrent",
    "LongTermDebtNoncurrent",
)
OPERATING_CASH_FLOW_TAGS = ("NetCashProvidedByUsedInOperatingActivities",)
CAPITAL_EXPENDITURE_TAGS = (
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
)


def extract_financial_metrics(company_facts: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []

    revenue_by_fy = _extract_metric_by_fiscal_year(company_facts, REVENUE_TAGS)
    net_income_by_fy = _extract_metric_by_fiscal_year(company_facts, NET_INCOME_TAGS)
    operating_income_by_fy = _extract_metric_by_fiscal_year(
        company_facts,
        OPERATING_INCOME_TAGS,
    )
    assets_by_fy = _extract_metric_by_fiscal_year(company_facts, ASSETS_TAGS)
    liabilities_by_fy = _extract_metric_by_fiscal_year(company_facts, LIABILITIES_TAGS)
    cash_by_fy = _extract_metric_by_fiscal_year(company_facts, CASH_TAGS)
    debt_by_fy = _extract_debt_by_fiscal_year(company_facts)
    operating_cash_flow_by_fy = _extract_metric_by_fiscal_year(
        company_facts,
        OPERATING_CASH_FLOW_TAGS,
    )
    capital_expenditure_by_fy = _extract_metric_by_fiscal_year(
        company_facts,
        CAPITAL_EXPENDITURE_TAGS,
    )

    if not revenue_by_fy:
        warnings.append("Revenue could not be extracted from SEC company facts.")
        return {"periods": [], "warnings": warnings}

    if not net_income_by_fy:
        warnings.append("Net income could not be extracted from SEC company facts.")
    if not operating_income_by_fy:
        warnings.append("Operating income could not be extracted from SEC company facts.")
    if operating_cash_flow_by_fy and not capital_expenditure_by_fy:
        warnings.append("Capital expenditure could not be extracted from SEC company facts.")

    periods: list[dict[str, Any]] = []
    previous_revenue: int | float | None = None
    for fiscal_year in sorted(revenue_by_fy):
        revenue = revenue_by_fy[fiscal_year]["val"]
        net_income_fact = net_income_by_fy.get(fiscal_year)
        net_income = net_income_fact["val"] if net_income_fact is not None else None
        operating_income_fact = operating_income_by_fy.get(fiscal_year)
        operating_income = (
            operating_income_fact["val"] if operating_income_fact is not None else None
        )
        assets = _get_fact_value(assets_by_fy, fiscal_year)
        liabilities = _get_fact_value(liabilities_by_fy, fiscal_year)
        cash = _get_fact_value(cash_by_fy, fiscal_year)
        debt = _get_fact_value(debt_by_fy, fiscal_year)
        operating_cash_flow = _get_fact_value(operating_cash_flow_by_fy, fiscal_year)
        capital_expenditure = _normalize_capex(
            _get_fact_value(capital_expenditure_by_fy, fiscal_year)
        )

        periods.append(
            {
                "fy": fiscal_year,
                "revenue": revenue,
                "revenue_growth": _calculate_growth(revenue, previous_revenue),
                "operating_income": operating_income,
                "operating_margin": _calculate_margin(operating_income, revenue),
                "net_income": net_income,
                "net_margin": _calculate_margin(net_income, revenue),
                "assets": assets,
                "liabilities": liabilities,
                "cash": cash,
                "debt": debt,
                "operating_cash_flow": operating_cash_flow,
                "capital_expenditure": capital_expenditure,
                "free_cash_flow": _calculate_free_cash_flow(
                    operating_cash_flow,
                    capital_expenditure,
                ),
                "metric_sources": _build_metric_sources(
                    fiscal_year=fiscal_year,
                    revenue_fact=revenue_by_fy[fiscal_year],
                    net_income_fact=net_income_fact,
                    operating_income_fact=operating_income_fact,
                    assets_fact=assets_by_fy.get(fiscal_year),
                    liabilities_fact=liabilities_by_fy.get(fiscal_year),
                    cash_fact=cash_by_fy.get(fiscal_year),
                    debt_fact=debt_by_fy.get(fiscal_year),
                    operating_cash_flow_fact=operating_cash_flow_by_fy.get(fiscal_year),
                    capital_expenditure_fact=capital_expenditure_by_fy.get(fiscal_year),
                    free_cash_flow_available=(
                        operating_cash_flow is not None and capital_expenditure is not None
                    ),
                ),
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

        unit = "USD"
        usd_facts = tag_data.get("units", {}).get(unit, [])
        if not isinstance(usd_facts, list):
            continue

        selected = _select_annual_facts_by_fiscal_year(usd_facts, tag=tag, unit=unit)
        if selected:
            return selected

    return {}


def _extract_debt_by_fiscal_year(company_facts: dict[str, Any]) -> dict[int, dict[str, Any]]:
    debt_by_fy = _extract_metric_by_fiscal_year(company_facts, DEBT_TAGS)
    if debt_by_fy:
        return debt_by_fy

    component_facts = [
        _extract_metric_by_fiscal_year(company_facts, (tag,))
        for tag in DEBT_COMPONENT_TAGS
    ]
    fiscal_years = set().union(*(facts.keys() for facts in component_facts))

    combined: dict[int, dict[str, Any]] = {}
    for fiscal_year in fiscal_years:
        component_values = [
            facts[fiscal_year]["val"]
            for facts in component_facts
            if fiscal_year in facts
        ]
        if component_values:
            combined[fiscal_year] = {
                "val": sum(component_values),
                "component_sources": [
                    _metric_source("debt_component", facts[fiscal_year])
                    for facts in component_facts
                    if fiscal_year in facts
                ],
            }

    return combined


def _select_annual_facts_by_fiscal_year(
    facts: list[dict[str, Any]],
    *,
    tag: str,
    unit: str,
) -> dict[int, dict[str, Any]]:
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
        fiscal_year: _with_fact_provenance(
            _choose_best_fact(fiscal_year_facts),
            tag=tag,
            unit=unit,
        )
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


def _calculate_free_cash_flow(
    operating_cash_flow: int | float | None,
    capital_expenditure: int | float | None,
) -> int | float | None:
    if operating_cash_flow is None or capital_expenditure is None:
        return None
    return operating_cash_flow - capital_expenditure


def _normalize_capex(value: int | float | None) -> int | float | None:
    if value is None:
        return None
    return abs(value)


def _get_fact_value(
    facts_by_fiscal_year: dict[int, dict[str, Any]],
    fiscal_year: int,
) -> int | float | None:
    fact = facts_by_fiscal_year.get(fiscal_year)
    if fact is None:
        return None
    return fact["val"]


def _with_fact_provenance(fact: dict[str, Any], *, tag: str, unit: str) -> dict[str, Any]:
    return {
        **fact,
        "_tag": tag,
        "_unit": unit,
    }


def _build_metric_sources(
    *,
    fiscal_year: int,
    revenue_fact: dict[str, Any],
    net_income_fact: dict[str, Any] | None,
    operating_income_fact: dict[str, Any] | None,
    assets_fact: dict[str, Any] | None,
    liabilities_fact: dict[str, Any] | None,
    cash_fact: dict[str, Any] | None,
    debt_fact: dict[str, Any] | None,
    operating_cash_flow_fact: dict[str, Any] | None,
    capital_expenditure_fact: dict[str, Any] | None,
    free_cash_flow_available: bool,
) -> dict[str, Any]:
    sources = {
        "revenue": _metric_source("revenue", revenue_fact),
    }
    optional_facts = {
        "net_income": net_income_fact,
        "operating_income": operating_income_fact,
        "assets": assets_fact,
        "liabilities": liabilities_fact,
        "cash": cash_fact,
        "debt": debt_fact,
        "operating_cash_flow": operating_cash_flow_fact,
        "capital_expenditure": capital_expenditure_fact,
    }
    for metric, fact in optional_facts.items():
        if fact is not None:
            sources[metric] = _metric_source(metric, fact)

    if free_cash_flow_available:
        sources["free_cash_flow"] = {
            "metric": "free_cash_flow",
            "fy": fiscal_year,
            "components": ["operating_cash_flow", "capital_expenditure"],
        }

    return sources


def _metric_source(metric: str, fact: dict[str, Any]) -> dict[str, Any]:
    return {
        "metric": metric,
        "fy": fact.get("fy"),
        "tag": fact.get("_tag"),
        "unit": fact.get("_unit"),
        "form": fact.get("form"),
        "filed": fact.get("filed"),
        "period": fact.get("end"),
        "accession_number": fact.get("accn"),
    }
