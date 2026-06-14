from typing import Any

SEC_COMPANY_FACTS_SOURCE_ID = "sec_company_facts"


def synthesize_research_insights(
    *,
    company_name: str,
    ticker: str,
    financial_metrics: dict[str, Any] | None,
    risk_themes: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    metrics = financial_metrics or {"periods": []}
    periods = metrics.get("periods", [])
    latest_period = periods[-1] if periods else None

    return {
        "executive_summary": _executive_summary(company_name, ticker, latest_period),
        "bull_case": _bull_case(latest_period),
        "bear_case": _bear_case(risk_themes),
        "open_questions": _open_questions(periods, risk_themes, warnings),
    }


def _executive_summary(
    company_name: str,
    ticker: str,
    latest_period: dict[str, Any] | None,
) -> list[str]:
    summary = [
        f"{company_name} ({ticker}) was reviewed using available SEC-derived evidence."
    ]
    if latest_period is not None:
        fiscal_year = latest_period.get("fy", "latest available fiscal year")
        summary.append(
            f"The latest extracted financial period is fiscal {fiscal_year}, based on structured SEC company facts."
        )
    return summary


def _bull_case(latest_period: dict[str, Any] | None) -> list[dict[str, Any]]:
    if latest_period is None:
        return []

    points: list[dict[str, Any]] = []
    fiscal_year = latest_period.get("fy", "the latest available fiscal year")
    revenue_growth = latest_period.get("revenue_growth")
    if isinstance(revenue_growth, int | float) and revenue_growth > 0:
        points.append(
            {
                "title": "Revenue growth",
                "summary": (
                    f"Extracted revenue increased {revenue_growth:.2%} year over year "
                    f"in fiscal {fiscal_year}."
                ),
                "source": "SEC company facts",
                "source_ids": [SEC_COMPANY_FACTS_SOURCE_ID],
            }
        )

    free_cash_flow = latest_period.get("free_cash_flow")
    if isinstance(free_cash_flow, int | float) and free_cash_flow > 0:
        points.append(
            {
                "title": "Positive free cash flow",
                "summary": (
                    f"Extracted free cash flow was {free_cash_flow} in fiscal {fiscal_year}."
                ),
                "source": "SEC company facts",
                "source_ids": [SEC_COMPANY_FACTS_SOURCE_ID],
            }
        )

    return points


def _bear_case(risk_themes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "title": str(theme.get("title", "Risk theme")),
            "summary": (
                "The bear case includes this source-grounded risk theme: "
                f"{theme.get('summary', 'No summary available.')}"
            ),
            "source": _risk_theme_source(theme),
            "source_ids": _source_ids(theme),
        }
        for theme in risk_themes
    ]


def _open_questions(
    periods: list[dict[str, Any]],
    risk_themes: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> list[str]:
    questions = [
        "What changed in the latest annual filing compared with prior years?",
        "Are revenue growth, margins, and free cash flow durable?",
        "Which risks require deeper analyst review?",
    ]
    if not periods or any(warning.get("code") == "metric_warning" for warning in warnings):
        questions.append(
            "Which missing SEC metrics are needed before drawing firmer research conclusions?"
        )
    if not risk_themes:
        questions.append(
            "What risk themes emerge once latest annual risk-factor text is available?"
        )
    return questions


def _risk_theme_source(theme: dict[str, Any]) -> str:
    source_form = theme.get("source_form", "filing")
    filing_date = theme.get("filing_date", "unknown date")
    accession_number = theme.get("accession_number", "unknown accession")
    return f"{source_form} filed {filing_date}, accession {accession_number}"


def _source_ids(source: dict[str, Any]) -> list[str]:
    values = source.get("source_ids")
    if not isinstance(values, list):
        return []

    return [
        normalized
        for value in values
        if (normalized := str(value).strip())
    ]
