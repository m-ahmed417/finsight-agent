from datetime import datetime, timezone
import re
from typing import Any

from langgraph.graph import END, StateGraph

from finsight_agent.app.graph.state import FinSightState
from finsight_agent.app.services.company_resolver import ResolutionStatus
from finsight_agent.app.services.compliance import (
    check_report_compliance,
    rewrite_unsafe_report,
)
from finsight_agent.app.services.filing_parser import (
    extract_risk_factors_section,
    find_latest_filing,
    normalize_accession_number,
)
from finsight_agent.app.services.metrics import extract_financial_metrics
from finsight_agent.app.services.research_synthesizer import synthesize_research_insights
from finsight_agent.app.services.risk_analyzer import analyze_risk_factors
from finsight_agent.app.services.report_generator import generate_research_report
from finsight_agent.app.services.report_validator import validate_report_quality

SEC_SUBMISSIONS_SOURCE_ID = "sec_submissions"
SEC_COMPANY_FACTS_SOURCE_ID = "sec_company_facts"
LATEST_10K_SOURCE_ID = "latest_10k"
LATEST_10Q_SOURCE_ID = "latest_10q"
LLM_DRAFT_CITATION_PATTERN = re.compile(r"\[([A-Za-z][A-Za-z0-9_-]*)\]")
LLM_SOURCE_GROUNDED_REPORT_FIELDS = (
    "financial_performance",
    "risk_factors",
    "bull_case",
    "bear_case",
)


def build_research_graph(
    resolver: Any,
    sec_client: Any,
    llm_client: Any | None = None,
):
    graph = StateGraph(FinSightState)

    graph.add_node("initialize", _initialize_state)
    graph.add_node("resolve_company", _make_resolve_company_node(resolver))
    graph.add_node("fetch_sec_data", _make_fetch_sec_data_node(sec_client))
    graph.add_node("identify_filings", _identify_filings)
    graph.add_node("fetch_filing_text", _make_fetch_filing_text_node(sec_client))
    graph.add_node("analyze_risks", _make_analyze_risks_node(llm_client))
    graph.add_node("extract_metrics", _extract_metrics)
    graph.add_node("synthesize_research", _synthesize_research)
    graph.add_node("draft_report", _make_draft_report_node(llm_client))
    graph.add_node("generate_report", _generate_report)
    graph.add_node("compliance_check", _compliance_check)
    graph.add_node("validate_report", _validate_report)

    graph.set_entry_point("initialize")
    graph.add_edge("initialize", "resolve_company")
    graph.add_conditional_edges(
        "resolve_company",
        _route_after_resolve,
        {
            "continue": "fetch_sec_data",
            "stop": END,
        },
    )
    graph.add_conditional_edges(
        "fetch_sec_data",
        _route_after_sec_fetch,
        {
            "continue": "identify_filings",
            "stop": END,
        },
    )
    graph.add_edge("identify_filings", "fetch_filing_text")
    graph.add_edge("fetch_filing_text", "analyze_risks")
    graph.add_edge("analyze_risks", "extract_metrics")
    graph.add_edge("extract_metrics", "synthesize_research")
    graph.add_edge("synthesize_research", "draft_report")
    graph.add_edge("draft_report", "generate_report")
    graph.add_edge("generate_report", "compliance_check")
    graph.add_conditional_edges(
        "compliance_check",
        _route_after_compliance,
        {
            "validate": "validate_report",
            "stop": END,
        },
    )
    graph.add_edge("validate_report", END)

    return graph.compile()


def _initialize_state(state: FinSightState) -> FinSightState:
    return {
        "ticker": state.get("ticker"),
        "company_name": state.get("company_name"),
        "cik": state.get("cik"),
        "resolution_status": state.get("resolution_status"),
        "resolution_confidence": state.get("resolution_confidence"),
        "candidate_matches": state.get("candidate_matches", []),
        "sec_submissions": state.get("sec_submissions"),
        "company_facts": state.get("company_facts"),
        "latest_10k": state.get("latest_10k"),
        "latest_10q": state.get("latest_10q"),
        "filing_text": state.get("filing_text"),
        "risk_factors": state.get("risk_factors", []),
        "risk_themes": state.get("risk_themes", []),
        "financial_metrics": state.get("financial_metrics"),
        "research_insights": state.get("research_insights"),
        "llm_report_sections": state.get("llm_report_sections"),
        "report_draft": state.get("report_draft"),
        "final_report": state.get("final_report"),
        "compliance_status": state.get("compliance_status"),
        "report_quality_status": state.get("report_quality_status"),
        "agent_steps": state.get("agent_steps", []),
        "sources": state.get("sources", []),
        "warnings": state.get("warnings", []),
        "errors": state.get("errors", []),
    }


