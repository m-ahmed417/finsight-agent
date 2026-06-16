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

## Configuration

Core environment variables:

```powershell
APP_ENV=local
DATABASE_URL=sqlite:///./finsight.db
SEC_USER_AGENT=FinSight/0.1 your-email@example.com
SEC_CACHE_DIR=.finsight_cache/sec
SEC_CACHE_TTL_SECONDS=86400
SEC_REQUEST_INTERVAL_SECONDS=0.1
LLM_PROVIDER=mock
LLM_MODEL=mock
OPENAI_API_KEY=
DEEPSEEK_API_KEY=
```

`LLM_PROVIDER` supports `mock`, `openai`, and `deepseek`. Keep `mock` for
deterministic local development and tests. Real providers should be configured
with a matching `LLM_MODEL` and provider API credentials in the environment.
Use `OPENAI_API_KEY` for `LLM_PROVIDER=openai` and `DEEPSEEK_API_KEY` for
`LLM_PROVIDER=deepseek`.

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
- filing document and extracted risk-factor text character counts
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
- structured warning details when filing text or risk-factor extraction is
  unavailable

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

Run an opt-in live LLM smoke test:

```powershell
$env:RUN_LIVE_LLM_TESTS="1"
uv run pytest tests/test_live_llm.py
```

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

Live smoke tests are skipped by default and should be run deliberately. The live
SEC test uses a temporary cache directory, respects `SEC_REQUEST_INTERVAL_SECONDS`,
and fetches:

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
