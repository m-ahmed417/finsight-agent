"""Add retry lineage to research runs.

Revision ID: 20260617_0003
Revises: 20260614_0002
Create Date: 2026-06-17
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260617_0003"
down_revision: str | None = "20260614_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_runs",
        sa.Column("retried_from_run_id", sa.String(length=36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("research_runs", "retried_from_run_id")
