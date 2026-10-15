"""Add workspace_id to projects and claim fields to decision_run_checkpoints."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027_workspace_isolation_and_checkpoint_claims"
down_revision = "0026_decision_run_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "projects" in tables:
        project_cols = {col["name"] for col in inspector.get_columns("projects")}
        if "workspace_id" not in project_cols:
            op.add_column("projects", sa.Column("workspace_id", sa.String(120), nullable=True))
        project_indexes = {idx["name"] for idx in inspector.get_indexes("projects")}
        if "ix_projects_workspace_id" not in project_indexes:
            op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])

    if "decision_run_checkpoints" in tables:
        cp_cols = {col["name"] for col in inspector.get_columns("decision_run_checkpoints")}
        if "claim_token" not in cp_cols:
            op.add_column(
                "decision_run_checkpoints",
                sa.Column("claim_token", sa.String(120), nullable=True),
            )
        if "claimed_by" not in cp_cols:
            op.add_column(
                "decision_run_checkpoints",
                sa.Column("claimed_by", sa.String(200), nullable=True),
            )
        if "claimed_at" not in cp_cols:
            op.add_column(
                "decision_run_checkpoints",
                sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "decision_run_checkpoints" in tables:
        cp_cols = {col["name"] for col in inspector.get_columns("decision_run_checkpoints")}
        with op.batch_alter_table("decision_run_checkpoints") as batch_op:
            if "claimed_at" in cp_cols:
                batch_op.drop_column("claimed_at")
            if "claimed_by" in cp_cols:
                batch_op.drop_column("claimed_by")
            if "claim_token" in cp_cols:
                batch_op.drop_column("claim_token")

    if "projects" in tables:
        project_indexes = {idx["name"] for idx in inspector.get_indexes("projects")}
        if "ix_projects_workspace_id" in project_indexes:
            op.drop_index("ix_projects_workspace_id", table_name="projects")
        project_cols = {col["name"] for col in inspector.get_columns("projects")}
        if "workspace_id" in project_cols:
            with op.batch_alter_table("projects") as batch_op:
                batch_op.drop_column("workspace_id")
