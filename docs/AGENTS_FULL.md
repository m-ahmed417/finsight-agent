# AGENTS_FULL.md

Comprehensive guide for AI agents working on FinSight. The root `AGENTS.md` is
the short operational guide; this file is the deeper project handbook.

## Project Identity

FinSight is a production-style AI equity research assistant built with FastAPI,
LangGraph, SEC EDGAR data, deterministic financial calculations, SQLite
persistence, optional LLM-assisted summarization/drafting, observability, and a
compliance layer.

The product is an evidence-based research assistant, not an investment advisor.
It helps users understand public companies through source-grounded research
briefs, SEC filings, financial metrics, business risks, and neutral bull/bear
analysis.

Primary positioning:

```text
FinSight orchestrates a multi-step research workflow that resolves public
companies, retrieves SEC filings, extracts financial metrics, summarizes
business risks, generates neutral bull and bear research cases, and produces
source-grounded research briefs with a compliance layer that avoids personalized
investment advice.
```

## Non-Negotiable Product Rules

- Never provide personalized financial advice.
- Never tell a user to buy, sell, hold, short, or allocate money to a security.
- Never claim guaranteed, risk-free, certain, or inevitable investment outcomes.
- Never invent missing financial facts, filing details, metrics, sources, or
  citations.
- Use deterministic Python code for financial calculations.
- Use LLMs only for interpretation, summarization, classification, report
  drafting, compliance checking, and safe rewriting.
- Keep every final research report neutral, evidence-based, and explicitly
  research-only.
- Track sources and limitations whenever data is missing, stale, incomplete, or
  uncertain.

Required disclaimer text for final reports:

```text
This report is for informational and educational research purposes only. It is
not financial advice, investment advice, or a recommendation to buy, sell, or
hold any security.
```

## Current Project State

FinSight is no longer in its foundation stage. The backend MVP is substantially
implemented.

Implemented baseline:

- UV-managed Python project.
- Python target: `>=3.12,<3.15`.
- Source layout under `src/finsight_agent`.
- FastAPI app with health endpoint.
- Pydantic settings with SEC and LLM configuration.
- Normal test suite and ruff linting.
- GitHub Actions CI for tests and lint.

Implemented research workflow:

- Deterministic company resolver.
- SEC client for company tickers, submissions, company facts, filing metadata,
  and filing documents.
- SEC caching/diagnostic metadata where available.
- Deterministic financial metrics extraction.
- Filing text retrieval, Item 1 Business extraction, and Item 1A risk-factor
  extraction.
- Deterministic business overview synthesis from SEC filing evidence.
- Deterministic risk analysis fallback.
- Optional LLM-assisted risk summarization.
- Deterministic research insight synthesis.
- Optional LLM-assisted report section drafting.
- Deterministic report generation.
- Deterministic compliance scan and safe rewrite path.
- Deterministic report quality validation.
- Stage 4N production report grounding: scaffold-language validation,
  source-id citation checks, professional limitations, and graph-level proof
  that normal SEC-evidence runs pass report quality validation.
- Stage 4O business overview grounding: latest 10-K Item 1 Business evidence,
  `business_sections` and `business_overview` graph state, cited Company
  Overview report text, and raw Item 1 text exclusion from final reports.
- Stage 4P model-provider testing: LLM provider configuration hardening, sanitized prompt
  evidence contracts, structured LLM fallback validation, and opt-in provider
  smoke tests for risk analysis, report drafting, and live SEC plus LLM graph
  execution.
- Stage 4Q financial presentation: readable financial values, deterministic
  period comparisons, `financial_presentation` helpers, formatted Financial
  Performance and Key Financial Metrics report sections, and LLM report draft
  financial performance validation that rejects raw metric values.
- LangGraph orchestration with typed state.
- Structured warnings/errors instead of brittle crashes where graceful partial
  output is possible.

Implemented persistence and API capabilities:

