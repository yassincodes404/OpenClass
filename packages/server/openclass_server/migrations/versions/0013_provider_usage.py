"""Daily provider usage rollups (calls, tokens, cost, latency, errors)."""

import sqlalchemy as sa
from alembic import op

revision = "0013_provider_usage"
down_revision = "0012_raw_event_content_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(200), nullable=False, default=""),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False, default=0),
        sa.Column("errors", sa.Integer(), nullable=False, default=0),
        sa.Column("input_tokens", sa.Integer(), nullable=False, default=0),
        sa.Column("output_tokens", sa.Integer(), nullable=False, default=0),
        sa.Column("estimated_cost", sa.Float(), nullable=False, default=0.0),
        sa.Column("latency_ms_total", sa.Float(), nullable=False, default=0.0),
    )
    op.create_index("ix_provider_usage_project_id", "provider_usage", ["project_id"])
    op.create_index(
        "uq_provider_usage_day",
        "provider_usage",
        ["project_id", "provider", "usage_date"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_provider_usage_day", table_name="provider_usage")
    op.drop_index("ix_provider_usage_project_id", table_name="provider_usage")
    op.drop_table("provider_usage")
