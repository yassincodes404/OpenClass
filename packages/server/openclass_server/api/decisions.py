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
)
from openclass_core.projects import ProjectService as ProjectDomainService
from openclass_core.providers import DecisionProvider

from openclass_server.api.schemas import (
    DecisionServiceCreate,
    DecisionServiceUpdateSchema,
    ExecuteDecisionRunRequest,
)
from openclass_server.provider_config import reject_credentials, resolve_decision_provider
from openclass_server.settings import Settings


def decisions_router(
    config: Settings, projects: ProjectDomainService, default_decision_provider: DecisionProvider
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
            exec_provider = resolve_decision_provider(config, service.provider_override)
        else:
            exec_provider = default_decision_provider
        executor = DecisionExecutor(exec_provider)
        runs: list[DecisionRun] = []
        for raw_id_str in body.raw_event_ids:
            try:
                event_id = UUID(raw_id_str)
            except ValueError as err:
                msg = f"Invalid event UUID: {raw_id_str}"
                raise HTTPException(status_code=422, detail=msg) from err
            event = await projects.get_event(identifier, event_id)
            run = await executor.execute(event, service)
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
