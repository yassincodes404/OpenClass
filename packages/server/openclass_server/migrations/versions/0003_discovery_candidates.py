"""Experimental discovery candidates and evidence snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0003_discovery_candidates"
down_revision = "0002_supervisor_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("classifier_id", sa.String(36), sa.ForeignKey("classifiers.id"), nullable=False),
        sa.Column(
            "base_ontology_version_id",
            sa.String(36),
            sa.ForeignKey("ontology_versions.id"),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_candidates_classifier_id", "candidates", ["classifier_id"])


def downgrade() -> None:
    op.drop_table("candidates")