- Run-based research API.
- Queued background research execution.
- SQLite persistence with Alembic migrations.
- Research runs with lifecycle statuses.
- Stored final reports, warnings, errors, sources, metrics, agent steps, and LLM
  call events.
- Failed-run retry support.
- Retry-chain retrieval.
- Research progress summary.
- Agent step audit trail.
- LLM call event endpoint.
- LLM usage summary endpoint.

Current completed stage:

```text
4Q - Financial Presentation and Period Analysis
```

Stage 4O added SEC Item 1 Business extraction and deterministic Company
Overview grounding on top of Stage 4N report-quality guarantees. Final reports
cite `[latest_10k]` when business evidence is used and do not copy raw Item 1
text into the report.

Use `docs/specs/4P-llm-provider-integration-agent-testing.md` as the Stage 4P
spec. The safe model testing order is mock first, provider smoke test second,
end-to-end live run last. Provider smoke tests use `RUN_LIVE_LLM_TESTS` and cover
risk analysis and report drafting. The end-to-end live run uses
`RUN_LIVE_SEC_LLM_GRAPH_TESTS` and exercises real SEC data plus the configured
real LLM provider without making exact prose assertions.

Stage 4Q added readable financial values and deterministic period comparisons
to final reports. Use `docs/specs/4Q-financial-presentation-period-analysis.md`
as the Stage 4Q spec. Raw metric values stay internal for calculations,
persistence, API payloads, and tests; report financial sections use formatted
values such as `$1.25B`, `$280.0M`, percentages such as `25.0%`, and `N/A` for
missing values. LLM report draft financial performance text that repeats raw
metric values is rejected and falls back to deterministic report generation.

## Development Method

Use a combination of spec-driven development and test-driven development.

For every new stage:

1. Write or update a spec first.
2. Define acceptance criteria in concrete, testable language.
3. Split work into small implementation slices.
4. For each slice, write failing tests first.
5. Implement the smallest production-quality change.
6. Run focused tests, then full verification when the slice is complete.
7. Update docs for user-facing or agent-facing behavior changes.

This project values deterministic, reliable tests. Avoid exact snapshots of LLM
prose; test structure, safety, citations, fallback behavior, and schema
contracts.

## Local Development Commands

Use UV for project commands:

```powershell
uv run python --version
uv run pytest
uv run ruff check .
uv run uvicorn finsight_agent.app.main:app --reload
```

If UV has certificate issues on Windows, use:

```powershell
uv --system-certs sync
```

Do not require manual virtual environment activation. Prefer `uv run ...` in
docs and examples.

## Current High-Level Architecture

```text
User / Client
  |
  v
FastAPI API Layer
  |
  v
LangGraph Research Workflow
  |
  |-- resolve_company
  |-- fetch_sec_data
  |-- extract_financial_metrics
  |-- fetch_filing_text
  |-- analyze_risks
  |-- synthesize_research
  |-- draft_report
  |-- generate_report
  |-- compliance_check
  |-- validate_report
  |-- persist_results
  |
  v
SQLite locally / PostgreSQL-ready storage
  |
  v
Research result, report, diagnostics, sources, warnings, and audit trail
```

Actual package structure:

```text
src/finsight_agent/
  app/
    main.py
    config.py

    api/
      routes.py
      schemas.py

    db/
      database.py
      models.py
      repository.py

    graph/
      builder.py
      runner.py
      state.py

    services/
      company_resolver.py
      compliance.py
      graph_result_validator.py
      llm_client.py
      llm_usage.py
      metrics.py
      report_generator.py
      report_validator.py
      research_job.py
      research_synthesizer.py
      risk_analyzer.py
      sec_client.py
```

Do not create unused structure prematurely. Grow the codebase around actual
feature needs and existing local patterns.

## Layer Responsibilities

### API Layer

The API layer should:

- Define HTTP endpoints.
- Validate request and response bodies using Pydantic schemas.
- Translate service, repository, or graph results into API responses.
- Avoid complex business logic.
- Return user-friendly errors.

Current important endpoints:

- `GET /health`
- `POST /research`
- `GET /research`
- `GET /research/{run_id}`
- `GET /research/{run_id}/progress`
- `POST /research/{run_id}/retry`
- `GET /research/{run_id}/retries`
- `GET /research/{run_id}/steps`
- `GET /research/{run_id}/llm-calls`
- `GET /research/{run_id}/llm-usage`

The API is run-based. Clients submit work, store the returned `run_id`, and poll
until the run reaches `completed` or `failed`.

### Services Layer

The services layer contains deterministic, testable business logic:

- Company resolution.
- SEC API access.
- Financial metric extraction.
- Filing/risk analysis helpers.
- Research insight synthesis.
- Report generation.
- Report quality validation.
- Compliance phrase scanning and safe rewriting.
- LLM provider abstraction.
- LLM usage summarization.
- Research job/retry helpers.

Services should not depend on FastAPI request objects.

### Graph Layer

The graph layer orchestrates workflow steps using LangGraph.

Each major research step is a graph node with a clear state contract. Nodes
should update typed state and record warnings/errors instead of raising raw
exceptions through the whole workflow when graceful continuation is possible.

Graph nodes should record agent steps with timing and status. LLM-aware nodes
should also record provider/model/fallback metadata and LLM call events.

### Database Layer

The database layer isolates persistence concerns:

- SQLAlchemy models.
- Session management.
- Repository functions.
- Alembic migrations.

SQLite is the local default. Keep schema choices PostgreSQL-ready where
reasonable.

### LLM Layer

The LLM layer is provider-abstracted. Do not scatter direct OpenAI, DeepSeek, or
other provider calls throughout graph nodes.

Use structured outputs with Pydantic where practical. Validate LLM output before
letting it affect final user-visible reports. Fall back deterministically when
LLM output is unavailable, invalid, unsafe, or insufficiently cited.

## LangGraph State

Use the typed state in `src/finsight_agent/app/graph/state.py` as the source of
truth. The state currently tracks fields including:

```text
run_id
user_query
ticker
company_name
cik
resolution_status
resolution_confidence
resolution_candidates
sec_submissions
company_facts
latest_10k
latest_10q
filing_text
risk_factors
risk_themes
financial_metrics
research_insights
llm_report_sections
report_draft
final_report
compliance_status
report_quality_status
llm_call_events
agent_steps
sources
warnings
errors
```

Prefer structured warnings/errors:

```json
{
  "code": "metric_warning",
  "message": "Revenue could not be extracted from SEC company facts.",
  "severity": "warning"
}
```

## Workflow Node Contracts

### `resolve_company`

Responsibilities:

- Accept ticker or company name.
- Resolve to ticker, company name, and SEC CIK.
- Normalize CIK to 10 digits where needed.
- Distinguish exact ticker match, exact company match, fuzzy match, ambiguous,
  and not found.
- Never use an LLM for deterministic matching.

Graceful behavior:

- Unknown company should stop with a clear error.
- Ambiguous company should return possible matches rather than guessing.

### `fetch_sec_data`

Responsibilities:

- Fetch SEC submissions JSON.
- Fetch SEC company facts JSON.
- Identify latest 10-K and latest 10-Q metadata.
- Track SEC source URLs, accession numbers, filing dates, retrieval times, cache
  diagnostics, and source IDs.
- Use configurable `SEC_USER_AGENT`.

Graceful behavior:

- SEC failures should produce structured warnings/errors.
- Missing company facts should not crash the whole run if useful partial output
  is still possible.

### `extract_financial_metrics`

Responsibilities:

- Extract metrics from SEC XBRL company facts.
- Prefer annual 10-K facts where available.
- Prefer USD units.
- Deduplicate by fiscal year, period, form, and filed date.
- Prefer the latest filed value for the same period.
- Calculate growth and margins in Python.
- Track source XBRL tags and source details.

Do not use an LLM for calculations.

Implemented/target metrics include:

- Revenue.
- Revenue growth.
- Operating income.
- Operating margin.
- Net income.
- Net margin.
- Operating cash flow.
- Capital expenditure.
- Free cash flow.
- Debt components where available.

