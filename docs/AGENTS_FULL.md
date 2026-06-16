# AGENTS.md

## Project Identity

FinSight is a production-style AI equity research assistant built with FastAPI,
LangGraph, SEC EDGAR data, deterministic financial calculations, and a compliance
layer that prevents personalized financial advice.

The product is an evidence-based research assistant, not an investment advisor.
It should help users understand public companies through source-grounded research
briefs, SEC filings, financial metrics, business risks, and neutral bull/bear
analysis.

Primary positioning:

> FinSight is a production-style AI equity research assistant built with
> LangGraph. It orchestrates a multi-step research workflow that resolves public
> companies, retrieves SEC filings, extracts financial metrics, summarizes
> business risks, generates bull and bear research cases, and produces
> source-grounded research briefs with a compliance layer that avoids personalized
> investment advice.

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

## Current Project Stage

The project is in its foundation stage.

Current baseline:

- UV-managed Python project.
- Python target: `>=3.12,<3.15`.
- Source layout under `src/finsight_agent`.
- Minimal FastAPI app.
- `GET /health` endpoint.
- Basic config loading with Pydantic Settings.
- `.env.example`.
- Initial health endpoint test.

Do not assume the full agent already exists. Add capabilities incrementally and
keep each stage testable.

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

Do not require manual virtual environment activation. It is acceptable to activate
`.venv`, but prefer `uv run ...` in docs and examples.

## High-Level Architecture

Target architecture:

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
  |-- generate_report
  |-- compliance_check
  |-- persist_results
  |
  v
SQLite locally / PostgreSQL-ready storage
  |
  v
Research Brief
```

Recommended package structure:

```text
src/finsight_agent/
  app/
    main.py
    config.py

    api/
      routes.py
      schemas.py

    graph/
      state.py
      builder.py
      nodes/
        resolve_company.py
        fetch_sec_data.py
        extract_metrics.py
        analyze_risks.py
        generate_report.py
        compliance_check.py
        persist_results.py

    services/
      company_resolver.py
      sec_client.py
      filing_parser.py
      metrics.py
      llm_client.py
      report_formatter.py
      compliance.py
      cache.py

    db/
      database.py
      models.py
      repository.py

    prompts/
      risk_analysis_prompt.py
      report_prompt.py
      compliance_prompt.py

    utils/
      logging.py
      errors.py
```

Do not create every file prematurely. Grow this structure as features are added.

## Layer Responsibilities

### API Layer

The API layer should:

- Define HTTP endpoints.
- Validate request and response bodies using Pydantic schemas.
- Translate service or graph results into API responses.
- Avoid complex business logic.
- Return user-friendly errors.

Core target endpoints:

- `GET /health`
- `POST /research`
- `GET /research/{run_id}`
- `GET /research/{run_id}/steps`
- `GET /companies/search?q=apple`

For production readiness, prefer a run-based API:

```text
POST /research -> creates a queued run and returns 202 Accepted with run_id/status
GET /research/{run_id} -> retrieves run state, final report, or structured errors
GET /research/{run_id}/steps -> retrieves audit trail
```

The API is run-based: clients submit work, store the returned `run_id`, and poll
until the run reaches `completed` or `failed`.

### Services Layer

The services layer should contain deterministic, testable business logic:

- Company resolution.
- SEC API access.
- Filing metadata parsing.
- Filing text retrieval/parsing.
- Financial metric extraction.
- Compliance phrase scanning.
- Report formatting helpers.

Services should not depend on FastAPI request objects.

### Graph Layer

The graph layer should orchestrate workflow steps using LangGraph.

Each major research step should be a graph node with a clear input/output
contract. Nodes should update typed state and record warnings/errors instead of
raising raw exceptions through the whole workflow when graceful continuation is
possible.

### Database Layer

The database layer should isolate persistence concerns:

- SQLAlchemy/SQLModel models.
- Session management.
- Repository functions.
- Alembic migrations once persistence is introduced.

SQLite is the local default. Keep the design PostgreSQL-ready.

### LLM Layer

The LLM layer should be provider-abstracted. Do not scatter direct OpenAI,
DeepSeek, or other provider calls throughout graph nodes.

Use structured outputs with Pydantic where practical.

## LangGraph State

Use a typed state object. Target shape:

```python
class FinSightState(TypedDict):
    run_id: str | None
    user_query: str

    ticker: str | None
    company_name: str | None
    cik: str | None
    resolution_status: str | None
    resolution_confidence: float | None

    sec_submissions: dict | None
    company_facts: dict | None
    latest_10k: dict | None
    latest_10q: dict | None
    filing_text: str | None

    financial_metrics: dict | None
    risk_factors: list[dict]

    report_draft: str | None
    final_report: str | None

    sources: list[dict]
    warnings: list[dict]
    errors: list[dict]

    compliance_status: str | None
    confidence: str | None
    limitations: list[str]
