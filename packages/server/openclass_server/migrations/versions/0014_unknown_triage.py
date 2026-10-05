"""Triage state for the UNKNOWN workspace (runs stay immutable)."""

import sqlalchemy as sa
from alembic import op

revision = "0014_unknown_triage"
down_revision = "0013_provider_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "unknown_triage",
        sa.Column("run_id", sa.String(36), sa.ForeignKey("decision_runs.id"), primary_key=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("category", sa.String(30), nullable=True),
        sa.Column("assignee", sa.String(200), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_unknown_triage_status", "unknown_triage", ["status"])


def downgrade() -> None:
    op.drop_index("ix_unknown_triage_status", table_name="unknown_triage")
    op.drop_table("unknown_triage")
