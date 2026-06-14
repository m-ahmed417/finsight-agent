from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_alembic_configuration_points_to_project_migrations() -> None:
    config = make_alembic_config("sqlite:///unused.db")

    assert config.get_main_option("script_location").endswith("alembic")
    assert (PROJECT_ROOT / "alembic" / "env.py").exists()
    assert (PROJECT_ROOT / "alembic" / "versions").exists()


def test_initial_migration_creates_research_tables(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration_test.db'}"
    config = make_alembic_config(database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) >= {
        "alembic_version",
        "research_runs",
        "agent_steps",
    }
    research_run_columns = {
        column["name"] for column in inspector.get_columns("research_runs")
    }
    assert {
        "id",
        "query",
        "ticker",
        "company_name",
        "status",
        "final_report",
        "financial_metrics_json",
        "filing_text_excerpt",
        "risk_factors_json",
        "risk_themes_json",
        "research_insights_json",
        "warnings_json",
        "errors_json",
        "sources_json",
        "created_at",
        "completed_at",
    }.issubset(research_run_columns)

    agent_step_columns = {column["name"] for column in inspector.get_columns("agent_steps")}
    assert {
        "id",
        "research_run_id",
        "node_name",
        "status",
        "message",
        "error_message",
        "created_at",
    }.issubset(agent_step_columns)