### `fetch_filing_text`

Responsibilities:

- Retrieve latest 10-K filing text or primary document when available.
- Track accession number, document URL, form type, filing date, report date, and
  retrieval metadata.
- Extract risk-factor text when feasible.
- Surface missing text as warnings instead of inventing risk analysis.

### `analyze_risks`

Responsibilities:

- Summarize key business risks from latest 10-K risk-factor text.
- Use deterministic fallback when no LLM client is configured or LLM output
  fails.
- Use the LLM only for summarization/classification.
- Include source filing metadata and source IDs with each risk theme.
- Avoid unsupported claims.

### `synthesize_research`

Responsibilities:

- Convert structured metrics, risk themes, and warnings into deterministic
  research insights.
- Generate neutral executive summary points, bull case points, bear case points,
  and open questions.
- Include source IDs on source-grounded points.

### `draft_report`

Responsibilities:

- Optionally ask an LLM to draft report sections from structured evidence.
- Require schema-valid report draft output.
- Require citations in source-grounded LLM sections.
- Fall back to deterministic generation when output is invalid, citationless,
  unavailable, or unsafe.
- Record LLM call events and fallback metadata.

### `generate_report`

Responsibilities:

- Generate a professional, neutral research brief.
- Use only provided evidence.
- Include warnings and limitations.
- Include sources used.
- Avoid recommendations and personalized advice.
- Prefer LLM-drafted sections only after validation; otherwise use
  deterministic sections.

Required report sections:

```markdown
# FinSight Research Brief: {Company Name} ({Ticker})

## 1. Research-Only Notice
## 2. Executive Summary
## 3. Company Overview
## 4. Financial Performance
## 5. Key Financial Metrics
## 6. Risk Factors
## 7. Bull Case
## 8. Bear Case
## 9. Open Questions for Further Research
## 10. Sources Used
## 11. Limitations
```

### `compliance_check`

Responsibilities:

- Run deterministic forbidden-phrase scan.
- Rewrite unsafe language if possible.
- Re-scan after rewriting.
- Block unsafe final reports if forbidden language remains.
- Ensure the required disclaimer is present.

Compliance statuses:

```text
allowed
needs_rewrite
blocked
```

Forbidden or high-risk language includes:

```text
buy, sell, hold, strong buy, strong sell, guaranteed, risk-free,
you should invest, put your money into, allocate your portfolio,
this stock will definitely, price will go up, price will crash
```

Allowed neutral research language includes:

```text
The bull case depends on...
The bear case includes...
A key risk is...
The company's financial performance shows...
```

### `validate_report`

Responsibilities:

- Run deterministic report quality checks after compliance.
- Confirm required sections.
- Confirm required disclaimer.
- Confirm SEC source signal.
- Confirm citations in citation-required sections.
- Warn on unknown source citations.
- Warn on weak/scaffold report content.
- Warn on unsafe language if any remains.

### `persist_results`

Responsibilities:

- Store run status, final report, warnings, errors, sources, agent steps, LLM
  call events, and metrics.
- Validate graph result shape before persistence.
- Do not silently corrupt user-facing state on persistence failures.

## Company Resolver Requirements

The resolver is deterministic and tested.

Resolution modes:

```text
exact_ticker_match
exact_company_match
fuzzy_company_match
ambiguous
not_found
```

Target output:

```json
{
  "ticker": "AAPL",
  "company_name": "Apple Inc.",
  "cik": "0000320193",
  "resolution_status": "exact_ticker_match",
  "confidence": 1.0
}
```

For ambiguous input, return candidates instead of guessing.

## SEC Data Requirements

Primary SEC sources:

- Company tickers mapping.
- Company submissions JSON.
- Company facts JSON.
- Filing metadata and primary documents.

The SEC client must:

