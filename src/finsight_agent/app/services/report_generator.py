from typing import Any

RESEARCH_ONLY_NOTICE = (
    "This report is for informational and educational research purposes only. "
    "It is not financial advice, investment advice, or a recommendation to buy, "
    "sell, or hold any security."
)

SEC_COMPANY_FACTS_SOURCE_ID = "sec_company_facts"
LATEST_10K_SOURCE_ID = "latest_10k"
LATEST_10Q_SOURCE_ID = "latest_10q"


def generate_research_report(
    *,
    company_name: str,
    ticker: str,
    financial_metrics: dict[str, Any] | None,
    latest_10k: dict[str, Any] | None,
    latest_10q: dict[str, Any] | None,
    warnings: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    risk_factors: list[dict[str, Any]] | None = None,
    risk_themes: list[dict[str, Any]] | None = None,
    research_insights: dict[str, Any] | None = None,
    llm_report_sections: dict[str, Any] | None = None,
) -> str:
    metrics = financial_metrics or {"periods": []}
    extracted_risk_factors = risk_factors or []
    analyzed_risk_themes = risk_themes or []
    insights = research_insights or {}
    drafted_sections = llm_report_sections or {}
    return "\n\n".join(
        [
            f"# FinSight Research Brief: {company_name} ({ticker})",
            f"## 1. Research-Only Notice\n\n{RESEARCH_ONLY_NOTICE}",
            "## 2. Executive Summary\n\n"
            + _executive_summary_section(
                insights,
                company_name,
                ticker,
                drafted_sections,
            ),
            "## 3. Company Overview\n\n"
            "A detailed business overview has not been generated yet. This section "
            "will later be grounded in filing text and company descriptions.",
            "## 4. Financial Performance\n\n"
            + _financial_performance_summary(metrics, drafted_sections),
            "## 5. Key Financial Metrics\n\n" + _metrics_table(metrics),
            "## 6. Risk Factors\n\n"
            + _risk_factors_section(
                extracted_risk_factors,
                analyzed_risk_themes,
                drafted_sections,
            ),
            "## 7. Bull Case\n\n"
            + _research_points_section(
                insights.get("bull_case", []),
                drafted_sections.get("bull_case"),
            ),
            "## 8. Bear Case\n\n"
            + _research_points_section(
                insights.get("bear_case", []),
                drafted_sections.get("bear_case"),
            ),
            "## 9. Open Questions for Further Research\n\n"
            + _open_questions_section(
                insights.get("open_questions", []),
                drafted_sections,
            ),
            "## 10. Sources Used\n\n" + _sources_section(latest_10k, latest_10q, sources),
            "## 11. Limitations\n\n" + _limitations_section(warnings),
        ]
    )


def _financial_performance_summary(
    financial_metrics: dict[str, Any],
    llm_report_sections: dict[str, Any],
) -> str:
    if llm_report_sections.get("financial_performance"):
        return str(llm_report_sections["financial_performance"])

    periods = financial_metrics.get("periods", [])
    if not periods:
        return "Financial metrics were unavailable or could not be extracted."

    latest = periods[-1]
    fiscal_year = latest.get("fy", "latest available period")
    revenue = _format_value(latest.get("revenue"))
    net_income = _format_value(latest.get("net_income"))
    free_cash_flow = _format_value(latest.get("free_cash_flow"))

    summary = (
        f"For fiscal year {fiscal_year}, extracted revenue was {revenue}, "
        f"net income was {net_income}, and free cash flow was {free_cash_flow}."
    )
    return f"{summary} {_format_citations([SEC_COMPANY_FACTS_SOURCE_ID])}"


