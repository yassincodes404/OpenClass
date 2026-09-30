"""Project integrations table for MCP, webhooks, REST APIs, and external providers."""

import sqlalchemy as sa
from alembic import op

revision = "0009_integrations"
down_revision = "0008_evolution_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_integrations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("endpoint", sa.String(1000), nullable=True),
        sa.Column("secret_ref", sa.String(200), nullable=True),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("last_health_check", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_project_integrations_project_id",
        "project_integrations",
        ["project_id"],
    )
    op.create_index(
        "ix_project_integrations_type",
        "project_integrations",
        ["type"],
    )
    op.create_index(
        "ix_project_integrations_status",
        "project_integrations",
        ["status"],
    )
    op.create_index(
        "ix_project_integrations_created_at",
        "project_integrations",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_integrations_created_at", table_name="project_integrations")
    op.drop_index("ix_project_integrations_status", table_name="project_integrations")
    op.drop_index("ix_project_integrations_type", table_name="project_integrations")
    op.drop_index("ix_project_integrations_project_id", table_name="project_integrations")
    op.drop_table("project_integrations")
