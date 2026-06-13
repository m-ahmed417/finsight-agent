import json
from pathlib import Path

from finsight_agent.app.services.metrics import extract_financial_metrics

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_sample_company_facts() -> dict:
    return json.loads((FIXTURES_DIR / "sample_company_facts.json").read_text())


def test_extracts_revenue_and_net_income_from_company_facts() -> None:
    metrics = extract_financial_metrics(load_sample_company_facts())

    periods = metrics["periods"]

    assert periods[0]["fy"] == 2023
    assert periods[0]["revenue"] == 1000000000
    assert periods[0]["net_income"] == 150000000
    assert periods[1]["fy"] == 2024
    assert periods[1]["revenue"] == 1250000000
    assert periods[1]["net_income"] == 250000000


def test_calculates_revenue_growth_and_net_margin() -> None:
    metrics = extract_financial_metrics(load_sample_company_facts())
    latest_period = metrics["periods"][1]

    assert latest_period["revenue_growth"] == 0.25
    assert latest_period["net_margin"] == 0.2


def test_extracts_operating_income_and_calculates_operating_margin() -> None:
    metrics = extract_financial_metrics(load_sample_company_facts())
    latest_period = metrics["periods"][1]

    assert latest_period["operating_income"] == 300000000
    assert latest_period["operating_margin"] == 0.24


def test_extracts_basic_balance_sheet_metrics() -> None:
    metrics = extract_financial_metrics(load_sample_company_facts())
    latest_period = metrics["periods"][1]

    assert latest_period["assets"] == 4000000000
    assert latest_period["liabilities"] == 2400000000
    assert latest_period["cash"] == 900000000
    assert latest_period["debt"] == 850000000


def test_extracts_cash_flow_metrics_and_calculates_free_cash_flow() -> None:
    metrics = extract_financial_metrics(load_sample_company_facts())
    latest_period = metrics["periods"][1]

    assert latest_period["operating_cash_flow"] == 400000000
    assert latest_period["capital_expenditure"] == 120000000
    assert latest_period["free_cash_flow"] == 280000000


def test_first_period_has_no_revenue_growth() -> None:
    metrics = extract_financial_metrics(load_sample_company_facts())
    first_period = metrics["periods"][0]

    assert first_period["revenue_growth"] is None


def test_prefers_annual_10k_fact_over_10q_fact_for_same_fiscal_year() -> None:
    metrics = extract_financial_metrics(load_sample_company_facts())
    latest_period = metrics["periods"][1]

    assert latest_period["revenue"] == 1250000000


def test_ignores_non_usd_units_for_usd_metrics() -> None:
    metrics = extract_financial_metrics(load_sample_company_facts())
    latest_period = metrics["periods"][1]

    assert latest_period["revenue"] != 999000000


def test_falls_back_to_alternate_revenue_tag() -> None:
    company_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 500000000,
                            }
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 50000000,
                            }
                        ]
                    }
                },
            }
        }
    }

    metrics = extract_financial_metrics(company_facts)

    assert metrics["periods"][0]["revenue"] == 500000000
    assert metrics["periods"][0]["net_margin"] == 0.1


def test_falls_back_to_alternate_cash_tag() -> None:
    company_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 500000000,
                            }
                        ]
                    }
                },
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 125000000,
                            }
                        ]
                    }
                },
            }
        }
    }

    metrics = extract_financial_metrics(company_facts)

    assert metrics["periods"][0]["cash"] == 125000000


def test_normalizes_negative_capex_as_positive_outflow() -> None:
    company_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 500000000,
                            }
                        ]
                    }
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 200000000,
                            }
                        ]
                    }
                },
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": -50000000,
                            }
                        ]
                    }
                },
            }
        }
    }

    metrics = extract_financial_metrics(company_facts)

    assert metrics["periods"][0]["capital_expenditure"] == 50000000
    assert metrics["periods"][0]["free_cash_flow"] == 150000000


def test_falls_back_to_alternate_capex_tag() -> None:
    company_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 500000000,
                            }
                        ]
                    }
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 200000000,
                            }
                        ]
                    }
                },
                "PaymentsToAcquireProductiveAssets": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 75000000,
                            }
                        ]
                    }
                },
            }
        }
    }

    metrics = extract_financial_metrics(company_facts)

    assert metrics["periods"][0]["capital_expenditure"] == 75000000
    assert metrics["periods"][0]["free_cash_flow"] == 125000000


def test_falls_back_to_debt_component_tags() -> None:
    company_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 500000000,
                            }
                        ]
                    }
                },
                "LongTermDebtCurrent": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 100000000,
                            }
                        ]
                    }
                },
                "LongTermDebtNoncurrent": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 300000000,
                            }
                        ]
                    }
                },
            }
        }
    }

    metrics = extract_financial_metrics(company_facts)

    assert metrics["periods"][0]["debt"] == 400000000


def test_missing_capex_adds_warning_and_free_cash_flow_is_none() -> None:
    company_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 500000000,
                            }
                        ]
                    }
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 200000000,
                            }
                        ]
                    }
                },
            }
        }
    }

    metrics = extract_financial_metrics(company_facts)

    assert metrics["periods"][0]["capital_expenditure"] is None
    assert metrics["periods"][0]["free_cash_flow"] is None
    assert "Capital expenditure could not be extracted from SEC company facts." in metrics[
        "warnings"
    ]


def test_missing_net_income_adds_warning_and_keeps_revenue_period() -> None:
    company_facts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 500000000,
                            }
                        ]
                    }
                }
            }
        }
    }

    metrics = extract_financial_metrics(company_facts)

    assert metrics["periods"][0]["fy"] == 2024
    assert metrics["periods"][0]["revenue"] == 500000000
    assert metrics["periods"][0]["net_income"] is None
    assert metrics["periods"][0]["net_margin"] is None
    assert "Net income could not be extracted from SEC company facts." in metrics[
        "warnings"
    ]


def test_missing_operating_income_adds_warning_but_keeps_period() -> None:
    company_facts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 500000000,
                            }
                        ]
                    }
                }
            }
        }
    }

    metrics = extract_financial_metrics(company_facts)

    assert metrics["periods"][0]["operating_income"] is None
    assert metrics["periods"][0]["operating_margin"] is None
    assert "Operating income could not be extracted from SEC company facts." in metrics[
        "warnings"
    ]


def test_missing_revenue_returns_no_periods_and_warning() -> None:
    company_facts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "val": 50000000,
                            }
                        ]
                    }
                }
            }
        }
    }

    metrics = extract_financial_metrics(company_facts)

    assert metrics["periods"] == []
    assert metrics["warnings"] == [
        "Revenue could not be extracted from SEC company facts."
    ]