def _metrics_table(financial_metrics: dict[str, Any]) -> str:
    periods = financial_metrics.get("periods", [])
    if not periods:
        return "No financial metrics are available."

    rows = [
        "| Fiscal Year | Revenue | Revenue Growth | Operating Margin | Net Margin | Free Cash Flow |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    rows.extend(
        " | ".join(
            [
                f"| {period.get('fy')}",
                _format_value(period.get("revenue")),
                _format_percentage(period.get("revenue_growth")),
                _format_percentage(period.get("operating_margin")),
                _format_percentage(period.get("net_margin")),
                f"{_format_value(period.get('free_cash_flow'))} |",
            ]
        )
        for period in periods
    )
    return "\n".join(rows)


def _sources_section(
    latest_10k: dict[str, Any] | None,
    latest_10q: dict[str, Any] | None,
    sources: list[dict[str, Any]],
) -> str:
    source_lines: list[str] = []
    seen_source_ids: set[str] = set()
    for source in sources:
        source_lines.append(_format_source_line(source))
        source_id = str(source.get("source_id", "")).strip()
        if source_id:
            seen_source_ids.add(source_id)

    if latest_10k and LATEST_10K_SOURCE_ID not in seen_source_ids:
        source_lines.append(
            f"- [{LATEST_10K_SOURCE_ID}] Latest 10-K: "
            f"filed {latest_10k.get('filing_date')}, "
            f"accession {latest_10k.get('accession_number')}."
        )
    if latest_10q and LATEST_10Q_SOURCE_ID not in seen_source_ids:
        source_lines.append(
            f"- [{LATEST_10Q_SOURCE_ID}] Latest 10-Q: "
            f"filed {latest_10q.get('filing_date')}, "
            f"accession {latest_10q.get('accession_number')}."
        )

    if not source_lines:
        return "No sources were recorded."
    return "\n".join(source_lines)


def _executive_summary_section(
    research_insights: dict[str, Any],
    company_name: str,
    ticker: str,
    llm_report_sections: dict[str, Any],
) -> str:
    drafted_summary = llm_report_sections.get("executive_summary")
    if drafted_summary:
        return _plain_bullet_section(drafted_summary)

    summary_points = research_insights.get("executive_summary", [])
    if summary_points:
        return "\n".join(f"- {point}" for point in summary_points)

    return (
        f"{company_name} ({ticker}) was analyzed using available SEC filing "
        "metadata and structured company facts. This draft is generated from "
        "deterministic data extraction and should be reviewed alongside the "
        "source filings."
    )


def _research_points_section(
    points: list[dict[str, Any]],
    drafted_points: list[str] | None = None,
) -> str:
    if drafted_points:
        return _plain_bullet_section(drafted_points)

    if not points:
        return (
            "This section is pending deterministic synthesis from grounded "
            "financial metrics and filing evidence."
        )

    return "\n".join(_format_research_point(point) for point in points)


def _format_research_point(point: dict[str, Any]) -> str:
    title = point.get("title", "Research point")
    summary = point.get("summary", "No summary available.")
    source = point.get("source")
    citations = _format_citations(point.get("source_ids"))
    if source:
        return f"- **{title}**: {summary} (Source: {source}){_citation_suffix(citations)}"
    return f"- **{title}**: {summary}{_citation_suffix(citations)}"


def _open_questions_section(
    questions: list[str],
    llm_report_sections: dict[str, Any],
) -> str:
    drafted_questions = llm_report_sections.get("open_questions")
    if drafted_questions:
        return _plain_bullet_section(drafted_questions)

    if not questions:
        return (
            "- What changed in the latest annual filing compared with prior years?\n"
            "- Are revenue growth, margins, and free cash flow durable?\n"
            "- Which risks require deeper analyst review?"
        )
    return "\n".join(f"- {question}" for question in questions)


def _risk_factors_section(
    risk_factors: list[dict[str, Any]],
    risk_themes: list[dict[str, Any]],
    llm_report_sections: dict[str, Any],
) -> str:
    drafted_risks = llm_report_sections.get("risk_factors")
    if drafted_risks:
        return _plain_bullet_section(drafted_risks)

    if risk_themes:
        return "\n".join(_format_risk_theme(theme) for theme in risk_themes)

    if not risk_factors:
        return (
            "Risk factor analysis has not been performed yet. Future versions will "
            "summarize risks from the latest available 10-K filing."
        )

    latest = risk_factors[0]
    form = latest.get("form", "filing")
    filing_date = latest.get("filing_date", "an unknown date")
    summary = (
        f"Risk-factor text was retrieved from the latest {form} filed {filing_date}. "
        "A future LLM-assisted step will summarize this extracted text into "
        "source-grounded risk themes."
    )
    return f"{summary}{_citation_suffix(_format_citations(latest.get('source_ids')))}"


