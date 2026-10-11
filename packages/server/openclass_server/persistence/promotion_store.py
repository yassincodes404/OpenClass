"""Ontology version persistence: append-only versions, events, guarded writes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class PromotionStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def ensure_initial_version(self, service_id: UUID, choices: list[dict[str, Any]]) -> int:
        """Backfill v1 from the service's current choices if absent."""
        async with self.sessions.begin() as session:
            existing = await session.execute(
                sa.text(
                    "SELECT version_number FROM service_versions"
                    " WHERE service_id = :sid ORDER BY version_number DESC LIMIT 1"
                ),
                {"sid": str(service_id)},
            )
            latest = existing.scalar()
            if latest is not None:
                return int(latest)
            await session.execute(
                sa.text(
                    "INSERT INTO service_versions"
                    " (id, service_id, version_number, choices, origin,"
                    "  rationale, actor, created_at)"
                    " VALUES (:id, :sid, 1, :choices, 'initial', 'genesis snapshot', 'system', :created)"
                ),
                {
                    "id": str(uuid4()),
                    "sid": str(service_id),
                    "choices": json.dumps(choices),
                    "created": datetime.now(UTC),
                },
            )
            return 1

    async def next_version(
        self,
        service_id: UUID,
        choices: list[dict[str, Any]],
        *,
        origin: str,
        rationale: str,
        actor: str,
    ) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            latest = await session.execute(
                sa.text(
                    "SELECT id, version_number FROM service_versions"
                    " WHERE service_id = :sid ORDER BY version_number DESC LIMIT 1"
                ),
                {"sid": str(service_id)},
            )
            row = latest.first()
            parent_id, parent_number = (row.id, row.version_number) if row else (None, 0)
            version_number = int(parent_number) + 1
            version_id = str(uuid4())
            await session.execute(
                sa.text(
                    "INSERT INTO service_versions"
                    " (id, service_id, version_number, parent_version_id, choices, origin,"
                    "  rationale, actor, created_at)"
                    " VALUES (:id, :sid, :number, :parent, :choices, :origin, :rationale,"
                    "         :actor, :created)"
                ),
                {
                    "id": version_id,
                    "sid": str(service_id),
                    "number": version_number,
                    "parent": parent_id,
                    "choices": json.dumps(choices),
                    "origin": origin,
                    "rationale": rationale,
                    "actor": actor,
                    "created": datetime.now(UTC),
                },
            )
            return {"id": version_id, "version_number": version_number, "parent": parent_number}

    async def record_event(
        self,
        project_id: UUID,
        service_id: UUID,
        event_type: str,
        actor: str,
        to_version: int,
        detail: dict[str, Any],
        from_version: int | None = None,
    ) -> None:
        async with self.sessions.begin() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO service_ontology_events"
                    " (id, project_id, service_id, event_type, actor, from_version,"
                    "  to_version, detail, created_at)"
                    " VALUES (:id, :pid, :sid, :event, :actor, :from, :to, :detail, :created)"
                ),
                {
                    "id": str(uuid4()),
                    "pid": str(project_id),
                    "sid": str(service_id),
                    "event": event_type,
                    "actor": actor,
                    "from": from_version,
                    "to": to_version,
                    "detail": json.dumps(detail),
                    "created": datetime.now(UTC),
                },
            )

    async def list_versions(self, service_id: UUID) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT id, version_number, parent_version_id, choices, origin,"
                    " rationale, actor, created_at FROM service_versions"
                    " WHERE service_id = :sid ORDER BY version_number"
                ),
                {"sid": str(service_id)},
            )
            return [
                {
                    "id": row.id,
                    "version_number": row.version_number,
                    "parent_version_id": row.parent_version_id,
                    "choices": json.loads(row.choices)
                    if isinstance(row.choices, str)
                    else row.choices,
                    "origin": row.origin,
                    "rationale": row.rationale,
                    "actor": row.actor,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    async def version_by_number(
        self, service_id: UUID, version_number: int
    ) -> dict[str, Any] | None:
        versions = await self.list_versions(service_id)
        return next((v for v in versions if v["version_number"] == version_number), None)

    async def update_service_choices(
        self, service_id: UUID, payload_choices: list[dict[str, Any]], payload: dict[str, Any]
    ) -> None:
        """Point the decision service at the promoted choice set (snapshot update)."""
        # The engine choice model forbids extra fields: keep engine-shaped keys.
        engine_choices = [
            {k: v for k, v in choice.items() if k in ("key", "label", "description")}
            for choice in payload_choices
        ]
        payload["nodes"] = payload.get("nodes", [])
        if payload["nodes"]:
            payload["nodes"][0]["choices"] = engine_choices
        async with self.sessions.begin() as session:
            await session.execute(
                sa.text(
                    "UPDATE decision_services SET payload = :payload, updated_at = :now"
                    " WHERE id = :sid"
                ),
                {
                    "payload": json.dumps(payload),
                    "now": datetime.now(UTC),
                    "sid": str(service_id),
                },
            )

    async def list_events(self, project_id: UUID) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT event_type, actor, from_version, to_version, detail, created_at"
                    " FROM service_ontology_events WHERE project_id = :pid"
                    " ORDER BY created_at"
                ),
                {"pid": str(project_id)},
            )
            return [
                {
                    "event": row.event_type,
                    "actor": row.actor,
                    "from_version": row.from_version,
                    "to_version": row.to_version,
                    "detail": json.loads(row.detail) if isinstance(row.detail, str) else row.detail,
                    "created_at": row.created_at,
                }
                for row in rows
            ]
