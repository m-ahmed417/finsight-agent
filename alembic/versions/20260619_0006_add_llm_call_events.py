"""Add LLM call event audit table.

Revision ID: 20260619_0006
Revises: 20260619_0005
Create Date: 2026-06-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260619_0006"
down_revision: str | None = "20260619_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_call_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("research_run_id", sa.String(length=36), nullable=False),
        sa.Column("node_name", sa.String(length=80), nullable=False),
        sa.Column("task", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("llm_provider", sa.String(length=40), nullable=True),
        sa.Column("llm_model", sa.String(length=120), nullable=True),
        sa.Column("prompt_version", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column("error_type", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), nullable=True),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_llm_call_events_research_run_id"),
        "llm_call_events",
        ["research_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_llm_call_events_research_run_id"),
        table_name="llm_call_events",
    )
    op.drop_table("llm_call_events")
