from typing import Any

from langgraph.graph import END, StateGraph

from finsight_agent.app.graph.state import FinSightState
from finsight_agent.app.services.company_resolver import ResolutionStatus
from finsight_agent.app.services.compliance import check_report_compliance
from finsight_agent.app.services.filing_parser import find_latest_filing
from finsight_agent.app.services.metrics import extract_financial_metrics
from finsight_agent.app.services.report_generator import generate_research_report


def build_research_graph(resolver: Any, sec_client: Any):
    graph = StateGraph(FinSightState)

    graph.add_node("initialize", _initialize_state)
    graph.add_node("resolve_company", _make_resolve_company_node(resolver))
    graph.add_node("fetch_sec_data", _make_fetch_sec_data_node(sec_client))
    graph.add_node("identify_filings", _identify_filings)
    graph.add_node("extract_metrics", _extract_metrics)
    graph.add_node("generate_report", _generate_report)
    graph.add_node("compliance_check", _compliance_check)

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
    graph.add_edge("identify_filings", "extract_metrics")
    graph.add_edge("extract_metrics", "generate_report")
    graph.add_edge("generate_report", "compliance_check")
    graph.add_edge("compliance_check", END)

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
        "financial_metrics": state.get("financial_metrics"),
        "report_draft": state.get("report_draft"),
        "final_report": state.get("final_report"),
        "compliance_status": state.get("compliance_status"),
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

        return {
            "sec_submissions": sec_submissions,
            "company_facts": company_facts,
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

    return {
        "latest_10k": latest_10k.model_dump(mode="json") if latest_10k else None,
        "latest_10q": latest_10q.model_dump(mode="json") if latest_10q else None,
        "agent_steps": _append_step(
            state,
            "identify_filings",
            "completed",
            "Identified latest 10-K and 10-Q filing metadata.",
        ),
    }


def _extract_metrics(state: FinSightState) -> FinSightState:
    company_facts = state.get("company_facts") or {}
    metrics = extract_financial_metrics(company_facts)
    warnings = state.get("warnings", [])
    warnings.extend(
        {
            "code": "metric_warning",
            "message": warning,
            "severity": "warning",
        }
        for warning in metrics.get("warnings", [])
    )

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


def _generate_report(state: FinSightState) -> FinSightState:
    report_draft = generate_research_report(
        company_name=state.get("company_name") or "Unknown Company",
        ticker=state.get("ticker") or "UNKNOWN",
        financial_metrics=state.get("financial_metrics"),
        latest_10k=state.get("latest_10k"),
        latest_10q=state.get("latest_10q"),
        warnings=state.get("warnings", []),
        sources=state.get("sources", []),
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
    warnings = state.get("warnings", [])
    warnings.extend(
        {
            "code": "compliance_warning",
            "message": warning,
            "severity": "warning",
        }
        for warning in result.warnings
    )

    if result.safe_report is None:
        errors = state.get("errors", [])
        errors.append(
            {
                "code": "compliance_blocked",
                "message": "Report contained unsafe financial-advice language.",
                "severity": "error",
            }
        )
        return {
            "compliance_status": result.status.value,
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


def _route_after_resolve(state: FinSightState) -> str:
    return "stop" if state.get("errors") else "continue"


def _route_after_sec_fetch(state: FinSightState) -> str:
    return "stop" if state.get("errors") else "continue"


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
