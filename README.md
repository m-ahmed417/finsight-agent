# FinSight Agent

Production-style AI equity research assistant built with FastAPI, LangGraph,
SEC EDGAR data, deterministic financial calculations, persistence, and a
compliance layer.

## Development

Run tests:

```powershell
uv run pytest
```

Run lint checks:

```powershell
uv run ruff check .
```

Run the API locally:

```powershell
uv run uvicorn finsight_agent.app.main:app --reload
```

## API Workflow

FinSight uses a run-based background workflow for research requests.
`POST /research` creates a persisted research run and returns immediately with
`202 Accepted`; it does not wait for the SEC/LLM workflow to finish.

Submit a research run:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/research" `
  -ContentType "application/json" `
  -Body '{"query":"AAPL"}'
```

The response includes a `run_id`, the original query, and `status="queued"`:

```json
{
  "run_id": "00000000-0000-0000-0000-000000000001",
  "retried_from_run_id": null,
  "query": "AAPL",
  "status": "queued",
  "created_at": "2026-06-16T13:00:00Z",
  "completed_at": null,
  "duration_seconds": null,
  "ticker": null,
  "company_name": null,
  "report": null,
  "financial_metrics": null,
  "warnings": [],
  "errors": [],
  "sources": []
}
```

Poll the run until it reaches a terminal status:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/research/{run_id}"
```

List recent runs:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/research?status=failed&limit=20"
```

`GET /research` returns recent runs in newest-first order as compact summaries.
Summaries include lifecycle fields plus `warnings_count`, `errors_count`, and
`has_report` so clients can scan runs without downloading full reports, metrics,
sources, or diagnostic payloads. Use `GET /research/{run_id}` for detailed fields.
Use `status=failed` to filter by a single lifecycle status. Use `limit=20` to
control how many runs are returned; the API accepts limits between 1 and 100.
When `has_more` is `true`, pass the returned `next_cursor` as `cursor` on the
next request to fetch the following page.

Example list response:

```json
{
  "items": [
    {
      "run_id": "00000000-0000-0000-0000-000000000002",
      "retried_from_run_id": null,
      "query": "AAPL",
      "status": "completed",
      "created_at": "2026-06-16T13:00:00Z",
      "completed_at": "2026-06-16T13:02:30Z",
      "duration_seconds": 150.0,
      "ticker": "AAPL",
      "company_name": "Apple Inc.",
      "warnings_count": 1,
      "errors_count": 0,
      "has_report": true
    }
  ],
  "next_cursor": "opaque-cursor",
  "has_more": true
}
```

Fetch the next page:

