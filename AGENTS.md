# AGENTS.md

Lean guide for AI agents working on FinSight. For the full project handbook, see
`docs/AGENTS_FULL.md`.

## Mission

FinSight is a production-style AI equity research assistant built with FastAPI,
LangGraph, SEC EDGAR data, deterministic financial calculations, SQLite
persistence, LLM-assisted summarization/drafting, observability, and a
compliance layer.

It produces neutral, source-grounded research briefs. It is not an investment
advisor.

## Current Stage

FinSight is well beyond foundation. The backend research workflow is now a
run-based, persisted, observable workflow.

Already implemented:

- UV-managed Python project, target `>=3.12,<3.15`.
- FastAPI app with `GET /health`.
- Run-based research API with queued background execution.
- Deterministic company resolver.
- SEC client for submissions, company facts, filing metadata, and filing
  documents.
- Deterministic financial metrics extraction.
- Filing text, Item 1 Business extraction, and Item 1A risk-factor extraction.
- Deterministic business overview synthesis from SEC filing evidence.
- Deterministic and optional LLM-assisted risk/theme analysis.
- Research insight synthesis.
- LangGraph workflow orchestration.
- Report generation, compliance checking, and report quality validation.
- SQLite persistence with Alembic migrations.
- Research run retry/retry-chain support.
- Agent step audit trail.
- LLM call event persistence and LLM usage summary endpoint.
- Stage 4N report-quality grounding: production-style generated reports,
  scaffold-language validation, source-id citation checks, professional
  limitations, and graph-level report-quality proof.
- Stage 4O business overview grounding: latest 10-K Item 1 Business evidence,
  `business_sections` and `business_overview` graph state, cited Company
  Overview report text, and raw Item 1 text exclusion from final reports.
- Stage 4P model-provider testing: LLM provider configuration hardening, sanitized prompt
  evidence contracts, structured LLM fallback validation, and opt-in provider
  smoke tests for risk analysis, report drafting, and live SEC plus LLM graph
  execution.
- Stage 4Q financial presentation: readable financial values, deterministic
  period comparisons, `financial_presentation` helpers, formatted report
  financial sections, and LLM report draft financial performance guardrails
  that reject raw metric values.
- Stage 4R filing evidence robustness: deterministic filing extraction for
  heading variants, table-of-contents noise, boundary detection, extraction
  diagnostics, and graph-level proof across fixture filing documents.
- Stage 4S report citation audit: deterministic `citation_audit` details in
  `report_quality_details`, known and unknown citation tracking, missing
  required citation details, persisted/API quality details, and LLM report draft
  citation safety proof.
- GitHub Actions CI for tests and linting.

Current completed stage:

```text
4S - Report Citation Audit and Quality Details
```

Stage 4O added SEC Item 1 Business extraction and deterministic business
overview grounding on top of the Stage 4N report-quality foundation. Final
reports keep the 11-section structure, cite `[latest_10k]` when Company Overview
uses business evidence, and avoid copying raw Item 1 text.

Stage 4P added controlled model API testing around the existing LLM adapter.
Use `docs/specs/4P-llm-provider-integration-agent-testing.md` as the stage spec.
The safe testing order is mock first, provider smoke test second, end-to-end live run last.
Provider smoke tests use `RUN_LIVE_LLM_TESTS` and cover risk analysis
and report drafting. The end-to-end live run uses
`RUN_LIVE_SEC_LLM_GRAPH_TESTS` and exercises real SEC data plus the configured
real LLM provider without making exact prose assertions.

Stage 4Q added readable financial values and deterministic period comparisons
to final reports. Use `docs/specs/4Q-financial-presentation-period-analysis.md`
as the stage spec. Raw metric values remain available internally for
calculations and API payloads, but report financial sections use formatted
values such as `$1.25B`, `$280.0M`, percentages such as `25.0%`, and `N/A` for
missing data. LLM report draft financial performance text that repeats raw
metric values is rejected and falls back to deterministic report generation.

Stage 4R strengthened deterministic filing extraction for latest 10-K Item 1
Business and Item 1A Risk Factors evidence. Use
`docs/specs/4R-filing-evidence-robustness.md` as the stage spec. The parser
handles heading variants, `PART I` labels, HTML/non-breaking-space input,
table-of-contents noise, and Item 1A, Item 1B, and Item 2 boundaries. It records
`extraction_diagnostics` and surfaces `business_section_unavailable` or
`risk_factors_unavailable` warnings instead of inventing missing filing
evidence.