def _make_resolve_company_node(resolver: Any):
    def resolve_company(state: FinSightState) -> FinSightState:
        resolution = resolver.resolve(state["user_query"])
        updates: FinSightState = {
            "resolution_status": resolution.status.value,
            "resolution_confidence": resolution.confidence,
        }

        if resolution.company is not None:
            updates.update(
                {
                    "ticker": resolution.company.ticker,
                    "company_name": resolution.company.company_name,
                    "cik": resolution.company.cik,
                    "agent_steps": _append_step(
                        state,
                        "resolve_company",
                        "completed",
                        f"Resolved {resolution.company.ticker} to {resolution.company.company_name}.",
                    ),
                }
            )
            return updates

        if resolution.status == ResolutionStatus.AMBIGUOUS:
            message = resolution.message or "Multiple companies matched the query."
            return {
                **updates,
                "candidate_matches": [
                    _company_to_candidate(match.company) for match in resolution.matches
                ],
                "agent_steps": _append_step(
                    state,
                    "resolve_company",
                    "failed",
                    message,
                ),
                "errors": [
                    {
                        "code": "company_ambiguous",
                        "message": message,
                        "severity": "error",
                    }
                ],
            }

        message = resolution.message or "Could not confidently resolve the company."
        return {
            **updates,
            "agent_steps": _append_step(
                state,
                "resolve_company",
                "failed",
                message,
            ),
            "errors": [
                {
                    "code": "company_not_found",
                    "message": message,
                    "severity": "error",
                }
            ],
        }

    return resolve_company


def _make_fetch_sec_data_node(sec_client: Any):
    def fetch_sec_data(state: FinSightState) -> FinSightState:
        cik = state.get("cik")
        if cik is None:
            return {
                "agent_steps": _append_step(
                    state,
                    "fetch_sec_data",
                    "failed",
                    "Cannot fetch SEC data without a CIK.",
                ),
                "errors": [
                    {
                        "code": "missing_cik",
                        "message": "Cannot fetch SEC data without a CIK.",
                        "severity": "error",
                    }
                ]
            }

        try:
            sec_submissions = sec_client.fetch_company_submissions(cik)
            company_facts = sec_client.fetch_company_facts(cik)
        except Exception as exc:
            message = str(exc)
            return {
                "agent_steps": _append_step(
                    state,
                    "fetch_sec_data",
                    "failed",
                    message,
                ),
                "errors": [
                    {
                        "code": "sec_fetch_failed",
                        "message": message,
                        "severity": "error",
                    }
                ]
            }

        normalized_cik = _normalize_cik(cik)
        retrieved_at = _utc_timestamp()
        return {
            "sec_submissions": sec_submissions,
            "company_facts": company_facts,
            "sources": [
                *state.get("sources", []),
                {
                    "source_id": SEC_SUBMISSIONS_SOURCE_ID,
                    "source_type": "sec_submissions",
                    "label": "SEC submissions",
                    "cik": normalized_cik,
                    "url": _sec_submissions_url(normalized_cik),
                    "retrieved_at": retrieved_at,
                },
                {
                    "source_id": SEC_COMPANY_FACTS_SOURCE_ID,
                    "source_type": "sec_company_facts",
                    "label": "SEC company facts",
                    "cik": normalized_cik,
                    "url": _sec_company_facts_url(normalized_cik),
                    "retrieved_at": retrieved_at,
                },
            ],
            "agent_steps": _append_step(
                state,
                "fetch_sec_data",
                "completed",
                "Fetched SEC submissions and company facts.",
            ),
        }

    return fetch_sec_data


