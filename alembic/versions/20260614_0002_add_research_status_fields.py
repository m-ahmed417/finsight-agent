"""Add research safety and quality status fields.

Revision ID: 20260614_0002
Revises: 20260614_0001
Create Date: 2026-06-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260614_0002"
down_revision: str | None = "20260614_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_runs",
        sa.Column("compliance_status", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "research_runs",
        sa.Column("report_quality_status", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("research_runs", "report_quality_status")
    op.drop_column("research_runs", "compliance_status")