```

Prefer structured warnings/errors:

```json
{
  "code": "metric_missing",
  "message": "Free cash flow could not be calculated because capital expenditure was unavailable.",
  "severity": "warning"
}
```

## Required Workflow Nodes

### `resolve_company`

Responsibilities:

- Accept ticker or company name.
- Resolve to ticker, company name, and SEC CIK.
- Normalize CIK to 10 digits where needed.
- Distinguish exact ticker match, exact company match, fuzzy match, ambiguous,
  and not found.
- Never use the LLM for basic deterministic matching.

Graceful behavior:

- Unknown company should stop with a clear error.
- Ambiguous company should return possible matches rather than guessing.

### `fetch_sec_data`

Responsibilities:

- Fetch SEC submissions JSON.
- Fetch SEC company facts JSON.
- Identify latest 10-K and latest 10-Q metadata.
- Track SEC source URLs, accession numbers, filing dates, and retrieval times.
- Use a configurable SEC User-Agent.
- Respect SEC usage with timeouts, retries, and reasonable rate limiting.

Graceful behavior:

- SEC failures should produce structured warnings/errors.
- Missing company facts should not crash the whole run if a qualitative report is
  still possible.

### `extract_financial_metrics`

Responsibilities:

- Extract metrics from SEC XBRL company facts.
- Prefer annual 10-K facts where available.
- Prefer USD units.
- Deduplicate by fiscal year, period, form, and filed date.
- Prefer latest filed value for the same period.
- Separate duration metrics from instant metrics.
- Calculate growth and margins in Python.
- Track source XBRL tags and units.

Do not use the LLM for calculations.

Target metrics:

- Revenue.
- Revenue growth.
- Operating income.
- Operating margin.
- Net income.
- Net margin.
- Total assets.
- Total liabilities.
- Cash and cash equivalents.
- Long-term debt.
- Operating cash flow.
- Capital expenditure.
- Free cash flow.

Use a tag priority system. Examples:

```text
Revenue:
- RevenueFromContractWithCustomerExcludingAssessedTax
- Revenues
- SalesRevenueNet

Net income:
- NetIncomeLoss

Operating income:
- OperatingIncomeLoss

Assets:
- Assets

Liabilities:
- Liabilities

Cash:
- CashAndCashEquivalentsAtCarryingValue
- CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents
```

### `fetch_filing_text`

Responsibilities:

- Retrieve latest 10-K filing text or primary document when available.
- Track accession number, document URL, form type, filing date, and period.
- Extract sections needed for risk analysis when feasible.

### `analyze_risks`

Responsibilities:

- Summarize key business risks from the latest 10-K.
- Use the LLM only for summarization/classification.
- Include source filing metadata with each risk.
- Avoid unsupported claims.

If risk text cannot be retrieved, report the limitation.

### `generate_report`

Responsibilities:

- Generate a professional, neutral research brief.
- Use only provided evidence.
- Include warnings and limitations.
- Include sources used.
- Avoid recommendations and personalized advice.

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

- Run a deterministic forbidden-phrase scan.
- Optionally run an LLM semantic compliance review.
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
buy
sell
hold
strong buy
strong sell
guaranteed
risk-free
you should invest
put your money into
allocate your portfolio
this stock will definitely
price will go up
price will crash
```

