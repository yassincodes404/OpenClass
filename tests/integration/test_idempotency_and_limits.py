"""Integration tests for Phase 4 boundaries: idempotent ingest and 429 limits."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _make_project(client: TestClient) -> str:
    response = client.post("/api/v1/projects", json={"name": "Idem Co", "description": ""})
    assert response.status_code == 201, response.text
    return response.json()["slug"]


def test_same_idempotency_key_replays_original_response(mock_client: TestClient):
    slug = _make_project(mock_client)
    headers = {"Idempotency-Key": "order-42"}
    first = mock_client.post(
        f"/api/v1/projects/{slug}/events", json={"content": "I was charged twice"}, headers=headers
    )
    assert first.status_code == 201, first.text
    second = mock_client.post(
        f"/api/v1/projects/{slug}/events", json={"content": "I was charged twice"}, headers=headers
    )
    assert second.status_code == 200
    assert second.headers.get("Idempotency-Replayed") == "true"
    assert second.json()["id"] == first.json()["id"]
    listing = mock_client.get(f"/api/v1/projects/{slug}/events")
    ids = [event["id"] for event in listing.json()]
    assert ids.count(first.json()["id"]) == 1  # no duplicate writes


def test_different_key_with_different_content_creates_new_event(mock_client: TestClient):
    slug = _make_project(mock_client)
    first = mock_client.post(
        f"/api/v1/projects/{slug}/events",
        json={"content": "first text"},
        headers={"Idempotency-Key": "a"},
    )
    second = mock_client.post(
        f"/api/v1/projects/{slug}/events",
        json={"content": "second text"},
        headers={"Idempotency-Key": "b"},
    )
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]


def test_batch_ingest_is_idempotent(mock_client: TestClient):
    slug = _make_project(mock_client)
    payload = {"items": [{"content": "one"}, {"content": "two"}], "source_type": "text"}
    first = mock_client.post(
        f"/api/v1/projects/{slug}/events/batch",
        json=payload,
        headers={"Idempotency-Key": "batch-1"},
    )
    assert first.status_code == 207
    second = mock_client.post(
        f"/api/v1/projects/{slug}/events/batch",
        json=payload,
        headers={"Idempotency-Key": "batch-1"},
    )
    assert second.status_code == 200
    assert second.headers.get("Idempotency-Replayed") == "true"
    first_ids = {entry["event"]["id"] for entry in first.json()["items"]}
    second_ids = {entry["event"]["id"] for entry in second.json()["items"]}
    assert first_ids == second_ids
    listing = mock_client.get(f"/api/v1/projects/{slug}/events")
    assert len(listing.json()) == 2


def test_rate_limit_returns_429_with_retry_after(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from openclass_server.main import create_app
    from openclass_server.settings import Settings

    url = f"sqlite+aiosqlite:///{tmp_path / 'rate-limit.db'}"
    monkeypatch.setenv("OPENCLASS_DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    settings = Settings(
        database_url=url,
        decision_provider="mock",
        rate_limit_ingest_per_minute=2,
        rate_limits_enabled=True,
    )
    app = create_app(settings)
    with TestClient(app) as scoped:
        created = scoped.post("/api/v1/projects", json={"name": "Limited Co"})
        assert created.status_code == 201, created.text
        slug = created.json()["slug"]
        statuses = [
            scoped.post(f"/api/v1/projects/{slug}/events", json={"content": f"msg {i}"}).status_code
            for i in range(4)
        ]
        assert statuses[:2] == [201, 201]
        assert 429 in statuses[2:]
        limited = scoped.post(f"/api/v1/projects/{slug}/events", json={"content": "again"})
        assert limited.status_code == 429
        assert int(limited.headers["Retry-After"]) >= 1
        assert "X-RateLimit-Limit" in limited.headers


def test_read_routes_are_not_rate_limited(mock_client: TestClient):
    slug = _make_project(mock_client)
    for _ in range(5):
        assert mock_client.get(f"/api/v1/projects/{slug}/events").status_code == 200


def test_content_deduped_event_records_idempotency_key(mock_client: TestClient):
    slug = _make_project(mock_client)
    first = mock_client.post(
        f"/api/v1/projects/{slug}/events",
        json={"content": "duplicate text"},
        headers={"Idempotency-Key": "key-first"},
    )
    assert first.status_code == 201
    deduped = mock_client.post(
        f"/api/v1/projects/{slug}/events",
        json={"content": "duplicate text"},
        headers={"Idempotency-Key": "key-second"},
    )
    assert deduped.status_code == 200
    assert deduped.json()["id"] == first.json()["id"]
    replayed = mock_client.post(
        f"/api/v1/projects/{slug}/events",
        json={"content": "duplicate text"},
        headers={"Idempotency-Key": "key-second"},
    )
    assert replayed.status_code == 200
    assert replayed.headers.get("Idempotency-Replayed") == "true"
    assert replayed.json()["id"] == first.json()["id"]


async def test_expired_idempotency_key_can_be_refreshed(
    mock_client: TestClient,
    database_url: str,
):
    from datetime import UTC, datetime, timedelta
    from uuid import UUID

    from openclass_server.persistence.idempotency import IdempotencyStore
    from openclass_server.persistence.tables import IdempotencyKeyRow
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    project_resp = mock_client.post(
        "/api/v1/projects", json={"name": "Expiry Co", "description": ""}
    )
    assert project_resp.status_code == 201
    project_id = UUID(project_resp.json()["id"])

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    store = IdempotencyStore(session_factory)
    try:

        async def execute(identity, value):
            async def operation():
                return {"id": value}

            return await store.execute(
                project_id,
                "expiring-key",
                method="POST",
                path="/events",
                body=identity,
                ttl_hours=24,
                operation=operation,
            )

        original, replayed = await execute({"content": "old"}, "old-id")
        assert original == {"id": "old-id"} and replayed is False
        past = datetime.now(UTC) - timedelta(hours=2)
        async with session_factory.begin() as session:
            await session.execute(
                update(IdempotencyKeyRow)
                .where(
                    IdempotencyKeyRow.project_id == str(project_id),
                    IdempotencyKeyRow.key == "expiring-key",
                )
                .values(created_at=past - timedelta(hours=1), expires_at=past)
            )

        record, replayed = await execute({"content": "replacement"}, "refreshed-id")
        assert record == {"id": "refreshed-id"} and replayed is False
        record, replayed = await execute({"content": "replacement"}, "must-not-replace")
        assert record == {"id": "refreshed-id"} and replayed is True
    finally:
        await engine.dispose()