def _identify_filings(state: FinSightState) -> FinSightState:
    submissions = state.get("sec_submissions") or {}
    latest_10k = find_latest_filing(submissions, form_type="10-K")
    latest_10q = find_latest_filing(submissions, form_type="10-Q")
    latest_10k_data = latest_10k.model_dump(mode="json") if latest_10k else None
    latest_10q_data = latest_10q.model_dump(mode="json") if latest_10q else None

    return {
        "latest_10k": latest_10k_data,
        "latest_10q": latest_10q_data,
        "sources": [
            *state.get("sources", []),
            *[
                source
                for source in (
                    _filing_source(
                        state.get("cik"),
                        latest_10k_data,
                        "Latest 10-K filing",
                        LATEST_10K_SOURCE_ID,
                    ),
                    _filing_source(
                        state.get("cik"),
                        latest_10q_data,
                        "Latest 10-Q filing",
                        LATEST_10Q_SOURCE_ID,
                    ),
                )
                if source is not None
            ],
        ],
        "agent_steps": _append_step(
            state,
            "identify_filings",
            "completed",
            "Identified latest 10-K and 10-Q filing metadata.",
        ),
    }


def _make_fetch_filing_text_node(sec_client: Any):
    def fetch_filing_text(state: FinSightState) -> FinSightState:
        latest_10k = state.get("latest_10k")
        cik = state.get("cik")
        if not latest_10k or not cik:
            return _filing_text_unavailable_update(
                state,
                "No latest 10-K filing was available for risk-factor extraction.",
            )

        accession_number = latest_10k.get("accession_number")
        primary_document = latest_10k.get("primary_document")
        if not accession_number or not primary_document:
            return _filing_text_unavailable_update(
                state,
                "Latest 10-K filing did not include a primary document.",
            )

        try:
            filing_text = sec_client.fetch_filing_document(
                cik=cik,
                accession_number=accession_number,
                primary_document=primary_document,
            )
        except Exception as exc:
            return _filing_text_unavailable_update(state, str(exc))

        section = extract_risk_factors_section(filing_text)
        if section is None:
            return {
                "filing_text": filing_text,
                "risk_factors": [],
                "warnings": [
                    *state.get("warnings", []),
                    {
                        "code": "risk_factors_unavailable",
                        "message": "Item 1A risk-factor section could not be extracted.",
                        "severity": "warning",
                    },
                ],
                "agent_steps": _append_step(
                    state,
                    "fetch_filing_text",
                    "completed",
                    "Retrieved latest 10-K but could not extract risk-factor text.",
                ),
            }

        source_url = _filing_document_url(
            cik=_normalize_cik(cik),
            accession_number=accession_number,
            primary_document=primary_document,
        )
        return {
            "filing_text": filing_text,
            "risk_factors": [
                {
                    "source_type": "sec_risk_factors",
                    "form": latest_10k.get("form"),
                    "filing_date": latest_10k.get("filing_date"),
                    "accession_number": accession_number,
                    "source_url": source_url,
                    "source_ids": [LATEST_10K_SOURCE_ID],
                    "text": section.text,
                }
            ],
            "agent_steps": _append_step(
                state,
                "fetch_filing_text",
                "completed",
                "Retrieved latest 10-K risk-factor text.",
            ),
        }

    return fetch_filing_text


def _make_analyze_risks_node(llm_client: Any | None):
    def analyze_risks(state: FinSightState) -> FinSightState:
        risk_factors = state.get("risk_factors", [])
        warnings = state.get("warnings", [])
        used_llm = False
        if llm_client is not None:
            try:
                analysis = _validate_risk_analysis(llm_client.summarize_risks(risk_factors))
                used_llm = True
            except Exception as exc:
                warnings = [
                    *warnings,
                    {
                        "code": "llm_risk_analysis_unavailable",
                        "message": str(exc),
                        "severity": "warning",
                    },
                ]
                analysis = analyze_risk_factors(risk_factors)
        else:
            analysis = analyze_risk_factors(risk_factors)

        warnings = [
            *warnings,
            *analysis.get("warnings", []),
        ]
        themes = analysis.get("themes", [])
        message = _risk_analysis_message(themes, used_llm)

        return {
            "risk_themes": themes,
            "warnings": warnings,
            "agent_steps": _append_step(
                state,
                "analyze_risks",
                "completed",
                message,
            ),
        }

    return analyze_risks


