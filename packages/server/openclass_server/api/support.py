"""Support integrations: routing rules, source webhooks, adapter status."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Request, Response
from openclass_core.projects import ProjectService as ProjectDomainService
from openclass_core.routing import (
    RoutingRule,
    adapter_status,
    decide_routing,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from openclass_server.settings import Settings


class RouteCreate(BaseModel):
    match_choice: str = Field(min_length=1, max_length=100)
    action: str = Field(pattern=r"^(tag|assign_queue)$")
    action_value: str = Field(default="", max_length=200)


class SourceDelivery(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)
    event_key: str = Field(min_length=1, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


def support_router(
    config: Settings,
    projects: ProjectDomainService,
    sessions: async_sessionmaker[AsyncSession],
    decision_provider: object,
) -> APIRouter:
    router = APIRouter(tags=["support"])

    async def _integration_by_source(project_id: UUID, source: str) -> dict[str, Any] | None:
        async with sessions() as session:
            row = await session.execute(
                sa.text(
                    "SELECT id, name, type, status FROM project_integrations"
                    " WHERE project_id = :pid AND name = :source LIMIT 1"
                ),
                {"pid": str(project_id), "source": source},
            )
            record = row.first()
        if record is None:
            return None
        return {"id": record.id, "name": record.name, "type": record.type, "status": record.status}

    async def _routes(project_id: UUID, integration_id: UUID | None = None) -> list[RoutingRule]:
        async with sessions() as session:
            query = (
                "SELECT id, project_id, integration_id, match_choice, action, action_value"
                " FROM integration_routes WHERE project_id = :pid"
            )
            params: dict[str, str] = {"pid": str(project_id)}
            if integration_id is not None:
                query += " AND integration_id = :iid"
                params["iid"] = str(integration_id)
            rows = await session.execute(sa.text(query), params)
            return [
                RoutingRule(
                    id=row.id,
                    project_id=row.project_id,
                    integration_id=row.integration_id,
                    match_choice=row.match_choice,
                    action=row.action,
                    action_value=row.action_value,
                )
                for row in rows
            ]

    @router.get("/api/v1/projects/{identifier}/integrations/adapters")
    async def adapters(identifier: str) -> list[dict[str, Any]]:
        await projects.get(identifier)
        return [
            adapter_status(name)
            for name in ("zendesk", "intercom", "freshdesk", "salesforce", "slack", "webhook")
        ]

    @router.get("/api/v1/projects/{identifier}/integrations/routes")
    async def list_routes(identifier: str) -> list[dict[str, Any]]:
        project = await projects.get(identifier)
        rules = await _routes(project.id)
        return [rule.model_dump(mode="json") for rule in rules]

    @router.post(
        "/api/v1/projects/{identifier}/integrations/{integration_id}/routes", status_code=201
    )
    async def create_route(
        identifier: str, integration_id: str, body: RouteCreate
    ) -> dict[str, Any]:
        if body.match_choice.upper() == "UNKNOWN":
            raise HTTPException(
                status_code=400,
                detail="UNKNOWN routing is fixed to escalation; it cannot be configured",
            )
        project = await projects.get(identifier)
        async with sessions() as session:
            exists = await session.execute(
                sa.text("SELECT 1 FROM project_integrations WHERE id = :iid AND project_id = :pid"),
                {"iid": integration_id, "pid": str(project.id)},
            )
            if exists.first() is None:
                raise HTTPException(status_code=404, detail="Integration not found")
        rule_id = str(uuid4())
        async with sessions.begin() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO integration_routes"
                    " (id, project_id, integration_id, match_choice, action,"
                    "  action_value, created_at)"
                    " VALUES (:id, :pid, :iid, :match, :action, :value, :created)"
                ),
                {
                    "id": rule_id,
                    "pid": str(project.id),
                    "iid": integration_id,
                    "match": body.match_choice.upper(),
                    "action": body.action,
                    "value": body.action_value,
                    "created": datetime.now(UTC),
                },
            )
        return {
            "id": rule_id,
            "match_choice": body.match_choice.upper(),
            "action": body.action,
            "action_value": body.action_value,
        }

    @router.post("/api/v1/projects/{identifier}/webhooks/{source}", status_code=201)
    async def source_webhook(
        identifier: str,
        source: str,
        body: SourceDelivery,
        request: Request,
        response: Response,
    ) -> dict[str, Any]:
        """Source-keyed webhook: bearer env token → observation → classify → route.

        Safe routing: UNKNOWN always escalates to human triage; known choices
        apply the configured rule. Outcomes are simulated records, never sends.
        """
        project = await projects.get(identifier)
        integration = await _integration_by_source(project.id, source)
        if integration is None:
            raise HTTPException(status_code=404, detail=f"No '{source}' integration configured")
        token_env = f"OPENCLASS_WEBHOOK_TOKEN_{source.upper().replace('-', '_')}"
        expected = os.environ.get(token_env, "")
        provided = request.headers.get("authorization", "")
        if not expected or provided != f"Bearer {expected}":
            raise HTTPException(status_code=401, detail="Invalid webhook token")

        # Idempotent receipts (0010 pattern): same key+content → replay, key
        # with different content → conflict.
        import hashlib

        fingerprint = hashlib.sha256(body.content.encode()).hexdigest()
        async with sessions() as session:
            prior = await session.execute(
                sa.text(
                    "SELECT event_id, fingerprint FROM webhook_receipts"
                    " WHERE project_id = :pid AND integration_id = :iid AND event_key = :key"
                ),
                {"pid": str(project.id), "iid": integration["id"], "key": body.event_key},
            )
            existing = prior.first()
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise HTTPException(
                    status_code=409, detail="Event key reused with different content"
                )
            response.status_code = 200
            return {
                "deduplicated": True,
                "event_id": existing.event_id,
                "routed": False,
                "simulated": True,
            }

        event, _deduped = await projects.ingest_event(
            identifier=identifier,
            content=body.content,
            source_type="webhook",
            metadata={"source": source, **body.metadata},
        )
        async with sessions.begin() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO webhook_receipts"
                    " (project_id, integration_id, event_key, fingerprint,"
                    "  event_id, source, created_at)"
                    " VALUES (:pid, :iid, :key, :fp, :eid, :source, :created)"
                ),
                {
                    "pid": str(project.id),
                    "iid": integration["id"],
                    "key": body.event_key,
                    "fp": fingerprint,
                    "eid": str(event.id),
                    "source": source,
                    "created": datetime.now(UTC),
                },
            )

        # Classify with the project's first decision service, then route.
        services = await projects.list_decision_services(identifier=identifier)
        selected = "UNKNOWN"
        if services:
            from openclass_core.decision_executor import DecisionExecutor

            executor = DecisionExecutor(decision_provider)  # type: ignore[arg-type]
            fetched = await projects.get_event(identifier, event.id)
            run = await executor.execute(fetched, services[0])
            await projects.record_decision_run(run)
            selected = run.selected_choice
        rules = await _routes(project.id)
        outcome = decide_routing(rules, selected)
        async with sessions.begin() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO routing_outcomes"
                    " (id, project_id, integration_id, event_id, selected_choice, action, detail, created_at)"
                    " VALUES (:id, :pid, :iid, :eid, :choice, :action, :detail, :created)"
                ),
                {
                    "id": str(uuid4()),
                    "pid": str(project.id),
                    "iid": integration["id"],
                    "eid": str(event.id),
                    "choice": selected,
                    "action": outcome["action"],
                    "detail": json.dumps(outcome),
                    "created": datetime.now(UTC),
                },
            )
        return {
            "event_id": str(event.id),
            "selected_choice": selected,
            "routing": outcome,
            "routed": True,
            "simulated": True,
        }

    @router.get("/api/v1/projects/{identifier}/integrations/outcomes")
    async def routing_outcomes(identifier: str) -> list[dict[str, Any]]:
        project = await projects.get(identifier)
        async with sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT selected_choice, action, detail, created_at"
                    " FROM routing_outcomes WHERE project_id = :pid"
                    " ORDER BY created_at DESC LIMIT 50"
                ),
                {"pid": str(project.id)},
            )
            return [
                {
                    "selected_choice": row.selected_choice,
                    "action": row.action,
                    "detail": json.loads(row.detail) if isinstance(row.detail, str) else row.detail,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    return router
