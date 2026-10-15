"""Atomic evidence identity, request identity and non-destructive history.

Legacy duplicate evidence is intentionally an operator-visible upgrade blocker.
No row is deleted, detached, relabeled or chosen as an arbitrary winner.
"""

import sqlalchemy as sa
from alembic import op

revision = "0029_engine_persistence_contracts"
down_revision = "0028_checkpoint_revision_and_lease_fencing"
branch_labels = None
depends_on = None

HISTORY = ("observations", "classification_runs", "unknown_events", "decision_runs", "run_feedback")
REFERENCES = ("raw_events", "decision_services", "decision_runs", "service_versions")
CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}


def _immutable(table: str, *, create: bool, postgres_name: str = "immutable_history") -> None:
    if op.get_bind().dialect.name == "postgresql":
        if create:
            op.execute(
                f"CREATE TRIGGER {postgres_name} BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION openclass_immutable()"
            )
        else:
            op.execute(f"DROP TRIGGER {postgres_name} ON {table}")
    else:
        for action in ("update", "delete"):
            name = f"immutable_{table}_{action}"
            if create:
                op.execute(
                    f"CREATE TRIGGER {name} BEFORE {action.upper()} ON {table} BEGIN "
                    "SELECT RAISE(ABORT, 'OpenClass history is append-only'); END"
                )
            else:
                op.execute(f"DROP TRIGGER {name}")


def _references(ondelete: str) -> None:
    for table in REFERENCES:
        foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys(table)
        with op.batch_alter_table(table, naming_convention=CONVENTION) as batch:
            for fk in foreign_keys:
                # Only these references had destructive cascades in 0028.
                if (fk.get("options") or {}).get("ondelete", "").upper() not in {
                    "CASCADE",
                    "RESTRICT",
                }:
                    continue
                columns = fk["constrained_columns"]
                name = fk["name"] or f"fk_{table}_{columns[0]}_{fk['referred_table']}"
                batch.drop_constraint(name, type_="foreignkey")
                batch.create_foreign_key(
                    name, fk["referred_table"], columns, fk["referred_columns"], ondelete=ondelete
                )


def upgrade() -> None:
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT decision_run_id, COUNT(*) FROM evidence_items "
                "WHERE decision_run_id IS NOT NULL GROUP BY decision_run_id HAVING COUNT(*) > 1 "
                "LIMIT 1"
            )
        )
        .first()
    )
    if duplicates is not None:
        raise RuntimeError(
            "0029 blocked: duplicate decision_run_id evidence exists. Preserve a backup; "
            "obtain an explicit reviewed reconciliation of evidence and case/audit references "
            "before retrying. No historical rows have been silently removed."
        )
    op.add_column("idempotency_keys", sa.Column("request_hash", sa.String(64), nullable=True))
    op.create_index(
        "uq_evidence_items_decision_run", "evidence_items", ["decision_run_id"], unique=True
    )
    op.drop_index("uq_provider_usage_day", table_name="provider_usage")
    # Preserve aggregate values exactly. Earlier releases may have combined
    # multiple models under one row; their attribution cannot be reconstructed.
    # Keep their recorded model rather than inventing a historical split.
    op.create_index(
        "uq_provider_usage_day",
        "provider_usage",
        ["project_id", "provider", "model", "usage_date"],
        unique=True,
    )
    _immutable("webhook_receipts", create=False)
    constraints = sa.inspect(op.get_bind()).get_unique_constraints("webhook_receipts")
    with op.batch_alter_table("webhook_receipts", naming_convention=CONVENTION) as batch:
        for constraint in constraints:
            if constraint["column_names"] == ["event_id"]:
                batch.drop_constraint(
                    constraint["name"] or "uq_webhook_receipts_event_id", type_="unique"
                )
    _immutable("webhook_receipts", create=True)
    _immutable("raw_events", create=False)
    _immutable("service_versions", create=False, postgres_name="immutable_service_versions")
    _references("RESTRICT")
    _immutable("raw_events", create=True)
    _immutable("service_versions", create=True, postgres_name="immutable_service_versions")
    for table in HISTORY:
        _immutable(table, create=True)


def downgrade() -> None:
    # Empty-schema round trips are useful for migration verification. Once
    # affected history exists, removing identity/protections may be lossy:
    # refuse before DDL rather than merge or erase operator data.
    protected = (
        *HISTORY,
        *REFERENCES,
        "webhook_receipts",
        "evidence_items",
        "provider_usage",
        "idempotency_keys",
    )
    for table in dict.fromkeys(protected):
        if op.get_bind().execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError(
                "0029 downgrade requires empty affected history; "
                "restore a reviewed pre-upgrade backup for populated databases"
            )
    for table in HISTORY:
        _immutable(table, create=False)
    _immutable("raw_events", create=False)
    _immutable("service_versions", create=False, postgres_name="immutable_service_versions")
    _references("CASCADE")
    _immutable("raw_events", create=True)
    _immutable("service_versions", create=True, postgres_name="immutable_service_versions")
    _immutable("webhook_receipts", create=False)
    with op.batch_alter_table("webhook_receipts") as batch:
        batch.create_unique_constraint("uq_webhook_receipts_event_id", ["event_id"])
    _immutable("webhook_receipts", create=True)
    op.drop_index("uq_provider_usage_day", table_name="provider_usage")
    op.create_index(
        "uq_provider_usage_day",
        "provider_usage",
        ["project_id", "provider", "usage_date"],
        unique=True,
    )
    op.drop_index("uq_evidence_items_decision_run", table_name="evidence_items")
    op.drop_column("idempotency_keys", "request_hash")
