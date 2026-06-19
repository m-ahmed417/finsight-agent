from types import SimpleNamespace

from sqlalchemy import create_engine, inspect, text

from finsight_agent.app.db import database


def test_sqlite_init_backfills_research_run_status_columns(
    tmp_path,
    monkeypatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE research_runs (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    query VARCHAR(120) NOT NULL,
                    ticker VARCHAR(20),
                    company_name VARCHAR(255),
                    status VARCHAR(30) NOT NULL,
                    final_report TEXT,
                    financial_metrics_json JSON,
                    warnings_json JSON NOT NULL DEFAULT '[]',
                    errors_json JSON NOT NULL DEFAULT '[]',
                    sources_json JSON NOT NULL DEFAULT '[]',
                    created_at DATETIME NOT NULL,
                    completed_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE agent_steps (
                    id INTEGER NOT NULL PRIMARY KEY,
                    research_run_id VARCHAR(36) NOT NULL,
                    node_name VARCHAR(80) NOT NULL,
                    status VARCHAR(30) NOT NULL,
                    message TEXT,
                    error_message TEXT,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "settings", SimpleNamespace(database_url=database_url))

    database.init_db()

    column_names = {
        column["name"]
        for column in inspect(engine).get_columns("research_runs")
    }
    assert {
        "compliance_status",
        "report_quality_status",
        "retried_from_run_id",
        "filing_text_excerpt",
        "risk_factors_json",
        "risk_themes_json",
        "research_insights_json",
    }.issubset(column_names)

    agent_step_column_names = {
        column["name"] for column in inspect(engine).get_columns("agent_steps")
    }
    assert {
        "started_at",
        "completed_at",
        "duration_seconds",
    }.issubset(agent_step_column_names)
