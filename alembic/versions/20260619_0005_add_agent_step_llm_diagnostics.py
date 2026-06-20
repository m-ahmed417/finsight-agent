"""Add LLM diagnostics to agent steps.

Revision ID: 20260619_0005
Revises: 20260618_0004
Create Date: 2026-06-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260619_0005"
down_revision: str | None = "20260618_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_steps",
        sa.Column("llm_provider", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "agent_steps",
        sa.Column("llm_model", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "agent_steps",
        sa.Column("llm_used", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "agent_steps",
        sa.Column("llm_fallback_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_steps", "llm_fallback_reason")
    op.drop_column("agent_steps", "llm_used")
    op.drop_column("agent_steps", "llm_model")
    op.drop_column("agent_steps", "llm_provider")
