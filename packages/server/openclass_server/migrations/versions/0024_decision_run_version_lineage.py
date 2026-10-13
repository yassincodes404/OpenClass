"""Add decision_service_version_id and service_hash lineage columns to decision_runs."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_decision_run_version_lineage"
down_revision = "0023_preserve_cluster_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    run_cols = {c["name"] for c in inspector.get_columns("decision_runs")}
    if "decision_service_version_id" not in run_cols:
        op.add_column(
            "decision_runs",
            sa.Column("decision_service_version_id", sa.String(36), nullable=True),
        )
    if "service_hash" not in run_cols:
        op.add_column(
            "decision_runs",
            sa.Column("service_hash", sa.String(64), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    run_cols = {c["name"] for c in inspector.get_columns("decision_runs")}
    if "service_hash" in run_cols:
        op.drop_column("decision_runs", "service_hash")
    if "decision_service_version_id" in run_cols:
        op.drop_column("decision_runs", "decision_service_version_id")
