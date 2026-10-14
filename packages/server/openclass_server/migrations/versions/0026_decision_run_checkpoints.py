"""Add decision_run_checkpoints table for durable multi-node graph pause and resume."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_decision_run_checkpoints"
down_revision = "0025_evaluation_holdouts_and_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "decision_run_checkpoints" not in tables:
        op.create_table(
            "decision_run_checkpoints",
            sa.Column(
                "run_id",
                sa.String(36),
                sa.ForeignKey("decision_runs.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("project_id", sa.String(36), nullable=False),
            sa.Column("decision_service_id", sa.String(36), nullable=False),
            sa.Column(
                "run_status",
                sa.String(32),
                nullable=False,
                server_default="completed",
            ),
            sa.Column("current_node_key", sa.String(200), nullable=True),
            sa.Column("next_node_key", sa.String(200), nullable=True),
            sa.Column("selected_choice", sa.String(120), nullable=False),
            sa.Column("supervision_outcome", sa.String(32), nullable=False),
            sa.Column("supervision_reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("completed_steps", sa.JSON(), nullable=False),
            sa.Column("state_snapshot", sa.JSON(), nullable=False),
            sa.Column("pinned_version_id", sa.String(36), nullable=True),
            sa.Column(
                "pinned_version_number",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
            sa.Column("pinned_service_hash", sa.String(64), nullable=True),
            sa.Column("pending_operation", sa.JSON(), nullable=True),
            sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("resumed_by", sa.String(200), nullable=True),
            sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resume_rationale", sa.Text(), nullable=True),
            sa.Column("cancelled_by", sa.String(200), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancel_reason", sa.Text(), nullable=True),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_decision_run_checkpoints_project_id",
            "decision_run_checkpoints",
            ["project_id"],
        )
        op.create_index(
            "ix_decision_run_checkpoints_decision_service_id",
            "decision_run_checkpoints",
            ["decision_service_id"],
        )
        op.create_index(
            "ix_decision_run_checkpoints_run_status",
            "decision_run_checkpoints",
            ["run_status"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "decision_run_checkpoints" in tables:
        existing_indexes = {
            idx["name"] for idx in inspector.get_indexes("decision_run_checkpoints")
        }
        for idx_name in (
            "ix_decision_run_checkpoints_run_status",
            "ix_decision_run_checkpoints_decision_service_id",
            "ix_decision_run_checkpoints_project_id",
        ):
            if idx_name in existing_indexes:
                op.drop_index(idx_name, table_name="decision_run_checkpoints")
        op.drop_table("decision_run_checkpoints")
