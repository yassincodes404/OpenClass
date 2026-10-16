"""HTTP integration boundary; domain policy and network adapters live separately."""

import json
import os
import re
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from openclass_core.integrations import (
    IntegrationConfig,
    IntegrationCreate,
    IntegrationHealthReport,
    IntegrationRepository,
    IntegrationService,
    IntegrationStatus,
    IntegrationType,
    IntegrationUpdate,
    WebhookDelivery,
    WebhookIngestResult,
)
from openclass_core.projects import ProjectService, ProjectStatus
from sqlalchemy.engine import make_url

from openclass_server.integration_adapters import (
    EnvironmentSecrets,
    HTTPIntegrationProbe,
    IntegrationConfigurationError,
    WebhookAuthenticationError,
)
from openclass_server.provider_config import reject_credentials
from openclass_server.security import (
    is_allowed_integration_secret_ref,
    validate_outbound_url,
)
from openclass_server.settings import Settings
from openclass_server.webhook_normalizers import (
    MAX_WEBHOOK_BYTES,
    normalize_webhook,
    verify_webhook,
)


def integration_router(
    config: Settings,
    projects: ProjectService,
    repository: IntegrationRepository,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{identifier}/integrations", tags=["integrations"])
    secrets = EnvironmentSecrets()
    service = IntegrationService(repository, HTTPIntegrationProbe(secrets))

    def validate_config(body: IntegrationCreate | IntegrationConfig) -> None:
        if body.type == IntegrationType.DATABASE:
            if (
                body.endpoint
                or body.metadata
                or (
                    body.secret_ref is not None
                    and not re.fullmatch(
                        r"OPENCLASS_INTEGRATION_DATABASE_[A-Z0-9_]+_SECRET", body.secret_ref
                    )
                )
            ):
                raise HTTPException(
                    status_code=422,
                    detail="Database checks require only a dedicated operator DSN reference",
                )
            secret = os.environ.get(body.secret_ref or "", "")
            from openclass_server.security import contains_secret

            if secret and contains_secret(body.model_dump(mode="json"), secret):
                raise HTTPException(
                    status_code=422, detail="Input contains an integration credential"
                )
            if secret:
                try:
                    password = make_url(secret).password
                except ValueError:
                    password = None
                if password and contains_secret(body.model_dump(mode="json"), password):
                    raise HTTPException(
                        status_code=422, detail="Input contains an integration credential"
                    )
        elif body.secret_ref and not is_allowed_integration_secret_ref(body.secret_ref):
            raise HTTPException(
                status_code=422, detail="Secret reference is not permitted for integrations"
            )
        if body.signature.mode != "bearer" and body.type != IntegrationType.WEBHOOK:
            raise HTTPException(
                status_code=422, detail="Signature configuration requires a webhook"
            )
        if body.outbound.enabled and body.type != IntegrationType.REST_API:
            raise HTTPException(
                status_code=422, detail="Outbound delivery requires a REST integration"
            )

    @router.get("", response_model=list[IntegrationConfig])
    async def list_integrations(identifier: str) -> list[IntegrationConfig]:
        project = await projects.get(identifier)
        return await repository.list_integrations(project.id)

    @router.post("", response_model=IntegrationConfig, status_code=201)
    async def create_integration(identifier: str, body: IntegrationCreate) -> IntegrationConfig:
        reject_credentials(body.model_dump(mode="json"), config)
        validate_config(body)
        if body.type == IntegrationType.REST_API and body.endpoint:
            try:
                validate_outbound_url(body.endpoint, allow_loopback=False, resolve_dns=False)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from None
        secrets.reject_configured_content(body.secret_ref, body.model_dump(mode="json"))
        project = await projects.get(identifier)
        if body.type == IntegrationType.WEBHOOK and not body.secret_ref:
            raise HTTPException(
                status_code=422, detail="Webhook requires an environment secret reference"
            )
        return await repository.create_integration(project.id, body)

    @router.get("/{integration_id}", response_model=IntegrationConfig)
    async def get_integration(identifier: str, integration_id: UUID) -> IntegrationConfig:
        project = await projects.get(identifier)
        return await repository.get_integration(project.id, integration_id)

    @router.patch("/{integration_id}", response_model=IntegrationConfig)
    async def update_integration(
        identifier: str,
        integration_id: UUID,
        body: IntegrationUpdate,
    ) -> IntegrationConfig:
        reject_credentials(body.model_dump(mode="json"), config)
        project = await projects.get(identifier)
        current = await repository.get_integration(project.id, integration_id)
        validate_config(
            IntegrationConfig.model_validate(
                {**current.model_dump(), **body.model_dump(exclude_unset=True)}
            )
        )
        if current.type == IntegrationType.REST_API and body.endpoint:
            try:
                validate_outbound_url(body.endpoint, allow_loopback=False, resolve_dns=False)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from None
        secrets.reject_configured_content(current.secret_ref, body.model_dump(mode="json"))
        secrets.reject_configured_content(body.secret_ref, body.model_dump(mode="json"))
        if body.status in {IntegrationStatus.CONNECTED, IntegrationStatus.DEGRADED}:
            raise HTTPException(
                status_code=422, detail="Use the connectivity check to set health status"
            )
        return await repository.update_integration(project.id, integration_id, body)

    @router.delete("/{integration_id}", status_code=204)
    async def delete_integration(identifier: str, integration_id: UUID) -> None:
        project = await projects.get(identifier)
        await repository.delete_integration(project.id, integration_id)

    @router.post("/{integration_id}/test", response_model=IntegrationHealthReport)
    async def test_integration(identifier: str, integration_id: UUID) -> IntegrationHealthReport:
        project = await projects.get(identifier)
        return await service.test(project.id, integration_id)

    @router.post(
        "/{integration_id}/webhook",
        response_model=WebhookIngestResult,
        status_code=201,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "anyOf": [WebhookDelivery.model_json_schema(), {"type": "object"}],
                            "description": (
                                "Generic WebhookDelivery or configured signed vendor payload. "
                                "Sign exact bytes."
                            ),
                        }
                    }
                },
            },
        },
        responses={
            200: {"model": WebhookIngestResult, "description": "Duplicate delivery"},
            401: {"description": "Invalid token"},
            409: {"description": "Event key reused with different content"},
            503: {"description": "Credential unavailable"},
        },
    )
    async def ingest_webhook(
        identifier: str,
        integration_id: UUID,
        request: Request,
        response: Response,
    ) -> WebhookIngestResult:
        project = await projects.get(identifier)
        integration = await repository.get_integration(project.id, integration_id)
        if integration.type != IntegrationType.WEBHOOK:
            raise HTTPException(status_code=400, detail="Integration is not a webhook")
        if project.status != ProjectStatus.ACTIVE:
            raise HTTPException(status_code=409, detail="Archived projects cannot ingest webhooks")
        try:
            raw = bytearray()
            async for chunk in request.stream():
                if len(raw) + len(chunk) > MAX_WEBHOOK_BYTES:
                    raise HTTPException(status_code=413, detail="Webhook payload is too large")
                raw.extend(chunk)
            verify_webhook(integration, bytes(raw), request.headers, secrets)
            try:
                decoded = json.loads(raw)
            except (ValueError, RecursionError):
                raise HTTPException(status_code=422, detail="Malformed webhook payload") from None
            secrets.reject_secret_content(integration, decoded)
            reject_credentials(decoded, config)
            try:
                body = normalize_webhook(integration, bytes(raw))
            except ValueError:
                raise HTTPException(status_code=422, detail="Malformed webhook payload") from None
        except WebhookAuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from None
        except IntegrationConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
        reject_credentials(body.model_dump(mode="json"), config)
        result = await service.ingest(integration, body)
        if result.status == "duplicate":
            response.status_code = 200
        return result

    return router
