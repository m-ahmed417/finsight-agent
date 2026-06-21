from collections.abc import Callable
from datetime import datetime, timezone
import re
from typing import Any

from langgraph.graph import END, StateGraph

from finsight_agent.app.graph.state import FinSightState
from finsight_agent.app.services.business_overview_synthesizer import (
    synthesize_business_overview,
)
from finsight_agent.app.services.company_resolver import ResolutionStatus
from finsight_agent.app.services.compliance import (
    check_report_compliance,
    rewrite_unsafe_report,
)
from finsight_agent.app.services.filing_parser import (
    extract_business_section_with_diagnostics,
    extract_risk_factors_section_with_diagnostics,
    find_latest_filing,
    normalize_accession_number,
)
from finsight_agent.app.services.llm_client import (
    REPORT_DRAFT_PROMPT_VERSION,
    RISK_ANALYSIS_PROMPT_VERSION,
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
SEC_PUBLISHER = "U.S. Securities and Exchange Commission"
BUSINESS_SECTION = "Item 1 Business"
RISK_FACTORS_SECTION = "Item 1A Risk Factors"
CACHE_METADATA_FIELDS = (
    "cache_status",
    "cache_key",
    "cache_age_seconds",
    "cache_ttl_seconds",
    "cache_expires_at",
    "cache_stale",
)
LLM_DRAFT_CITATION_PATTERN = re.compile(r"\[([A-Za-z][A-Za-z0-9_-]*)\]")
LLM_SOURCE_GROUNDED_REPORT_FIELDS = (
    "financial_performance",
    "risk_factors",
    "bull_case",
    "bear_case",
)
RAW_FINANCIAL_PRESENTATION_FIELDS = (
    "revenue",
    "operating_income",
    "net_income",
    "assets",
    "liabilities",
    "cash",
    "debt",
    "operating_cash_flow",
    "capital_expenditure",
    "free_cash_flow",
)


def build_research_graph(
    resolver: Any,
    sec_client: Any,
    llm_client: Any | None = None,
):
    graph = StateGraph(FinSightState)

    graph.add_node("initialize", _timed_node("initialize", _initialize_state))
    graph.add_node(
        "resolve_company",
        _timed_node("resolve_company", _make_resolve_company_node(resolver)),
    )
    graph.add_node(
        "fetch_sec_data",
        _timed_node("fetch_sec_data", _make_fetch_sec_data_node(sec_client)),
    )
    graph.add_node("identify_filings", _timed_node("identify_filings", _identify_filings))
    graph.add_node(
        "fetch_filing_text",
        _timed_node("fetch_filing_text", _make_fetch_filing_text_node(sec_client)),
    )
    graph.add_node(
        "analyze_risks",
        _timed_node("analyze_risks", _make_analyze_risks_node(llm_client)),
    )
    graph.add_node("extract_metrics", _timed_node("extract_metrics", _extract_metrics))
    graph.add_node(
        "synthesize_research",
        _timed_node("synthesize_research", _synthesize_research),
    )
    graph.add_node(
        "draft_report",
        _timed_node("draft_report", _make_draft_report_node(llm_client)),
    )
    graph.add_node("generate_report", _timed_node("generate_report", _generate_report))
    graph.add_node(
        "compliance_check",
        _timed_node("compliance_check", _compliance_check),
    )
    graph.add_node("validate_report", _timed_node("validate_report", _validate_report))

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
        "business_sections": state.get("business_sections", []),
        "business_overview": state.get("business_overview"),
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
        "llm_call_events": state.get("llm_call_events", []),
        "sources": state.get("sources", []),
        "warnings": state.get("warnings", []),
        "errors": state.get("errors", []),
    }


def _timed_node(
    node_name: str,
    node: Callable[[FinSightState], FinSightState],
) -> Callable[[FinSightState], FinSightState]:
    def wrapped(state: FinSightState) -> FinSightState:
        started_at = datetime.now(timezone.utc)
        updates = node(state)
        completed_at = datetime.now(timezone.utc)
        return _annotate_new_agent_steps(
            state,
            updates,
            started_at=started_at,
            completed_at=completed_at,
        )

    wrapped.__name__ = f"timed_{node_name}"
    return wrapped


def _annotate_new_agent_steps(
    state: FinSightState,
    updates: FinSightState,
    *,
    started_at: datetime,
    completed_at: datetime,
) -> FinSightState:
    steps = updates.get("agent_steps")
    if not isinstance(steps, list):
        return updates

    previous_step_count = len(state.get("agent_steps", []))
    if len(steps) <= previous_step_count:
        return updates

    duration_seconds = max((completed_at - started_at).total_seconds(), 0.0)
    started_at_text = started_at.isoformat()
    completed_at_text = completed_at.isoformat()
    timed_steps = [
        (
            _annotate_step_timing(
                step,
                started_at=started_at_text,
                completed_at=completed_at_text,
                duration_seconds=duration_seconds,
            )
            if index >= previous_step_count and isinstance(step, dict)
            else step
        )
        for index, step in enumerate(steps)
    ]
    return {**updates, "agent_steps": timed_steps}


