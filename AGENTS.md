# AGENTS.md

Lean guide for AI agents working on FinSight. For full project guidance, see
`docs/AGENTS_FULL.md`.

## Mission

FinSight is a production-style AI equity research assistant built with FastAPI,
LangGraph, SEC EDGAR data, deterministic financial calculations, and a compliance
layer. It produces neutral, source-grounded research briefs. It is not an
investment advisor.

## Current Stage

Foundation is in place:

- UV-managed Python project, target `>=3.12,<3.15`.
- Source layout: `src/finsight_agent`.
- FastAPI app with `GET /health`.
- Pydantic settings in `app/config.py`.
- Initial pytest coverage.

Next planned stage: deterministic company resolver.

## Core Rules

- Do not provide financial advice or buy/sell/hold recommendations.
- Do not invent financial data, filing details, metrics, or citations.
- Use Python, not LLMs, for financial calculations.
- Use LLMs only for summarization, classification, report drafting, compliance
  review, and safe rewriting.
- Track warnings, limitations, and sources for research outputs.
- Keep changes incremental and tested.
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

## Architecture Direction

Target layers:

```text
FastAPI API
  -> LangGraph workflow
  -> services: resolver, SEC client, metrics, compliance, LLM adapter
  -> database: SQLite locally, PostgreSQL-ready later
```

Keep route handlers thin. Put deterministic business logic in services. Put
workflow orchestration in `app/graph`. Put persistence in `app/db`.

## Target Workflow

Research flow:

```text
resolve_company
fetch_sec_data
extract_financial_metrics
fetch_filing_text
analyze_risks
generate_report
compliance_check
persist_results
```

Use typed graph state. Store warnings/errors instead of crashing when graceful
partial output is possible.

## Company Resolver Requirements

The resolver must be deterministic and tested. Support:

```text
exact_ticker_match
exact_company_match
fuzzy_company_match
ambiguous
not_found
```

Return ticker, company name, normalized 10-digit CIK, status, confidence, and
candidate matches when ambiguous. Do not use an LLM for resolver logic.

## SEC and Metrics Rules

- Use `SEC_USER_AGENT` from settings.
- Mock SEC HTTP calls in tests.
- Track source URLs, filing dates, accession numbers, and retrieval time.
- Prefer annual 10-K facts for annual metrics.
- Prefer USD units.
- Track XBRL tags used for metrics.
- Surface missing or uncertain data as warnings.

## Compliance Rules

Flag or rewrite unsafe language such as:

```text
buy, sell, hold, guaranteed, risk-free, you should invest,
allocate your portfolio, price will go up, price will crash
```

Allow neutral research phrasing such as:

```text
The bull case depends on...
The bear case includes...
A key risk is...
```

Always run a final deterministic compliance scan before returning a report.

## Testing Expectations

Add or update tests with behavior changes. Prioritize deterministic tests:

- health/API tests
- company resolver tests
- SEC client tests with mocked responses
- metrics tests with fixtures
- compliance tests
- graph path tests once LangGraph is added

Before finishing changes, run:

```powershell
uv run pytest
uv run ruff check .
```

## Implementation Order

1. Company resolver.
2. SEC client.
3. Metrics extraction.
4. LangGraph state/workflow.
5. `POST /research`.
6. SQLite persistence.
7. Report generation with mock LLM.
8. Compliance checker.
9. Real LLM provider abstraction.
10. README and deployment polish.

When in doubt, keep the MVP small, traceable, source-grounded, and safe.

