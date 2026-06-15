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
- structured warning details when filing text or risk-factor extraction is
  unavailable

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

Live smoke tests are skipped by default and should be run deliberately. The live
SEC test uses a temporary cache directory, respects `SEC_REQUEST_INTERVAL_SECONDS`,
and fetches:

- SEC company tickers
- Apple's submissions metadata
- Apple's company facts
- the ticker endpoint a second time to verify cache reuse

It asserts basic response shape only, not exact financial values, so it remains
stable across normal SEC filing updates.

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