- Use `SEC_USER_AGENT` from settings.
- Set reasonable timeouts.
- Handle 4xx/5xx responses cleanly.
- Support retry/backoff for transient failures where implemented.
- Avoid aggressive request rates.
- Track source URLs and retrieval timestamps.
- Be easy to mock in tests.

Do not hardcode personal email addresses in source code.

## Source Provenance

Every material source should be traceable.

For filing sources, track:

- Source ID.
- Source type.
- SEC URL.
- Publisher.
- Ticker.
- Company name.
- CIK.
- Form type.
- Accession number.
- Filing date.
- Report date.
- Primary document.
- Retrieval timestamp.
- Cache metadata where available.

For metrics, track where possible:

- Metric name.
- Value.
- Fiscal year.
- Unit.
- XBRL tag.
- Form type.
- Filing accession number.
- Filed date.
- Period end date.

Reports should prefer precise statements such as:

```text
Based on the latest available 10-K filed on YYYY-MM-DD...
```

and avoid vague claims when the source or date is unknown.

## Report Quality Requirements

Reports must be source-grounded and production-style.

Required:

- The 11-section structure remains stable.
- The required research-only disclaimer is present.
- Financial, risk, bull, and bear sections include source IDs when they make
  source-grounded claims.
- Citations must refer to known source IDs where source metadata is available.
- Company Overview should use latest 10-K Item 1 Business evidence when
  available and cite `[latest_10k]`.
- Financial sections should present readable financial values while raw metric
  values remain internal.
- Financial sections should include deterministic period comparisons when
  enough comparable fiscal-year data exists.
- Financial claims and metrics-table source cues should cite `[sec_company_facts]`.
- Sources section should list SEC data and filing sources with meaningful
  metadata.
- Limitations section should surface missing/uncertain data.
- Raw filing text should not be copied into the final report.
- Raw Item 1 text should not be copied into the final report.
- Reports should be neutral and avoid investment advice.

Disallowed scaffold language includes:

```text
MVP draft
future versions will
pending deterministic synthesis
not been generated yet
future LLM-assisted step
no sources were recorded
```

Missing data should become a limitation or warning, not invented prose.

## Stage 4N Status

Stage 4N is Report Quality and Grounding. It is implemented.

It was implemented with spec-driven development plus TDD:

### 4N-0: Spec

Created:

```text
docs/specs/4N-report-quality-grounding.md
```

The spec should include:

- Problem statement.
- Goals.
- Non-goals.
- Input contract.
- Output/report contract.
- Required language rules.
- Required citation/source rules.
- Required limitations behavior.
- Acceptance criteria.
- Test plan.
- Definition of done.

### 4N-1: Validator TDD

Wrote failing tests in `tests/test_report_validator.py`, then strengthened
`src/finsight_agent/app/services/report_validator.py`.

The validator should catch scaffold language and weak content in Company
Overview, Risk Factors, Bull Case, Bear Case, Sources, and Limitations where
appropriate.

### 4N-2: Generator TDD

Wrote failing tests in `tests/test_report_generator.py`, then improved
`src/finsight_agent/app/services/report_generator.py`.

Generated reports should:

- Include a careful company overview without invented facts.
- Avoid scaffold/MVP/future-work language.
- Include professional limitations even when no warnings exist.
- Preserve source citations.
- Avoid raw filing text.
- Avoid financial advice language.

### 4N-3: Graph Proof

Added graph-level tests in `tests/test_graph.py` proving normal research runs:

- Produce a final report.
- Retain the required disclaimer.
- End with `report_quality_status == "passed"` when enough SEC-derived evidence
  exists.
- Do not emit report quality warnings caused by scaffold language.
- Include known citations such as `[sec_company_facts]` and `[latest_10k]`.
- Preserve LLM fallback behavior.
- Run compliance before quality validation.

### 4N-4: Docs and Verification

Updated README/docs after behavior was correct, then ran:

```powershell
uv run pytest
uv run ruff check .
```

## Stage 4O Status

Stage 4O is Business Overview and Filing Evidence. It is implemented.

```text
4O - Business Overview and Filing Evidence
```

