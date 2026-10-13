"""Routing rules for support integrations (UNKNOWN path is fixed to escalate)."""

import sqlalchemy as sa
from alembic import op

revision = "0022_integration_routes"
down_revision = "0021_alert_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_routes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "integration_id",
            sa.String(36),
            sa.ForeignKey("project_integrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("match_choice", sa.String(100), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("action_value", sa.String(200), nullable=False, default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "routing_outcomes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False, index=True
        ),
        sa.Column("integration_id", sa.String(36), nullable=False),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("raw_events.id"), nullable=False),
        sa.Column("selected_choice", sa.String(100), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("routing_outcomes")
    op.drop_table("integration_routes")