Allowed neutral research language includes:

```text
The bull case depends on...
The bear case includes...
Investors may want to investigate...
A key risk is...
The company's financial performance shows...
```

### `persist_results`

Responsibilities:

- Store run status, final report, warnings, errors, sources, step metadata, and
  financial metrics.
- Do not let persistence failures silently corrupt user-facing state.

## Company Resolver Requirements

The resolver should be deterministic and testable.

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

For ambiguous input, return candidates:

```json
{
  "resolution_status": "ambiguous",
  "matches": [
    {"ticker": "AAPL", "company_name": "Apple Inc.", "cik": "0000320193"},
    {"ticker": "APLE", "company_name": "Apple Hospitality REIT, Inc.", "cik": "..."}
  ]
}
```

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
- Support retry/backoff for transient failures.
- Avoid aggressive request rates.
- Track source URLs and retrieval timestamps.
- Be easy to mock in tests.

Caching policy target:

```text
Company tickers mapping: cache for about 24 hours.
Submissions JSON: cache for about 6-24 hours.
Company facts JSON: cache for about 6-24 hours.
Filing documents: cache by accession number where practical.
```

Do not hardcode personal email addresses in source code.

## Source Provenance

Every material source should be traceable.

For filing sources, track:

- Source type.
- SEC URL.
- Ticker.
- CIK.
- Form type.
- Accession number.
- Filing date.
- Period end date.
- Retrieved timestamp.

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

## Data Quality and Limitations

SEC data is messy. Code defensively.

Use structured warnings for:

- `metric_missing`
- `tag_fallback_used`
- `stale_filing`
- `multiple_units_found`
- `non_usd_unit_ignored`
- `incomplete_period`
- `restated_value_possible`
- `cash_flow_unavailable`
- `filing_text_unavailable`
- `sec_api_failure`
- `llm_unavailable`
- `compliance_rewrite_failed`

Reports must surface important limitations to the user.

## Database Target

Use SQLite for local development. Keep the schema PostgreSQL-ready.

Target models:

### Company

```text
id
ticker
company_name
cik
exchange
created_at
updated_at
```

### ResearchRun

```text
id
query
ticker
company_name
status
final_report
warnings_json
sources_json
error_message
created_at
completed_at
```

Recommended statuses:

```text
queued
running
completed
failed
```

### AgentStep

```text
id
research_run_id
node_name
status
input_json
output_json
warnings_json
error_message
started_at
completed_at
duration_ms
retry_count
model_name
token_usage_json
```

### FinancialMetric

```text
id
research_run_id
fiscal_year
revenue
revenue_growth
operating_income
operating_margin
net_income
net_margin
assets
liabilities
cash
debt
operating_cash_flow
capital_expenditure
free_cash_flow
source_json
created_at
```

Use Alembic migrations once models are introduced.

## LLM Usage Rules

Allowed LLM usage:

- Summarizing business descriptions.
- Summarizing and categorizing risk factors.
- Drafting the final report from structured evidence.
- Semantic compliance checking.
- Rewriting unsafe language into neutral research language.

Disallowed LLM usage:

- Ticker matching when deterministic matching is available.
- Raw financial calculations.
- Inventing missing data.
- Predicting prices as fact.
- Providing buy/sell/hold recommendations.
- Personalized portfolio allocation.

Prompting rules:

- Provide structured evidence to the model.
- Tell the model to avoid unsupported claims.
- Tell the model to explicitly state when evidence is unavailable.
- Validate structured outputs with Pydantic where possible.
- Fail gracefully on invalid JSON or schema validation errors.

## Error Handling

Handle these cases gracefully:

- Unknown ticker.
- Ambiguous company name.
- SEC API failure.
- Missing company facts.
- Missing 10-K.
- Malformed filing data.
- LLM timeout/failure.
- Invalid LLM structured output.
- Compliance failure.
- Database failure.

User-facing errors should be clear and non-technical:

