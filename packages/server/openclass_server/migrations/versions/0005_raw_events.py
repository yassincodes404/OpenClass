"""Raw events: immutable source observations persisted before semantic processing."""

import sqlalchemy as sa
from alembic import op

revision = "0005_raw_events"
down_revision = "0004_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_raw_events_project_id", "raw_events", ["project_id"])
    op.create_index("ix_raw_events_created_at", "raw_events", ["created_at"])
    op.create_index("ix_raw_events_source_type", "raw_events", ["source_type"])


def downgrade() -> None:
    op.drop_index("ix_raw_events_source_type", table_name="raw_events")
    op.drop_index("ix_raw_events_created_at", table_name="raw_events")
    op.drop_index("ix_raw_events_project_id", table_name="raw_events")
    op.drop_table("raw_events")