def _extract_metrics(state: FinSightState) -> FinSightState:
    company_facts = state.get("company_facts") or {}
    metrics = extract_financial_metrics(company_facts)
    warnings = [
        *state.get("warnings", []),
        *[
            {
                "code": "metric_warning",
                "message": warning,
                "severity": "warning",
            }
            for warning in metrics.get("warnings", [])
        ],
    ]

    return {
        "financial_metrics": metrics,
        "warnings": warnings,
        "agent_steps": _append_step(
            state,
            "extract_metrics",
            "completed",
            "Extracted financial metrics from SEC company facts.",
        ),
    }


def _synthesize_research(state: FinSightState) -> FinSightState:
    insights = synthesize_research_insights(
        company_name=state.get("company_name") or "Unknown Company",
        ticker=state.get("ticker") or "UNKNOWN",
        financial_metrics=state.get("financial_metrics"),
        risk_themes=state.get("risk_themes", []),
        warnings=state.get("warnings", []),
    )
    return {
        "research_insights": insights,
        "agent_steps": _append_step(
            state,
            "synthesize_research",
            "completed",
            "Generated deterministic bull, bear, summary, and open-question points.",
        ),
    }


def _make_draft_report_node(llm_client: Any | None):
    def draft_report(state: FinSightState) -> FinSightState:
        if llm_client is None or not hasattr(llm_client, "draft_report"):
            return {
                "llm_report_sections": None,
                "agent_steps": _append_step(
                    state,
                    "draft_report",
                    "completed",
                    "Using deterministic report generator.",
                ),
            }

        try:
            draft = _validate_report_draft(
                llm_client.draft_report(_report_evidence(state)),
                known_source_ids=_known_source_ids(state),
            )
        except Exception as exc:
            return {
                "llm_report_sections": None,
                "warnings": [
                    *state.get("warnings", []),
                    {
                        "code": "llm_report_drafting_unavailable",
                        "message": str(exc),
                        "severity": "warning",
                    },
                ],
                "agent_steps": _append_step(
                    state,
                    "draft_report",
                    "completed",
                    "Using deterministic report generator after LLM report drafting failed.",
                ),
            }

        return {
            "llm_report_sections": draft["sections"],
            "warnings": [
                *state.get("warnings", []),
                *draft.get("warnings", []),
            ],
            "agent_steps": _append_step(
                state,
                "draft_report",
                "completed",
                "Generated LLM-assisted report sections from structured evidence.",
            ),
        }

    return draft_report


def _generate_report(state: FinSightState) -> FinSightState:
    report_draft = generate_research_report(
        company_name=state.get("company_name") or "Unknown Company",
        ticker=state.get("ticker") or "UNKNOWN",
        financial_metrics=state.get("financial_metrics"),
        latest_10k=state.get("latest_10k"),
        latest_10q=state.get("latest_10q"),
        warnings=state.get("warnings", []),
        sources=state.get("sources", []),
        risk_factors=state.get("risk_factors", []),
        risk_themes=state.get("risk_themes", []),
        research_insights=state.get("research_insights"),
        llm_report_sections=state.get("llm_report_sections"),
    )
    return {
        "report_draft": report_draft,
        "agent_steps": _append_step(
            state,
            "generate_report",
            "completed",
            "Generated deterministic research report draft.",
        ),
    }


