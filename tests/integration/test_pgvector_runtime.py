"""Distinguish genuine vector functionality from checkpoint concurrency evidence."""

import asyncio

import pytest
from openclass_server.settings import EXPECTED_SCHEMA_REVISION
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.postgres


def test_real_pgvector_operations_index_and_migrated_schema(postgres_url: str) -> None:
    async def verify() -> None:
        engine = create_async_engine(postgres_url)
        try:
            async with engine.begin() as connection:
                version = await connection.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                )
                assert version, "The real pgvector extension must be installed"
                kind = await connection.scalar(
                    text("SELECT typtype::text FROM pg_type WHERE typname = 'vector'")
                )
                assert kind == "b", "A text domain is not the pgvector base type"
                revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
                assert revision == EXPECTED_SCHEMA_REVISION
                distance = await connection.scalar(
                    text("SELECT '[1,0,0]'::vector <=> '[0,1,0]'::vector")
                )
                assert distance == pytest.approx(1.0)
                summed = await connection.scalar(
                    text("SELECT ('[1,2,3]'::vector + '[3,2,1]'::vector)::text")
                )
                assert summed == "[4,4,4]"
                # A disposable relation proves the extension's index operator class,
                # without pretending the application's embedding query uses it yet.
                await connection.execute(
                    text(
                        "CREATE TEMP TABLE vector_verification "
                        "(id integer PRIMARY KEY, embedding vector(3)) ON COMMIT DROP"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO vector_verification VALUES "
                        "(1, '[1,0,0]'), (2, '[0,1,0]'), (3, '[0.9,0.1,0]')"
                    )
                )
                await connection.execute(
                    text(
                        "CREATE INDEX ON vector_verification "
                        "USING hnsw (embedding vector_cosine_ops)"
                    )
                )
                rows = await connection.scalars(
                    text(
                        "SELECT id FROM vector_verification "
                        "ORDER BY embedding <=> '[1,0,0]'::vector LIMIT 3"
                    )
                )
                assert list(rows) == [1, 3, 2]
        finally:
            await engine.dispose()

    asyncio.run(verify())