It was implemented with spec-driven development plus TDD:

### 4O-0: Spec

Created:

```text
docs/specs/4O-business-overview-filing-evidence.md
```

### 4O-1: Filing Parser TDD

Added tested parser support for latest 10-K Item 1 Business extraction while
preserving Item 1A Risk Factors extraction behavior.

### 4O-2: Graph State and Extraction Integration

Added `business_sections` and `business_overview` to typed graph state. The
workflow now extracts Item 1 Business and Item 1A Risk Factors from the same
latest 10-K document, records source metadata, and emits
`business_section_unavailable` when Item 1 cannot be extracted.

### 4O-3: Deterministic Business Overview Synthesis

Added deterministic `business_overview` synthesis from structured SEC filing
evidence. The synthesis preserves source IDs and avoids copying raw Item 1 text.

### 4O-4: Report Generator Integration

Integrated `business_overview` into Company Overview report generation. When
business evidence is available, Company Overview cites `[latest_10k]`; when it
is missing, the report limitations surface the missing evidence.

### 4O-5: Graph Proof, Docs, and Verification

Added graph-level proof that normal SEC-evidence runs use Item 1 Business
evidence in the final report, list Item 1 Business extraction metadata in
Sources Used, avoid raw Item 1 text, and still pass report quality validation.

## Stage 4P Status

Stage 4P is LLM Provider Integration and Agent Testing. It is implemented.

```text
4P - LLM Provider Integration and Agent Testing
```

The stage spec is:

```text
docs/specs/4P-llm-provider-integration-agent-testing.md
```

Implemented so far:

- `4P-0`: Wrote the Stage 4P spec.
- `4P-1`: Hardened provider configuration for `mock`, `openai`, and `deepseek`.
- `4P-2`: Hardened prompt/evidence contracts and prompt payload sanitization.
- `4P-3`: Strengthened LLM output validation and deterministic fallback proof.
- `4P-4`: Added opt-in provider smoke test coverage and docs for controlled live
  model testing.
- `4P-5`: Added the opt-in live SEC plus LLM graph smoke test and completed
  controlled agent testing docs.

Controlled model testing order:

1. mock first with `LLM_PROVIDER=mock` and normal deterministic tests.
2. provider smoke test second with `RUN_LIVE_LLM_TESTS=1` for risk analysis and
   report drafting.
3. end-to-end live run last with `RUN_LIVE_SEC_LLM_GRAPH_TESTS=1` after provider
   smoke tests pass.

Do not require real model API access in normal unit tests or default CI.

## Stage 4Q Status

Stage 4Q is Financial Presentation and Period Analysis. It is implemented.

The stage spec is:

```text
docs/specs/4Q-financial-presentation-period-analysis.md
```

Implemented:

- `4Q-0`: Wrote the Stage 4Q spec.
- `4Q-1`: Added tested `financial_presentation` helpers for readable financial
  values and one-decimal percentages.
- `4Q-2`: Added deterministic period comparisons for revenue direction,
  margin movement, free cash flow changes, one-period limitations, and prior
  revenue of zero.
- `4Q-3`: Integrated formatted values, `N/A` handling, `[sec_company_facts]`
  source cues, and comparison text into report financial sections.
- `4Q-4`: Added graph proof that normal SEC-evidence runs produce formatted
  financial sections and pass report quality validation. LLM report draft
  financial performance text that repeats raw metric values now triggers
  deterministic fallback.
- `4Q-5`: Updated README and agent docs, then ran full verification.

Keep financial calculations deterministic. LLMs may draft report language only
after validation; they must not calculate values, fill missing metrics, or
bypass the readable financial presentation layer.

## Data Quality and Limitations

SEC data is messy. Code defensively.

Use structured warnings for issues such as:

- `metric_warning`
- `filing_text_unavailable`
- `risk_analysis_warning`
- `sec_api_failure`
- `llm_risk_analysis_unavailable`
- `llm_report_drafting_unavailable`
- `llm_input_truncated`
- `compliance_warning`
- `report_quality_warning`

