"""Persisted replay evaluations with metrics and gate outcomes."""

import sqlalchemy as sa
from alembic import op

revision = "0019_evaluation_runs"
down_revision = "0018_evaluation_sets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False, index=True
        ),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("evaluation_sets.id"), nullable=False),
        sa.Column(
            "candidate_id", sa.String(36), sa.ForeignKey("cluster_candidates.id"), nullable=False
        ),
        sa.Column("overall_passed", sa.Boolean(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("gates", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("evaluation_runs")
