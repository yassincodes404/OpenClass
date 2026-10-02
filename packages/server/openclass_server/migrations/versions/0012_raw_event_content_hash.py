"""Content-hash dedup identity for raw events.

raw_events is append-only (trigger from 0010), so the backfill temporarily
drops the immutability trigger and reinstates it after filling content_hash.
A unique index (instead of a constraint) keeps this portable across
PostgreSQL and SQLite.
"""

from hashlib import sha256

import sqlalchemy as sa
from alembic import op

revision = "0012_raw_event_content_hash"
down_revision = "0011_idempotency_keys"
branch_labels = None
depends_on = None


def _drop_immutable(bind: sa.Connection) -> None:
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("DROP TRIGGER IF EXISTS immutable_history ON raw_events"))
    else:
        bind.execute(sa.text("DROP TRIGGER IF EXISTS immutable_raw_events_update"))


def _restore_immutable(bind: sa.Connection) -> None:
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text(
                "CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON raw_events "
                "FOR EACH ROW EXECUTE FUNCTION openclass_immutable()"
            )
        )
    else:
        bind.execute(
            sa.text(
                "CREATE TRIGGER immutable_raw_events_update BEFORE UPDATE ON raw_events "
                "BEGIN SELECT RAISE(ABORT, 'OpenClass history is append-only'); END"
            )
        )


def upgrade() -> None:
    op.add_column("raw_events", sa.Column("content_hash", sa.String(64), nullable=True))
    bind = op.get_bind()
    _drop_immutable(bind)
    rows = bind.execute(sa.text("SELECT id, content FROM raw_events")).fetchall()
    for row_id, content in rows:
        digest = sha256((content or "").strip().encode()).hexdigest()
        bind.execute(
            sa.text("UPDATE raw_events SET content_hash = :h WHERE id = :id"),
            {"h": digest, "id": row_id},
        )
    _restore_immutable(bind)
    op.create_index(
        "uq_raw_events_content", "raw_events", ["project_id", "content_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_raw_events_content", table_name="raw_events")
    op.drop_column("raw_events", "content_hash")