def _compliance_check(state: FinSightState) -> FinSightState:
    report_draft = state.get("report_draft") or ""
    result = check_report_compliance(report_draft)
    warnings = [
        *state.get("warnings", []),
        *_compliance_warning_updates(result.warnings),
    ]

    if result.safe_report is None:
        rewrite_result = rewrite_unsafe_report(report_draft)
        warnings = [
            *warnings,
            *_compliance_warning_updates(rewrite_result.warnings),
        ]
        if rewrite_result.safe_report is not None:
            return {
                "compliance_status": rewrite_result.status.value,
                "final_report": rewrite_result.safe_report,
                "warnings": warnings,
                "agent_steps": _append_step(
                    state,
                    "compliance_check",
                    "completed",
                    "Report required deterministic compliance rewrite and passed.",
                ),
            }

        errors = [
            *state.get("errors", []),
            {
                "code": "compliance_blocked",
                "message": "Report contained unsafe financial-advice language.",
                "severity": "error",
            },
        ]
        return {
            "compliance_status": rewrite_result.status.value,
            "final_report": None,
            "warnings": warnings,
            "errors": errors,
            "agent_steps": _append_step(
                state,
                "compliance_check",
                "failed",
                "Report contained unsafe financial-advice language.",
            ),
        }

    return {
        "compliance_status": result.status.value,
        "final_report": result.safe_report,
        "warnings": warnings,
        "agent_steps": _append_step(
            state,
            "compliance_check",
            "completed",
            "Report passed deterministic compliance checks.",
        ),
    }


def _compliance_warning_updates(warnings: list[str]) -> list[dict[str, str]]:
    return [
        {
            "code": "compliance_warning",
            "message": warning,
            "severity": "warning",
        }
        for warning in warnings
    ]


def _validate_report(state: FinSightState) -> FinSightState:
    result = validate_report_quality(
        state.get("final_report"),
        sources=state.get("sources", []),
    )
    warnings = [
        *state.get("warnings", []),
        *[
            {
                "code": "report_quality_warning",
                "message": warning["message"],
                "severity": warning["severity"],
                "details": {"validator_code": warning["code"]},
            }
            for warning in result.warnings
        ],
    ]
    message = (
        "Report quality validation completed without warnings."
        if not result.warnings
        else "Report quality validation completed with warnings."
    )
    return {
        "report_quality_status": result.status.value,
        "warnings": warnings,
        "agent_steps": _append_step(
            state,
            "validate_report",
            "completed",
            message,
        ),
    }


def _route_after_resolve(state: FinSightState) -> str:
    return "stop" if state.get("errors") else "continue"


def _route_after_sec_fetch(state: FinSightState) -> str:
    return "stop" if state.get("errors") else "continue"


def _route_after_compliance(state: FinSightState) -> str:
    return "validate" if state.get("final_report") else "stop"


def _company_to_candidate(company: Any) -> dict[str, str]:
    return {
        "ticker": company.ticker,
        "company_name": company.company_name,
        "cik": company.cik,
    }


def _append_step(
    state: FinSightState,
    node_name: str,
    status: str,
    message: str,
) -> list[dict[str, str]]:
    return [
        *state.get("agent_steps", []),
        {
            "node_name": node_name,
            "status": status,
            "message": message,
        },
    ]


def _validate_risk_analysis(analysis: Any) -> dict[str, Any]:
    if not isinstance(analysis, dict):
        msg = "LLM risk analysis must return a dictionary."
        raise ValueError(msg)

    themes = analysis.get("themes")
    warnings = analysis.get("warnings", [])
    if not isinstance(themes, list):
        msg = "LLM risk analysis must include a themes list."
        raise ValueError(msg)
    if not themes:
        msg = "LLM risk analysis must include at least one theme."
        raise ValueError(msg)
    if not isinstance(warnings, list):
        msg = "LLM risk analysis warnings must be a list."
        raise ValueError(msg)

    return {"themes": themes, "warnings": warnings}


