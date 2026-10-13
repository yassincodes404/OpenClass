"""Add dataset_hash, example split/metadata, and evaluation run provenance columns."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_evaluation_holdouts_and_provenance"
down_revision = "0024_decision_run_version_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    set_cols = {c["name"] for c in inspector.get_columns("evaluation_sets")}
    if "dataset_hash" not in set_cols:
        op.add_column(
            "evaluation_sets",
            sa.Column("dataset_hash", sa.String(64), nullable=True),
        )

    ex_cols = {c["name"] for c in inspector.get_columns("evaluation_examples")}
    if "split" not in ex_cols:
        op.add_column(
            "evaluation_examples",
            sa.Column("split", sa.String(20), nullable=True),
        )
    if "example_metadata" not in ex_cols:
        op.add_column(
            "evaluation_examples",
            sa.Column("example_metadata", sa.JSON(), nullable=True),
        )

    run_cols = {c["name"] for c in inspector.get_columns("evaluation_runs")}
    if "is_simulated" not in run_cols:
        op.add_column(
            "evaluation_runs",
            sa.Column("is_simulated", sa.Boolean(), nullable=True),
        )
    if "provider" not in run_cols:
        op.add_column(
            "evaluation_runs",
            sa.Column("provider", sa.String(50), nullable=True),
        )
    if "model" not in run_cols:
        op.add_column(
            "evaluation_runs",
            sa.Column("model", sa.String(100), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    run_cols = {c["name"] for c in inspector.get_columns("evaluation_runs")}
    for col in ("model", "provider", "is_simulated"):
        if col in run_cols:
            op.drop_column("evaluation_runs", col)

    ex_cols = {c["name"] for c in inspector.get_columns("evaluation_examples")}
    for col in ("example_metadata", "split"):
        if col in ex_cols:
            op.drop_column("evaluation_examples", col)

    set_cols = {c["name"] for c in inspector.get_columns("evaluation_sets")}
    if "dataset_hash" in set_cols:
        op.drop_column("evaluation_sets", "dataset_hash")
