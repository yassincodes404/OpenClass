"""System diagnostics describe persisted schema health, never inferred model health."""

import time

from fastapi import APIRouter
from openclass_core.models import Model
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from openclass_server.settings import EXPECTED_SCHEMA_REVISION, Settings


class DatabaseHealth(Model):
    connected: bool
    latency_ms: float
    schema_revision: str | None
    migration_current: bool


class SystemHealth(Model):
    status: str
    database: DatabaseHealth
    decision_provider: str
    discovery_provider: str
    version: str


def system_router(config: Settings, engine: AsyncEngine) -> APIRouter:
    router = APIRouter(tags=["system"])

    @router.get("/api/v1/system/health", response_model=SystemHealth)
    async def system_health() -> SystemHealth:
        started = time.perf_counter()
        connected = False
        revision = None
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
                connected = True
                revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        except (SQLAlchemyError, TimeoutError, OSError):
            pass
        current = revision == EXPECTED_SCHEMA_REVISION
        return SystemHealth(
            status="healthy" if connected and current else "unhealthy",
            database=DatabaseHealth(
                connected=connected,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                schema_revision=revision,
                migration_current=current,
            ),
            decision_provider=config.decision_provider,
            discovery_provider=config.discovery_provider,
            version="0.0.1",
        )

    return router