def _validate_report_draft(
    draft: Any,
    *,
    known_source_ids: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(draft, dict):
        msg = "LLM report draft must return a dictionary."
        raise ValueError(msg)

    sections = draft.get("sections")
    warnings = draft.get("warnings", [])
    if not isinstance(sections, dict):
        msg = "LLM report draft must include sections."
        raise ValueError(msg)
    required_string_fields = ("financial_performance",)
    required_list_fields = (
        "executive_summary",
        "risk_factors",
        "bull_case",
        "bear_case",
        "open_questions",
    )
    for field in required_string_fields:
        if not isinstance(sections.get(field), str) or not sections[field].strip():
            msg = "LLM report draft must include valid report sections."
            raise ValueError(msg)
    for field in required_list_fields:
        values = sections.get(field)
        if not isinstance(values, list) or not values:
            msg = "LLM report draft must include valid report sections."
            raise ValueError(msg)
        if any(not isinstance(value, str) or not value.strip() for value in values):
            msg = "LLM report draft must include valid report sections."
            raise ValueError(msg)
    if not isinstance(warnings, list):
        msg = "LLM report draft warnings must be a list."
        raise ValueError(msg)
    if known_source_ids is not None and not _has_required_llm_draft_citations(
        sections,
        known_source_ids,
    ):
        msg = (
            "LLM report draft must include known source_id citations in "
            "source-grounded sections."
        )
        raise ValueError(msg)

    return {"sections": sections, "warnings": warnings}


def _has_required_llm_draft_citations(
    sections: dict[str, Any],
    known_source_ids: set[str],
) -> bool:
    for field in LLM_SOURCE_GROUNDED_REPORT_FIELDS:
        section_citations = set().union(
            *[
                _extract_llm_draft_citations(value)
                for value in _report_section_values(sections[field])
            ]
        )
        if not section_citations.intersection(known_source_ids):
            return False
    return True


def _report_section_values(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        return [value]
    return value


def _extract_llm_draft_citations(text: str) -> set[str]:
    return {match.group(1) for match in LLM_DRAFT_CITATION_PATTERN.finditer(text)}


def _known_source_ids(state: FinSightState) -> set[str]:
    source_ids: set[str] = set()
    for source in state.get("sources", []):
        source_id = source.get("source_id")
        if source_id is None:
            continue
        normalized = str(source_id).strip()
        if normalized:
            source_ids.add(normalized)
    return source_ids


def _report_evidence(state: FinSightState) -> dict[str, Any]:
    return {
        "company_name": state.get("company_name"),
        "ticker": state.get("ticker"),
        "latest_10k": state.get("latest_10k"),
        "latest_10q": state.get("latest_10q"),
        "financial_metrics": state.get("financial_metrics"),
        "risk_themes": state.get("risk_themes", []),
        "research_insights": state.get("research_insights"),
        "sources": state.get("sources", []),
        "warnings": state.get("warnings", []),
    }


def _risk_analysis_message(themes: list[dict[str, Any]], used_llm: bool) -> str:
    if not themes:
        return "Risk-factor text was unavailable for analysis."
    if used_llm:
        return "Generated LLM-assisted risk themes from extracted 10-K text."
    return "Generated deterministic risk themes from extracted 10-K text."


def _filing_text_unavailable_update(
    state: FinSightState,
    message: str,
) -> FinSightState:
    return {
        "filing_text": None,
        "risk_factors": [],
        "warnings": [
            *state.get("warnings", []),
            {
                "code": "filing_text_unavailable",
                "message": message,
                "severity": "warning",
            },
        ],
        "agent_steps": _append_step(
            state,
            "fetch_filing_text",
            "completed",
            "Could not retrieve latest 10-K risk-factor text.",
        ),
    }


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_cik(cik: str) -> str:
    digits = "".join(char for char in str(cik).strip() if char.isdigit())
    return digits.zfill(10)


def _sec_submissions_url(cik: str) -> str:
    return f"https://data.sec.gov/submissions/CIK{cik}.json"


def _sec_company_facts_url(cik: str) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def _filing_source(
    cik: str | None,
    filing: dict[str, Any] | None,
    label: str,
    source_id: str,
) -> dict[str, Any] | None:
    if cik is None or filing is None:
        return None

    normalized_cik = _normalize_cik(cik)
    return {
        "source_id": source_id,
        "source_type": "sec_filing",
        "label": label,
        "cik": normalized_cik,
        "form": filing.get("form"),
        "filing_date": filing.get("filing_date"),
        "report_date": filing.get("report_date"),
        "accession_number": filing.get("accession_number"),
        "primary_document": filing.get("primary_document"),
        "url": _filing_document_url(
            cik=normalized_cik,
            accession_number=filing.get("accession_number"),
            primary_document=filing.get("primary_document"),
        ),
    }


def _filing_document_url(
    *,
    cik: str,
    accession_number: str | None,
    primary_document: str | None,
) -> str | None:
    if not accession_number or not primary_document:
        return None

    cik_path = str(int(cik))
    accession_path = normalize_accession_number(accession_number)
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{cik_path}/{accession_path}/{primary_document}"
    )