Reports must surface important limitations to the user.

## Database and Persistence

SQLite is the local default. Keep the schema PostgreSQL-ready.

Important persisted concepts:

- Research runs.
- Agent steps.
- LLM call events.
- Financial metrics where applicable.
- Warnings/errors JSON.
- Sources JSON.
- Final report.
- Retry lineage.

Research run statuses include:

```text
queued
running
completed
failed
```

Agent steps should preserve:

- Node name.
- Status.
- Message.
- Error message.
- Started/completed timestamps.
- Duration.
- LLM provider/model where applicable.
- Whether LLM output was used.
- LLM fallback reason.

LLM call events should preserve:

- Node name.
- Task.
- Status.
- Provider/model.
- Prompt version.
- Started/completed timestamps.
- Input/output/total tokens.
- Provider request ID.
- Fallback usage/reason.
- Error type/message.

## LLM Usage Rules

Allowed LLM usage:

- Summarizing business/risk text.
- Categorizing risk themes.
- Drafting final report sections from structured evidence.
- Compliance checking or safe rewriting.

Disallowed LLM usage:

- Ticker/company resolver logic.
- Raw financial calculations.
- Inventing missing data.
- Predicting prices as fact.
- Providing buy/sell/hold recommendations.
- Personalized portfolio allocation.

Prompting rules:

- Provide structured evidence to the model.
- Tell the model to avoid unsupported claims.
- Tell the model to state when evidence is unavailable.
- Require source citations for source-grounded report sections.
- Validate structured outputs with Pydantic where possible.
- Fail gracefully on invalid JSON or schema validation errors.

Normal tests should use fake or mock LLM clients. Live LLM tests must remain
opt-in.

## Error Handling

Handle these cases gracefully:

- Unknown ticker.
- Ambiguous company name.
- SEC API failure.
- Missing company facts.
- Missing 10-K.
- Malformed filing data.
- Filing text unavailable.
- LLM timeout/failure.
- Invalid LLM structured output.
- LLM output missing required citations.
- Compliance failure.
- Report quality warning.
- Database failure.

User-facing errors should be clear and non-technical:

```json
{
  "status": "failed",
  "error": "Could not confidently resolve the company. Try using a stock ticker such as AAPL or MSFT."
}
```

Internal diagnostics should preserve detail without leaking secrets.

## Observability Requirements

Production-grade behavior requires traceability.

Track:

- Run ID.
- Node name.
- Node status.
- Node duration.
- Warnings/errors.
- Sources.
- SEC source metadata and cache diagnostics.
- LLM provider/model.
- LLM task and prompt version.
- Token usage where available.
- LLM provider request ID where available.
- LLM fallback reason.
- Retry lineage.

Design for LangSmith or OpenTelemetry later, but do not block current progress
on full tracing.

## Testing Strategy

Add tests as features are introduced. Prioritize deterministic tests before live
service tests.

Required test areas:

### Health/API

- `GET /health` returns `{"status": "ok"}`.
- OpenAPI exposes expected schemas and endpoints.

### Company Resolver

- Exact ticker resolution.
- Exact company resolution.
- Fuzzy company resolution.
- Ambiguous company candidates.
- Not-found behavior.

### SEC Client

Use fixtures and mocked HTTP responses.

Test:

- Submissions parsing.
- Company facts parsing.
- Latest 10-K detection.
- Latest 10-Q detection.
- Filing document URL construction.
- SEC error handling.
- Cache diagnostics where applicable.

### Metrics Service

Test:

- Revenue growth calculation.
- Margin calculation.
- Free cash flow calculation.
- Missing values.
- Fallback XBRL tags.
- Annual 10-K preference.
- Unit handling.
- Source/XBRL metadata.

### Risk and Synthesis

Test:

- Risk-factor extraction availability.
- Deterministic risk fallback.
- LLM risk output normalization with fake clients.
- Research insight synthesis.
- Source IDs on bull/bear case points.

### LLM Contracts

