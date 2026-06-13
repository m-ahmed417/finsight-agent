# FinSight Testing Plan

This document defines how FinSight will use test-driven development and staged
testing to build a production-style AI equity research assistant.

The goal is not just to have tests. The goal is to make the system safe to
change, easy to debug, and trustworthy when handling financial research data.

## Testing Philosophy

FinSight should be built with test-driven development wherever practical.

Default workflow:

```text
1. Define the behavior.
2. Write a failing test.
3. Run the test and confirm it fails for the expected reason.
4. Implement the smallest useful change.
5. Run the test and confirm it passes.
6. Refactor while keeping tests green.
7. Run the full test suite and linter.
```

This is the standard red, green, refactor cycle:

```text
Red -> Green -> Refactor
```

For this project, tests should focus on observable behavior and contracts. Avoid
testing implementation details that can change without changing behavior.

Good test:

```text
`AAPL` resolves to Apple Inc. with CIK `0000320193`.
```

Less useful test:

```text
The resolver loops through a list in a specific order.
```

## Core Testing Rules

- Write tests before production behavior when adding new functionality.
- Keep unit tests deterministic and fast.
- Do not call real SEC APIs in normal tests.
- Do not call real LLM APIs in normal tests.
- Use fixtures for SEC-like data.
- Use mocked HTTP responses for SEC client tests.
- Use fake or mock LLM providers for graph/report tests.
- Test financial calculations with explicit expected values.
- Test compliance with both unsafe and safe language.
- Prefer structural assertions over exact prose for generated reports.
- Run `pytest` and `ruff` before calling a slice complete.

## Commands

Run all tests:

```powershell
uv run pytest
```

Run one test file:

```powershell
uv run pytest tests/test_company_resolver.py
```

Run one test:

```powershell
uv run pytest tests/test_company_resolver.py::test_exact_ticker_match_is_case_insensitive
```

Run lint checks:

```powershell
uv run ruff check .
```

Run app manually:

```powershell
uv run uvicorn finsight_agent.app.main:app --reload
```

## Test Directory Structure

Target structure:

```text
tests/
  fixtures/
    sec_company_tickers.json
    sample_submissions.json
    sample_company_facts.json
    sample_10k_excerpt.txt

  test_health.py
  test_company_resolver.py
  test_sec_client.py
  test_filing_parser.py
  test_metrics.py
  test_compliance.py
  test_graph.py
  test_research_api.py
```

Only create files as features are introduced. Do not add empty test files.

## Test Categories

### Unit Tests

Use unit tests for deterministic logic:

- Company resolver.
- SEC response parsing.
- Filing metadata helpers.
- Financial metric calculations.
- Compliance phrase scanning.
- Report formatting helpers.

These tests should not require a database, network, or LLM.

### Fixture-Based Tests

Use fixture files for realistic but local SEC data:

- Company ticker mapping.
- Company submissions JSON.
- Company facts JSON.
- Filing excerpts.

Fixtures should be small enough to understand, but realistic enough to catch data
shape problems.

### HTTP-Mocked Tests

Use `respx` to mock `httpx` calls for the SEC client.

Test:

- Successful JSON responses.
- 404 responses.
- 429/rate-limit responses.
- 5xx responses.
- Timeout behavior.
- Malformed JSON.

No normal test should depend on live SEC availability.

### API Tests

Use FastAPI's test client or an equivalent ASGI test client.

Test:

- Request validation.
- Response schemas.
- Error responses.
- Status codes.
- Thin route behavior.

API tests should not duplicate all service-level tests.

### Graph Tests

Use fake services inside LangGraph tests.

Test workflow behavior:

- Successful run.
- Company resolution failure.
- Missing SEC data path.
- Missing metrics path.
- Compliance rewrite path.
- Critical failure path.

Graph tests should verify routing, state updates, warnings, and final status.

### LLM Contract Tests

Do not test exact LLM prose.

Instead, test contracts:

- Required sections are present.
- Required disclaimer is present.
- Sources are included.
- Limitations are included when inputs are incomplete.
- Forbidden advice language is absent.
- Structured outputs validate against Pydantic models.

Use a fake LLM provider for normal tests.

### Integration Tests

Integration tests should combine multiple local components:

- Resolver plus SEC fixture loader.
- Metrics service plus company facts fixture.
- API route plus fake graph.
- Graph plus fake SEC client and fake LLM.

