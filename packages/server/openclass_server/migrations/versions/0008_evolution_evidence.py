"""Evolution inbox, evidence items, evidence cases, and run feedback."""

import sqlalchemy as sa
from alembic import op

revision = "0008_evolution_evidence"
down_revision = "0007_project_choice_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "decision_service_id",
            sa.String(36),
            sa.ForeignKey("decision_services.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("diagnosis", sa.String(50), nullable=True),
        sa.Column("diagnosis_rationale", sa.Text(), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_evidence_cases_project_id", "evidence_cases", ["project_id"])
    op.create_index("ix_evidence_cases_status", "evidence_cases", ["status"])

    op.create_table(
        "evidence_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "raw_event_id",
            sa.String(36),
            sa.ForeignKey("raw_events.id"),
            nullable=True,
        ),
        sa.Column(
            "decision_run_id",
            sa.String(36),
            sa.ForeignKey("decision_runs.id"),
            nullable=True,
        ),
        sa.Column(
            "decision_service_id",
            sa.String(36),
            sa.ForeignKey("decision_services.id"),
            nullable=True,
        ),
        sa.Column(
            "evidence_case_id",
            sa.String(36),
            sa.ForeignKey("evidence_cases.id"),
            nullable=True,
        ),
        sa.Column("trigger_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("diagnosis", sa.String(50), nullable=True),
        sa.Column("diagnosis_rationale", sa.Text(), nullable=True),
        sa.Column("selected_choice", sa.String(100), nullable=True),
        sa.Column("supervision_outcome", sa.String(20), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_evidence_items_project_id", "evidence_items", ["project_id"])
    op.create_index("ix_evidence_items_decision_run_id", "evidence_items", ["decision_run_id"])
    op.create_index("ix_evidence_items_evidence_case_id", "evidence_items", ["evidence_case_id"])
    op.create_index("ix_evidence_items_trigger_type", "evidence_items", ["trigger_type"])
    op.create_index("ix_evidence_items_status", "evidence_items", ["status"])
    op.create_index("ix_evidence_items_created_at", "evidence_items", ["created_at"])

    op.create_table(
        "run_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "decision_run_id",
            sa.String(36),
            sa.ForeignKey("decision_runs.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("corrected_choice", sa.String(100), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_run_feedback_project_id", "run_feedback", ["project_id"])
    op.create_index("ix_run_feedback_decision_run_id", "run_feedback", ["decision_run_id"])


def downgrade() -> None:
    op.drop_index("ix_run_feedback_decision_run_id", table_name="run_feedback")
    op.drop_index("ix_run_feedback_project_id", table_name="run_feedback")
    op.drop_table("run_feedback")

    op.drop_index("ix_evidence_items_created_at", table_name="evidence_items")
    op.drop_index("ix_evidence_items_status", table_name="evidence_items")
    op.drop_index("ix_evidence_items_trigger_type", table_name="evidence_items")
    op.drop_index("ix_evidence_items_evidence_case_id", table_name="evidence_items")
    op.drop_index("ix_evidence_items_decision_run_id", table_name="evidence_items")
    op.drop_index("ix_evidence_items_project_id", table_name="evidence_items")
    op.drop_table("evidence_items")

    op.drop_index("ix_evidence_cases_status", table_name="evidence_cases")
    op.drop_index("ix_evidence_cases_project_id", table_name="evidence_cases")
    op.drop_table("evidence_cases")
