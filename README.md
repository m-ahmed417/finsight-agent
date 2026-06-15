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

Run an opt-in live LLM smoke test:

```powershell
$env:RUN_LIVE_LLM_TESTS="1"
uv run pytest tests/test_live_llm.py
```

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
