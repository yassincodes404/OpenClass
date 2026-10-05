"""Project-scoped discovery candidates with evidence links (inactive by construction)."""

import sqlalchemy as sa
from alembic import op

revision = "0016_cluster_candidates"
down_revision = "0015_embeddings_clusters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cluster_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False, index=True
        ),
        sa.Column(
            "cluster_id",
            sa.String(36),
            sa.ForeignKey("unknown_clusters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("canonical_name", sa.String(200), nullable=True),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("existing_match", sa.String(200), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "candidate_evidence",
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("cluster_candidates.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("decision_runs.id"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("candidate_evidence")
    op.drop_table("cluster_candidates")