def _annotate_step_timing(
    step: dict[str, Any],
    *,
    started_at: str,
    completed_at: str,
    duration_seconds: float,
) -> dict[str, Any]:
    step_duration = step.get("duration_seconds")
    return {
        **step,
        "started_at": step.get("started_at") or started_at,
        "completed_at": step.get("completed_at") or completed_at,
        "duration_seconds": (
            duration_seconds if step_duration is None else step_duration
        ),
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
            sec_submissions, submissions_metadata = (
                _call_sec_client_with_optional_metadata(
                    sec_client,
                    "fetch_company_submissions_with_metadata",
                    "fetch_company_submissions",
                    cik,
                )
            )
            company_facts, company_facts_metadata = (
                _call_sec_client_with_optional_metadata(
                    sec_client,
                    "fetch_company_facts_with_metadata",
                    "fetch_company_facts",
                    cik,
                )
            )
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
        sources = [
            {
                "source_id": SEC_SUBMISSIONS_SOURCE_ID,
                "source_type": "sec_submissions",
                "label": "SEC submissions",
                "publisher": SEC_PUBLISHER,
                "cik": normalized_cik,
                "company_name": state.get("company_name"),
                "ticker": state.get("ticker"),
                "url": _sec_submissions_url(normalized_cik),
                "data_format": "json",
                "retrieval_method": "http_get",
                "description": "SEC submissions filing metadata.",
                "retrieved_at": retrieved_at,
                **_cache_source_fields(submissions_metadata),
            },
            {
                "source_id": SEC_COMPANY_FACTS_SOURCE_ID,
                "source_type": "sec_company_facts",
                "label": "SEC company facts",
                "publisher": SEC_PUBLISHER,
                "cik": normalized_cik,
                "company_name": state.get("company_name"),
                "ticker": state.get("ticker"),
                "url": _sec_company_facts_url(normalized_cik),
                "data_format": "json",
                "retrieval_method": "http_get",
                "description": "SEC XBRL company facts.",
                "retrieved_at": retrieved_at,
                **_cache_source_fields(company_facts_metadata),
            },
        ]
        return {
            "sec_submissions": sec_submissions,
            "company_facts": company_facts,
            "sources": [
                *state.get("sources", []),
                *sources,
            ],
            "agent_steps": _append_step(
                state,
                "fetch_sec_data",
                "completed",
                _fetch_sec_data_message(normalized_cik, sources),
            ),
        }

    return fetch_sec_data


def _identify_filings(state: FinSightState) -> FinSightState:
    submissions = state.get("sec_submissions") or {}
    latest_10k = find_latest_filing(submissions, form_type="10-K")
    latest_10q = find_latest_filing(submissions, form_type="10-Q")
    latest_10k_data = latest_10k.model_dump(mode="json") if latest_10k else None
    latest_10q_data = latest_10q.model_dump(mode="json") if latest_10q else None
    metadata_retrieved_at = (
        _source_field(
            state.get("sources", []),
            SEC_SUBMISSIONS_SOURCE_ID,
            "retrieved_at",
        )
        or _utc_timestamp()
    )

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
                        metadata_retrieved_at=metadata_retrieved_at,
                        company_name=state.get("company_name"),
                        ticker=state.get("ticker"),
                    ),
                    _filing_source(
                        state.get("cik"),
                        latest_10q_data,
                        "Latest 10-Q filing",
                        LATEST_10Q_SOURCE_ID,
                        metadata_retrieved_at=metadata_retrieved_at,
                        company_name=state.get("company_name"),
                        ticker=state.get("ticker"),
                    ),
                )
                if source is not None
            ],
        ],
        "agent_steps": _append_step(
            state,
            "identify_filings",
            "completed",
            _identify_filings_message(latest_10k_data, latest_10q_data),
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
            filing_text, document_metadata = _call_sec_client_with_optional_metadata(
                sec_client,
                "fetch_filing_document_with_metadata",
                "fetch_filing_document",
                cik=cik,
                accession_number=accession_number,
                primary_document=primary_document,
            )
        except Exception as exc:
            return _filing_text_unavailable_update(state, str(exc))

        source_url = _filing_document_url(
            cik=_normalize_cik(cik),
            accession_number=accession_number,
            primary_document=primary_document,
        )
        document_retrieved_at = _utc_timestamp()
        business_extraction = extract_business_section_with_diagnostics(filing_text)
        risk_extraction = extract_risk_factors_section_with_diagnostics(filing_text)
        business_section = business_extraction.section
        risk_section = risk_extraction.section
        warnings = [
            *state.get("warnings", []),
            *_filing_section_warnings(
                business_section=business_section,
                risk_section=risk_section,
                business_diagnostics=business_extraction.diagnostics.model_dump(),
                risk_diagnostics=risk_extraction.diagnostics.model_dump(),
                accession_number=accession_number,
                primary_document=primary_document,
                document_character_count=len(filing_text),
            ),
        ]
        return {
            "filing_text": filing_text,
            "business_sections": _business_section_records(
                business_section,
                latest_10k=latest_10k,
                accession_number=accession_number,
                source_url=source_url,
                extracted_at=document_retrieved_at,
            ),
            "risk_factors": _risk_factor_records(
                risk_section,
                latest_10k=latest_10k,
                accession_number=accession_number,
                source_url=source_url,
                extracted_at=document_retrieved_at,
            ),
            "sources": _update_source_metadata(
                state.get("sources", []),
                LATEST_10K_SOURCE_ID,
                _filing_source_extraction_updates(
                    business_section=business_section,
                    risk_section=risk_section,
                    business_diagnostics=business_extraction.diagnostics.model_dump(),
                    risk_diagnostics=risk_extraction.diagnostics.model_dump(),
                    document_retrieved_at=document_retrieved_at,
                    document_character_count=len(filing_text),
                    document_metadata=document_metadata,
                ),
            ),
            "warnings": warnings,
            "agent_steps": _append_step(
                state,
                "fetch_filing_text",
                "completed",
                _filing_text_extraction_message(
                    document_character_count=len(filing_text),
                    business_text_character_count=(
                        len(business_section.text)
                        if business_section is not None
                        else None
                    ),
                    risk_factor_text_character_count=(
                        len(risk_section.text) if risk_section is not None else None
                    ),
                ),
            ),
        }

    return fetch_filing_text


def _make_analyze_risks_node(llm_client: Any | None):
    def analyze_risks(state: FinSightState) -> FinSightState:
        risk_factors = state.get("risk_factors", [])
        warnings = state.get("warnings", [])
        used_llm = False
        llm_step_metadata = _llm_step_metadata(
            llm_client,
            used=False,
            fallback_reason="No LLM client configured.",
        )
        llm_call_event = _skipped_llm_call_event(
            llm_client,
            node_name="analyze_risks",
            task="risk_analysis",
            prompt_version=RISK_ANALYSIS_PROMPT_VERSION,
            fallback_reason="No LLM client configured.",
        )
        if llm_client is not None:
            started_at = datetime.now(timezone.utc)
            try:
                analysis = _validate_risk_analysis(llm_client.summarize_risks(risk_factors))
                completed_at = datetime.now(timezone.utc)
                used_llm = True
                llm_step_metadata = _llm_step_metadata(llm_client, used=True)
                llm_call_event = _llm_call_event(
                    llm_client,
                    node_name="analyze_risks",
                    task="risk_analysis",
                    status="completed",
                    prompt_version=RISK_ANALYSIS_PROMPT_VERSION,
                    started_at=started_at,
                    completed_at=completed_at,
                    fallback_used=False,
                )
            except Exception as exc:
                completed_at = datetime.now(timezone.utc)
                fallback_reason = str(exc)
                warnings = [
                    *warnings,
                    {
                        "code": "llm_risk_analysis_unavailable",
                        "message": fallback_reason,
                        "severity": "warning",
                        "details": _llm_warning_details(
                            llm_client,
                            fallback="deterministic_risk_analysis",
                        ),
                    },
                ]
                llm_step_metadata = _llm_step_metadata(
                    llm_client,
                    used=False,
                    fallback_reason=fallback_reason,
                )
                llm_call_event = _llm_call_event(
                    llm_client,
                    node_name="analyze_risks",
                    task="risk_analysis",
                    status="failed",
                    prompt_version=RISK_ANALYSIS_PROMPT_VERSION,
                    started_at=started_at,
                    completed_at=completed_at,
                    fallback_used=True,
                    fallback_reason=fallback_reason,
                    error=exc,
                )
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
                **llm_step_metadata,
            ),
            "llm_call_events": _append_llm_call_event(state, llm_call_event),
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
        "sources": _update_source_metadata(
            state.get("sources", []),
            SEC_COMPANY_FACTS_SOURCE_ID,
            _company_facts_source_updates(metrics),
        ),
        "warnings": warnings,
        "agent_steps": _append_step(
            state,
            "extract_metrics",
            "completed",
            _metrics_extraction_message(metrics),
        ),
    }


