"""Decision services and decision runs: first-class decision configurations and
immutable execution records.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_decision_services_and_runs"
down_revision = "0005_raw_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_services",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("project_id", "slug", name="uq_decision_services_project_id_slug"),
    )
    op.create_index("ix_decision_services_project_id", "decision_services", ["project_id"])
    op.create_index("ix_decision_services_created_at", "decision_services", ["created_at"])

    op.create_table(
        "decision_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "raw_event_id",
            sa.String(36),
            sa.ForeignKey("raw_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "decision_service_id",
            sa.String(36),
            sa.ForeignKey("decision_services.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision_node_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("execution_mode", sa.String(50), nullable=False),
        sa.Column("real_inference", sa.Boolean(), nullable=False),
        sa.Column("selected_choice", sa.String(100), nullable=False),
        sa.Column("supervision_outcome", sa.String(20), nullable=False),
        sa.Column("top_probability", sa.Float(), nullable=False),
        sa.Column("margin", sa.Float(), nullable=False),
        sa.Column("unknown_probability", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_decision_runs_project_id", "decision_runs", ["project_id"])
    op.create_index("ix_decision_runs_created_at", "decision_runs", ["created_at"])
    op.create_index("ix_decision_runs_raw_event_id", "decision_runs", ["raw_event_id"])
    op.create_index(
        "ix_decision_runs_decision_service_id", "decision_runs", ["decision_service_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_decision_runs_decision_service_id", table_name="decision_runs")
    op.drop_index("ix_decision_runs_raw_event_id", table_name="decision_runs")
    op.drop_index("ix_decision_runs_created_at", table_name="decision_runs")
    op.drop_index("ix_decision_runs_project_id", table_name="decision_runs")
    op.drop_table("decision_runs")

    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(
            "uq_decision_services_project_id_slug", "decision_services", type_="unique"
        )
    op.drop_index("ix_decision_services_created_at", table_name="decision_services")
    op.drop_index("ix_decision_services_project_id", table_name="decision_services")
    op.drop_table("decision_services")
