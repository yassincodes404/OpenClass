"""Triage-state store for the UNKNOWN workspace (engine side)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from openclass_core.projects import ProjectAuditEvent
from openclass_core.unknown_pool import UnknownTriage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class UnknownTriageStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def get(self, run_id: UUID) -> UnknownTriage | None:
        async with self.sessions() as session:
            row = await session.execute(
                sa.text(
                    "SELECT run_id, status, category, assignee, note, updated_at"
                    " FROM unknown_triage WHERE run_id = :run_id"
                ),
                {"run_id": str(run_id)},
            )
            record = row.first()
        if record is None:
            return None
        return UnknownTriage(
            run_id=record.run_id,
            status=record.status,
            category=record.category,
            assignee=record.assignee,
            note=record.note,
            updated_at=record.updated_at,
        )

    async def upsert(self, triage: UnknownTriage) -> UnknownTriage:
        async with self.sessions.begin() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO unknown_triage"
                    " (run_id, status, category, assignee, note, updated_at)"
                    " VALUES (:run_id, :status, :category, :assignee, :note, :updated_at)"
                    " ON CONFLICT (run_id) DO UPDATE SET"
                    " status = excluded.status, category = excluded.category,"
                    " assignee = excluded.assignee, note = excluded.note,"
                    " updated_at = excluded.updated_at"
                ),
                {
                    "run_id": triage.run_id,
                    "status": triage.status,
                    "category": triage.category,
                    "assignee": triage.assignee,
                    "note": triage.note,
                    "updated_at": triage.updated_at or datetime.now(UTC),
                },
            )
        return triage

    async def list_all(self, project_id: UUID) -> dict[str, UnknownTriage]:
        async with self.sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT t.run_id, t.status, t.category, t.assignee, t.note, t.updated_at"
                    " "
                    "FROM unknown_triage t JOIN decision_runs r ON r.id = t.run_id"
                    " WHERE r.project_id = :project_id"
                ),
                {"project_id": str(project_id)},
            )
            return {
                record.run_id: UnknownTriage(
                    run_id=record.run_id,
                    status=record.status,
                    category=record.category,
                    assignee=record.assignee,
                    note=record.note,
                    updated_at=record.updated_at,
                )
                for record in rows
            }

    async def append_audit(
        self,
        project_id: UUID,
        actor: str,
        action: str,
        target: str,
        data: dict[str, object] | None = None,
    ) -> None:
        """Audit entries carry actor/action/target (+ optional ids) — never content."""
        event = ProjectAuditEvent(
            project_id=project_id,
            event_type=cast(Any, action),
            actor=actor,
            payload={"target": target, **(data or {})},
        )
        async with self.sessions.begin() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO audit_events"
                    " (id, project_id, event_type, actor, payload, created_at)"
                    " VALUES (:id, :project_id, :event_type, :actor, :payload, :created_at)"
                ),
                {
                    "id": str(event.id),
                    "project_id": str(event.project_id),
                    "event_type": event.event_type,
                    "actor": event.actor,
                    "payload": json.dumps(event.model_dump(mode="json")),
                    "created_at": event.created_at,
                },
            )

    async def audit_history(
        self, project_id: UUID, event_prefix: str, subject_id: str
    ) -> list[dict[str, Any]]:
        """Ordered audit rows for one subject (e.g. a candidate's transitions)."""
        async with self.sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT event_type, actor, payload, created_at FROM audit_events"
                    " WHERE project_id = :project_id AND event_type LIKE :prefix"
                    " ORDER BY created_at ASC"
                ),
                {"project_id": str(project_id), "prefix": event_prefix + "%"},
            )
            history: list[dict[str, Any]] = []
            for row in rows:
                payload = row.payload
                if isinstance(payload, str):
                    payload = json.loads(payload)
                payload = payload if isinstance(payload, dict) else {}
                inner_payload = (
                    payload["payload"]
                    if "event_type" in payload and isinstance(payload.get("payload"), dict)
                    else payload
                )
                if inner_payload.get("candidate_id") == subject_id:
                    history.append(
                        {
                            "event": row.event_type,
                            "actor": row.actor,
                            "payload": inner_payload,
                            "created_at": row.created_at,
                        }
                    )
            return history
