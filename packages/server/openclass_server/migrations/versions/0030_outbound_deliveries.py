"""Durable integration delivery; additive upgrade, never recreate history."""

import sqlalchemy as sa
from alembic import op

revision = "0030_outbound_deliveries"
down_revision = "0029_engine_persistence_contracts"
branch_labels = None
depends_on = None


def _immutable(table: str, create: bool) -> None:
    if op.get_bind().dialect.name == "postgresql":
        if create:
            op.execute(
                f"CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION openclass_immutable()"
            )
        else:
            op.execute(f"DROP TRIGGER immutable_history ON {table}")
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


def upgrade() -> None:
    for name in ("signature", "outbound"):
        op.add_column(
            "project_integrations", sa.Column(name, sa.JSON(), nullable=False, server_default="{}")
        )
    op.create_table(
        "outbound_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("integration_id", sa.String(36), nullable=False),
        sa.Column(
            "outcome_id",
            sa.String(36),
            sa.ForeignKey("routing_outcomes.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("idempotency_key", sa.String(300), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("intent", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("had_ambiguous_attempt", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claim_token", sa.String(36), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_outbound_identity"),
    )
    op.create_index("ix_outbound_due", "outbound_deliveries", ["state", "next_attempt_at"])
    op.create_table(
        "outbound_delivery_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "delivery_id", sa.String(36), sa.ForeignKey("outbound_deliveries.id"), nullable=False
        ),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    _immutable("outbound_delivery_history", True)
    _immutable("routing_outcomes", True)
    # Bind effect identity permanently while allowing fenced state transitions.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE FUNCTION openclass_outbound_identity() RETURNS trigger AS $$ BEGIN "
            "IF TG_OP = 'DELETE' OR ROW(OLD.id, OLD.project_id, OLD.integration_id, "
            "OLD.outcome_id, "
            "OLD.idempotency_key, OLD.request_hash, OLD.intent::text, OLD.created_at) "
            "IS DISTINCT FROM "
            "ROW(NEW.id, NEW.project_id, NEW.integration_id, NEW.outcome_id, NEW.idempotency_key, "
            "NEW.request_hash, NEW.intent::text, NEW.created_at) THEN "
            "RAISE EXCEPTION 'Outbound identity is immutable'; END IF; "
            "RETURN NEW; END; $$ LANGUAGE plpgsql"
        )
        op.execute(
            "CREATE TRIGGER immutable_identity BEFORE UPDATE OR DELETE ON outbound_deliveries "
            "FOR EACH ROW EXECUTE FUNCTION openclass_outbound_identity()"
        )
    else:
        op.execute(
            "CREATE TRIGGER outbound_identity_update BEFORE UPDATE OF id, project_id, "
            "integration_id, "
            "outcome_id, idempotency_key, request_hash, intent, created_at ON outbound_deliveries "
            "BEGIN SELECT RAISE(ABORT, 'Outbound identity is immutable'); END"
        )
        op.execute(
            "CREATE TRIGGER outbound_identity_delete BEFORE DELETE ON outbound_deliveries "
            "BEGIN SELECT RAISE(ABORT, 'Outbound history is append-only'); END"
        )


def downgrade() -> None:
    # Losing queued effects, receipts or signature configuration is not a safe
    # rollback. Fail BEFORE any DDL. Restore a reviewed backup for populated DBs.
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM outbound_deliveries LIMIT 1")).first():
        raise RuntimeError(
            "0030 downgrade requires empty outbound history; preserve a reviewed backup"
        )
    for signature, outbound in bind.execute(
        sa.text("SELECT signature, outbound FROM project_integrations")
    ):
        import json

        sig = json.loads(signature) if isinstance(signature, str) else signature
        policy = json.loads(outbound) if isinstance(outbound, str) else outbound
        signature_defaults = {"mode": "bearer", "replay_window_seconds": 300}
        outbound_defaults = {"enabled": False, "receiver_enforces_idempotency": False}
        if (
            not isinstance(sig, dict)
            or not isinstance(policy, dict)
            or any(
                key not in signature_defaults or value != signature_defaults[key]
                for key, value in sig.items()
            )
            or any(
                key not in outbound_defaults or value != outbound_defaults[key]
                for key, value in policy.items()
            )
        ):
            raise RuntimeError("0030 downgrade would lose active signature/delivery configuration")
    _immutable("routing_outcomes", False)
    op.drop_table("outbound_delivery_history")
    op.drop_table("outbound_deliveries")
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION openclass_outbound_identity()")
    op.drop_column("project_integrations", "outbound")
    op.drop_column("project_integrations", "signature")
