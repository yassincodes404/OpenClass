import asyncio
from logging.config import fileConfig

from alembic import context
from openclass_server.persistence.database import create_database_engine
from openclass_server.persistence.tables import Base
from openclass_server.settings import Settings
from sqlalchemy import Connection, pool

config = context.config
if config.config_file_name and config.get_section("loggers"):
    fileConfig(config.config_file_name)


def run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online() -> None:
    engine = create_database_engine(Settings(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=Settings().database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
