"""Inactive project choice candidates with evidence and base service identity."""

import sqlalchemy as sa
from alembic import op

revision = "0007_project_choice_candidates"
down_revision = "0006_decision_services_and_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_choice_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "decision_service_id",
            sa.String(36),
            sa.ForeignKey("decision_services.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_project_choice_candidates_project_id", "project_choice_candidates", ["project_id"]
    )
    op.create_index(
        "ix_project_choice_candidates_decision_service_id",
        "project_choice_candidates",
        ["decision_service_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_choice_candidates_decision_service_id", table_name="project_choice_candidates"
    )
    op.drop_index("ix_project_choice_candidates_project_id", table_name="project_choice_candidates")
    op.drop_table("project_choice_candidates")
