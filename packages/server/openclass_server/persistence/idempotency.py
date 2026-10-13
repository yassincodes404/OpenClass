"""Idempotency-key store for mutating routes (engine side, HTTP concern)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def response_hash(response: Any) -> str:
    canonical = json.dumps(response, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class IdempotencyStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def get(self, project_id: UUID, key: str) -> Any | None:
        async with self.sessions() as session:
            row = await session.execute(
                text(
                    "SELECT response, expires_at FROM idempotency_keys"
                    " WHERE project_id = :project_id AND key = :key"
                ),
                {"project_id": str(project_id), "key": key},
            )
            record = row.first()
        if record is None:
            return None
        response, expires_at = record
        expires = datetime.fromisoformat(expires_at) if isinstance(expires_at, str) else expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < datetime.now(UTC):
            return None
        return json.loads(response) if isinstance(response, str) else response

    async def store(self, project_id: UUID, key: str, response: Any, ttl_hours: int) -> None:
        now_ts = datetime.now(UTC)
        async with self.sessions.begin() as session:
            await session.execute(
                text(
                    "INSERT INTO idempotency_keys"
                    " (project_id, key, response_hash, response, created_at, expires_at)"
                    " VALUES (:project_id, :key, :hash, :response, :created_at, :expires_at)"
                    " ON CONFLICT (project_id, key) DO UPDATE SET"
                    " response_hash = EXCLUDED.response_hash,"
                    " response = EXCLUDED.response,"
                    " created_at = EXCLUDED.created_at,"
                    " expires_at = EXCLUDED.expires_at"
                    " WHERE idempotency_keys.expires_at < EXCLUDED.created_at"
                ),
                {
                    "project_id": str(project_id),
                    "key": key,
                    "hash": response_hash(response),
                    "response": json.dumps(response),
                    "created_at": now_ts,
                    "expires_at": now_ts + timedelta(hours=ttl_hours),
                },
            )
