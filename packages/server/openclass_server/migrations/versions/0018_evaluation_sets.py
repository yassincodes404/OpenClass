"""Verified evaluation datasets and examples (immutable after seal)."""

import sqlalchemy as sa
from alembic import op

revision = "0018_evaluation_sets"
down_revision = "0017_candidate_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False, index=True
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, default=""),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "evaluation_examples",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("evaluation_sets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("annotator", sa.String(200), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, default=""),
        sa.Column("slice_tag", sa.String(30), nullable=False, default="historical"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("evaluation_examples")
    op.drop_table("evaluation_sets")