`GET /research?status=failed&limit=20&cursor={next_cursor}`

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/research?status=failed&limit=20&cursor={next_cursor}"
```

Research run statuses are:

- `queued`: the run has been accepted and stored.
- `running`: the background workflow is executing.
- `completed`: the report and research data are available.
- `failed`: the workflow stopped with one or more structured `errors`.

Every research response includes lifecycle timestamps. `created_at` is the UTC
time when the run was accepted. `completed_at` is `null` while a run is
`queued` or `running`, then becomes the UTC time when the run reaches a
terminal status (`completed` or `failed`). `duration_seconds` is `null` until
`completed_at` is set, then reports the elapsed seconds between `created_at`
and `completed_at`.

When a run is `completed`, read the `report`, `financial_metrics`,
`risk_factors`, `risk_themes`, `research_insights`, `warnings`, `errors`, and
`sources` fields from `GET /research/{run_id}`. When a run is `failed`, inspect
`errors`, `warnings`, and any partial `sources` for the reason and available
diagnostics.

### Report Quality and Grounding

Generated reports are structured research briefs, not recommendations. Each
final report keeps the required 11-section structure, includes the required
research-only disclaimer, lists sources and limitations, and avoids financial
advice language.

The required disclaimer is:

```text
This report is for informational and educational research purposes only. It is
not financial advice, investment advice, or a recommendation to buy, sell, or
hold any security.
```

Reports cite known source IDs such as `[sec_company_facts]` and `[latest_10k]`
for source-grounded financial, risk, bull-case, and bear-case claims. Missing
data is surfaced as warnings or limitations instead of invented facts.

The workflow also extracts Item 1 Business evidence from the latest 10-K when
available. The Company Overview uses the deterministic `business_overview`
artifact derived from that evidence, cites `[latest_10k]`, mentions filing
metadata such as filing date or accession number, and avoids copying raw Item 1 text
into the report. If Item 1 Business cannot be extracted, the limitation is surfaced
through warnings or limitations instead of replacing it with external company
descriptions.

### Financial Presentation and Period Analysis

Financial metrics are still calculated deterministically from SEC company facts
in Python. In final reports, FinSight presents those metrics with readable
financial values such as `$1.25B`, `$280.0M`, and `N/A`; percentage metrics use
readable output such as `25.0%`. The raw numeric metric values remain internal
for calculations, persistence, API responses, and deterministic tests.

The Financial Performance and Key Financial Metrics sections include
deterministic period comparisons when enough fiscal-year data is available.
Examples include revenue increases or decreases, margin movement in percentage
points, and free cash flow changes. Financial claims continue to cite
`[sec_company_facts]`, and missing values are shown as `N/A` or surfaced through
warnings and limitations rather than invented.

LLM report drafts that repeat raw metric values in financial performance text
are rejected by graph validation and use deterministic fallback, so model
drafting cannot bypass source-grounded financial presentation.

Before persistence, the workflow runs deterministic compliance checks and then
report quality validation. Completed runs expose `compliance_status` and
`report_quality_status`; when enough SEC-derived evidence is available, normal
research runs should finish with `report_quality_status="passed"`. The validator
also guards against scaffold language. Examples include `MVP draft`,
`future versions will`, `pending deterministic synthesis`, and
`no sources were recorded`.

On application startup, FinSight recovers stale in-progress runs. Any `queued`
or `running` run older than `RESEARCH_RUN_STALE_AFTER_SECONDS` is marked
`failed` with a structured `research_run_stale` error so polling clients do not
wait forever on abandoned background work.

Fetch stored workflow progress:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/research/{run_id}/progress"
```

`GET /research/{run_id}/progress` returns a compact progress summary built from
the stored `agent_steps`: `total_steps`, `completed_steps`, `failed_steps`,
`latest_step`, `workflow_started_at`, `workflow_completed_at`, and
`workflow_duration_seconds`. It is intended for polling UIs that need the latest
stored workflow position without downloading the full audit trail.

Retry a failed run:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/research/{run_id}/retry"
```

`POST /research/{run_id}/retry` only retries runs whose current status is
`failed`. A successful retry returns `202 Accepted` with a new queued run using
the original query. The original failed run is preserved for audit history, and
the retry response contains a different `run_id` for the new queued run. Its
`retried_from_run_id` points to the original failed run. Unknown run IDs return
`404`. Runs that are still `queued` or `running`, or already `completed`, return
`409` with `Only failed research runs can be retried`.

Fetch the retry chain for any run in a retry family:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/research/{run_id}/retries"
```

`GET /research/{run_id}/retries` returns the original run and its retry chain in
creation order using the same response shape as `GET /research/{run_id}`.
Unknown run IDs return `404`.

Fetch the persisted audit trail:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/research/{run_id}/steps"
```

`GET /research/{run_id}/steps` returns the stored `agent_steps` as records with
`node_name`, `status`, `message`, `error_message`, `started_at`, `completed_at`,
`duration_seconds`, `llm_provider`, `llm_model`, `llm_used`, and
`llm_fallback_reason` fields. Workflow-generated steps populate UTC timing
metadata and record whether LLM output or deterministic fallback was used for
LLM-aware steps. Timing and LLM fields remain nullable so older or partial
workflow steps can still be returned without inventing execution details.

Fetch model-call audit events:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/research/{run_id}/llm-calls"
```

