import sqlite3
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from openclass_core.models import ClassificationResult, DomainEvent, Observation
from openclass_server.main import create_app
from openclass_server.persistence.repository import SQLRepository
from openclass_server.settings import Settings
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def test_sqlite_history_rejects_mutations(
    client: TestClient, database_url: str, classifier_body: dict
) -> None:
    client.post("/api/v1/classifiers", json=classifier_body).raise_for_status()
    with sqlite3.connect(database_url.removeprefix("sqlite+aiosqlite:///")) as db:
        for table in ("ontology_versions", "ontology_events"):
            for sql in (f"UPDATE {table} SET payload = '{{}}'", f"DELETE FROM {table}"):
                with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                    db.execute(sql)
                db.rollback()


def test_migration_round_trip_and_metadata_match(database_url: str) -> None:
    config = Config("alembic.ini")
    command.check(config)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)


@pytest.mark.postgres
def test_postgres_api_and_vector(postgres_url: str, classifier_body: dict) -> None:
    classifier_body["slug"] = f"pg-{uuid4().hex}"
    with TestClient(create_app(Settings(database_url=postgres_url))) as client:
        assert client.get("/health/ready").status_code == 200
        client.post("/api/v1/classifiers", json=classifier_body).raise_for_status()
        result = client.post(
            f"/api/v1/classifiers/{classifier_body['slug']}/classify",
            json={"observation": "cancel my plan"},
        )
        assert result.status_code == 200
        assert result.json()["selected_class"] is None
        unknowns = client.get(f"/api/v1/classifiers/{classifier_body['slug']}/unknowns").json()
        assert len(unknowns) == 1
        assert unknowns[0]["classification"]["id"] == result.json()["id"]


@pytest.mark.postgres
async def test_postgres_append_only_and_atomic_rollback(postgres_url: str) -> None:
    # The sync migration fixture runs before the async test opens its own engine.
    engine = create_async_engine(postgres_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    from openclass_core.models import OntologyClass
    from openclass_core.service import ClassificationService
    from openclass_provider_mock import MockDecisionProvider

    repository = SQLRepository(sessions)
    service = ClassificationService(repository, MockDecisionProvider())
    classifier = await service.create_classifier(
        slug=f"atomic-{uuid4().hex}",
        name="Atomic",
        description="",
        classes=(OntologyClass(canonical_name="billing", display_name="Billing"),),
        actor="test",
    )
    result = await service.classify(classifier.slug, Observation(content="billing"))
    for table in ("ontology_versions", "ontology_events"):
        async with engine.connect() as connection:
            with pytest.raises(DBAPIError, match="append-only"):
                await connection.execute(
                    text(f"DELETE FROM {table} WHERE classifier_id = :id"),
                    {"id": str(classifier.id)},
                )
            await connection.rollback()
    observation = Observation(content="new observation")
    new_result = ClassificationResult.model_validate(
        {**result.model_dump(), "id": uuid4(), "observation_id": observation.id}
    )
    # Event references a nonexistent classifier, forcing the entire write to roll back.
    invalid_event = DomainEvent(classifier_id=uuid4(), type="test", actor="test", payload={})
    with pytest.raises(IntegrityError):
        await repository.save_classification(observation, new_result, None, (invalid_event,))
    async with engine.connect() as connection:
        count = await connection.scalar(
            text("SELECT count(*) FROM observations WHERE id = :id"), {"id": str(observation.id)}
        )
        assert count == 0
        assert await connection.scalar(text("SELECT '[1,2,3]'::vector <-> '[1,2,3]'::vector")) == 0
    await engine.dispose()