These should still avoid live network calls.

### Optional Live Tests

Live SEC tests may be useful later, but they must be opt-in.

They should:

- Be skipped by default.
- Require an explicit environment variable such as `RUN_LIVE_SEC_TESTS=1`.
- Use a real `SEC_USER_AGENT`.
- Be rate-limited and minimal.

Do not require live tests for local development or CI.

## Stage-by-Stage Testing Plan

## Stage 1: Project Foundation

Purpose:

```text
Prove the project imports, the FastAPI app starts, and the test suite works.
```

Tests:

- `GET /health` returns `{"status": "ok"}`.
- App imports without side effects.
- Settings can be loaded.

Current status:

- Health endpoint test exists.

Definition of done:

```text
uv run pytest
uv run ruff check .
```

## Stage 2: Company Resolver

Purpose:

```text
Resolve user input into ticker, company name, and CIK before any SEC calls.
```

Test first:

- Exact ticker match is case-insensitive.
- Exact company-name match is case-insensitive.
- CIK is normalized to 10 digits.
- Empty query returns `not_found`.
- Unknown query returns `not_found`.
- Single partial match returns a low-confidence match.
- Multiple partial matches return `ambiguous`.

Next resolver tests:

- SEC ticker mapping fixture is converted into `CompanyRecord` objects.
- Duplicate or malformed records are handled safely.
- Candidate ordering is deterministic.
- Ambiguous results include useful candidate data.

No network calls in resolver tests.

## Stage 3: SEC Client

Purpose:

```text
Fetch and parse SEC EDGAR data safely.
```

Test first with mocked HTTP:

- Fetch company tickers mapping.
- Fetch company submissions JSON.
- Fetch company facts JSON.
- Builds correct SEC URLs.
- Sends configured `SEC_USER_AGENT`.
- Applies timeouts.
- Handles 404 with a structured error.
- Handles 429/rate limit with a structured error.
- Handles 5xx with a structured error.
- Handles malformed JSON.

Fixtures:

- `tests/fixtures/sec_company_tickers.json`
- `tests/fixtures/sample_submissions.json`
- `tests/fixtures/sample_company_facts.json`

Definition of done:

- No SEC client test touches the real network.
- All errors are testable and user-safe at the boundary.

## Stage 4: Filing Metadata and Parser

Purpose:

```text
Identify latest 10-K and 10-Q filings and retrieve relevant filing text.
```

Test first:

- Latest 10-K is selected from submissions fixture.
- Latest 10-Q is selected from submissions fixture.
- Missing 10-K returns a warning, not an unhandled crash.
- Accession numbers are normalized for URL construction.
- Filing source metadata includes form, accession, filing date, and period date.

Later parser tests:

- Extract risk-factor section from a simple 10-K excerpt.
- Handle missing risk-factor section.
- Handle malformed or unexpectedly formatted filing text.

## Stage 5: Financial Metrics Service

Purpose:

```text
Extract and calculate financial metrics deterministically from SEC company facts.
```

Test first:

- Revenue is extracted from preferred tag.
- Revenue falls back to alternate tags.
- Revenue growth is calculated correctly.
- Operating margin is calculated correctly.
- Net margin is calculated correctly.
- Missing metric produces a warning.
- USD units are preferred.
- Annual 10-K facts are preferred.
- Instant metrics are handled separately from duration metrics.

Calculation tests should use explicit values.

Example:

```text
Revenue 2023 = 100
Revenue 2024 = 125
Revenue growth = 0.25
```

Do not use an LLM for any metric test or calculation.

## Stage 6: Compliance Checker

Purpose:

```text
Prevent unsafe financial-advice language from reaching the final report.
```

Test unsafe phrases:

- "You should buy this stock."
- "This is guaranteed to go up."
- "Allocate 20% of your portfolio."
- "This is risk-free."
- "The price will crash."

Test safe phrases:

- "The bull case depends on revenue growth."
- "The bear case includes margin pressure."
- "Investors may want to investigate customer concentration."

Test required behavior:

- Required disclaimer is inserted or verified.
- Unsafe language is flagged.
- Final deterministic scan catches forbidden phrases.
- Blocked reports are not returned as safe.

## Stage 7: LangGraph Workflow

Purpose:

```text
Orchestrate resolver, SEC fetching, metrics, risk analysis, report generation,
compliance, and persistence.
```

