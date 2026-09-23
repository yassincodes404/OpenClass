"""Database construction shared by the server and migration runner."""

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from openclass_server.settings import Settings


def create_database_engine(settings: Settings, **options: Any) -> AsyncEngine:
    connect_args: dict[str, Any] = {}
    if settings.database_url.startswith("postgresql+asyncpg:"):
        connect_args["timeout"] = settings.database_connect_timeout
    engine = create_async_engine(settings.database_url, connect_args=connect_args, **options)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(connection: Any, record: Any) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine
