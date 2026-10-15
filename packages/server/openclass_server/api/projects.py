"""Public projects routes over typed services and repository ports."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request, Response
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
    ClaimProjectRequest,
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


def _mark_replayed(stored: Any) -> Any:
    """A replayed response commits nothing new: report deduped=true."""
    if isinstance(stored, dict):
        replayed = dict(stored)
        if "deduped" in replayed:
            replayed["deduped"] = True
        if isinstance(replayed.get("items"), list):
            replayed["items"] = [
                {**item, "deduped": True} if isinstance(item, dict) and "deduped" in item else item
                for item in replayed["items"]
            ]
        return replayed
    return stored


MAX_EVENT_CONTENT_CHARS = 10_000
MAX_BATCH_ITEMS = 500


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
    async def list_projects(
        include_unassigned: Annotated[bool, Query()] = False,
    ) -> list[Project]:
        return await projects.list_projects(include_unassigned=include_unassigned)

    @router.get("/api/v1/projects/{identifier}", response_model=Project)
    async def get_project(identifier: str) -> Project:
        return await projects.get(identifier)

    @router.post("/api/v1/projects/{identifier}/claim", response_model=Project)
    async def claim_project(
        identifier: str,
        request: Request,
        body: Annotated[ClaimProjectRequest | None, Body()] = None,
    ) -> Project:
        if body is not None:
            reject_credentials(body.model_dump(mode="json"), config)
        explicit_ws = (
            body.workspace_id.strip() if body is not None and body.workspace_id else None
        ) or getattr(request.state, "workspace_id", None)
        if not explicit_ws:
            raise HTTPException(
                status_code=422,
                detail="Target workspace_id is required to claim an unassigned project",
            )
        actor = (
            (body.actor.strip() if body is not None and body.actor else None)
            or getattr(request.state, "actor", None)
            or "operator"
        )
        return await projects.claim_unassigned(
            identifier,
            workspace_id=explicit_ws,
            actor=actor,
        )

    @router.patch("/api/v1/projects/{identifier}", response_model=Project)
    async def update_project(identifier: str, body: UpdateProject) -> Project:
        reject_credentials(body.model_dump(mode="json"), config)
        status = ProjectStatus(body.status) if body.status is not None else None
        update = ProjectUpdate(
            name=body.name,
            description=body.description,
            status=status,
            workspace_id=body.workspace_id,
        )
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
    ) -> Response:
        reject_credentials(body.model_dump(mode="json"), config)
        if not body.content.strip():
            raise HTTPException(status_code=400, detail="content cannot be blank")
        if len(body.content) > MAX_EVENT_CONTENT_CHARS:
            raise HTTPException(
                status_code=413,
                detail=f"content exceeds {MAX_EVENT_CONTENT_CHARS} characters",
            )
        if idempotency is not None and idempotency_key:
            project = await projects.get(identifier)
            stored = await idempotency.get(project.id, idempotency_key)
            if stored is not None:
                return JSONResponse(
                    status_code=200,
                    content=_mark_replayed(stored),
                    headers={"Idempotency-Replayed": "true"},
                )
        event, deduped = await projects.ingest_event(
            identifier=identifier,
            content=body.content,
            source_type=body.source_type,
            metadata=body.metadata,
        )
        payload = event.model_dump(mode="json")
        payload["deduped"] = deduped
        if idempotency is not None and idempotency_key:
            project = await projects.get(identifier)
            await idempotency.store(
                project.id, idempotency_key, payload, config.idempotency_ttl_hours
            )
        return JSONResponse(status_code=200 if deduped else 201, content=payload)

    @router.post(
        "/api/v1/projects/{identifier}/events/batch",
        status_code=207,
    )
    async def ingest_events_batch(
        identifier: str,
        body: RawEventBatchCreate,
        idempotency_key: IdempotencyKeyHeader = None,
    ) -> Response:
        reject_credentials(body.model_dump(mode="json"), config)
        if len(body.items) > MAX_BATCH_ITEMS:
            raise HTTPException(
                status_code=413,
                detail=f"batch exceeds {MAX_BATCH_ITEMS} items",
            )
        if idempotency is not None and idempotency_key:
            project = await projects.get(identifier)
            stored = await idempotency.get(project.id, idempotency_key)
            if stored is not None:
                return JSONResponse(
                    status_code=200,
                    content=_mark_replayed(stored),
                    headers={"Idempotency-Replayed": "true"},
                )
        items: list[dict[str, Any]] = []
        entries: list[dict[str, Any]] = []
        for index, item in enumerate(body.items):
            content = item.get("content", "")
            if not isinstance(content, str) or not content.strip():
                entries.append({"index": index, "status": 400, "error": "content cannot be blank"})
            elif len(content) > MAX_EVENT_CONTENT_CHARS:
                entries.append(
                    {
                        "index": index,
                        "status": 413,
                        "error": f"content exceeds {MAX_EVENT_CONTENT_CHARS} characters",
                    }
                )
            else:
                items.append(item)
                entries.append({"index": index, "status": None})
        if items:
            results = await projects.ingest_events_batch(
                identifier=identifier,
                items=items,
                source_type=body.source_type,
            )
            for (event, deduped), entry in zip(
                results, [e for e in entries if e["status"] is None], strict=True
            ):
                entry["status"] = 200 if deduped else 201
                entry["event"] = event.model_dump(mode="json")
                entry["deduped"] = deduped
        elif all(entry["status"] not in (None, 200, 201) for entry in entries):
            raise HTTPException(status_code=400, detail="no valid events to ingest")
        payload: Any = {"items": entries}
        if idempotency is not None and idempotency_key:
            project = await projects.get(identifier)
            await idempotency.store(
                project.id, idempotency_key, payload, config.idempotency_ttl_hours
            )
        return JSONResponse(status_code=207, content=payload)

    @router.get("/api/v1/projects/{identifier}/providers/usage")
    async def provider_usage(
        identifier: str,
        date_from: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = "2026-01-01",
        date_to: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = "2100-01-01",
    ) -> list[dict[str, Any]]:
        project = await projects.get(identifier)
        return await project_repository.provider_usage(project.id, date_from, date_to)

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
