"""Append-only candidate reviews (human decisions with rationale)."""

import sqlalchemy as sa
from alembic import op

revision = "0017_candidate_reviews"
down_revision = "0016_cluster_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("cluster_candidates.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("reviewer", sa.String(200), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Status values widened to the full lifecycle enum (plain varchar; the
    # application state machine is the authority, transitions are event-logged).
    # The column is already unconstrained varchar, so only Postgres needs a widen.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE cluster_candidates ALTER COLUMN status TYPE varchar(30)")


def downgrade() -> None:
    op.drop_table("candidate_reviews")
