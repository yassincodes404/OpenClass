"""Transactional routing intent and fenced delivery lifecycle.

No external calls occur inside a transaction. A sending lease expiry is NOT
evidence of remote failure. Immutable intent/history retain every transition.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from openclass_core.integrations import IntegrationStatus, IntegrationType
from openclass_core.outbound import (
    AuthoritativeReceipt,
    DeliveryClaim,
    OutboundIntent,
    OutboundPolicy,
    SendResult,
)
from openclass_core.projects import ProjectAuditEvent
from openclass_core.repositories import ConflictError
from openclass_core.routing import RouteOutcome
from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from .mappers import audit_event_row
from .tables import (
    OutboundDeliveryRow,
    OutboundHistoryRow,
    ProjectIntegrationRow,
    ProjectRow,
    RoutingOutcomeRow,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class OutboundStore:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        max_attempts: int = 3,
        lease_seconds: int = 60,
    ) -> None:
        self.sessions = sessions
        self.max_attempts = max_attempts
        self.lease_seconds = lease_seconds

    @staticmethod
    def _history(
        session: AsyncSession, row: OutboundDeliveryRow, state: str, code: str, now: datetime
    ) -> None:
        session.add(
            OutboundHistoryRow(
                id=str(uuid4()),
                delivery_id=row.id,
                state=state,
                attempt=row.attempts,
                code=code,
                created_at=now,
            )
        )
        session.add(
            audit_event_row(
                ProjectAuditEvent(
                    project_id=UUID(row.project_id),
                    actor="outbound-dispatcher",
                    event_type="integration.updated",
                    payload={
                        "delivery_event": f"integration.delivery_{state}",
                        "delivery_id": row.id,
                        "attempt": row.attempts,
                        "code": code,
                        "had_ambiguous_attempt": row.had_ambiguous_attempt,
                    },
                )
            )
        )

    async def record_outcome(
        self,
        *,
        project_id: UUID,
        integration_id: str,
        event_id: str,
        outcome: RouteOutcome,
        allow_external: bool = False,
    ) -> tuple[dict[str, str], bool]:
        row_id = str(
            uuid5(NAMESPACE_URL, f"openclass:route_outcome:{project_id}:{outcome.idempotency_key}")
        )
        request = {
            "project_id": str(project_id),
            "integration_id": integration_id,
            "event_id": event_id,
            "outcome": outcome.model_dump(mode="json"),
        }
        request_hash = hashlib.sha256(
            json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        async def replay(
            session: AsyncSession, existing: RoutingOutcomeRow
        ) -> tuple[dict[str, str], bool]:
            detail = dict(existing.detail)
            # A legacy NULL/missing hash is not proof of identical intent. Never
            # upgrade a simulated historical outcome into execution authority.
            if detail.get("request_hash") != request_hash:
                raise ConflictError(
                    "Routing identity was already used with different or legacy content"
                )
            delivery = await session.scalar(
                select(OutboundDeliveryRow).where(OutboundDeliveryRow.outcome_id == row_id)
            )
            if delivery:
                detail["delivery_state"] = delivery.state
            return detail, True

        try:
            async with self.sessions.begin() as session:
                project = await session.scalar(
                    select(ProjectRow).where(ProjectRow.id == str(project_id)).with_for_update()
                )
                existing = await session.get(RoutingOutcomeRow, row_id)
                if existing:
                    return await replay(session, existing)
                detail = {
                    **outcome.to_payload(),
                    "request_hash": request_hash,
                    "delivery_state": "simulated",
                }
                intent: OutboundIntent | None = None
                if outcome.delivery_mode == "webhook_verified":
                    if not allow_external:
                        raise ConflictError("External delivery is disabled by the operator")
                    integration = await session.scalar(
                        select(ProjectIntegrationRow)
                        .where(
                            ProjectIntegrationRow.project_id == str(project_id),
                            ProjectIntegrationRow.id == integration_id,
                        )
                        .with_for_update()
                    )
                    policy = (
                        OutboundPolicy.model_validate(integration.outbound)
                        if integration
                        else OutboundPolicy()
                    )
                    if (
                        not integration
                        or not policy.enabled
                        or integration.type != IntegrationType.REST_API
                        or integration.status == IntegrationStatus.DISCONNECTED
                        or not project
                        or project.status != "active"
                    ):
                        raise ConflictError("External delivery configuration is unavailable")
                    if not integration.endpoint or not integration.secret_ref:
                        raise ConflictError(
                            "External delivery requires a destination and dedicated credential"
                        )
                    from openclass_server.integration_adapters import EnvironmentSecrets
                    from openclass_server.security import (
                        is_allowed_integration_secret_ref,
                        validate_outbound_url,
                    )

                    validate_outbound_url(integration.endpoint, resolve_dns=False)
                    if not is_allowed_integration_secret_ref(integration.secret_ref):
                        raise ConflictError("External delivery credential is not permitted")
                    EnvironmentSecrets().reject_configured_content(integration.secret_ref, request)
                    intent = OutboundIntent(
                        project_id=project_id,
                        integration_id=UUID(integration_id),
                        event_id=UUID(event_id),
                        run_id=outcome.run_id,
                        route_id=outcome.route_id,
                        selected_choice=outcome.selected_choice,
                        action=outcome.action,  # type: ignore[arg-type]
                        action_value=outcome.tag if outcome.action == "tag" else outcome.queue,  # type: ignore[arg-type]
                        endpoint=integration.endpoint,
                        secret_ref=integration.secret_ref,
                        receiver_enforces_idempotency=policy.receiver_enforces_idempotency,
                    )
                    detail["delivery_state"] = "queued"
                now = utcnow()
                session.add(
                    RoutingOutcomeRow(
                        id=row_id,
                        project_id=str(project_id),
                        integration_id=integration_id,
                        event_id=event_id,
                        selected_choice=outcome.selected_choice,
                        action=outcome.action,
                        detail=detail,
                        created_at=now,
                    )
                )
                await session.flush()
                if intent:
                    delivery = OutboundDeliveryRow(
                        id=str(uuid4()),
                        project_id=str(project_id),
                        integration_id=integration_id,
                        outcome_id=row_id,
                        idempotency_key=intent.idempotency_key,
                        request_hash=intent.request_hash,
                        intent=intent.model_dump(mode="json"),
                        state="queued",
                        attempts=0,
                        next_attempt_at=now,
                        created_at=now,
                        claim_token=None,
                        lease_until=None,
                    )
                    session.add(delivery)
                    await session.flush()
                    self._history(session, delivery, "queued", "enqueued", now)
                else:
                    session.add(
                        audit_event_row(
                            ProjectAuditEvent(
                                project_id=project_id,
                                actor="routing",
                                event_type="integration.updated",
                                payload={
                                    "delivery_event": "integration.routing_simulated",
                                    "outcome_id": row_id,
                                    "run_id": outcome.run_id,
                                },
                            )
                        )
                    )
                return detail, False
        except IntegrityError:
            async with self.sessions() as session:
                existing = await session.get(RoutingOutcomeRow, row_id)
                if existing:
                    return await replay(session, existing)
            raise ConflictError("Routing transaction could not be committed") from None

    async def claim(self, *, now: datetime | None = None) -> DeliveryClaim | None:
        now = now or utcnow()
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(OutboundDeliveryRow)
                .where(
                    OutboundDeliveryRow.state == "queued",
                    OutboundDeliveryRow.next_attempt_at <= now,
                    OutboundDeliveryRow.attempts < self.max_attempts,
                )
                .order_by(OutboundDeliveryRow.next_attempt_at, OutboundDeliveryRow.id)
                .limit(1)
            )
            if not row:
                return None
            token = str(uuid4())
            lease = now + timedelta(seconds=self.lease_seconds)
            result = await session.execute(
                update(OutboundDeliveryRow)
                .execution_options(synchronize_session="fetch", populate_existing=True)
                .where(
                    OutboundDeliveryRow.id == row.id,
                    OutboundDeliveryRow.state == "queued",
                    OutboundDeliveryRow.claim_token.is_(None),
                    OutboundDeliveryRow.attempts == row.attempts,
                )
                .values(state="claimed", claim_token=token, lease_until=lease)
                .returning(OutboundDeliveryRow.id)
            )
            if result.first() is None:
                return None
            self._history(session, row, "claimed", "claimed", now)
            return DeliveryClaim(
                id=UUID(row.id),
                token=token,
                intent=OutboundIntent.model_validate(row.intent),
                attempt=row.attempts + 1,
                lease_until=lease,
            )

    @staticmethod
    def _fence(claim: DeliveryClaim, state: str, now: datetime) -> tuple[Any, ...]:
        return (
            OutboundDeliveryRow.id == str(claim.id),
            OutboundDeliveryRow.state == state,
            OutboundDeliveryRow.claim_token == claim.token,
            OutboundDeliveryRow.lease_until > now,
            OutboundDeliveryRow.request_hash == claim.intent.request_hash,
            OutboundDeliveryRow.project_id == str(claim.intent.project_id),
        )

    async def begin_send(self, claim: DeliveryClaim, *, now: datetime | None = None) -> bool:
        now = now or utcnow()
        async with self.sessions.begin() as session:
            # Same project -> integration lock order as ingress/enqueue.
            project = await session.scalar(
                select(ProjectRow)
                .where(ProjectRow.id == str(claim.intent.project_id))
                .with_for_update()
            )
            integration = await session.scalar(
                select(ProjectIntegrationRow)
                .where(
                    ProjectIntegrationRow.id == str(claim.intent.integration_id),
                    ProjectIntegrationRow.project_id == str(claim.intent.project_id),
                )
                .with_for_update()
            )
            valid = bool(
                integration
                and project
                and project.status == "active"
                and integration.status != "disconnected"
                and integration.type == "rest_api"
                and integration.endpoint == claim.intent.endpoint
                and integration.secret_ref == claim.intent.secret_ref
                and OutboundPolicy.model_validate(integration.outbound)
                == OutboundPolicy(
                    enabled=True,
                    receiver_enforces_idempotency=claim.intent.receiver_enforces_idempotency,
                )
            )
            state: str | ColumnElement[str] = (
                "sending"
                if valid
                else case(
                    (OutboundDeliveryRow.had_ambiguous_attempt, "uncertain"), else_="cancelled"
                )
            )
            values: dict[str, Any] = {"state": state}
            if valid:
                values["attempts"] = OutboundDeliveryRow.attempts + 1
            else:
                values.update(claim_token=None, lease_until=None)
            row = await session.scalar(
                update(OutboundDeliveryRow)
                .execution_options(synchronize_session="fetch", populate_existing=True)
                .where(
                    *self._fence(claim, "claimed", now),
                    OutboundDeliveryRow.attempts < self.max_attempts,
                    OutboundDeliveryRow.attempts == claim.attempt - 1,
                )
                .values(**values)
                .returning(OutboundDeliveryRow)
            )
            if not row:
                return False
            self._history(
                session, row, row.state, "sending" if valid else "configuration_revoked", now
            )
            return valid

    async def finish(
        self, claim: DeliveryClaim, result: SendResult, *, now: datetime | None = None
    ) -> bool:
        now = now or utcnow()
        state: str | ColumnElement[str]
        if result.status == "accepted":
            state = "sent"
        elif result.status == "ambiguous":
            state = (
                "queued"
                if claim.intent.receiver_enforces_idempotency and claim.attempt < self.max_attempts
                else "uncertain"
            )
        else:
            state = (
                "queued"
                if claim.attempt < self.max_attempts
                else case((OutboundDeliveryRow.had_ambiguous_attempt, "uncertain"), else_="failed")
            )
        async with self.sessions.begin() as session:
            row = await session.scalar(
                update(OutboundDeliveryRow)
                .execution_options(synchronize_session="fetch", populate_existing=True)
                .where(
                    *self._fence(claim, "sending", now),
                    OutboundDeliveryRow.attempts == claim.attempt,
                )
                .values(
                    state=state,
                    claim_token=None,
                    lease_until=None,
                    next_attempt_at=now + timedelta(seconds=min(300, 2**claim.attempt)),
                    had_ambiguous_attempt=(
                        True
                        if result.status == "ambiguous"
                        else OutboundDeliveryRow.had_ambiguous_attempt
                    ),
                )
                .returning(OutboundDeliveryRow)
            )
            if not row:
                return False
            self._history(session, row, row.state, result.code, now)
            return True

    async def recover(self, *, now: datetime | None = None, limit: int = 100) -> None:
        now = now or utcnow()
        async with self.sessions.begin() as session:
            expired = (
                await session.scalars(
                    select(OutboundDeliveryRow)
                    .where(
                        or_(
                            and_(
                                OutboundDeliveryRow.state.in_(["claimed", "sending"]),
                                OutboundDeliveryRow.lease_until <= now,
                            ),
                            and_(
                                OutboundDeliveryRow.state == "queued",
                                OutboundDeliveryRow.attempts >= self.max_attempts,
                            ),
                        )
                    )
                    .order_by(OutboundDeliveryRow.lease_until)
                    .limit(min(limit, 100))
                )
            ).all()
            for old in expired:
                intent = OutboundIntent.model_validate(old.intent)
                state = (
                    "queued"
                    if old.attempts < self.max_attempts
                    and (
                        old.state == "claimed"
                        or (old.state == "sending" and intent.receiver_enforces_idempotency)
                    )
                    else "uncertain"
                )
                exhausted = old.state == "queued"
                row = await session.scalar(
                    update(OutboundDeliveryRow)
                    .execution_options(synchronize_session="fetch", populate_existing=True)
                    .where(
                        OutboundDeliveryRow.id == old.id,
                        OutboundDeliveryRow.state == old.state,
                        OutboundDeliveryRow.claim_token == old.claim_token,
                        OutboundDeliveryRow.lease_until == old.lease_until,
                        (
                            OutboundDeliveryRow.attempts >= self.max_attempts
                            if exhausted
                            else OutboundDeliveryRow.lease_until <= now
                        ),
                    )
                    .values(
                        state=state,
                        claim_token=None,
                        lease_until=None,
                        next_attempt_at=now + timedelta(seconds=min(300, 2**old.attempts)),
                        had_ambiguous_attempt=old.had_ambiguous_attempt or old.state == "sending",
                    )
                    .returning(OutboundDeliveryRow)
                )
                if row:
                    self._history(
                        session, row, state, "attempt_limit" if exhausted else "lease_expired", now
                    )

    async def get_uncertain_intent(self, delivery_id: UUID) -> OutboundIntent | None:
        async with self.sessions() as session:
            row = await session.scalar(
                select(OutboundDeliveryRow).where(
                    OutboundDeliveryRow.id == str(delivery_id),
                    OutboundDeliveryRow.state == "uncertain",
                )
            )
            return OutboundIntent.model_validate(row.intent) if row else None

    async def reconcile(self, delivery_id: UUID, receipt: AuthoritativeReceipt) -> bool:
        """Trusted positive readback only. Negative absence never authorizes retry."""
        if not receipt.applied:
            return False
        async with self.sessions.begin() as session:
            row = await session.scalar(
                update(OutboundDeliveryRow)
                .execution_options(synchronize_session="fetch", populate_existing=True)
                .where(
                    OutboundDeliveryRow.id == str(delivery_id),
                    OutboundDeliveryRow.state == "uncertain",
                    OutboundDeliveryRow.idempotency_key == receipt.idempotency_key,
                    OutboundDeliveryRow.request_hash == receipt.request_hash,
                )
                .values(state="sent")
                .returning(OutboundDeliveryRow)
            )
            if not row:
                return False
            self._history(session, row, "sent", "authoritative_receipt", utcnow())
            session.add(
                audit_event_row(
                    ProjectAuditEvent(
                        project_id=UUID(row.project_id),
                        actor="outbound-reconciler",
                        event_type="integration.updated",
                        payload={
                            "delivery_event": "integration.delivery_reconciled",
                            "delivery_id": row.id,
                            "receipt_hash": hashlib.sha256(receipt.receipt_id.encode()).hexdigest(),
                        },
                    )
                )
            )
            return True

    async def list_states(self, project_id: UUID | None = None) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            query = (
                select(OutboundDeliveryRow)
                .order_by(OutboundDeliveryRow.created_at.desc())
                .limit(100)
            )
            if project_id:
                query = query.where(OutboundDeliveryRow.project_id == str(project_id))
            return [
                {
                    "id": r.id,
                    "outcome_id": r.outcome_id,
                    "state": r.state,
                    "attempts": r.attempts,
                    "had_ambiguous_attempt": r.had_ambiguous_attempt,
                }
                for r in await session.scalars(query)
            ]
