from collections.abc import Iterator

from sqlalchemy import inspect, text
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from finsight_agent.app.config import get_settings
from finsight_agent.app.db.models import Base


def _connect_args(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


settings = get_settings()
engine = create_engine(
    settings.database_url,
    connect_args=_connect_args(settings.database_url),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_research_run_columns()


def get_db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _ensure_sqlite_research_run_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    existing_columns = {
        column["name"]
        for column in inspect(engine).get_columns("research_runs")
    }
    column_definitions = {
        "compliance_status": "VARCHAR(30)",
        "report_quality_status": "VARCHAR(30)",
        "filing_text_excerpt": "TEXT",
        "risk_factors_json": "JSON NOT NULL DEFAULT '[]'",
        "risk_themes_json": "JSON NOT NULL DEFAULT '[]'",
        "research_insights_json": "JSON",
    }
    with engine.begin() as connection:
        for column_name, column_definition in column_definitions.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE research_runs ADD COLUMN {column_name} {column_definition}"
                    )
                )