Stage 4S added deterministic report citation audit and quality details. Use
`docs/specs/4S-report-citation-audit-quality-details.md` as the stage spec.
Completed graph/API results now expose `report_quality_details` with a
`citation_audit` object containing `known_source_ids`, `unknown_citations`,
`sections_missing_required_citations`, and missing section details. LLM report
draft citation failures use deterministic fallback instead of passing through
as grounded report text.

## Development Method

From 4N onward, use both spec-driven development and test-driven development.

For a new stage:

1. Write or update a spec first.
2. Convert the spec into acceptance criteria.
3. Write failing tests for the next small slice.
4. Implement the smallest production-quality change.
5. Run verification.
6. Update docs when behavior changes.

The recent stage specs are:

```text
docs/specs/4N-report-quality-grounding.md
docs/specs/4O-business-overview-filing-evidence.md
docs/specs/4P-llm-provider-integration-agent-testing.md
docs/specs/4Q-financial-presentation-period-analysis.md
docs/specs/4R-filing-evidence-robustness.md
docs/specs/4S-report-citation-audit-quality-details.md
```

## Core Rules

- Do not provide financial advice or buy/sell/hold recommendations.
- Do not invent financial data, filing details, metrics, sources, or citations.
- Use Python, not LLMs, for financial calculations.
- Use LLMs only for summarization, classification, report drafting, compliance
  review, and safe rewriting.
- Track warnings, limitations, and sources for research outputs.
- Keep reports neutral, source-grounded, and explicitly research-only.
- Keep changes incremental, tested, and consistent with the existing layers.
- Do not edit `.venv/`, `venv/`, `.ruff_cache/`, `.pytest_cache/`, or `.env`.

Required report disclaimer:

```text
This report is for informational and educational research purposes only. It is
not financial advice, investment advice, or a recommendation to buy, sell, or
hold any security.
```

## Commands

Use UV:

```powershell
uv run python --version
uv run pytest
uv run ruff check .
uv run uvicorn finsight_agent.app.main:app --reload
```

If UV hits Windows certificate issues:

```powershell
uv --system-certs sync
```

## Architecture

Current layers:

```text
FastAPI API
  -> LangGraph workflow
  -> services: resolver, SEC client, metrics, risks, synthesis, reports,
               compliance, report quality, LLM adapter, LLM usage
  -> database: SQLite locally, PostgreSQL-ready later
```

Keep route handlers thin. Put deterministic business logic in `app/services`.
Put workflow orchestration in `app/graph`. Put persistence in `app/db`.

Current research flow:

```text
resolve_company
fetch_sec_data
extract_financial_metrics
fetch_filing_text
analyze_risks
synthesize_research
draft_report
generate_report
compliance_check
validate_report
persist_results
```

Use typed graph state. Store warnings/errors instead of crashing when graceful
partial output is possible.

## Current API Surface

Important endpoints include:

- `GET /health`
- `POST /research`
- `GET /research/{run_id}`
- `GET /research`
- `GET /research/{run_id}/progress`
- `POST /research/{run_id}/retry`
- `GET /research/{run_id}/retries`
- `GET /research/{run_id}/steps`
- `GET /research/{run_id}/llm-calls`
- `GET /research/{run_id}/llm-usage`

The API is run-based. `POST /research` returns a queued run. Clients poll until
the run reaches `completed` or `failed`.

## Report Quality Rules

Reports must:

- Keep the required 11-section report structure.
- Include the required disclaimer.
- Include sources and limitations.
- Use known `source_id` citations for source-grounded claims.
- Use latest 10-K Item 1 Business evidence for Company Overview when available.
- Cite `[latest_10k]` when Company Overview uses business-section evidence.
- Preserve filing extraction diagnostics in graph state and source metadata.
- Preserve `report_quality_details` and `citation_audit` details for completed
  report quality validation.
- Present financial metrics as readable financial values while keeping raw
  metric values internal.
- Include deterministic period comparisons when enough fiscal-year data exists.
- Cite `[sec_company_facts]` for financial performance and metrics-table
  source cues.
- Avoid raw copied filing text.
- Avoid raw Item 1 text in final reports.
- Avoid financial advice language.
- Avoid scaffold language such as "MVP draft", "future versions will",
  "pending deterministic synthesis", "not generated yet", and "future
  LLM-assisted step".

Missing data should be surfaced as limitations or warnings, not invented.

## LLM Rules

Allowed LLM uses:

- Risk summarization/classification.
- Report section drafting from structured evidence.
- Compliance review or safe rewriting.

Disallowed LLM uses:

- Company resolver logic.
- Financial calculations.
- Filling missing facts.
- Price predictions as fact.
- Buy/sell/hold advice.
- LLM report draft financial performance text that repeats raw metric values.

LLM-aware workflow steps should preserve diagnostics:

