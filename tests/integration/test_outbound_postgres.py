"""Real migrated PostgreSQL enqueue/worker concurrency (hosted CI only)."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from openclass_core.outbound import SendResult
from openclass_core.routing import RoutingRule, evaluate_routing
from openclass_server.main import create_app
from openclass_server.persistence.outbound_store import OutboundStore
from openclass_server.settings import Settings
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.postgres


async def test_postgres_atomic_enqueue_and_stale_owner_recovery(postgres_url, monkeypatch):
    monkeypatch.setenv("TEST_PG_OUTBOUND_TOKEN", "synthetic-pg-outbound")
    with TestClient(
        create_app(Settings(database_url=postgres_url, decision_provider="mock"))
    ) as client:
        project = client.post("/api/v1/projects", json={"name": f"Outbox {uuid4().hex[:8]}"}).json()
        base = f"/api/v1/projects/{project['id']}"
        integration = client.post(
            base + "/integrations",
            json={
                "name": "receiver",
                "type": "rest_api",
                "endpoint": "https://receiver.example/actions",
                "secret_ref": "TEST_PG_OUTBOUND_TOKEN",
                "outbound": {"enabled": True},
            },
        ).json()
        event = client.post(
            base + "/events", json={"content": "Billing", "source_type": "text"}
        ).json()
    engine = create_async_engine(postgres_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = OutboundStore(sessions)
    outcome = evaluate_routing(
        [
            RoutingRule(
                id="route",
                project_id=project["id"],
                integration_id=integration["id"],
                match_choice="BILLING",
                action="tag",
                action_value="billing",
            )
        ],
        "BILLING",
        run_id=str(uuid4()),
        delivery_mode="webhook_verified",
    )
    args = dict(
        project_id=UUID(project["id"]),
        integration_id=integration["id"],
        event_id=event["id"],
        outcome=outcome,
        allow_external=True,
    )
    try:
        enqueued = await asyncio.gather(
            store.record_outcome(**args), OutboundStore(sessions).record_outcome(**args)
        )
        assert sorted(result[1] for result in enqueued) == [False, True]
        now = datetime.now(UTC)
        claims = await asyncio.gather(store.claim(now=now), OutboundStore(sessions).claim(now=now))
        # Disposable CI DB may contain other projects; inspect this delivery's claims.
        own = [c for c in claims if c and c.intent.project_id == UUID(project["id"])]
        assert len(own) == 1
        claim = own[0]
        assert await store.begin_send(claim, now=now)
        await OutboundStore(sessions).recover(now=now + timedelta(seconds=61))
        assert not await store.finish(
            claim, SendResult(status="accepted", code="http_2xx"), now=now + timedelta(seconds=62)
        )
        states = await store.list_states(UUID(project["id"]))
        assert len(states) == 1 and states[0]["state"] == "uncertain"
        with pytest.raises(DBAPIError):
            async with sessions.begin() as session:
                await session.execute(
                    text("UPDATE outbound_deliveries SET intent='{}' WHERE id=:id"),
                    {"id": states[0]["id"]},
                )
        with pytest.raises(DBAPIError):
            async with sessions.begin() as session:
                await session.execute(
                    text("DELETE FROM outbound_delivery_history WHERE delivery_id=:id"),
                    {"id": states[0]["id"]},
                )
    finally:
        await engine.dispose()