Use fake services first.

Test graph paths:

- Successful run.
- Resolver returns `not_found` and graph stops cleanly.
- Resolver returns `ambiguous` and graph returns candidates.
- SEC data missing creates warnings and continues when possible.
- Metrics missing creates limitations.
- Report generation failure is handled.
- Compliance failure triggers rewrite path.
- Compliance failure after rewrite blocks final report.

Graph tests should assert state shape:

- `ticker`
- `company_name`
- `cik`
- `warnings`
- `errors`
- `sources`
- `final_report`
- `compliance_status`

## Stage 8: API Research Endpoints

Purpose:

```text
Expose research workflow through FastAPI.
```

Test first:

- `POST /research` validates request body.
- Empty query returns validation error.
- Successful request returns `run_id`, `status`, and report data.
- Failed resolution returns a user-friendly error.
- `GET /research/{run_id}` returns stored run.
- Unknown run ID returns 404.
- `GET /companies/search` returns resolver candidates.

Use fake graph/repository dependencies where possible.

## Stage 9: Database Persistence

Purpose:

```text
Store companies, research runs, agent steps, metrics, reports, warnings, and
sources.
```

Use a temporary SQLite database in tests.

Test:

- Create research run.
- Update run status.
- Store final report.
- Store warnings and sources JSON.
- Store agent step records.
- Store financial metrics.
- Retrieve run by ID.
- Unknown run returns `None` or expected repository result.

Do not use the developer's local `finsight.db` in tests.

## Stage 10: Report Generation

Purpose:

```text
Generate structured research briefs from evidence.
```

Use a fake LLM provider first.

Test:

- Required report sections are present.
- Required disclaimer is present.
- Metrics table appears when metrics exist.
- Missing metrics produce limitations.
- Sources appear in the final section.
- Report avoids unsupported claims.

Do not snapshot full LLM prose. Test structure and safety.

## Stage 11: End-to-End Local MVP

Purpose:

```text
Prove the system works as one local application without live external services.
```

Use:

- Fixture SEC data.
- Fake SEC client.
- Fake LLM provider.
- Temporary SQLite database.

Test:

- `POST /research` with `AAPL` returns completed report.
- Report has disclaimer.
- Report has sources.
- Run can be retrieved by ID.
- Agent steps are stored.
- No forbidden advice phrases appear.

This is the most important confidence test before adding live SEC behavior.

## Stage 12: Optional Live SEC Smoke Test

Purpose:

```text
Confirm that live SEC integration works without making normal tests flaky.
```

Rules:

- Skipped by default.
- Requires `RUN_LIVE_SEC_TESTS=1`.
- Requires valid `SEC_USER_AGENT`.
- Uses only one or two well-known tickers.
- Has conservative timeout and rate behavior.

Example tickers:

```text
AAPL
MSFT
```

Never make live SEC tests required for CI unless intentionally configured.

## CI Plan

When CI is added, default checks should be:

```text
uv run pytest
uv run ruff check .
```

Recommended GitHub Actions jobs:

- Install UV.
- Set Python from `.python-version`.
- Run `uv sync`.
- Run `uv run pytest`.
- Run `uv run ruff check .`.

Do not run live SEC or live LLM tests in default CI.

## Test Data Policy

Fixtures should:

- Be small.
- Be deterministic.
- Avoid secrets.
- Preserve realistic SEC field names.
- Include edge cases where useful.

Do not store:

- API keys.
- Personal credentials.
- Large raw filings unless absolutely necessary.
- User-specific `.env` files.

## Definition of Done for a Feature Slice

A feature slice is complete when:

```text
1. The intended behavior is described.
2. A failing test is written first where practical.
3. The implementation passes the new test.
4. Full pytest suite passes.
5. Ruff passes.
6. The change is small enough to explain clearly.
7. Any new environment variable is added to `.env.example`.
8. Documentation is updated when behavior or workflow changes.
```

## Practical Workflow for Future Work

Before coding:

```text
State the behavior to be added.
Name the test file to be changed or created.
Describe the expected failure.
```

During coding:

```text
Write the test.
Run the targeted test.
Implement the minimum code.
Run the targeted test again.
```

Before finishing:

```text
uv run pytest
uv run ruff check .
```

Then summarize:

```text
What changed.
What tests were added.
What commands passed.
What remains for the next stage.
```

