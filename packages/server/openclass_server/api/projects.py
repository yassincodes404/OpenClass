"""Public projects routes over typed services and repository ports."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Query, Response
from fastapi.responses import JSONResponse
from openclass_core.analytics import ProjectAnalytics, summarize_project_runs
from openclass_core.projects import (
    Project,
    ProjectRepository,
    ProjectStatus,
    ProjectUpdate,
    RawEvent,
)
from openclass_core.projects import ProjectService as ProjectDomainService

from openclass_server.api.schemas import (
    CreateProject,
    ProjectSummaryResponse,
    RawEventBatchCreate,
    RawEventCreate,
    UpdateProject,
)
from openclass_server.persistence.idempotency import IdempotencyStore
from openclass_server.provider_config import reject_credentials
from openclass_server.settings import Settings

IdempotencyKeyHeader = Annotated[str | None, Header(alias="Idempotency-Key", max_length=200)]


def projects_router(
    config: Settings,
    projects: ProjectDomainService,
    project_repository: ProjectRepository,
    idempotency: IdempotencyStore | None = None,
) -> APIRouter:
    router = APIRouter(tags=["projects"])

    @router.post("/api/v1/projects", response_model=Project, status_code=201)
    async def create_project(body: CreateProject) -> Project:
        reject_credentials(body.model_dump(mode="json"), config)
        return await projects.create(body.name, body.description)

    @router.get("/api/v1/projects", response_model=list[Project])
    async def list_projects() -> list[Project]:
        return await projects.list_projects()

    @router.get("/api/v1/projects/{identifier}", response_model=Project)
    async def get_project(identifier: str) -> Project:
        return await projects.get(identifier)

    @router.patch("/api/v1/projects/{identifier}", response_model=Project)
    async def update_project(identifier: str, body: UpdateProject) -> Project:
        reject_credentials(body.model_dump(mode="json"), config)
        status = ProjectStatus(body.status) if body.status is not None else None
        update = ProjectUpdate(name=body.name, description=body.description, status=status)
        return await projects.update(identifier, update)

    @router.get("/api/v1/projects/{identifier}/summary", response_model=ProjectSummaryResponse)
    async def project_summary(identifier: str) -> ProjectSummaryResponse:
        summary = await projects.summary(identifier)
        return ProjectSummaryResponse(**summary.model_dump())

    @router.get("/api/v1/projects/{identifier}/analytics", response_model=ProjectAnalytics)
    async def project_analytics(identifier: str) -> ProjectAnalytics:
        project = await projects.get(identifier)
        return summarize_project_runs(
            project.id,
            await project_repository.count_raw_events(project.id),
            await project_repository.analytics_runs(project.id),
        )

    @router.get("/api/v1/projects/{identifier}/audit")
    async def project_audit(identifier: str) -> list[dict[str, Any]]:
        return [event.model_dump(mode="json") for event in await projects.audit(identifier)]

    @router.post("/api/v1/projects/{identifier}/events", response_model=RawEvent, status_code=201)
    async def ingest_event(
        identifier: str,
        body: RawEventCreate,
        idempotency_key: IdempotencyKeyHeader = None,
    ) -> RawEvent | Response:
        reject_credentials(body.model_dump(mode="json"), config)
        if idempotency is not None and idempotency_key:
            project = await projects.get(identifier)
            stored = await idempotency.get(project.id, idempotency_key)
            if stored is not None:
                return JSONResponse(
                    status_code=200,
                    content=stored,
                    headers={"Idempotency-Replayed": "true"},
                )
            event = await projects.ingest_event(
                identifier=identifier,
                content=body.content,
                source_type=body.source_type,
                metadata=body.metadata,
            )
            payload = event.model_dump(mode="json")
            payload["deduped"] = False
            await idempotency.store(
                project.id, idempotency_key, payload, config.idempotency_ttl_hours
            )
            return JSONResponse(status_code=201, content=payload)
        return await projects.ingest_event(
            identifier=identifier,
            content=body.content,
            source_type=body.source_type,
            metadata=body.metadata,
        )

    @router.post(
        "/api/v1/projects/{identifier}/events/batch",
        response_model=list[RawEvent],
        status_code=201,
    )
    async def ingest_events_batch(
        identifier: str,
        body: RawEventBatchCreate,
        idempotency_key: IdempotencyKeyHeader = None,
    ) -> list[RawEvent] | Response:
        reject_credentials(body.model_dump(mode="json"), config)
        if idempotency is not None and idempotency_key:
            project = await projects.get(identifier)
            stored = await idempotency.get(project.id, idempotency_key)
            if stored is not None:
                return JSONResponse(
                    status_code=200,
                    content=stored,
                    headers={"Idempotency-Replayed": "true"},
                )
            events = await projects.ingest_events_batch(
                identifier=identifier,
                items=body.items,
                source_type=body.source_type,
            )
            payload = [event.model_dump(mode="json") for event in events]
            await idempotency.store(
                project.id, idempotency_key, payload, config.idempotency_ttl_hours
            )
            return JSONResponse(status_code=201, content=payload)
        return await projects.ingest_events_batch(
            identifier=identifier,
            items=body.items,
            source_type=body.source_type,
        )

    @router.get("/api/v1/projects/{identifier}/events", response_model=list[RawEvent])
    async def list_events(
        identifier: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[RawEvent]:
        return await projects.list_events(identifier=identifier, limit=limit, offset=offset)

    @router.get("/api/v1/projects/{identifier}/events/{event_id}", response_model=RawEvent)
    async def get_event(identifier: str, event_id: UUID) -> RawEvent:
        return await projects.get_event(identifier=identifier, event_id=event_id)

    return router
