"""Embeddings and UNKNOWN clusters with provenance.

Vectors are stored as JSON in both dialects for this phase: grouping runs an
exact cosine pass in Python (fine at current scale, per phase plan). A pgvector
ANN index is introduced only when scale demands it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_embeddings_clusters"
down_revision = "0014_unknown_triage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "embeddings",
        sa.Column("run_id", sa.String(36), sa.ForeignKey("decision_runs.id"), primary_key=True),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "unknown_clusters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False, index=True
        ),
        sa.Column("algorithm", sa.String(50), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "cluster_members",
        sa.Column(
            "cluster_id",
            sa.String(36),
            sa.ForeignKey("unknown_clusters.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("decision_runs.id"), primary_key=True),
        sa.Column("similarity", sa.Float(), nullable=False, default=0.0),
    )


def downgrade() -> None:
    op.drop_table("cluster_members")
    op.drop_table("unknown_clusters")
    op.drop_table("embeddings")
