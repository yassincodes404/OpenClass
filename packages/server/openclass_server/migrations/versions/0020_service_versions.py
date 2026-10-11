"""Immutable decision-service ontology versions + promotion events."""

import sqlalchemy as sa
from alembic import op

revision = "0020_service_versions"
down_revision = "0019_evaluation_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "service_id",
            sa.String(36),
            sa.ForeignKey("decision_services.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.String(36), nullable=True),
        sa.Column("choices", sa.JSON(), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, default=""),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("service_id", "version_number"),
    )
    op.create_table(
        "service_ontology_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False, index=True
        ),
        sa.Column("service_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("from_version", sa.Integer(), nullable=True),
        sa.Column("to_version", sa.Integer(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # History is append-only: reject UPDATE/DELETE on versions and events.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("service_versions", "service_ontology_events"):
            op.execute(
                f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION openclass_immutable()"
            )
    else:
        for table in ("service_versions", "service_ontology_events"):
            for operation in ("update", "delete"):
                op.execute(
                    f"CREATE TRIGGER immutable_{table}_{operation} "
                    f"BEFORE {operation} ON {table} BEGIN "
                    "SELECT RAISE(ABORT, 'OpenClass history is append-only'); END"
                )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("service_versions", "service_ontology_events"):
            op.execute(f"DROP TRIGGER immutable_{table} ON {table}")
    else:
        for table in ("service_versions", "service_ontology_events"):
            for operation in ("update", "delete"):
                op.execute(f"DROP TRIGGER immutable_{table}_{operation}")
    op.drop_table("service_ontology_events")
    op.drop_table("service_versions")
