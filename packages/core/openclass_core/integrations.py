"""Integrations domain models and protocols for OpenClass.

Integrations enable OpenClass projects to connect to external systems:
- Model Context Protocol (MCP) servers (tools, prompts, resources)
- Inbound Webhooks for external event ingestion
- Outbound REST / HTTP APIs for notifications and workflows
- External AI / Decision Provider credentials (e.g. Vercel AI Gateway, Gemini, OpenAI)
- Databases and business connectors (e.g. PostgreSQL, CRM, Stripe)

In accordance with OpenClass architecture:
- Core owns domain rules and typed schemas.
- Integrations operate under capability permissions and audit trails.
- Plaintext secrets are never stored in entity models (secret_ref only).
"""

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from .models import Model
from .projects import ProjectAuditEvent, RawEvent

SECRET_REFERENCE_PATTERN = r"^[A-Z][A-Z0-9_]{0,199}$"


def now() -> datetime:
    return datetime.now(UTC)


class IntegrationType(StrEnum):
    MCP = "mcp"
    WEBHOOK = "webhook"
    REST_API = "rest_api"
    PROVIDER = "provider"
    DATABASE = "database"


class IntegrationStatus(StrEnum):
    CONNECTED = "connected"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    PENDING = "pending"


class IntegrationConfig(Model):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    name: str = Field(min_length=1, max_length=200)
    type: IntegrationType
    status: IntegrationStatus = Field(default=IntegrationStatus.PENDING)
    endpoint: str | None = Field(default=None, max_length=1000)
    secret_ref: str | None = Field(default=None, pattern=SECRET_REFERENCE_PATTERN)
    capabilities: tuple[str, ...] = Field(default_factory=tuple)
    latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    last_health_check: datetime | None = None
    error_message: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class IntegrationCreate(Model):
    name: str = Field(min_length=1, max_length=200)
    type: IntegrationType
    endpoint: str | None = Field(default=None, max_length=1000)
    secret_ref: str | None = Field(default=None, pattern=SECRET_REFERENCE_PATTERN)
    capabilities: tuple[str, ...] = Field(default_factory=tuple)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntegrationUpdate(Model):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: IntegrationStatus | None = None
    endpoint: str | None = Field(default=None, max_length=1000)
    secret_ref: str | None = Field(default=None, pattern=SECRET_REFERENCE_PATTERN)
    capabilities: tuple[str, ...] | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def has_changes(self) -> "IntegrationUpdate":
        if (
            self.name is None
            and self.status is None
            and self.endpoint is None
            and self.secret_ref is None
            and self.capabilities is None
            and self.metadata is None
            and not self.model_fields_set.intersection({"endpoint", "secret_ref"})
        ):
            raise ValueError("IntegrationUpdate must set at least one field")
        return self


class IntegrationHealthReport(Model):
    integration_id: UUID
    status: IntegrationStatus
    latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    capabilities: tuple[str, ...] = Field(default_factory=tuple)
    error_message: str | None = Field(default=None, max_length=2000)
    timestamp: datetime = Field(default_factory=now)


class WebhookIngestResult(Model):
    event_id: UUID
    project_id: UUID
    integration_id: UUID
    status: Literal["ingested", "duplicate"] = "ingested"
    source: str
    timestamp: datetime = Field(default_factory=now)


class WebhookDelivery(Model):
    """An external event identity is scoped to its project and integration."""

    event_key: str = Field(min_length=1, max_length=200)
    source: str = Field(default="webhook", min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=100_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def nonblank(self) -> "WebhookDelivery":
        if not self.content.strip() or not self.event_key.strip() or not self.source.strip():
            raise ValueError("Webhook content, source and event key cannot be blank")
        return self

    def fingerprint(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


class IntegrationRepository(Protocol):
    async def create_integration(
        self,
        project_id: UUID,
        integration: IntegrationCreate,
    ) -> IntegrationConfig: ...

    async def get_integration(
        self,
        project_id: UUID,
        integration_id: UUID,
    ) -> IntegrationConfig: ...

    async def list_integrations(
        self,
        project_id: UUID,
    ) -> list[IntegrationConfig]: ...

    async def update_integration(
        self,
        project_id: UUID,
        integration_id: UUID,
        patch: IntegrationUpdate,
    ) -> IntegrationConfig: ...

    async def delete_integration(
        self,
        project_id: UUID,
        integration_id: UUID,
    ) -> None: ...

    async def record_integration_health(
        self,
        project_id: UUID,
        integration_id: UUID,
        report: IntegrationHealthReport,
    ) -> IntegrationConfig: ...

    async def ingest_webhook(
        self,
        integration: IntegrationConfig,
        delivery: WebhookDelivery,
        event: RawEvent,
        audit: ProjectAuditEvent,
    ) -> WebhookIngestResult: ...


class IntegrationProbe(Protocol):
    async def check(self, integration: IntegrationConfig) -> IntegrationHealthReport: ...


class IntegrationService:
    """Domain ingestion and health orchestration; no transport or secret access."""

    def __init__(self, repository: IntegrationRepository, probe: IntegrationProbe) -> None:
        self.repository = repository
        self.probe = probe

    async def test(self, project_id: UUID, integration_id: UUID) -> IntegrationHealthReport:
        integration = await self.repository.get_integration(project_id, integration_id)
        report = await self.probe.check(integration)
        await self.repository.record_integration_health(project_id, integration_id, report)
        return report

    async def ingest(
        self, integration: IntegrationConfig, delivery: WebhookDelivery
    ) -> WebhookIngestResult:
        if integration.type != IntegrationType.WEBHOOK:
            raise ValueError("Integration is not a webhook")
        event = RawEvent(
            project_id=integration.project_id,
            source_type="webhook",
            content=delivery.content,
            metadata={
                **delivery.metadata,
                "integration_id": str(integration.id),
                "integration_source": delivery.source,
                "external_event_key": delivery.event_key,
            },
        )
        audit = ProjectAuditEvent(
            project_id=integration.project_id,
            event_type="integration.webhook_ingested",
            actor="integration",
            payload={"integration_id": str(integration.id), "event_id": str(event.id)},
        )
        return await self.repository.ingest_webhook(integration, delivery, event, audit)