- Provider and model.
- Whether LLM output was used.
- Fallback reason.
- Prompt version.
- Start/completion timing.
- Token usage where available.
- Provider request ID where available.
- Error type/message where relevant.

## Testing Expectations

Add or update tests with behavior changes. Prioritize deterministic tests:

- API/schema tests.
- Company resolver tests.
- SEC client tests with mocked responses.
- Metrics tests with fixtures.
- Risk analyzer and research synthesizer tests.
- Compliance tests.
- Report generator and report validator tests.
- Graph path tests with fake SEC/LLM clients.
- Repository and migration tests for persistence changes.

Do not call real SEC or real LLM services in normal unit tests. Live tests must
remain opt-in.

For real LLM providers, keep `LLM_PROVIDER=mock` for normal local and CI
verification. Use provider smoke test runs only with explicit flags such as
`RUN_LIVE_LLM_TESTS=1`; never require model API access in normal tests.

Before finishing code changes, run:

```powershell
uv run pytest
uv run ruff check .
```

## Stage 4N and 4O Status

Stage 4N was implemented in small, tested slices:

1. `4N-0`: Wrote `docs/specs/4N-report-quality-grounding.md`.
2. `4N-1`: Strengthened report quality validator with failing tests first.
3. `4N-2`: Improved deterministic report generation with failing tests first.
4. `4N-3`: Proved end-to-end graph report quality.
5. `4N-4`: Updated docs and ran full verification.

Stage 4O was implemented in small, tested slices:

```text
4O - Business Overview and Filing Evidence
```

1. `4O-0`: Wrote `docs/specs/4O-business-overview-filing-evidence.md`.
2. `4O-1`: Added tested Item 1 Business filing parser support.
3. `4O-2`: Added `business_sections` and `business_overview` graph state and
   extraction integration.
4. `4O-3`: Added deterministic business overview synthesis.
5. `4O-4`: Integrated business overview evidence into report generation.
6. `4O-5`: Proved graph-level final report grounding, updated docs, and ran
   full verification.

Stage 4P was implemented in small, tested slices:

```text
4P - LLM Provider Integration and Agent Testing
```

1. `4P-0`: Wrote `docs/specs/4P-llm-provider-integration-agent-testing.md`.
2. `4P-1`: Hardened LLM provider configuration for real providers.
3. `4P-2`: Hardened prompt/evidence contracts and prompt sanitization.
4. `4P-3`: Strengthened LLM output validation and deterministic fallback proof.
5. `4P-4`: Added provider smoke test coverage and docs for controlled live model
   testing.
6. `4P-5`: Added the opt-in live SEC plus LLM graph smoke test and completed
   controlled agent testing docs.

Stage 4Q was implemented in small, tested slices:

```text
4Q - Financial Presentation and Period Analysis
```

1. `4Q-0`: Wrote `docs/specs/4Q-financial-presentation-period-analysis.md`.
2. `4Q-1`: Added tested `financial_presentation` helpers for readable
   financial values and percentages.
3. `4Q-2`: Added deterministic period comparisons for revenue, margins, and
   free cash flow.
4. `4Q-3`: Integrated formatted financial presentation into report generation.
5. `4Q-4`: Added graph proof and rejected LLM report draft financial
   performance text that repeats raw metric values.
6. `4Q-5`: Updated docs and ran full verification.

Stage 4R was implemented in small, tested slices:

```text
4R - Filing Evidence Robustness
```

1. `4R-0`: Wrote `docs/specs/4R-filing-evidence-robustness.md`.
2. `4R-1`: Added fixture-backed parser tests for heading variants and
   table-of-contents noise.
3. `4R-2`: Hardened filing section boundaries so Item 1, Item 1A, Item 1B,
   and Item 2 content does not leak across sections.
4. `4R-3`: Added structured `extraction_diagnostics` and propagated them
   through graph state, warnings, and latest 10-K source metadata.
5. `4R-4`: Added graph proof across robust filing fixtures and missing
   risk-factor extraction.
6. `4R-5`: Updated README and agent docs, then ran full verification.

Stage 4S was implemented in small, tested slices:

```text
4S - Report Citation Audit and Quality Details
```

1. `4S-0`: Wrote `docs/specs/4S-report-citation-audit-quality-details.md`.
2. `4S-1`: Added the deterministic citation audit service.
3. `4S-2`: Integrated citation audit details into report quality validation.
4. `4S-3`: Propagated `report_quality_details` through graph state, API
   responses, persistence, and migration coverage.
5. `4S-4`: Added graph proof that LLM report draft missing or unknown citation
   failures use deterministic fallback.
6. `4S-5`: Updated README and agent docs, then ran full verification.

When in doubt, keep the MVP small, traceable, source-grounded, and safe.
