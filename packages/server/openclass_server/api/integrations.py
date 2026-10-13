"""HTTP integration boundary; domain policy and network adapters live separately."""

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


def integration_router(
    config: Settings,
    projects: ProjectService,
    repository: IntegrationRepository,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{identifier}/integrations", tags=["integrations"])
    secrets = EnvironmentSecrets()
    service = IntegrationService(repository, HTTPIntegrationProbe(secrets))

    @router.get("", response_model=list[IntegrationConfig])
    async def list_integrations(identifier: str) -> list[IntegrationConfig]:
        project = await projects.get(identifier)
        return await repository.list_integrations(project.id)

    @router.post("", response_model=IntegrationConfig, status_code=201)
    async def create_integration(identifier: str, body: IntegrationCreate) -> IntegrationConfig:
        reject_credentials(body.model_dump(mode="json"), config)
        if body.secret_ref and not is_allowed_integration_secret_ref(body.secret_ref):
            raise HTTPException(
                status_code=422, detail="Secret reference is not permitted for integrations"
            )
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
        if body.secret_ref and not is_allowed_integration_secret_ref(body.secret_ref):
            raise HTTPException(
                status_code=422, detail="Secret reference is not permitted for integrations"
            )
        project = await projects.get(identifier)
        current = await repository.get_integration(project.id, integration_id)
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
        body: WebhookDelivery,
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
            secrets.authenticate(integration, request.headers)
            secrets.reject_secret_content(integration, body.model_dump(mode="json"))
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