Do not test exact model prose. Test:

- Structured output validation.
- Invalid JSON/schema failures.
- Citation requirements.
- Fallback behavior.
- LLM call event metadata.
- Usage summary rollups.

### Compliance

Unsafe examples should fail or be rewritten:

```text
You should buy this stock.
This is guaranteed to go up.
Allocate 20% of your portfolio.
```

Safe examples should pass:

```text
The bull case depends on revenue growth and margin expansion.
```

### Report Output

Avoid snapshotting exact LLM prose. Test:

- Required sections are present.
- Disclaimer is present.
- Forbidden advice phrases are absent.
- Sources are included.
- Known source IDs are cited.
- Limitations are included when data is missing.
- Scaffold/MVP language is absent.

### LangGraph

Test:

- Successful graph run.
- Company resolution failure.
- Missing metrics but graceful warnings.
- Missing filing text but graceful warnings.
- Deterministic fallback when no LLM client is configured.
- LLM-assisted happy path with fake clients.
- LLM failure fallback.
- Invalid/citationless LLM report fallback.
- Compliance rewrite path.
- Compliance blocked path.
- Report quality validation path.

### Persistence and API

Test:

- Research run lifecycle.
- Background job persistence.
- Retry and retry-chain behavior.
- Agent step storage.
- LLM call event storage.
- LLM usage endpoint.
- Migration coverage.

## Coding Guidelines

- Prefer small, focused modules.
- Keep route handlers thin.
- Keep deterministic logic out of LLM prompts.
- Prefer typed Pydantic models or typed dictionaries for structured data.
- Prefer dependency injection for clients/services that need mocking.
- Avoid global network calls at import time.
- Avoid hardcoded secrets, emails, API keys, or local machine paths.
- Add tests with every meaningful behavior change.
- Keep error messages user-friendly at API boundaries.
- Preserve detailed diagnostics in structured warnings, steps, or call events.
- Use `ruff` and `pytest` before considering code changes complete.

## File Editing Guidelines for Agents

- Do not edit `.venv/`, `venv/`, `.ruff_cache/`, `.pytest_cache/`, or `.env`.
- Do not commit or rely on `.env` contents.
- Update `.env.example` when adding new required environment variables.
- Update tests when adding behavior.
- Update README or docs when changing user-facing setup or commands.
- Do not delete or overwrite user work without explicit instruction.

## What Is Left

Post-4O likely remaining work includes:

- More robust filing section extraction across historical 10-K formats and
  additional sections beyond Item 1 Business and Item 1A Risk Factors.
- Controlled external metadata only if it can remain source-grounded and
  citation-aware.
- Deeper financial analysis only where it can remain deterministic,
  source-grounded, and well tested.
- More nuanced report quality scoring and citation coverage checks.
- More live LLM provider testing and production configuration docs.
- PostgreSQL deployment readiness.
- API auth/rate limiting if externally exposed.
- Deployment docs/containerization.
- Optional frontend or report viewing UI.
- Optional export formats such as Markdown/PDF after report content quality is
  strong.
- More live SEC smoke tests and operational monitoring.
- Risk-factor change detection between latest and previous 10-K filings.

Do not build a frontend before the backend workflow and report quality are
reliable.

## Definition of Done for Current Backend MVP

The backend MVP is strong when:

- A user can call `POST /research` with a ticker and receive a queued run ID.
- The system resolves the company.
- The system fetches SEC data.
- The system calculates basic financial metrics.
- The system analyzes risks or records a clear limitation.
- The system generates a structured, source-grounded report.
- The system runs compliance and report quality validation.
- The result is stored in the database.
- The user can poll by run ID until `completed` or `failed`.
- The user can inspect progress, steps, sources, warnings, LLM calls, and LLM
  usage.
- Core functionality is covered by deterministic tests.
- CI runs tests and lint.
- The README explains local use clearly.
- The report avoids financial advice and scaffold language.

When in doubt, keep the MVP small, traceable, source-grounded, and safe.