def _synthesize_research(state: FinSightState) -> FinSightState:
    company_name = state.get("company_name") or "Unknown Company"
    ticker = state.get("ticker") or "UNKNOWN"
    business_overview = synthesize_business_overview(
        company_name=company_name,
        ticker=ticker,
        business_sections=state.get("business_sections", []),
        warnings=state.get("warnings", []),
    )
    insights = synthesize_research_insights(
        company_name=company_name,
        ticker=ticker,
        financial_metrics=state.get("financial_metrics"),
        risk_themes=state.get("risk_themes", []),
        warnings=state.get("warnings", []),
    )
    return {
        "business_overview": business_overview,
        "research_insights": insights,
        "agent_steps": _append_step(
            state,
            "synthesize_research",
            "completed",
            (
                "Generated deterministic business overview, bull, bear, summary, "
                "and open-question points."
            ),
        ),
    }


def _make_draft_report_node(llm_client: Any | None):
    def draft_report(state: FinSightState) -> FinSightState:
        if llm_client is None or not hasattr(llm_client, "draft_report"):
            fallback_reason = "No report-drafting LLM client configured."
            return {
                "llm_report_sections": None,
                "agent_steps": _append_step(
                    state,
                    "draft_report",
                    "completed",
                    "Using deterministic report generator.",
                    **_llm_step_metadata(
                        llm_client,
                        used=False,
                        fallback_reason=fallback_reason,
                    ),
                ),
                "llm_call_events": _append_llm_call_event(
                    state,
                    _skipped_llm_call_event(
                        llm_client,
                        node_name="draft_report",
                        task="report_drafting",
                        prompt_version=REPORT_DRAFT_PROMPT_VERSION,
                        fallback_reason=fallback_reason,
                    ),
                ),
            }

        started_at = datetime.now(timezone.utc)
        try:
            draft = _validate_report_draft(
                llm_client.draft_report(_report_evidence(state)),
                known_source_ids=_known_source_ids(state),
                financial_metrics=state.get("financial_metrics"),
            )
            completed_at = datetime.now(timezone.utc)
        except Exception as exc:
            completed_at = datetime.now(timezone.utc)
            fallback_reason = str(exc)
            return {
                "llm_report_sections": None,
                "warnings": [
                    *state.get("warnings", []),
                    {
                        "code": "llm_report_drafting_unavailable",
                        "message": fallback_reason,
                        "severity": "warning",
                        "details": _llm_warning_details(
                            llm_client,
                            fallback="deterministic_report_generator",
                        ),
                    },
                ],
                "agent_steps": _append_step(
                    state,
                    "draft_report",
                    "completed",
                    "Using deterministic report generator after LLM report drafting failed.",
                    **_llm_step_metadata(
                        llm_client,
                        used=False,
                        fallback_reason=fallback_reason,
                    ),
                ),
                "llm_call_events": _append_llm_call_event(
                    state,
                    _llm_call_event(
                        llm_client,
                        node_name="draft_report",
                        task="report_drafting",
                        status="failed",
                        prompt_version=REPORT_DRAFT_PROMPT_VERSION,
                        started_at=started_at,
                        completed_at=completed_at,
                        fallback_used=True,
                        fallback_reason=fallback_reason,
                        error=exc,
                    ),
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
                **_llm_step_metadata(llm_client, used=True),
            ),
            "llm_call_events": _append_llm_call_event(
                state,
                _llm_call_event(
                    llm_client,
                    node_name="draft_report",
                    task="report_drafting",
                    status="completed",
                    prompt_version=REPORT_DRAFT_PROMPT_VERSION,
                    started_at=started_at,
                    completed_at=completed_at,
                    fallback_used=False,
                ),
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
        business_overview=state.get("business_overview"),
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


def _call_sec_client_with_optional_metadata(
    sec_client: Any,
    metadata_method_name: str,
    fallback_method_name: str,
    *args: Any,
    **kwargs: Any,
) -> tuple[Any, dict[str, Any]]:
    metadata_method = getattr(sec_client, metadata_method_name, None)
    if callable(metadata_method):
        result = metadata_method(*args, **kwargs)
    else:
        result = getattr(sec_client, fallback_method_name)(*args, **kwargs)

    return _sec_client_result_data_and_metadata(result)


def _sec_client_result_data_and_metadata(result: Any) -> tuple[Any, dict[str, Any]]:
    if not (hasattr(result, "data") and hasattr(result, "metadata")):
        return result, {}

    return result.data, _sec_response_metadata_to_dict(result.metadata)


def _sec_response_metadata_to_dict(metadata: Any) -> dict[str, Any]:
    if metadata is None:
        return {}
    if isinstance(metadata, dict):
        raw_metadata = metadata
    else:
        raw_metadata = {
            "url": getattr(metadata, "url", None),
            **{
                field: getattr(metadata, field, None)
                for field in CACHE_METADATA_FIELDS
            },
        }

    return {
        key: value
        for key, value in raw_metadata.items()
        if value is not None
    }


def _cache_source_fields(metadata: dict[str, Any]) -> dict[str, Any]:
    return _selected_metadata_fields(metadata, CACHE_METADATA_FIELDS)


def _document_cache_source_fields(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        f"document_{field}": value
        for field, value in _selected_metadata_fields(
            metadata,
            CACHE_METADATA_FIELDS,
        ).items()
    }


def _selected_metadata_fields(
    metadata: dict[str, Any],
    field_names: tuple[str, ...],
) -> dict[str, Any]:
    return {
        field_name: metadata[field_name]
        for field_name in field_names
        if metadata.get(field_name) is not None
    }


def _fetch_sec_data_message(normalized_cik: str, sources: list[dict[str, Any]]) -> str:
    source_ids = ", ".join(source["source_id"] for source in sources)
    return (
        f"Fetched SEC submissions and company facts for CIK {normalized_cik}; "
        f"recorded sources: {source_ids}."
    )


def _identify_filings_message(
    latest_10k: dict[str, Any] | None,
    latest_10q: dict[str, Any] | None,
) -> str:
    filing_summaries = [
        summary
        for summary in (
            _filing_diagnostic_summary("latest 10-K", latest_10k),
            _filing_diagnostic_summary("latest 10-Q", latest_10q),
        )
        if summary is not None
    ]
    if not filing_summaries:
        return "No latest 10-K or 10-Q filing metadata was identified."
    return "Identified " + " and ".join(filing_summaries) + "."


def _filing_diagnostic_summary(
    label: str,
    filing: dict[str, Any] | None,
) -> str | None:
    if filing is None:
        return None
    accession_number = filing.get("accession_number", "unknown accession")
    filing_date = filing.get("filing_date", "unknown filing date")
    return f"{label} {accession_number} filed {filing_date}"


def _metrics_extraction_message(metrics: dict[str, Any]) -> str:
    periods = metrics.get("periods", [])
    fiscal_years = [
        str(period["fy"])
        for period in periods
        if isinstance(period.get("fy"), int)
    ]
    xbrl_tags = _xbrl_tags_from_metric_sources(metrics)
    if not fiscal_years:
        return "Financial metrics were unavailable from SEC company facts."
    return (
        "Extracted financial metrics from SEC company facts; "
        f"fiscal years: {', '.join(fiscal_years)}; "
        f"XBRL tags used: {len(xbrl_tags)}."
    )


def _llm_step_metadata(
    llm_client: Any | None,
    *,
    used: bool,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    provider, model = _llm_client_identity(llm_client)
    return {
        key: value
        for key, value in {
            "llm_provider": provider,
            "llm_model": model,
            "llm_used": used,
            "llm_fallback_reason": fallback_reason,
        }.items()
        if value is not None
    }


def _llm_warning_details(llm_client: Any, *, fallback: str) -> dict[str, str]:
    provider, model = _llm_client_identity(llm_client)
    return {
        key: value
        for key, value in {
            "llm_provider": provider,
            "llm_model": model,
            "fallback": fallback,
        }.items()
        if value is not None
    }


def _skipped_llm_call_event(
    llm_client: Any | None,
    *,
    node_name: str,
    task: str,
    prompt_version: str,
    fallback_reason: str,
) -> dict[str, Any]:
    provider, model = _llm_client_identity(llm_client)
    return {
        key: value
        for key, value in {
            "node_name": node_name,
            "task": task,
            "status": "skipped",
            "llm_provider": provider,
            "llm_model": model,
            "prompt_version": prompt_version,
            "fallback_used": True,
            "fallback_reason": fallback_reason,
        }.items()
        if value is not None
    }


def _llm_call_event(
    llm_client: Any,
    *,
    node_name: str,
    task: str,
    status: str,
    prompt_version: str,
    started_at: datetime,
    completed_at: datetime,
    fallback_used: bool,
    fallback_reason: str | None = None,
    error: Exception | None = None,
) -> dict[str, Any]:
    provider, model = _llm_client_identity(llm_client)
    event = {
        "node_name": node_name,
        "task": task,
        "status": status,
        "llm_provider": provider,
        "llm_model": model,
        "prompt_version": prompt_version,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_seconds": max((completed_at - started_at).total_seconds(), 0.0),
        **_llm_call_usage_metadata(llm_client),
        "error_type": type(error).__name__ if error is not None else None,
        "error_message": str(error) if error is not None else None,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
    }
    return {key: value for key, value in event.items() if value is not None}


def _llm_call_usage_metadata(llm_client: Any) -> dict[str, Any]:
    metadata = getattr(llm_client, "last_call_metadata", None)
    if not isinstance(metadata, dict):
        return {}

    return {
        key: value
        for key, value in {
            "input_tokens": _optional_non_negative_int(metadata.get("input_tokens")),
            "output_tokens": _optional_non_negative_int(metadata.get("output_tokens")),
            "total_tokens": _optional_non_negative_int(metadata.get("total_tokens")),
            "provider_request_id": _optional_text(
                metadata.get("provider_request_id") or metadata.get("request_id")
            ),
        }.items()
        if value is not None
    }


def _llm_client_identity(llm_client: Any | None) -> tuple[str | None, str | None]:
    if llm_client is None:
        return None, None
    return (
        _optional_text(
            getattr(llm_client, "provider", None)
            or getattr(llm_client, "provider_name", None)
        ),
        _optional_text(
            getattr(llm_client, "model_name", None)
            or getattr(llm_client, "model", None)
        ),
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def _append_step(
    state: FinSightState,
    node_name: str,
    status: str,
    message: str,
    **metadata: Any,
) -> list[dict[str, Any]]:
    step = {
        "node_name": node_name,
        "status": status,
        "message": message,
        **{key: value for key, value in metadata.items() if value is not None},
    }
    return [
        *state.get("agent_steps", []),
        step,
    ]


def _append_llm_call_event(
    state: FinSightState,
    event: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        *state.get("llm_call_events", []),
        event,
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

    return {
        "themes": themes,
        "warnings": _normalize_llm_warnings(
            warnings,
            default_code="llm_risk_analysis_warning",
        ),
    }


def _validate_report_draft(
    draft: Any,
    *,
    known_source_ids: set[str] | None = None,
    financial_metrics: dict[str, Any] | None = None,
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
    if known_source_ids is not None:
        _validate_llm_draft_citations(sections, known_source_ids)
    if financial_metrics is not None:
        _validate_llm_financial_presentation(sections, financial_metrics)

    return {
        "sections": sections,
        "warnings": _normalize_llm_warnings(
            warnings,
            default_code="llm_report_drafting_warning",
        ),
    }


def _normalize_llm_warnings(
    warnings: list[Any],
    *,
    default_code: str,
) -> list[dict[str, Any]]:
    normalized_warnings: list[dict[str, Any]] = []
    for warning in warnings:
        if isinstance(warning, dict):
            message = str(warning.get("message") or warning).strip()
            normalized_warnings.append(
                {
                    **warning,
                    "code": str(warning.get("code") or default_code),
                    "message": message,
                    "severity": str(warning.get("severity") or "warning"),
                }
            )
            continue

        message = str(warning).strip()
        if not message:
            continue
        normalized_warnings.append(
            {
                "code": default_code,
                "message": message,
                "severity": "warning",
            }
        )
    return normalized_warnings


def _validate_llm_draft_citations(
    sections: dict[str, Any],
    known_source_ids: set[str],
) -> None:
    unknown_citations = _unknown_llm_draft_citations(sections, known_source_ids)
    if unknown_citations:
        source_id = sorted(unknown_citations)[0]
        msg = f"LLM report draft cited unknown source_id: {source_id}."
        raise ValueError(msg)

    if not _has_required_llm_draft_citations(sections, known_source_ids):
        msg = (
            "LLM report draft must include known source_id citations in "
            "source-grounded sections."
        )
        raise ValueError(msg)


def _validate_llm_financial_presentation(
    sections: dict[str, Any],
    financial_metrics: dict[str, Any],
) -> None:
    financial_performance = sections.get("financial_performance")
    if not isinstance(financial_performance, str):
        return

    raw_values = _raw_financial_metric_values(financial_metrics)
    if any(
        _contains_raw_metric_value(financial_performance, raw_value)
        for raw_value in raw_values
    ):
        msg = "LLM report draft financial performance used unformatted raw metric values."
        raise ValueError(msg)


def _raw_financial_metric_values(financial_metrics: dict[str, Any]) -> set[str]:
    periods = financial_metrics.get("periods", [])
    if not isinstance(periods, list):
        return set()

    raw_values: set[str] = set()
    for period in periods:
        if not isinstance(period, dict):
            continue
        for field in RAW_FINANCIAL_PRESENTATION_FIELDS:
            normalized_value = _raw_financial_metric_value(period.get(field))
            if normalized_value is not None:
                raw_values.add(normalized_value)
    return raw_values


def _raw_financial_metric_value(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None

    integer_value = int(value)
    if abs(integer_value) < 100_000:
        return None
    return str(integer_value)


def _contains_raw_metric_value(text: str, raw_value: str) -> bool:
    pattern = rf"(?<![\d.]){re.escape(raw_value)}(?![\d.])"
    return re.search(pattern, text) is not None


def _unknown_llm_draft_citations(
    sections: dict[str, Any],
    known_source_ids: set[str],
) -> set[str]:
    citations: set[str] = set()
    for value in sections.values():
        citations.update(
            *[
                _extract_llm_draft_citations(section_value)
                for section_value in _report_section_values(value)
            ]
        )
    return citations - known_source_ids


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


def _source_field(
    sources: list[dict[str, Any]],
    source_id: str,
    field: str,
) -> Any | None:
    for source in sources:
        if source.get("source_id") == source_id:
            return source.get(field)
    return None


def _update_source_metadata(
    sources: list[dict[str, Any]],
    source_id: str,
    updates: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {**source, **updates} if source.get("source_id") == source_id else {**source}
        for source in sources
    ]


def _company_facts_source_updates(metrics: dict[str, Any]) -> dict[str, Any]:
    periods = metrics.get("periods", [])
    updates: dict[str, Any] = {
        "metric_extracted_at": _utc_timestamp(),
        "metric_extraction_status": (
            "metrics_extracted" if periods else "metrics_unavailable"
        ),
    }

    fiscal_years = sorted(
        {
            period["fy"]
            for period in periods
            if isinstance(period.get("fy"), int)
        }
    )
    if fiscal_years:
        updates["metric_fiscal_years"] = fiscal_years

    xbrl_tags = _xbrl_tags_from_metric_sources(metrics)
    if xbrl_tags:
        updates["xbrl_tags_used"] = xbrl_tags

    forms = _forms_from_metric_sources(metrics)
    if forms:
        updates["filing_forms_used"] = forms

    return updates


def _xbrl_tags_from_metric_sources(metrics: dict[str, Any]) -> list[str]:
    tags: set[str] = set()
    for source in _iter_metric_source_records(metrics):
        tag = source.get("tag")
        if isinstance(tag, str) and tag.strip():
            tags.add(tag.strip())
    return sorted(tags)


def _forms_from_metric_sources(metrics: dict[str, Any]) -> list[str]:
    forms: set[str] = set()
    for source in _iter_metric_source_records(metrics):
        form = source.get("form")
        if isinstance(form, str) and form.strip():
            forms.add(form.strip())
    return sorted(forms)


def _iter_metric_source_records(metrics: dict[str, Any]):
    for period in metrics.get("periods", []):
        metric_sources = period.get("metric_sources", {})
        if not isinstance(metric_sources, dict):
            continue
        for source in metric_sources.values():
            if isinstance(source, dict):
                yield source
                component_sources = source.get("component_sources", [])
                if isinstance(component_sources, list):
                    yield from (
                        component
                        for component in component_sources
                        if isinstance(component, dict)
                    )


def _report_evidence(state: FinSightState) -> dict[str, Any]:
    return {
        "company_name": state.get("company_name"),
        "ticker": state.get("ticker"),
        "latest_10k": state.get("latest_10k"),
        "latest_10q": state.get("latest_10q"),
        "financial_metrics": state.get("financial_metrics"),
        "risk_themes": state.get("risk_themes", []),
        "research_insights": state.get("research_insights"),
        "business_overview": state.get("business_overview"),
        "sources": state.get("sources", []),
        "warnings": state.get("warnings", []),
    }


def _business_section_records(
    section: Any | None,
    *,
    latest_10k: dict[str, Any],
    accession_number: str,
    source_url: str | None,
    extracted_at: str,
) -> list[dict[str, Any]]:
    if section is None:
        return []

    return [
        {
            "source_id": LATEST_10K_SOURCE_ID,
            "source_type": "sec_business_section",
            "form": latest_10k.get("form"),
            "filing_date": latest_10k.get("filing_date"),
            "accession_number": accession_number,
            "source_url": source_url,
            "source_ids": [LATEST_10K_SOURCE_ID],
            "section": "Item 1",
            "section_label": "Business",
            "extracted_at": extracted_at,
            "text_character_count": len(section.text),
            "extraction_diagnostics": section.extraction_diagnostics,
            "text": section.text,
        }
    ]


def _risk_factor_records(
    section: Any | None,
    *,
    latest_10k: dict[str, Any],
    accession_number: str,
    source_url: str | None,
    extracted_at: str,
) -> list[dict[str, Any]]:
    if section is None:
        return []

    return [
        {
            "source_id": LATEST_10K_SOURCE_ID,
            "source_type": "sec_risk_factors",
            "form": latest_10k.get("form"),
            "filing_date": latest_10k.get("filing_date"),
            "accession_number": accession_number,
            "source_url": source_url,
            "source_ids": [LATEST_10K_SOURCE_ID],
            "section": "Item 1A",
            "section_label": "Risk Factors",
            "extracted_at": extracted_at,
            "text_character_count": len(section.text),
            "extraction_diagnostics": section.extraction_diagnostics,
            "text": section.text,
        }
    ]


def _filing_section_warnings(
    *,
    business_section: Any | None,
    risk_section: Any | None,
    business_diagnostics: dict[str, Any],
    risk_diagnostics: dict[str, Any],
    accession_number: str,
    primary_document: str,
    document_character_count: int,
) -> list[dict[str, Any]]:
    warning_details = {
        "source_id": LATEST_10K_SOURCE_ID,
        "accession_number": accession_number,
        "primary_document": primary_document,
        "document_character_count": document_character_count,
    }
    warnings: list[dict[str, Any]] = []
    if business_section is None:
        warnings.append(
            {
                "code": "business_section_unavailable",
                "message": "Item 1 business section could not be extracted.",
                "severity": "warning",
                "details": {
                    **warning_details,
                    "extraction_diagnostics": business_diagnostics,
                },
            }
        )
    if risk_section is None:
        warnings.append(
            {
                "code": "risk_factors_unavailable",
                "message": "Item 1A risk-factor section could not be extracted.",
                "severity": "warning",
                "details": {
                    **warning_details,
                    "extraction_diagnostics": risk_diagnostics,
                },
            }
        )
    return warnings


def _filing_source_extraction_updates(
    *,
    business_section: Any | None,
    risk_section: Any | None,
    business_diagnostics: dict[str, Any],
    risk_diagnostics: dict[str, Any],
    document_retrieved_at: str,
    document_character_count: int,
    document_metadata: dict[str, Any],
) -> dict[str, Any]:
    updates: dict[str, Any] = {
        "document_retrieved_at": document_retrieved_at,
        "document_character_count": document_character_count,
        "extraction_status": _filing_extraction_status(
            business_section,
            risk_section,
        ),
        "extracted_sections": _extracted_filing_sections(
            business_section,
            risk_section,
        ),
        "business_extraction_diagnostics": business_diagnostics,
        "risk_factor_extraction_diagnostics": risk_diagnostics,
        **_document_cache_source_fields(document_metadata),
    }
    if business_section is not None:
        updates["business_text_character_count"] = len(business_section.text)
    if risk_section is not None:
        updates["risk_factor_text_character_count"] = len(risk_section.text)
    return updates


def _extracted_filing_sections(
    business_section: Any | None,
    risk_section: Any | None,
) -> list[str]:
    sections: list[str] = []
    if business_section is not None:
        sections.append(BUSINESS_SECTION)
    if risk_section is not None:
        sections.append(RISK_FACTORS_SECTION)
    return sections


def _filing_extraction_status(
    business_section: Any | None,
    risk_section: Any | None,
) -> str:
    if business_section is not None and risk_section is not None:
        return "business_and_risk_factors_extracted"
    if business_section is not None:
        return "business_extracted"
    if risk_section is not None:
        return "risk_factors_extracted"
    return "filing_sections_not_found"


def _filing_text_extraction_message(
    *,
    document_character_count: int,
    business_text_character_count: int | None,
    risk_factor_text_character_count: int | None,
) -> str:
    if (
        business_text_character_count is not None
        and risk_factor_text_character_count is not None
    ):
        return (
            "Retrieved latest 10-K business and risk-factor text; "
            f"document characters: {document_character_count}, "
            f"business characters: {business_text_character_count}, "
            f"risk-factor characters: {risk_factor_text_character_count}."
        )
    if risk_factor_text_character_count is not None:
        return (
            "Retrieved latest 10-K risk-factor text; business section unavailable; "
            f"document characters: {document_character_count}, "
            f"risk-factor characters: {risk_factor_text_character_count}."
        )
    if business_text_character_count is not None:
        return (
            "Retrieved latest 10-K business text; risk-factor section unavailable; "
            f"document characters: {document_character_count}, "
            f"business characters: {business_text_character_count}."
        )
    return (
        "Retrieved latest 10-K but could not extract business or risk-factor text; "
        f"document characters: {document_character_count}."
    )


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
        "business_sections": [],
        "business_overview": state.get("business_overview"),
        "risk_factors": [],
        "warnings": [
            *state.get("warnings", []),
            {
                "code": "filing_text_unavailable",
                "message": message,
                "severity": "warning",
                "details": {"reason": message},
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
    *,
    metadata_retrieved_at: str,
    company_name: str | None,
    ticker: str | None,
) -> dict[str, Any] | None:
    if cik is None or filing is None:
        return None

    normalized_cik = _normalize_cik(cik)
    accession_number = filing.get("accession_number")
    primary_document = filing.get("primary_document")
    return {
        "source_id": source_id,
        "source_type": "sec_filing",
        "label": label,
        "publisher": SEC_PUBLISHER,
        "cik": normalized_cik,
        "company_name": company_name,
        "ticker": ticker,
        "form": filing.get("form"),
        "filing_date": filing.get("filing_date"),
        "report_date": filing.get("report_date"),
        "accession_number": accession_number,
        "accession_path": (
            normalize_accession_number(accession_number)
            if accession_number
            else None
        ),
        "primary_document": primary_document,
        "url": _filing_document_url(
            cik=normalized_cik,
            accession_number=accession_number,
            primary_document=primary_document,
        ),
        "data_format": "html",
        "metadata_source_ids": [SEC_SUBMISSIONS_SOURCE_ID],
        "metadata_retrieved_at": metadata_retrieved_at,
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