```json
{
  "status": "failed",
  "error": "Could not confidently resolve the company. Try using a stock ticker such as AAPL or MSFT."
}
```

Internal logs should preserve diagnostic detail without leaking secrets.

## Observability Requirements

Production-grade behavior requires traceability.

Track:

- Request ID.
- Run ID.
- Node name.
- Node status.
- Node duration.
- Retry count.
- SEC request URL/status/duration.
- LLM provider/model.
- Token usage where available.
- Warnings and errors.

Design for LangSmith or OpenTelemetry later, but do not block MVP progress on
full tracing.

## Testing Strategy

Add tests as features are introduced. Prioritize deterministic tests before LLM
tests.

Required test areas:

### Health/API

- `GET /health` returns `{"status": "ok"}`.

### Company Resolver

- `AAPL` resolves to Apple Inc.
- `MSFT` resolves to Microsoft Corporation.
- Unknown ticker returns a clear not-found result.
- Ambiguous company name returns candidates.

### SEC Client

Use fixtures and mocked HTTP responses.

Test:

- Submissions parsing.
- Company facts parsing.
- Latest 10-K detection.
- Latest 10-Q detection.
- SEC error handling.

### Metrics Service

Test:

- Revenue growth calculation.
- Margin calculation.
- Missing values.
- Fallback XBRL tags.
- Annual 10-K preference.
- Instant vs duration metric handling.

### Compliance Checker

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

### LangGraph

Test:

- Successful graph run.
- Company resolution failure.
- Missing metrics but report still generated with warnings.
- Compliance rewrite path.
- Critical error path.

### Report Output

Avoid snapshotting exact LLM prose. Instead test:

- Required sections are present.
- Disclaimer is present.
- Forbidden advice phrases are absent.
- Sources are included.
- Limitations are included when data is missing.

## Implementation Order

Preferred build order:

1. Maintain project foundation: UV, FastAPI app, config, health endpoint.
2. Add company resolver and deterministic tests.
3. Add SEC client with mocked tests.
4. Add metrics extraction service with fixtures.
5. Add graph state and initial LangGraph workflow.
6. Wire `POST /research` to queued background graph execution.
7. Add SQLite persistence and repositories.
8. Add report generation with a mock LLM provider first.
9. Add compliance checker.
10. Add real LLM provider abstraction.
11. Add run step audit trail endpoint.
12. Add caching/retry/backoff.
13. Add README polish, sample outputs, and deployment docs.

Do not build a frontend before the backend workflow is reliable.

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
- Preserve detailed diagnostics in structured logs or step records.
- Use `ruff` and `pytest` before considering a change complete.

## File Editing Guidelines for Agents

- Do not edit generated environments such as `.venv/`, `venv/`, `.ruff_cache/`,
  or `.pytest_cache/`.
- Do not commit or rely on `.env` contents.
- Do update `.env.example` when adding new required environment variables.
- Do update tests when adding behavior.
- Do update README or docs when changing user-facing setup or commands.
- Do not delete or overwrite user work without explicit instruction.

## Definition of Done for MVP

The MVP is complete when:

- A user can call `POST /research` with a ticker and receive a queued run ID.
- The system resolves the company.
- The system fetches SEC data.
- The system calculates basic financial metrics.
- The system generates a structured research report.
- The system runs a compliance check.
- The result is stored in the database.
- The user can poll the research run by ID until it is `completed` or `failed`.
- Core functionality is covered by tests.
- The README explains the project clearly.
- The report avoids financial advice.

## Future Enhancements

Do not build these until the core MVP is stable:

- Frontend dashboard.
- PDF export.
- Historical metric charts.
- Peer comparison.
- FRED macroeconomic data.
- Earnings transcript analysis.
- Risk-factor change detection between latest and previous 10-K filings.
- Watchlist monitoring.
- Human review/editing workflow.
- LangSmith tracing.
- PostgreSQL and pgvector.
- Docker deployment.

The strongest V2 feature would be:

> Compare the latest 10-K risk factors with the previous 10-K and highlight new,
> removed, or expanded risks.
