import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from openclass_server.persistence.database import create_database_engine
from openclass_server.persistence.tables import Base
from openclass_server.settings import Settings
from sqlalchemy import Connection, pool

config = context.config
if config.config_file_name and config.get_section("loggers"):
    fileConfig(config.config_file_name)


def include_name(
    name: str | None,
    type_: Any,
    parent_names: Any,  # noqa: ARG001
) -> bool:
    if type_ == "table" and name is not None and name.startswith("control_"):
        return False
    return True


def run(connection: Connection) -> None:
    sqlite = connection.dialect.name == "sqlite"
    try:
        if sqlite:
            # SQLite batch recreation drops parent tables. Disable FK actions
            # only here, then validate every retained reference.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            compare_type=True,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()
            if sqlite and connection.exec_driver_sql("PRAGMA foreign_key_check").first():
                raise RuntimeError("Migration left invalid historical foreign-key references")
        if sqlite:
            connection.commit()
    finally:
        if sqlite:
            try:
                # PRAGMA is a no-op inside a physical SQLite transaction.
                # Settle failed migrations before restoring the pooled handle.
                connection.rollback()
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
                connection.commit()
                if enabled != 1:
                    raise RuntimeError("Cannot restore SQLite foreign-key enforcement")
            except BaseException:
                # Never return an unenforced/broken physical handle to a pool.
                connection.invalidate()
                raise


async def online() -> None:
    engine = create_database_engine(Settings(), poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run)
    finally:
        await engine.dispose()


if config.attributes.get("connection") is not None:
    run(config.attributes["connection"])
elif context.is_offline_mode():
    context.configure(
        url=Settings().database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
