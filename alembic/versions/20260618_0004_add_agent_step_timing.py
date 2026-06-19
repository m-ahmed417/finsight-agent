"""Add timing fields to agent steps.

Revision ID: 20260618_0004
Revises: 20260617_0003
Create Date: 2026-06-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260618_0004"
down_revision: str | None = "20260617_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_steps",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_steps",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_steps",
        sa.Column("duration_seconds", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_steps", "duration_seconds")
    op.drop_column("agent_steps", "completed_at")
    op.drop_column("agent_steps", "started_at")
