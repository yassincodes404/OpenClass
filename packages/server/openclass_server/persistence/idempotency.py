"""Idempotency-key store for mutating routes (engine side, HTTP concern)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from openclass_core.projects import get_current_workspace_id
from openclass_core.repositories import ConflictError, NotFoundError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .tables import IdempotencyKeyRow, ProjectRow
from .unit_of_work import TransactionSessions


def response_hash(response: Any) -> str:
    canonical = json.dumps(response, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def request_hash(method: str, path: str, body: Any) -> str:
    """JSON object ordering is immaterial; array order and content are not."""
    return response_hash({"method": method.upper(), "path": path, "body": body})


class IdempotencyStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = TransactionSessions(sessions)

    async def execute(
        self,
        project_id: UUID,
        key: str,
        *,
        method: str,
        path: str,
        body: Any,
        ttl_hours: int,
        operation: Callable[[], Awaitable[dict[str, Any]]],
    ) -> tuple[dict[str, Any], bool]:
        """Reserve, mutate and persist the reply in one database transaction.

        The project lock provides cross-process serialization on PostgreSQL;
        SQLite uses an immediate writer transaction. A crash releases the lock
        and rolls back both the reservation and all ingestion writes, so there
        is no orphaned pending key and no lease timeout to guess.
        """
        identity = request_hash(method, path, body)
        async with self.sessions.begin() as session:
            project = await session.scalar(
                select(ProjectRow).where(ProjectRow.id == str(project_id)).with_for_update()
            )
            if project is None:
                raise NotFoundError("Project not found")
            workspace_id = project.workspace_id
            if workspace_id is None and isinstance(project.payload, dict):
                legacy_workspace = project.payload.get("workspace_id")
                if isinstance(legacy_workspace, str) and legacy_workspace.strip():
                    workspace_id = legacy_workspace.strip()
            if workspace_id != get_current_workspace_id():
                raise NotFoundError("Project not found")
            row = await session.get(IdempotencyKeyRow, (str(project_id), key))
            # Read the clock after waiting for the lock, not before.
            now_ts = datetime.now(UTC)
            if row is not None:
                expires = row.expires_at
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=UTC)
                if expires > now_ts:
                    if row.request_hash != identity:
                        raise ConflictError(
                            "Idempotency key was used for a different request "
                            "or has unverifiable legacy identity"
                        )
                    assert isinstance(row.response, dict)
                    return row.response, True
            payload = await operation()
            if row is None:
                row = IdempotencyKeyRow(project_id=str(project_id), key=key)
                session.add(row)
            row.request_hash = identity
            row.response_hash = response_hash(payload)
            row.response = payload
            row.created_at = now_ts
            row.expires_at = now_ts + timedelta(hours=ttl_hours)
            return payload, False
