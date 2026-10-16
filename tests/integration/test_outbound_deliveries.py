"""Fenced durable delivery: accepted is not business verification."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from openclass_core.outbound import AuthoritativeReceipt, SendResult
from openclass_core.repositories import ConflictError
from openclass_core.routing import RoutingRule, evaluate_routing
from openclass_server.outbound import OutboundDispatcher
from openclass_server.persistence.outbound_store import OutboundStore
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def delivery_setup(mock_client, database_url, monkeypatch):
    monkeypatch.setenv("TEST_OUTBOUND_TOKEN", "synthetic-outbound-token")
    project = mock_client.post("/api/v1/projects", json={"name": "Durable"}).json()
    integration = mock_client.post(
        f"/api/v1/projects/{project['slug']}/integrations",
        json={
            "name": "receiver",
            "type": "rest_api",
            "endpoint": "https://public.example/actions",
            "secret_ref": "TEST_OUTBOUND_TOKEN",
            "outbound": {"enabled": True},
        },
    ).json()
    event = mock_client.post(
        f"/api/v1/projects/{project['slug']}/events",
        json={
            "content": "billing request",
            "source_type": "text",
        },
    ).json()
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = OutboundStore(sessions)
    rule = RoutingRule(
        id="rule",
        project_id=project["id"],
        integration_id=integration["id"],
        match_choice="BILLING",
        action="tag",
        action_value="billing",
    )
    outcome = evaluate_routing([rule], "BILLING", run_id="run", delivery_mode="webhook_verified")
    yield store, sessions, project, integration, event, outcome
    await engine.dispose()


async def enqueue(setup):
    store, _, project, integration, event, outcome = setup
    return await store.record_outcome(
        project_id=UUID(project["id"]),
        integration_id=integration["id"],
        event_id=event["id"],
        outcome=outcome,
        allow_external=True,
    )


async def test_atomic_enqueue_duplicate_conflict_and_rollback(delivery_setup):
    store, sessions, project, integration, event, outcome = delivery_setup
    first, duplicate = await enqueue(delivery_setup)
    assert not duplicate and first["delivery_state"] == "queued"
    assert (await enqueue(delivery_setup))[1]
    with pytest.raises(ConflictError):
        await store.record_outcome(
            project_id=UUID(project["id"]),
            integration_id=integration["id"],
            event_id=event["id"],
            outcome=outcome.model_copy(update={"tag": "changed"}),
            allow_external=True,
        )
    async with sessions() as session:
        assert await session.scalar(text("SELECT count(*) FROM outbound_deliveries")) == 1
        assert await session.scalar(text("SELECT count(*) FROM routing_outcomes")) == 1
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM audit_events WHERE "
                    "json_extract(payload, '$.payload.delivery_event')="
                    "'integration.delivery_queued'"
                )
            )
            == 1
        )
    # Fail the last write and ensure outcome and outbox both roll back.
    async with sessions.begin() as session:
        await session.execute(
            text(
                "CREATE TRIGGER fail_outbound_audit BEFORE INSERT ON audit_events WHEN "
                "json_extract(NEW.payload, '$.payload.delivery_event')="
                "'integration.delivery_queued' "
                "BEGIN SELECT RAISE(ABORT, 'fault'); END"
            )
        )
    from sqlalchemy.exc import IntegrityError

    with pytest.raises((IntegrityError, ConflictError)):
        await store.record_outcome(
            project_id=UUID(project["id"]),
            integration_id=integration["id"],
            event_id=event["id"],
            outcome=outcome.model_copy(
                update={"run_id": "another", "idempotency_key": "another:rule"}
            ),
            allow_external=True,
        )
    async with sessions() as session:
        assert await session.scalar(text("SELECT count(*) FROM outbound_deliveries")) == 1
        assert await session.scalar(text("SELECT count(*) FROM routing_outcomes")) == 1


async def test_accepted_then_timeout_never_blindly_retried_after_restart(delivery_setup):
    store, sessions, *_ = delivery_setup
    await enqueue(delivery_setup)
    calls = []

    class AcceptedThenTimeout:
        async def send(self, claim):
            calls.append(claim.intent.idempotency_key)
            return SendResult(status="ambiguous", code="transport")

    await OutboundDispatcher(store, AcceptedThenTimeout()).drain()
    restarted = OutboundStore(sessions)
    await OutboundDispatcher(restarted, AcceptedThenTimeout()).drain()
    assert len(calls) == 1
    assert (await restarted.list_states())[0]["state"] == "uncertain"
    delivery_id = UUID((await restarted.list_states())[0]["id"])
    intent = await restarted.get_uncertain_intent(delivery_id)
    identity = {"idempotency_key": intent.idempotency_key, "request_hash": intent.request_hash}
    # Negative readback is NOT safe replay authority.
    assert not await restarted.reconcile(
        delivery_id, AuthoritativeReceipt(applied=False, receipt_id="absent", **identity)
    )
    assert not await restarted.reconcile(
        delivery_id,
        AuthoritativeReceipt(
            applied=True, receipt_id="wrong-request", **{**identity, "request_hash": "0" * 64}
        ),
    )

    class Readback:
        async def reconcile(self, captured):
            assert captured == intent
            return AuthoritativeReceipt(applied=True, receipt_id="receiver-confirmed", **identity)

    assert await OutboundDispatcher(restarted, AcceptedThenTimeout()).reconcile(
        delivery_id, Readback()
    )
    assert (await restarted.list_states())[0]["state"] == "sent"


async def test_concurrent_claims_expiry_and_stale_ack_are_fenced(delivery_setup):
    store, sessions, *_ = delivery_setup
    await enqueue(delivery_setup)
    now = datetime.now(UTC)
    results = await asyncio.gather(store.claim(now=now), OutboundStore(sessions).claim(now=now))
    winner = next(item for item in results if item)
    assert sum(item is not None for item in results) == 1
    assert await store.begin_send(winner, now=now)
    await store.recover(now=now + timedelta(seconds=61))
    assert not await store.finish(
        winner, SendResult(status="accepted", code="http_2xx"), now=now + timedelta(seconds=62)
    )
    assert (await store.list_states())[0]["state"] == "uncertain"


async def test_revoked_or_retargeted_configuration_cannot_send(delivery_setup):
    store, sessions, *_ = delivery_setup
    await enqueue(delivery_setup)
    claim = await store.claim()
    async with sessions.begin() as session:
        await session.execute(
            text("UPDATE project_integrations SET endpoint='https://other.example'")
        )
    assert not await store.begin_send(claim)
    assert (await store.list_states())[0]["state"] == "cancelled"


@pytest.mark.parametrize("idempotent,final", [(True, "uncertain"), (False, "uncertain")])
async def test_receiver_contract_controls_retry_and_attempt_exhaustion(
    delivery_setup, idempotent, final
):
    from openclass_server.persistence.tables import ProjectIntegrationRow

    store, sessions, *_ = delivery_setup
    async with sessions.begin() as session:
        from sqlalchemy import update

        await session.execute(
            update(ProjectIntegrationRow).values(
                outbound={"enabled": True, "receiver_enforces_idempotency": idempotent}
            )
        )
    await enqueue(delivery_setup)
    now = datetime.now(UTC)
    keys = []
    for index in range(3 if idempotent else 1):
        claim = await store.claim(now=now)
        keys.append(claim.intent.idempotency_key)
        assert claim.attempt == index + 1
        assert await store.begin_send(claim, now=now)
        assert await store.finish(claim, SendResult(status="ambiguous", code="transport"), now=now)
        now += timedelta(seconds=20)
    assert len(set(keys)) == 1
    assert await store.claim(now=now) is None
    assert (await store.list_states())[0]["state"] == final


async def test_definitely_unsent_exhaustion_fails_and_claimed_restart_is_safe(delivery_setup):
    store, _, *_ = delivery_setup
    await enqueue(delivery_setup)
    now = datetime.now(UTC)
    stale = await store.claim(now=now)
    await store.recover(now=now + timedelta(seconds=61))
    now += timedelta(seconds=70)
    for index in range(3):
        claim = await store.claim(now=now)
        assert claim.attempt == index + 1
        assert not await store.begin_send(stale, now=now)
        assert await store.begin_send(claim, now=now)
        assert await store.finish(claim, SendResult(status="not_sent", code="credential"), now=now)
        now += timedelta(seconds=20)
    assert (await store.list_states())[0]["state"] == "failed"
    assert await store.claim(now=now) is None


async def test_cancellation_keeps_inflight_claim_and_idle_failure_loop_survives(delivery_setup):
    store, _, *_ = delivery_setup
    await enqueue(delivery_setup)
    entered = asyncio.Event()

    class Hanging:
        async def send(self, claim):
            entered.set()
            await asyncio.Event().wait()

    dispatcher = OutboundDispatcher(store, Hanging())
    task = asyncio.create_task(dispatcher.drain())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await store.list_states())[0]["state"] == "sending"
    await store.recover(now=datetime.now(UTC) + timedelta(seconds=61))
    assert (await store.list_states())[0]["state"] == "uncertain"

    class IdleFailure:
        async def recover(self):
            raise OSError("must-not-log-secret")

    task = asyncio.create_task(OutboundDispatcher(IdleFailure(), Hanging()).run(0.01))
    await asyncio.sleep(0.04)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_delivery_identity_and_history_are_database_immutable(delivery_setup):
    from sqlalchemy.exc import IntegrityError

    store, sessions, *_ = delivery_setup
    await enqueue(delivery_setup)
    for statement in (
        "UPDATE outbound_deliveries SET intent='{}'",
        "UPDATE outbound_deliveries SET id='rewritten'",
        "DELETE FROM outbound_deliveries",
        "UPDATE outbound_delivery_history SET code='rewritten'",
        "DELETE FROM outbound_delivery_history",
        "DELETE FROM routing_outcomes",
    ):
        with pytest.raises(IntegrityError):
            async with sessions.begin() as session:
                await session.execute(text(statement))


async def test_http_sender_timeout_redaction_and_no_redirect(delivery_setup):
    import httpx
    from openclass_server.outbound import HTTPOutboundSender

    store, _, *_ = delivery_setup
    await enqueue(delivery_setup)
    claim = await store.claim()
    requests = []

    def accepted_timeout(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer synthetic-outbound-token"
        raise httpx.ReadTimeout("synthetic-outbound-token upstream body", request=request)

    result = await HTTPOutboundSender(transport=httpx.MockTransport(accepted_timeout)).send(claim)
    assert result.status == "ambiguous"
    assert "synthetic" not in result.model_dump_json()

    def redirect(request):
        requests.append(request)
        return httpx.Response(
            302, headers={"Location": "http://127.0.0.1/admin"}, text="synthetic-outbound-token"
        )

    assert (
        await HTTPOutboundSender(transport=httpx.MockTransport(redirect)).send(claim)
    ).status == "ambiguous"
    assert len(requests) == 2

    def accepted_value_error(request):
        raise ValueError("synthetic-outbound-token after-send decode failure")

    result = await HTTPOutboundSender(transport=httpx.MockTransport(accepted_value_error)).send(
        claim
    )
    assert result.status == "ambiguous"


async def test_concurrent_identical_enqueue_replays_once(delivery_setup):
    results = await asyncio.gather(enqueue(delivery_setup), enqueue(delivery_setup))
    assert sorted(item[1] for item in results) == [False, True]


def test_sqlite_migration_roundtrip_metadata_and_legacy_preservation(tmp_path, monkeypatch):
    import sqlite3

    from alembic import command
    from alembic.config import Config
    from openclass_server.persistence.tables import OutboundDeliveryRow, OutboundHistoryRow
    from sqlalchemy import create_engine, inspect

    database = tmp_path / "migration30.db"
    monkeypatch.setenv("OPENCLASS_DATABASE_URL", f"sqlite+aiosqlite:///{database}")
    config = Config("alembic.ini")
    command.upgrade(config, "0029_engine_persistence_contracts")
    with sqlite3.connect(database) as db:
        db.execute(
            "INSERT INTO projects(id,slug,status,name,description,created_at,updated_at,payload) "
            "VALUES ('p','legacy','active','Legacy','','2026-01-01','2026-01-01','{}')"
        )
        db.execute(
            "INSERT INTO project_integrations(id,project_id,name,type,status,capabilities,"
            "metadata_json,created_at,updated_at) VALUES "
            "('i','p','Legacy webhook','webhook','pending','[]','{}','2026-01-01','2026-01-01')"
        )
    command.upgrade(config, "head")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT signature,outbound FROM project_integrations").fetchone() == (
            "{}",
            "{}",
        )
        assert db.execute("SELECT payload FROM projects").fetchone() == ("{}",)
    engine = create_engine(f"sqlite:///{database}")
    try:
        inspector = inspect(engine)
        for model in (OutboundDeliveryRow, OutboundHistoryRow):
            actual = inspector.get_columns(model.__tablename__)
            expected = model.__table__.columns
            assert {c["name"] for c in actual} == set(expected.keys())
            assert {c["name"]: c["nullable"] for c in actual} == {
                c.name: c.nullable for c in expected
            }
            for column in actual:
                declared = expected[column["name"]]
                assert column["type"]._type_affinity == declared.type._type_affinity
                assert getattr(column["type"], "length", None) == getattr(
                    declared.type, "length", None
                )
            assert {
                tuple(f["constrained_columns"])
                for f in inspector.get_foreign_keys(model.__tablename__)
            } == {
                tuple(f.parent.name for f in constraint.elements)
                for constraint in model.__table__.foreign_key_constraints
            }
        assert inspector.get_indexes("outbound_deliveries")[0]["name"] == "ix_outbound_due"
        assert {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("outbound_deliveries")
        } == {
            ("project_id", "idempotency_key"),
            ("outcome_id",),
        }
        integration_columns = {
            item["name"]: item for item in inspector.get_columns("project_integrations")
        }
        for name in ("signature", "outbound"):
            assert integration_columns[name]["nullable"] is False
            assert integration_columns[name]["default"].strip("'") == "{}"
    finally:
        engine.dispose()
    command.downgrade(config, "0029_engine_persistence_contracts")
    command.upgrade(config, "head")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT name FROM project_integrations").fetchone() == ("Legacy webhook",)
        db.execute('UPDATE project_integrations SET signature=\'{"mode":"zendesk"}\'')
    with pytest.raises(RuntimeError, match="lose active"):
        command.downgrade(config, "0029_engine_persistence_contracts")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0030_outbound_deliveries",
        )
        assert db.execute("SELECT signature FROM project_integrations").fetchone() == (
            '{"mode":"zendesk"}',
        )


async def test_populated_outbound_downgrade_refuses_before_ddl(delivery_setup, monkeypatch):
    from alembic import command
    from alembic.config import Config

    await enqueue(delivery_setup)
    with pytest.raises(RuntimeError, match="empty outbound history"):
        await asyncio.to_thread(
            command.downgrade, Config("alembic.ini"), "0029_engine_persistence_contracts"
        )
    store, sessions, *_ = delivery_setup
    assert (await store.list_states())[0]["state"] == "queued"
    async with sessions() as session:
        assert (
            await session.scalar(text("SELECT version_num FROM alembic_version"))
            == "0030_outbound_deliveries"
        )


async def test_existing_api_opt_in_queue_acceptance_and_unknown_denial(
    delivery_setup, mock_client, database_url
):
    import httpx
    from openclass_server.main import create_app
    from openclass_server.outbound import HTTPOutboundSender
    from openclass_server.settings import Settings

    store, sessions, project, integration, event, _ = delivery_setup
    base = f"/api/v1/projects/{project['id']}"
    service = mock_client.post(
        base + "/decision-services",
        json={
            "name": "Router",
            "instructions": "Route.",
            "choices": [{"key": "BILLING", "label": "Billing"}],
        },
    ).json()
    route = mock_client.post(
        f"{base}/integrations/{integration['id']}/routes",
        json={"match_choice": "BILLING", "action": "tag", "action_value": "billing"},
    )
    assert route.status_code == 201
    run = mock_client.post(
        f"{base}/decision-services/{service['id']}/runs", json={"raw_event_ids": [event["id"]]}
    ).json()[0]
    body = {
        "run_id": run["id"],
        "integration_id": integration["id"],
        "delivery_mode": "webhook_verified",
    }
    evaluate = base + "/integrations/routes/evaluate"
    assert mock_client.post(evaluate, json=body).status_code == 409
    # ASGITransport deliberately does not run lifespan: no live dispatcher/network.
    app = create_app(
        Settings(database_url=database_url, decision_provider="mock", outbound_enabled=True)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as enabled:
        response = await enabled.post(evaluate, json=body)
        assert response.status_code == 201, response.text
        assert response.json()["routing"]["delivery_state"] == "queued"
        assert response.json()["simulated"] is False
        assert (await enabled.post(evaluate, json=body)).json()["deduplicated"] is True
        calls = []

        def accepted(request):
            calls.append(request)
            return httpx.Response(204)

        dispatcher = OutboundDispatcher(
            store, HTTPOutboundSender(transport=httpx.MockTransport(accepted))
        )
        assert await dispatcher.drain() == 1
        assert await dispatcher.drain() == 0
        assert len(calls) == 1
        result = (await enabled.get(base + "/integrations/outcomes")).json()[0]
        assert result["delivery_state"] == result["detail"]["delivery_state"] == "sent"
        unknown_event = mock_client.post(
            base + "/events", json={"content": "Something entirely novel", "source_type": "text"}
        ).json()
        unknown = mock_client.post(
            f"{base}/decision-services/{service['id']}/runs",
            json={"raw_event_ids": [unknown_event["id"]]},
        ).json()[0]
        assert unknown["selected_choice"] == "UNKNOWN"
        denied = await enabled.post(evaluate, json={**body, "run_id": unknown["id"]})
        assert denied.status_code == 400
    async with sessions() as session:
        assert await session.scalar(text("SELECT count(*) FROM outbound_deliveries")) == 1
        assert await session.scalar(text("SELECT count(*) FROM routing_outcomes")) == 1
        assert (
            await session.scalar(
                text("SELECT selected_choice FROM decision_runs WHERE id=:id"), {"id": run["id"]}
            )
            == "BILLING"
        )


async def test_reclaimed_idempotent_delivery_rejects_stale_owner_and_changed_claim(delivery_setup):
    from openclass_server.persistence.tables import ProjectIntegrationRow
    from sqlalchemy import update

    store, sessions, *_ = delivery_setup
    async with sessions.begin() as session:
        await session.execute(
            update(ProjectIntegrationRow).values(
                outbound={"enabled": True, "receiver_enforces_idempotency": True}
            )
        )
    await enqueue(delivery_setup)
    now = datetime.now(UTC)
    old = await store.claim(now=now)
    assert await store.begin_send(old, now=now)
    await store.recover(now=now + timedelta(seconds=61))
    now += timedelta(seconds=70)
    new = await store.claim(now=now)
    assert new.token != old.token and new.attempt == 2
    altered = new.model_copy(
        update={"intent": new.intent.model_copy(update={"action_value": "changed"})}
    )
    assert not await store.begin_send(altered, now=now)
    assert await store.begin_send(new, now=now)
    assert not await store.finish(old, SendResult(status="accepted", code="http_2xx"), now=now)
    assert await store.finish(new, SendResult(status="accepted", code="http_2xx"), now=now)
    assert not await store.finish(new, SendResult(status="ambiguous", code="transport"), now=now)
    assert (await store.list_states())[0]["state"] == "sent"


@pytest.mark.parametrize("change", ["delete", "disconnect", "disable", "credential", "archive"])
async def test_revocation_stops_future_attempts(delivery_setup, change):
    store, sessions, *_ = delivery_setup
    await enqueue(delivery_setup)
    claim = await store.claim()
    statements = {
        "delete": "DELETE FROM project_integrations",
        "disconnect": "UPDATE project_integrations SET status='disconnected'",
        "disable": "UPDATE project_integrations SET outbound='{}'",
        "credential": "UPDATE project_integrations SET secret_ref='TEST_OTHER_TOKEN'",
        "archive": "UPDATE projects SET status='archived'",
    }
    async with sessions.begin() as session:
        await session.execute(text(statements[change]))
    assert not await store.begin_send(claim)
    assert (await store.list_states())[0]["state"] == "cancelled"


async def test_legacy_missing_request_hash_never_authorizes_replay(delivery_setup):
    from uuid import NAMESPACE_URL, uuid5

    from openclass_server.persistence.tables import RoutingOutcomeRow

    store, sessions, project, integration, event, outcome = delivery_setup
    async with sessions.begin() as session:
        session.add(
            RoutingOutcomeRow(
                id=str(
                    uuid5(
                        NAMESPACE_URL,
                        f"openclass:route_outcome:{project['id']}:{outcome.idempotency_key}",
                    )
                ),
                project_id=project["id"],
                integration_id=integration["id"],
                event_id=event["id"],
                selected_choice="BILLING",
                action="tag",
                detail=outcome.to_payload(),
                created_at=datetime.now(UTC),
            )
        )
    with pytest.raises(ConflictError, match="legacy"):
        await enqueue(delivery_setup)
    assert await store.list_states() == []


async def test_lowered_attempt_budget_does_not_leave_unclaimable_queue(delivery_setup):
    store, sessions, *_ = delivery_setup
    await enqueue(delivery_setup)
    now = datetime.now(UTC)
    claim = await store.claim(now=now)
    assert await store.begin_send(claim, now=now)
    assert await store.finish(claim, SendResult(status="not_sent", code="credential"), now=now)
    limited = OutboundStore(sessions, max_attempts=1)
    await limited.recover(now=now + timedelta(seconds=20))
    assert (await limited.list_states())[0]["state"] == "uncertain"
    assert await limited.claim(now=now + timedelta(seconds=20)) is None


async def test_batch_bound_and_route_credential_echo(delivery_setup, mock_client):
    store, _, project, integration, event, outcome = delivery_setup
    route = mock_client.post(
        f"/api/v1/projects/{project['id']}/integrations/{integration['id']}/routes",
        json={
            "match_choice": "BILLING",
            "action": "tag",
            "action_value": "synthetic-outbound-token",
        },
    )
    assert route.status_code == 400
    assert "synthetic-outbound-token" not in route.text
    for number in range(3):
        run_id = f"bounded-{number}"
        await store.record_outcome(
            project_id=UUID(project["id"]),
            integration_id=integration["id"],
            event_id=event["id"],
            outcome=outcome.model_copy(
                update={"run_id": run_id, "idempotency_key": f"{run_id}:rule"}
            ),
            allow_external=True,
        )

    class Accepted:
        async def send(self, claim):
            return SendResult(status="accepted", code="http_2xx")

    dispatcher = OutboundDispatcher(store, Accepted(), batch_size=2)
    assert await dispatcher.drain() == 2
    assert sum(item["state"] == "queued" for item in await store.list_states()) == 1
    assert await dispatcher.drain() == 1
    assert await dispatcher.drain() == 0


async def test_revocation_after_ambiguous_attempt_preserves_uncertainty(delivery_setup):
    from openclass_server.persistence.tables import ProjectIntegrationRow
    from sqlalchemy import update

    store, sessions, *_ = delivery_setup
    async with sessions.begin() as session:
        await session.execute(
            update(ProjectIntegrationRow).values(
                outbound={"enabled": True, "receiver_enforces_idempotency": True}
            )
        )
    await enqueue(delivery_setup)
    now = datetime.now(UTC)
    first = await store.claim(now=now)
    assert await store.begin_send(first, now=now)
    assert await store.finish(first, SendResult(status="ambiguous", code="transport"), now=now)
    async with sessions.begin() as session:
        await session.execute(update(ProjectIntegrationRow).values(outbound={"enabled": False}))
    retry = await store.claim(now=now + timedelta(seconds=20))
    assert not await store.begin_send(retry, now=now + timedelta(seconds=20))
    assert (await store.list_states())[0]["state"] == "uncertain"


async def test_definitely_unsent_retry_cannot_erase_an_earlier_ambiguous_send(delivery_setup):
    from openclass_server.persistence.tables import ProjectIntegrationRow
    from sqlalchemy import update

    store, sessions, *_ = delivery_setup
    async with sessions.begin() as session:
        await session.execute(
            update(ProjectIntegrationRow).values(
                outbound={"enabled": True, "receiver_enforces_idempotency": True}
            )
        )
    await enqueue(delivery_setup)
    now = datetime.now(UTC)
    for status in ("ambiguous", "not_sent", "not_sent"):
        claim = await store.claim(now=now)
        assert await store.begin_send(claim, now=now)
        assert await store.finish(
            claim,
            SendResult(status=status, code="transport" if status == "ambiguous" else "credential"),
            now=now,
        )
        now += timedelta(seconds=20)
    assert (await store.list_states())[0]["state"] == "uncertain"
