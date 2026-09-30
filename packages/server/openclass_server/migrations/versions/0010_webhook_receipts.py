"""Atomic webhook deduplication and append-only source/audit history."""

import sqlalchemy as sa
from alembic import op

revision = "0010_webhook_receipts"
down_revision = "0009_integrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_receipts",
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("integration_id", sa.String(36), primary_key=True),
        sa.Column("event_key", sa.String(200), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "event_id", sa.String(36), sa.ForeignKey("raw_events.id"), nullable=False, unique=True
        ),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for table in ("webhook_receipts", "raw_events", "audit_events"):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(
                f"CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION openclass_immutable()"
            )
        else:
            for operation in ("UPDATE", "DELETE"):
                op.execute(
                    f"CREATE TRIGGER immutable_{table}_{operation.lower()} "
                    f"BEFORE {operation} ON {table} BEGIN "
                    "SELECT RAISE(ABORT, 'OpenClass history is append-only'); END"
                )


def downgrade() -> None:
    for table in ("webhook_receipts", "raw_events", "audit_events"):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"DROP TRIGGER immutable_history ON {table}")
        else:
            for operation in ("update", "delete"):
                op.execute(f"DROP TRIGGER immutable_{table}_{operation}")
    op.drop_table("webhook_receipts")