`GET /research/{run_id}/llm-calls` returns the stored `llm_call_events` for
LLM-aware workflow nodes. Each record includes `node_name`, `task`, `status`,
`llm_provider`, `llm_model`, `prompt_version`, `started_at`, `completed_at`,
`duration_seconds`, `input_tokens`, `output_tokens`, `total_tokens`,
`provider_request_id`, `error_type`, `error_message`, `fallback_used`, and
`fallback_reason`. Successful provider calls are recorded with
`status=completed`; failed provider calls are recorded with `status=failed` and
the deterministic fallback reason; disabled model calls are recorded with
`status=skipped`.

Fetch a compact LLM usage summary:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/research/{run_id}/llm-usage"
```

`GET /research/{run_id}/llm-usage` rolls up the stored model-call audit events
without returning the full event list. It reports `total_calls`,
`completed_calls`, `failed_calls`, `skipped_calls`, `fallback_count`,
`total_duration_seconds`, `total_input_tokens`, `total_output_tokens`,
`total_tokens`, `providers`, and `models`. Token totals are provider-reported
when available; FinSight does not estimate dollar cost here because model
pricing changes outside the codebase.

## Configuration

Core environment variables:

```powershell
APP_ENV=local
DATABASE_URL=sqlite:///./finsight.db
SEC_USER_AGENT=FinSight/0.1 your-email@example.com
SEC_CACHE_DIR=.finsight_cache/sec
SEC_CACHE_TTL_SECONDS=86400
SEC_REQUEST_INTERVAL_SECONDS=0.1
RESEARCH_RUN_STALE_AFTER_SECONDS=3600
LLM_PROVIDER=mock
LLM_MODEL=mock
OPENAI_API_KEY=
DEEPSEEK_API_KEY=
```

`LLM_PROVIDER` supports `mock`, `openai`, and `deepseek`. Keep
`LLM_PROVIDER=mock` for deterministic local development and tests. To test a
real provider, set `LLM_PROVIDER=openai` or `LLM_PROVIDER=deepseek` with a
matching `LLM_MODEL`; real providers require a non-empty `LLM_MODEL`. Use
`OPENAI_API_KEY` for `LLM_PROVIDER=openai` and `DEEPSEEK_API_KEY` for
`LLM_PROVIDER=deepseek`. Please do not store API keys in committed files; configure
them through your local environment or an uncommitted `.env`.

`RESEARCH_RUN_STALE_AFTER_SECONDS` controls startup recovery for abandoned
background research runs. The default is `3600` seconds. During startup, FinSight
marks stale `queued` and `running` runs as `failed` rather than leaving them in
a non-terminal polling state.

### SEC Data Operations

SEC live-data access is configured with:

- `SEC_USER_AGENT`: Required for live SEC access. Use a descriptive value that
  identifies the app and a contact email, for example
  `FinSight/0.1 your-name@example.com`.
- `SEC_CACHE_DIR`: Filesystem cache directory for SEC JSON and filing document
  responses. Set it to an empty value to disable caching.
- `SEC_CACHE_TTL_SECONDS`: Cache freshness window in seconds. The default is
  `86400` (24 hours). Cached responses older than this value are refetched from
  SEC before the workflow continues.
- `SEC_REQUEST_INTERVAL_SECONDS`: Minimum delay between live SEC HTTP requests.
  Cached responses do not wait on this interval.

The research workflow records SEC diagnostics in the persisted `agent_steps`,
`sources`, `warnings`, and `errors` fields. Useful debugging details include:

- normalized CIK values used for SEC requests
- recorded source IDs such as `sec_submissions`, `sec_company_facts`, and
  `latest_10k`
- latest 10-K and 10-Q accession numbers and filing dates
- filing document plus extracted business and risk-factor text character counts
- latest 10-K extracted sections such as Item 1 Business and Item 1A Risk
  Factors
- metric fiscal years and XBRL tag counts used during deterministic extraction
- SEC cache status for source fetches:
  - `cache_status` and `cache_key` on JSON sources such as `sec_submissions`
    and `sec_company_facts`
  - `document_cache_status` and `document_cache_key` on filing document
    sources such as `latest_10k`
- SEC cache freshness for source fetches:
  - `cache_age_seconds`, `cache_ttl_seconds`, `cache_expires_at`, and
    `cache_stale` on JSON sources
  - matching `document_cache_*` fields on filing document sources
- structured warning details when filing text, business-section extraction, or
  risk-factor extraction is unavailable

Cache statuses are:

- `hit`: the response was read from the filesystem cache
- `miss`: the response came from a live SEC HTTP request and caching is enabled
- `disabled`: the response came from a live SEC HTTP request because
  `SEC_CACHE_DIR` is empty or unset

Cache keys are logical request identifiers used by the SEC client before hashing
them into filesystem cache filenames. They are useful for debugging cache reuse,
but they are not local file paths.

When `SEC_CACHE_TTL_SECONDS` is set, FinSight reports cache freshness metadata.
Fresh cache entries are returned with `cache_stale=false`; expired entries are
refetched and the refreshed response is reported as `cache_status=miss`. Set
`SEC_CACHE_DIR` to an empty value to disable caching entirely.

These diagnostics are operational metadata only. They should help debug data
retrieval and extraction behavior without changing the report's research-only
stance.

### Live Smoke Tests

Run an opt-in live LLM smoke test for provider-backed risk analysis and report
drafting:

```powershell
$env:LLM_PROVIDER="openai"
$env:LLM_MODEL="gpt-4.1-mini"
$env:OPENAI_API_KEY="..."
$env:RUN_LIVE_LLM_TESTS="1"
uv run pytest tests/test_live_llm.py
```

For DeepSeek, use `LLM_PROVIDER=deepseek`, set a DeepSeek-compatible
`LLM_MODEL`, and provide `DEEPSEEK_API_KEY` instead.

Run an opt-in live SEC smoke test:

```powershell
$env:SEC_USER_AGENT="FinSight/0.1 your-name@example.com"
$env:RUN_LIVE_SEC_TESTS="1"
uv run pytest tests/test_live_sec.py
```

Run an opt-in live SEC graph smoke test:

```powershell
$env:SEC_USER_AGENT="FinSight/0.1 your-name@example.com"
$env:RUN_LIVE_SEC_GRAPH_TESTS="1"
uv run pytest tests/test_live_sec_graph.py
```

Run an opt-in end-to-end live SEC plus live LLM graph smoke test:

```powershell
$env:SEC_USER_AGENT="FinSight/0.1 your-name@example.com"
$env:LLM_PROVIDER="openai"
$env:LLM_MODEL="gpt-4.1-mini"
$env:OPENAI_API_KEY="..."
$env:RUN_LIVE_SEC_LLM_GRAPH_TESTS="1"
uv run pytest tests/test_live_sec_llm_graph.py
```

Live smoke tests are skipped by default and should be run deliberately. The live
LLM smoke test exercises provider-backed risk analysis and report drafting
without making exact prose assertions. Use the safe testing order: mock first,
provider smoke test second, end-to-end live run last. These live tests are not
intended for normal CI.

The live SEC test uses a temporary cache directory, respects
`SEC_REQUEST_INTERVAL_SECONDS`, and fetches:

- SEC company tickers
- Apple's submissions metadata
- Apple's company facts
- the ticker endpoint a second time to verify cache reuse

It asserts basic response shape only, not exact financial values, so it remains
stable across normal SEC filing updates.

The live SEC graph test runs the LangGraph workflow for Apple using the real SEC
client, the deterministic local company resolver, and the mock LLM provider. It
asserts report/state shape, required safety fields, source metadata, cache
diagnostics, and compliance status without asserting exact financial values.

The live SEC plus LLM graph test runs the same Apple workflow with real SEC data
and the configured real LLM provider. It verifies the final report disclaimer,
known citations, compliance status, report quality status, LLM call events,
usage summary, and deterministic fallback visibility when provider output is
unavailable or rejected. It also avoids exact model prose assertions.

## Database Migrations

FinSight uses Alembic for database schema migrations.

Apply migrations to the configured database:

```powershell
uv run alembic upgrade head
```

Create a new migration after model changes:

```powershell
uv run alembic revision --autogenerate -m "Describe schema change"
```

By default, migrations use `DATABASE_URL` from the environment or
`sqlite:///./finsight.db`.
