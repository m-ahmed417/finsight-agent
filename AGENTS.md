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
- Filing text and risk-factor extraction.
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
- GitHub Actions CI for tests and linting.

Current completed stage:

```text
4N - Report Quality and Grounding
```

Stage 4N removed scaffold/MVP language from generated reports and made final
reports production-style, neutral, source-grounded, citation-aware, and honest
about limitations. The next named stage has not been selected yet.

## Development Method

From 4N onward, use both spec-driven development and test-driven development.

For a new stage:

1. Write or update a spec first.
2. Convert the spec into acceptance criteria.
3. Write failing tests for the next small slice.
4. Implement the smallest production-quality change.
5. Run verification.
6. Update docs when behavior changes.

The Stage 4N spec is:

```text
docs/specs/4N-report-quality-grounding.md
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
- Avoid raw copied filing text.
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

Before finishing code changes, run:

```powershell
uv run pytest
uv run ruff check .
```

## Stage 4N Status

Stage 4N was implemented in small, tested slices:

1. `4N-0`: Wrote `docs/specs/4N-report-quality-grounding.md`.
2. `4N-1`: Strengthened report quality validator with failing tests first.
3. `4N-2`: Improved deterministic report generation with failing tests first.
4. `4N-3`: Proved end-to-end graph report quality.
5. `4N-4`: Updated docs and ran full verification.

When in doubt, keep the MVP small, traceable, source-grounded, and safe.
