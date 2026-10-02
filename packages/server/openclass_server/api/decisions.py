"""Public decisions routes over typed services and repository ports."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from openclass_core.decision_executor import DecisionExecutor
from openclass_core.projects import (
    DecisionRun,
    DecisionService,
    DecisionServiceStatus,
    DecisionServiceUpdate,
    ProjectRepository,
)
from openclass_core.projects import ProjectService as ProjectDomainService
from openclass_core.providers import DecisionProvider, ProviderError
from openclass_core.repositories import NotFoundError

from openclass_server.api.schemas import (
    DecisionServiceCreate,
    DecisionServiceUpdateSchema,
    ExecuteDecisionRunRequest,
)
from openclass_server.provider_config import reject_credentials, resolve_decision_provider
from openclass_server.settings import Settings


def decisions_router(
    config: Settings,
    projects: ProjectDomainService,
    default_decision_provider: DecisionProvider,
    project_repository: ProjectRepository | None = None,
) -> APIRouter:
    router = APIRouter(tags=["decisions"])

    @router.post(
        "/api/v1/projects/{identifier}/decision-services",
        response_model=DecisionService,
        status_code=201,
    )
    async def create_decision_service(
        identifier: str, body: DecisionServiceCreate
    ) -> DecisionService:
        reject_credentials(body.model_dump(mode="json"), config)
        return await projects.create_decision_service(
            identifier=identifier,
            name=body.name,
            instructions=body.instructions,
            choices=[c.model_dump(mode="json") for c in body.choices],
            description=body.description,
            provider_override=body.provider_override,
        )

    @router.get(
        "/api/v1/projects/{identifier}/decision-services",
        response_model=list[DecisionService],
    )
    async def list_decision_services(identifier: str) -> list[DecisionService]:
        return await projects.list_decision_services(identifier=identifier)

    @router.get(
        "/api/v1/projects/{identifier}/decision-services/{service_id}",
        response_model=DecisionService,
    )
    async def get_decision_service(identifier: str, service_id: str) -> DecisionService:
        return await projects.get_decision_service(
            identifier=identifier, service_id_or_slug=service_id
        )

    @router.patch(
        "/api/v1/projects/{identifier}/decision-services/{service_id}",
        response_model=DecisionService,
    )
    async def update_decision_service(
        identifier: str, service_id: str, body: DecisionServiceUpdateSchema
    ) -> DecisionService:
        reject_credentials(body.model_dump(mode="json"), config)
        status_enum = DecisionServiceStatus(body.status) if body.status is not None else None
        update = DecisionServiceUpdate(
            name=body.name,
            description=body.description,
            instructions=body.instructions,
            status=status_enum,
            provider_override=body.provider_override,
        )
        return await projects.update_decision_service(
            identifier=identifier,
            service_id_or_slug=service_id,
            update=update,
        )

    @router.post(
        "/api/v1/projects/{identifier}/decision-services/{service_id}/runs",
        response_model=list[DecisionRun],
        status_code=201,
    )
    async def execute_decision_runs(
        identifier: str, service_id: str, body: ExecuteDecisionRunRequest
    ) -> list[DecisionRun]:
        service = await projects.get_decision_service(identifier, service_id)
        if service.provider_override:
            try:
                exec_provider = resolve_decision_provider(config, service.provider_override)
            except ValueError as err:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unsupported provider override: {service.provider_override}",
                ) from err
        else:
            exec_provider = default_decision_provider
        executor = DecisionExecutor(exec_provider)
        runs: list[DecisionRun] = []
        event_ids: list[UUID] = []
        if body.content:
            event, deduped = await projects.ingest_event(
                identifier=identifier, content=body.content, source_type="text"
            )
            event_ids.append(event.id)
        for raw_id_str in body.raw_event_ids:
            event_ids.append(UUID(raw_id_str))
        for run_event_id in event_ids:
            try:
                event = await projects.get_event(identifier, run_event_id)
            except NotFoundError as err:
                msg = f"Event not found: {run_event_id}"
                raise HTTPException(status_code=404, detail=msg) from err
            try:
                run = await executor.execute(event, service)
            except ProviderError:
                # Provider failures are observable (usage error counter + audit
                # event) but never persist a run or leak provider details.
                if project_repository is not None:
                    await project_repository.record_provider_error(
                        service.project_id, "provider", "", 0.0
                    )
                raise
            await projects.record_decision_run(run)
            runs.append(run)
        return runs

    @router.get(
        "/api/v1/projects/{identifier}/runs",
        response_model=list[DecisionRun],
    )
    async def list_decision_runs(
        identifier: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[DecisionRun]:
        return await projects.list_decision_runs(identifier=identifier, limit=limit, offset=offset)

    @router.get(
        "/api/v1/projects/{identifier}/runs/{run_id}",
        response_model=DecisionRun,
    )
    async def get_decision_run(identifier: str, run_id: UUID) -> DecisionRun:
        return await projects.get_decision_run(identifier=identifier, run_id=run_id)

    return router
