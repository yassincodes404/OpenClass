"""Project-scoped integration configuration, health and atomic webhook receipts."""

from datetime import UTC, datetime
from uuid import UUID

from openclass_core.integrations import (
    IntegrationConfig,
    IntegrationCreate,
    IntegrationHealthReport,
    IntegrationStatus,
    IntegrationType,
    IntegrationUpdate,
    WebhookDelivery,
    WebhookIngestResult,
)
from openclass_core.projects import ProjectAuditEvent, RawEvent
from openclass_core.repositories import ConflictError, NotFoundError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .mappers import audit_event_row, raw_event_row
from .tables import ProjectIntegrationRow, WebhookReceiptRow


class SQLIntegrationRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def ingest_webhook(
        self,
        integration: IntegrationConfig,
        delivery: WebhookDelivery,
        event: RawEvent,
        audit: ProjectAuditEvent,
    ) -> WebhookIngestResult:
        key = (str(integration.project_id), str(integration.id), delivery.event_key)
        fingerprint = delivery.fingerprint()

        def result(receipt: WebhookReceiptRow, duplicate: bool) -> WebhookIngestResult:
            if receipt.fingerprint != fingerprint:
                raise ConflictError("Webhook event key was already used with different content")
            return WebhookIngestResult(
                event_id=UUID(receipt.event_id),
                project_id=integration.project_id,
                integration_id=integration.id,
                source=receipt.source,
                status="duplicate" if duplicate else "ingested",
                timestamp=receipt.created_at,
            )

        try:
            async with self.sessions.begin() as session:
                current = await session.scalar(
                    select(ProjectIntegrationRow)
                    .where(
                        ProjectIntegrationRow.project_id == key[0],
                        ProjectIntegrationRow.id == key[1],
                    )
                    .with_for_update()
                )
                if current is None:
                    raise NotFoundError("Integration not found")
                if (
                    current.type != integration.type.value
                    or current.secret_ref != integration.secret_ref
                ):
                    raise ConflictError("Integration changed during webhook authentication")
                existing = await session.get(WebhookReceiptRow, key)
                if existing is not None:
                    return result(existing, True)
                session.add(raw_event_row(event))
                session.add(audit_event_row(audit))
                await session.flush()
                receipt = WebhookReceiptRow(
                    project_id=key[0],
                    integration_id=key[1],
                    event_key=key[2],
                    fingerprint=fingerprint,
                    event_id=str(event.id),
                    source=delivery.source,
                    created_at=event.created_at,
                )
                session.add(receipt)
                await session.flush()
                return result(receipt, False)
        except IntegrityError:
            # SQLite relies on the unique key; PostgreSQL also locks the configuration.
            # Rollback removes the losing observation and audit before reading the winner.
            async with self.sessions() as session:
                existing = await session.get(WebhookReceiptRow, key)
                if existing is not None:
                    return result(existing, True)
            raise ConflictError("Webhook delivery conflicts with existing state") from None

    # ── Integrations ──────────────────────────────────────────

    @staticmethod
    def _to_integration(row: ProjectIntegrationRow) -> IntegrationConfig:
        return IntegrationConfig(
            id=UUID(row.id),
            project_id=UUID(row.project_id),
            name=row.name,
            type=IntegrationType(row.type),
            status=IntegrationStatus(row.status),
            endpoint=row.endpoint,
            secret_ref=row.secret_ref,
            capabilities=tuple(row.capabilities or []),
            latency_ms=row.latency_ms,
            last_health_check=row.last_health_check,
            error_message=row.error_message,
            metadata=dict(row.metadata_json or {}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def create_integration(
        self,
        project_id: UUID,
        integration: IntegrationCreate,
        actor: str = "user",
    ) -> IntegrationConfig:
        config = IntegrationConfig(
            project_id=project_id,
            name=integration.name,
            type=integration.type,
            status=IntegrationStatus.PENDING,
            endpoint=integration.endpoint,
            secret_ref=integration.secret_ref,
            capabilities=integration.capabilities,
            metadata=integration.metadata,
        )
        row = ProjectIntegrationRow(
            id=str(config.id),
            project_id=str(project_id),
            name=config.name,
            type=config.type.value,
            status=config.status.value,
            endpoint=config.endpoint,
            secret_ref=config.secret_ref,
            capabilities=list(config.capabilities),
            latency_ms=config.latency_ms,
            last_health_check=config.last_health_check,
            error_message=config.error_message,
            metadata_json=config.metadata,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )
        audit_event = ProjectAuditEvent(
            project_id=project_id,
            event_type="integration.created",
            actor=actor,
            payload={
                "integration_id": str(config.id),
                "name": config.name,
                "type": config.type.value,
            },
        )
        try:
            async with self.sessions.begin() as session:
                session.add(row)
                session.add(audit_event_row(audit_event))
        except IntegrityError:
            raise NotFoundError("Project does not exist") from None
        return config

    async def get_integration(
        self,
        project_id: UUID,
        integration_id: UUID,
    ) -> IntegrationConfig:
        async with self.sessions() as session:
            row = await session.scalar(
                select(ProjectIntegrationRow).where(
                    ProjectIntegrationRow.project_id == str(project_id),
                    ProjectIntegrationRow.id == str(integration_id),
                )
            )
            if row is None:
                raise NotFoundError("Integration not found")
            return self._to_integration(row)

    async def list_integrations(
        self,
        project_id: UUID,
    ) -> list[IntegrationConfig]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(ProjectIntegrationRow)
                .where(ProjectIntegrationRow.project_id == str(project_id))
                .order_by(ProjectIntegrationRow.created_at.desc())
            )
            return [self._to_integration(row) for row in rows]

    async def update_integration(
        self,
        project_id: UUID,
        integration_id: UUID,
        patch: IntegrationUpdate,
        actor: str = "user",
    ) -> IntegrationConfig:
        now_dt = datetime.now(UTC)
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(ProjectIntegrationRow)
                .where(
                    ProjectIntegrationRow.project_id == str(project_id),
                    ProjectIntegrationRow.id == str(integration_id),
                )
                .with_for_update()
            )
            if row is None:
                raise NotFoundError("Integration not found")
            if patch.name is not None:
                row.name = patch.name
            if patch.status is not None:
                row.status = patch.status.value
            if "endpoint" in patch.model_fields_set:
                row.endpoint = patch.endpoint
            if "secret_ref" in patch.model_fields_set:
                row.secret_ref = patch.secret_ref
            if patch.capabilities is not None:
                row.capabilities = list(patch.capabilities)
            if patch.metadata is not None:
                row.metadata_json = dict(patch.metadata)
            if patch.model_fields_set.intersection({"endpoint", "secret_ref", "capabilities"}):
                row.status = IntegrationStatus.PENDING.value
                row.latency_ms = None
                row.last_health_check = None
                row.error_message = None
            row.updated_at = now_dt

            audit_event = ProjectAuditEvent(
                project_id=project_id,
                event_type="integration.updated",
                actor=actor,
                payload={
                    "integration_id": str(integration_id),
                    "changes": patch.model_dump(exclude_unset=True),
                },
            )
            session.add(audit_event_row(audit_event))
            return self._to_integration(row)

    async def delete_integration(
        self,
        project_id: UUID,
        integration_id: UUID,
        actor: str = "user",
    ) -> None:
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(ProjectIntegrationRow)
                .where(
                    ProjectIntegrationRow.project_id == str(project_id),
                    ProjectIntegrationRow.id == str(integration_id),
                )
                .with_for_update()
            )
            if row is None:
                raise NotFoundError("Integration not found")
            await session.delete(row)
            audit_event = ProjectAuditEvent(
                project_id=project_id,
                event_type="integration.deleted",
                actor=actor,
                payload={"integration_id": str(integration_id), "name": row.name},
            )
            session.add(audit_event_row(audit_event))

    async def record_integration_health(
        self,
        project_id: UUID,
        integration_id: UUID,
        report: IntegrationHealthReport,
        actor: str = "system",
    ) -> IntegrationConfig:
        now_dt = datetime.now(UTC)
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(ProjectIntegrationRow)
                .where(
                    ProjectIntegrationRow.project_id == str(project_id),
                    ProjectIntegrationRow.id == str(integration_id),
                )
                .with_for_update()
            )
            if row is None:
                raise NotFoundError("Integration not found")
            row.status = report.status.value
            row.latency_ms = report.latency_ms
            row.last_health_check = report.timestamp
            row.error_message = report.error_message
            row.updated_at = now_dt

            audit_event = ProjectAuditEvent(
                project_id=project_id,
                event_type="integration.tested",
                actor=actor,
                payload={
                    "integration_id": str(integration_id),
                    "status": report.status.value,
                    "latency_ms": report.latency_ms,
                    "error": report.error_message,
                },
            )
            session.add(audit_event_row(audit_event))
            return self._to_integration(row)