def _format_risk_theme(theme: dict[str, Any]) -> str:
    title = theme.get("title", "Risk theme")
    summary = theme.get("summary", "No summary available.")
    source_form = theme.get("source_form", "filing")
    filing_date = theme.get("filing_date", "unknown date")
    accession_number = theme.get("accession_number", "unknown accession")
    summary_text = (
        f"- **{title}**: {summary} "
        f"({source_form} filed {filing_date}, accession {accession_number})"
    )
    return f"{summary_text}{_citation_suffix(_format_citations(theme.get('source_ids')))}"


def _limitations_section(warnings: list[dict[str, Any]]) -> str:
    if not warnings:
        return "- This report is an MVP draft and does not yet include risk-factor analysis."

    return "\n".join(f"- {warning.get('message', warning)}" for warning in warnings)


def _format_value(value: Any) -> str:
    if value is None:
        return "N/A"
    return str(value)


def _format_percentage(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2%}"


def _format_source_line(source: dict[str, Any]) -> str:
    label = source.get("label") or source.get("source_type") or "Source"
    source_id = str(source.get("source_id", "")).strip()
    label_prefix = f"[{source_id}] " if source_id else ""
    url = source.get("url")
    details = _source_detail_fragments(source)
    detail_suffix = f" ({'; '.join(details)})" if details else ""
    if url:
        return f"- {label_prefix}{label}: {url}{detail_suffix}"
    return f"- {label_prefix}{label}{detail_suffix}"


def _source_detail_fragments(source: dict[str, Any]) -> list[str]:
    details: list[str] = []
    if source.get("form") and source.get("filing_date"):
        details.append(f"{source['form']} filed {source['filing_date']}")
    elif source.get("filing_date"):
        details.append(f"filed {source['filing_date']}")

    if source.get("report_date"):
        details.append(f"report date {source['report_date']}")
    if source.get("accession_number"):
        details.append(f"accession {source['accession_number']}")
    if source.get("primary_document"):
        details.append(f"primary document {source['primary_document']}")
    if source.get("metric_fiscal_years"):
        fiscal_years = ", ".join(str(year) for year in source["metric_fiscal_years"])
        details.append(f"metric fiscal years {fiscal_years}")
    if source.get("xbrl_tags_used"):
        tags = ", ".join(str(tag) for tag in source["xbrl_tags_used"])
        details.append(f"XBRL tags used: {tags}")
    if source.get("extracted_sections"):
        sections = ", ".join(str(section) for section in source["extracted_sections"])
        details.append(f"extracted sections: {sections}")
    if source.get("extraction_status"):
        details.append(str(source["extraction_status"]).replace("_", " "))
    if source.get("document_retrieved_at"):
        details.append(f"document retrieved {source['document_retrieved_at']}")
    elif source.get("retrieved_at"):
        details.append(f"retrieved {source['retrieved_at']}")
    elif source.get("metadata_retrieved_at"):
        details.append(f"metadata retrieved {source['metadata_retrieved_at']}")

    return details


def _plain_bullet_section(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _format_citations(source_ids: Any) -> str:
    if not isinstance(source_ids, list):
        return ""

    citations: list[str] = []
    seen: set[str] = set()
    for source_id in source_ids:
        normalized = str(source_id).strip()
        if not normalized or normalized in seen:
            continue
        citations.append(f"[{normalized}]")
        seen.add(normalized)

    return " ".join(citations)


def _citation_suffix(citations: str) -> str:
    return f" {citations}" if citations else ""
