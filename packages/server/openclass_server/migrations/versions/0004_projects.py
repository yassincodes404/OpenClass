"""Projects: persistent workspaces with an append-only audit trail."""

import sqlalchemy as sa
from alembic import op

revision = "0004_projects"
down_revision = "0003_discovery_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("owner_id", sa.String(80), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_project_id", "audit_events", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_project_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_projects_owner_id", table_name="projects")
    op.drop_table("projects")
