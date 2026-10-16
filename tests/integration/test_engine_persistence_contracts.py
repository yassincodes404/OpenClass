"""Engine contracts on migrated SQLite and disposable, real PostgreSQL.

Faults are injected *after* writes have flushed, not before the first mutation.
Every PostgreSQL test uses OPENCLASS_TEST_DATABASE_URL; never a developer DB.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from openclass_core.evidence import FeedbackAction
from openclass_core.projects import DecisionRun, ProjectAuditEvent, ProjectService
from openclass_core.repositories import ConflictError, NotFoundError
from openclass_server.main import create_app
from openclass_server.persistence.database import create_database_engine
from openclass_server.persistence.idempotency import IdempotencyStore, request_hash
from openclass_server.persistence.project_repository import SQLProjectRepository
from openclass_server.persistence.tables import (
    DecisionRunCheckpointRow,
    DecisionRunRow,
    EvidenceCaseRow,
    EvidenceItemRow,
    IdempotencyKeyRow,
    ProviderUsageRow,
    RunFeedbackRow,
)
from openclass_server.settings import EXPECTED_SCHEMA_REVISION, Settings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def contract_url(request: pytest.FixtureRequest) -> str:
    return request.getfixturevalue(
        "postgres_url" if request.param == "postgres" else "database_url"
    )


@asynccontextmanager
async def persistence(
    url: str,
) -> AsyncIterator[tuple[SQLProjectRepository, ProjectService]]:
    engine = create_database_engine(Settings(database_url=url), poolclass=sa.pool.NullPool)
    try:
        repository = SQLProjectRepository(async_sessionmaker(engine, expire_on_commit=False))
        yield repository, ProjectService(repository)
    finally:
        await engine.dispose()


async def fixture_run(repo: SQLProjectRepository, *, unknown: bool = True):
    service = ProjectService(repo)
    project = await service.create(f"Contract {uuid4()}")
    event, _ = await service.ingest_event(str(project.id), "retained source observation")
    decision = await service.create_decision_service(
        str(project.id),
        "Router",
        "Choose conservatively.",
        choices=[{"key": "KNOWN", "label": "Known"}],
    )
    run = DecisionRun(
        project_id=project.id,
        raw_event_id=event.id,
        decision_service_id=decision.id,
        decision_node_id=decision.nodes[0].id,
        decision_service_version_id=decision.active_version_id,
        provider="mock",
        model="model-a",
        execution_mode="mock",
        real_inference=False,
        selected_choice="UNKNOWN" if unknown else "KNOWN",
        probabilities={"UNKNOWN": 1.0 if unknown else 0.0, "KNOWN": 0.0 if unknown else 1.0},
        top_probability=1.0,
        margin=1.0,
        unknown_probability=1.0 if unknown else 0.0,
        supervision_outcome="UNKNOWN" if unknown else "TRUSTED",
        supervision_reason="simulated test fixture",
        latency_ms=10.0,
        input_snapshot={"content": event.content, "content_hash": event.content_hash},
        instructions_snapshot=decision.instructions,
        choices_snapshot=[],
    )
    return service, project, event, decision, run


async def count(repo: SQLProjectRepository, row, project_id: UUID) -> int:
    async with repo.sessions() as session:
        return int(
            await session.scalar(
                sa.select(sa.func.count()).select_from(row).where(row.project_id == str(project_id))
            )
            or 0
        )


async def test_run_evidence_usage_checkpoint_and_audit_roll_back(contract_url, monkeypatch):
    async with persistence(contract_url) as (repo, _):
        service, project, event, _, run = await fixture_run(repo)
        before = await repo.count_audit_events(project.id)
        original = repo.create_evidence_item

        async def fail_after_flush(item, audit):
            await original(item, audit)
            raise RuntimeError("injected after evidence insert")

        monkeypatch.setattr(repo, "create_evidence_item", fail_after_flush)
        with pytest.raises(RuntimeError, match="injected"):
            await service.record_decision_run(run)
        for table in (DecisionRunRow, DecisionRunCheckpointRow, EvidenceItemRow, ProviderUsageRow):
            assert await count(repo, table, project.id) == 0
        assert await repo.count_audit_events(project.id) == before
        assert (await repo.get_raw_event(project.id, event.id)).content == event.content


async def test_feedback_and_evidence_roll_back_together(contract_url, monkeypatch):
    async with persistence(contract_url) as (repo, _):
        service, project, _, _, run = await fixture_run(repo, unknown=False)
        await service.record_decision_run(run)
        before = await repo.count_audit_events(project.id)
        original = repo.create_evidence_item

        async def fail_after_flush(item, audit):
            await original(item, audit)
            raise RuntimeError("injected after correction evidence")

        monkeypatch.setattr(repo, "create_evidence_item", fail_after_flush)
        with pytest.raises(RuntimeError, match="injected"):
            await service.submit_run_feedback(
                str(project.id), run.id, FeedbackAction.CORRECT, corrected_choice="UNKNOWN"
            )
        assert await count(repo, RunFeedbackRow, project.id) == 0
        assert await count(repo, EvidenceItemRow, project.id) == 0
        assert await repo.count_audit_events(project.id) == before
        assert (await repo.get_decision_run(project.id, run.id)).selected_choice == "KNOWN"


async def test_batch_bulk_write_is_one_transaction(contract_url, monkeypatch):
    async with persistence(contract_url) as (repo, _):
        service = ProjectService(repo)
        project = await service.create(f"Batch {uuid4()}")
        original = repo.create_raw_events

        async def fail_after_flush(events):
            await original(events)
            raise RuntimeError("injected after batch insert")

        with monkeypatch.context() as patch:
            patch.setattr(repo, "create_raw_events", fail_after_flush)
            with pytest.raises(RuntimeError, match="injected"):
                await service.ingest_events_batch(
                    str(project.id), [{"content": "one"}, {"content": "two"}]
                )
        assert await repo.count_raw_events(project.id) == 0
        results = await service.ingest_events_batch(
            str(project.id), [{"content": "one"}, {"content": "one"}, {"content": "two"}]
        )
        assert [deduped for _, deduped in results] == [False, True, False]
        assert results[0][0].id == results[1][0].id
        assert await repo.count_raw_events(project.id) == 2

        async def no_individual_lookup(*args, **kwargs):
            pytest.fail("batch deduplication must use a set-based SQL lookup")

        monkeypatch.setattr(repo, "get_raw_event_by_hash", no_individual_lookup)
        repeated = await service.ingest_events_batch(
            str(project.id), [{"content": "one"}, {"content": "two"}]
        )
        assert all(deduped for _, deduped in repeated)


async def test_case_creation_and_multi_attachment_roll_back(contract_url):
    async with persistence(contract_url) as (repo, _):
        service, project, _, _, run = await fixture_run(repo)
        evidence = await service.record_decision_run(run)
        assert evidence is not None
        before = await repo.count_audit_events(project.id)
        # The first attachment flushes before the second ID fails lookup.
        missing = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        with pytest.raises(NotFoundError):
            await service.create_evidence_case(
                str(project.id), "Incomplete case", evidence_ids=[evidence.id, missing]
            )
        assert await count(repo, EvidenceCaseRow, project.id) == 0
        assert (await repo.get_evidence_item(project.id, evidence.id)).evidence_case_id is None
        assert await repo.count_audit_events(project.id) == before
        case = await service.create_evidence_case(str(project.id), "Existing case")
        before = await repo.count_audit_events(project.id)
        with pytest.raises(NotFoundError):
            await service.add_evidence_items_to_case(
                str(project.id), case.id, [evidence.id, missing]
            )
        assert (await repo.get_evidence_item(project.id, evidence.id)).evidence_case_id is None
        assert await repo.count_audit_events(project.id) == before


@pytest.mark.parametrize("attachment", ["existing", "create"])
@pytest.mark.parametrize("terminal_status", ["resolved", "dismissed"])
async def test_http_case_attachments_preserve_ready_evidence_and_terminal_unknown(
    contract_url, attachment, terminal_status
):
    from openclass_server.persistence.unknown_triage import UnknownTriageStore

    async with persistence(contract_url) as (repo, service):
        _, project, _, _, run = await fixture_run(repo)
        evidence = await service.record_decision_run(run)
        assert evidence is not None
    settings = Settings(
        database_url=contract_url, decision_provider="mock", rate_limits_enabled=False
    )
    with TestClient(create_app(settings)) as client:
        base = f"/api/v1/projects/{project.id}"
        for target in ("triaged", "ready_for_evolution"):
            response = client.post(
                f"{base}/evidence/{evidence.id}/transition",
                json={"target_status": target},
            )
            assert response.status_code == 200, response.text
        response = client.post(f"{base}/unknowns/{run.id}/transition", json={"to": terminal_status})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == terminal_status

        if attachment == "existing":
            case = client.post(f"{base}/evidence-cases", json={"title": "Existing case"})
            assert case.status_code == 201, case.text
            case_id = case.json()["id"]
            response = client.post(
                f"{base}/evidence-cases/{case_id}/evidence",
                json={"evidence_ids": [str(evidence.id)]},
            )
            assert response.status_code == 200, response.text
        else:
            response = client.post(
                f"{base}/evidence-cases",
                json={"title": "New case", "evidence_ids": [str(evidence.id)]},
            )
            assert response.status_code == 201, response.text
            case_id = response.json()["id"]
        members = client.get(f"{base}/evidence-cases/{case_id}/evidence")
        assert members.status_code == 200, members.text
        assert [item["id"] for item in members.json()] == [str(evidence.id)]
        assert members.json()[0]["status"] == "ready_for_evolution"

    async with persistence(contract_url) as (repo, _):
        stored = await repo.get_evidence_item(project.id, evidence.id)
        assert stored.status == "ready_for_evolution"
        assert stored.evidence_case_id == UUID(case_id)
        assert (
            await UnknownTriageStore(repo._session_factory).get(run.id)
        ).status == terminal_status
        assert (await repo.get_decision_run(project.id, run.id)).selected_choice == "UNKNOWN"


async def test_concurrent_feedback_has_one_evidence_and_retains_both_feedbacks(contract_url):
    async with persistence(contract_url) as (repo, _):
        service, project, _, _, run = await fixture_run(repo, unknown=False)
        await service.record_decision_run(run)
        # Separate repository instances: an instance-local asyncio lock cannot
        # make this test pass on PostgreSQL.
        other = SQLProjectRepository(repo._session_factory)
        feedbacks = await asyncio.gather(
            *[
                ProjectService(repository).submit_run_feedback(
                    str(project.id),
                    run.id,
                    FeedbackAction.CORRECT,
                    corrected_choice="UNKNOWN",
                    note=f"review {index}",
                )
                for index, repository in enumerate((repo, other))
            ]
        )
        assert len({feedback.id for feedback in feedbacks}) == 2
        assert await count(repo, RunFeedbackRow, project.id) == 2
        assert await count(repo, EvidenceItemRow, project.id) == 1
        assert (
            sum(
                event.event_type == "evidence.created"
                for event in await repo.audit_events(project.id)
            )
            == 1
        )


async def test_request_identity_concurrency_failure_expiry_and_restart(contract_url):
    async with persistence(contract_url) as (repo, _):
        service = ProjectService(repo)
        project = await service.create(f"Idempotency {uuid4()}")
        key = "parallel-reservation"
        path = f"/api/v1/projects/{project.id}/events"
        calls = 0

        async def operation():
            nonlocal calls
            calls += 1
            event, deduped = await service.ingest_event(str(project.id), "atomic source")
            return {"id": str(event.id), "deduped": deduped}

        async def execute(store, *, body=None, method="POST", route=path, callback=operation):
            return await store.execute(
                project.id,
                key,
                method=method,
                path=route,
                body=body or {"content": "atomic source", "metadata": {"b": 2, "a": 1}},
                ttl_hours=24,
                operation=callback,
            )

        stores = [IdempotencyStore(repo._session_factory) for _ in range(4)]
        replies = await asyncio.gather(*[execute(store) for store in stores])
        assert calls == 1
        assert sorted(replayed for _, replayed in replies) == [False, True, True, True]
        assert len({reply["id"] for reply, _ in replies}) == 1
        assert request_hash("post", path, {"a": 1, "b": 2}) == request_hash(
            "POST", path, {"b": 2, "a": 1}
        )
        for mismatch in (
            {"body": {"content": "changed"}},
            {"method": "PATCH"},
            {"route": path + "/batch"},
        ):
            with pytest.raises(ConflictError):
                await execute(stores[0], **mismatch)

        async def fail_after_ingest():
            await service.ingest_event(str(project.id), "should roll back")
            raise RuntimeError("injected response failure")

        async with repo.sessions.begin() as session:
            await session.execute(
                sa.update(IdempotencyKeyRow)
                .where(
                    IdempotencyKeyRow.project_id == str(project.id),
                    IdempotencyKeyRow.key == key,
                )
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        with pytest.raises(RuntimeError, match="injected"):
            await execute(stores[0], callback=fail_after_ingest)
        assert await repo.count_raw_events(project.id) == 1
        reused, replayed = await execute(stores[0], body={"content": "replacement"})
        assert replayed is False

    # Reopen a completely new engine/store: no process-local reservation state.
    async with persistence(contract_url) as (restarted, _):

        async def must_not_run():
            pytest.fail("restart must replay the committed response")

        reply, replayed = await IdempotencyStore(restarted._session_factory).execute(
            project.id,
            key,
            method="POST",
            path=path,
            body={"content": "replacement"},
            ttl_hours=24,
            operation=must_not_run,
        )
        assert replayed is True
        assert reply == reused


async def test_usage_is_model_sensitive_and_errors_have_safe_history(contract_url):
    async with persistence(contract_url) as (repo, _):
        service, project, _, _, run = await fixture_run(repo, unknown=False)
        await service.record_decision_run(run)
        await service.record_decision_run(
            run.model_copy(update={"id": uuid4(), "model": "model-b"})
        )
        await repo.record_provider_error(project.id, "mock", "model-b", 20.0)
        rows = await repo.provider_usage(project.id, "2020-01-01", "2100-01-01")
        by_model = {row["model"]: row for row in rows}
        assert set(by_model) == {"model-a", "model-b"}
        assert (by_model["model-a"]["calls"], by_model["model-a"]["errors"]) == (1, 0)
        assert (by_model["model-b"]["calls"], by_model["model-b"]["errors"]) == (1, 1)
        events = [
            e
            for e in await repo.audit_events(project.id)
            if e.event_type == "decision.provider_failed"
        ]
        assert len(events) == 1
        assert events[0].payload == {"provider": "mock", "model": "model-b", "latency_ms": 20.0}


async def test_unknown_sql_filter_precedes_paging_and_analytics_do_not_scan_payloads(
    contract_url,
    monkeypatch,
):
    async with persistence(contract_url) as (repo, _):
        service, project, _, _, template = await fixture_run(repo)
        old = datetime.now(UTC) - timedelta(days=1)
        # 251 eligible runs are hidden behind 1,001 newer known runs.
        async with repo.transaction():
            for index in range(1252):
                unknown = index < 251
                run = template.model_copy(
                    update={
                        "id": uuid4(),
                        "created_at": old if unknown else datetime.now(UTC),
                        "selected_choice": "UNKNOWN" if unknown else "KNOWN",
                        "supervision_outcome": "UNKNOWN" if unknown else "TRUSTED",
                        "latency_ms": float(index + 1),
                    }
                )
                await repo.create_decision_run(run)
        first = await repo.list_decision_runs(project.id, 200, unknown_only=True)
        second = await repo.list_decision_runs(project.id, 200, 200, unknown_only=True)
        assert len(first) == 200 and len(second) == 51
        assert len({run.id for run in first + second}) == 251
        assert [str(run.id) for run in first] == sorted(
            [str(run.id) for run in first + second], reverse=True
        )[:200]
        assert all(run.selected_choice == "UNKNOWN" for run in first + second)

        async def no_payload_scan(*args, **kwargs):
            pytest.fail("analytics must use SQL, not legacy full run/audit scans")

        monkeypatch.setattr(repo, "analytics_runs", no_payload_scan)
        monkeypatch.setattr(repo, "audit_events", no_payload_scan)
        metrics = await repo.analytics_summary(project.id)
        assert metrics["total_runs"] == 1252 and metrics["unknown_runs"] == 251
        assert metrics["p50_latency_ms"] == 626.0
        assert metrics["p95_latency_ms"] == 1190.0
        assert (await service.summary(str(project.id))).decision_runs == 1252
        stats = await repo.unknown_statistics(project.id)
        assert (stats["total_unknown"], stats["total_runs"]) == (251, 1252)
        assert stats["by_status"] == {"needs_evidence": 251}


@pytest.mark.parametrize(
    ("choice", "outcome", "expected_choice", "expected_outcome"),
    [
        (None, None, "UNKNOWN", "UNKNOWN"),
        ("KNOWN", "UNKNOWN", "KNOWN", "UNKNOWN"),
        ("UNKNOWN", "TRUSTED", "UNKNOWN", "TRUSTED"),
        ("KNOWN", "TRUSTED", "KNOWN", "TRUSTED"),
    ],
)
async def test_checkpoint_sql_eligibility_agrees_with_returned_decisions(
    contract_url, choice, outcome, expected_choice, expected_outcome
):
    from openclass_core.unknown_pool import run_is_unknown

    async with persistence(contract_url) as (repo, _):
        service, project, _, _, run = await fixture_run(repo)
        await service.record_decision_run(run)
        async with repo.sessions.begin() as session:
            if choice is None:
                await session.execute(
                    sa.delete(DecisionRunCheckpointRow).where(
                        DecisionRunCheckpointRow.run_id == str(run.id)
                    )
                )
            else:
                await session.execute(
                    sa.update(DecisionRunCheckpointRow)
                    .where(DecisionRunCheckpointRow.run_id == str(run.id))
                    .values(selected_choice=choice, supervision_outcome=outcome)
                )
        effective = await repo.get_decision_run(project.id, run.id)
        assert effective.selected_choice == expected_choice
        assert effective.supervision_outcome == expected_outcome
        DecisionRun.model_validate(effective.model_dump())
        listed = await service.list_unknown_runs(str(project.id), limit=1)
        assert [item.id for item in listed] == ([run.id] if run_is_unknown(effective) else [])
        assert all(run_is_unknown(item) for item in listed)


@pytest.mark.parametrize("field", ["selected_choice", "supervision_outcome"])
async def test_checkpoint_decisions_cannot_be_cleared_to_null(contract_url, field):
    async with persistence(contract_url) as (repo, _):
        service, project, _, _, run = await fixture_run(repo)
        await service.record_decision_run(run)
        with pytest.raises(sa.exc.IntegrityError):
            async with repo.sessions.begin() as session:
                await session.execute(
                    sa.update(DecisionRunCheckpointRow)
                    .where(DecisionRunCheckpointRow.run_id == str(run.id))
                    .values(**{field: None})
                )
        effective = await repo.get_decision_run(project.id, run.id)
        assert (effective.selected_choice, effective.supervision_outcome) == ("UNKNOWN", "UNKNOWN")


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
async def test_history_rejects_sql_mutation_and_parent_deletion(contract_url, operation):
    async with persistence(contract_url) as (repo, _):
        service, project, _, _, run = await fixture_run(repo)
        await service.record_decision_run(run)
        feedback = await service.submit_run_feedback(str(project.id), run.id, FeedbackAction.NOTE)
        for table, identifier in (("decision_runs", run.id), ("run_feedback", feedback.id)):
            with pytest.raises(sa.exc.DBAPIError):
                async with repo.sessions.begin() as session:
                    statement = (
                        f"UPDATE {table} SET payload = payload WHERE id = :id"
                        if operation == "UPDATE"
                        else f"DELETE FROM {table} WHERE id = :id"
                    )
                    await session.execute(sa.text(statement), {"id": str(identifier)})
        with pytest.raises(sa.exc.DBAPIError):
            async with repo.sessions.begin() as session:
                await session.execute(
                    sa.text("DELETE FROM projects WHERE id = :id"), {"id": str(project.id)}
                )
        assert await repo.count_decision_runs(project.id) == 1


def test_http_changed_body_and_cross_route_key_conflict(mock_client):
    project = mock_client.post("/api/v1/projects", json={"name": "HTTP identity"}).json()["id"]
    base = f"/api/v1/projects/{project}/events"
    headers = {"Idempotency-Key": "identity"}
    assert mock_client.post(base, headers=headers, json={"content": "first"}).status_code == 201
    assert mock_client.post(base, headers=headers, json={"content": "changed"}).status_code == 409
    assert (
        mock_client.post(
            base + "/batch", headers=headers, json={"items": [{"content": "first"}]}
        ).status_code
        == 409
    )
    assert len(mock_client.get(base).json()) == 1


async def test_http_unknown_paging_and_uncapped_evidence_sync(contract_url):
    async with persistence(contract_url) as (repo, _):
        service, project, _, _, template = await fixture_run(repo)
        old = datetime.now(UTC) - timedelta(days=1)
        first_id = None
        async with repo.transaction():
            for _index in range(251):
                run = template.model_copy(update={"id": uuid4(), "created_at": old})
                await service.record_decision_run(run)
                first_id = first_id or run.id
            for _index in range(251):
                run = template.model_copy(
                    update={
                        "id": uuid4(),
                        "selected_choice": "KNOWN",
                        "supervision_outcome": "TRUSTED",
                    }
                )
                await repo.create_decision_run(run)
        assert first_id is not None
        # Select the last eligible item by stable database ordering. Its evidence
        # is outside any 200-item scan, regardless of tied timestamps.
        last = (await repo.list_decision_runs(project.id, 1, 250, unknown_only=True))[0]
        evidence = await repo.get_evidence_for_run(project.id, last.id)
        assert evidence is not None
    settings = Settings(
        database_url=contract_url, decision_provider="mock", rate_limits_enabled=False
    )
    with TestClient(create_app(settings)) as client:
        base = f"/api/v1/projects/{project.id}/unknowns"
        page = client.get(base, params={"limit": 200}).json()
        rest = client.get(base, params={"limit": 200, "offset": page["next_cursor"]}).json()
        assert len(page["items"]) == 200 and len(rest["items"]) == 51
        assert rest["next_cursor"] is None
        transitioned = client.post(f"{base}/{last.id}/transition", json={"to": "triaged"})
        assert transitioned.status_code == 200, transitioned.text
        ev = client.get(f"/api/v1/projects/{project.id}/evidence/{evidence.id}").json()
        assert ev["status"] == "triaged"
        filtered = client.get(base, params={"state": "triaged", "limit": 1}).json()
        assert [item["run_id"] for item in filtered["items"]] == [str(last.id)]
        assert client.get(base + "/stats").json()["total_unknown"] == 251


async def test_mixed_schema_alembic_check(contract_url):
    engine = create_database_engine(Settings(database_url=contract_url), poolclass=sa.pool.NullPool)
    control = f"control_contract_{uuid4().hex}"
    try:
        async with engine.connect() as connection:
            await connection.execute(sa.text(f"CREATE TABLE {control} (id INTEGER PRIMARY KEY)"))
            await connection.commit()

            def check(sync):
                config = Config("alembic.ini")
                config.attributes["connection"] = sync
                command.check(config)

            await connection.run_sync(check)
            revision = await connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
            assert revision == EXPECTED_SCHEMA_REVISION
    finally:
        async with engine.begin() as connection:
            await connection.execute(sa.text(f"DROP TABLE IF EXISTS {control}"))
        await engine.dispose()


@asynccontextmanager
async def migration_engine(url, tmp_path):
    """A fresh SQLite file or an agent-created isolated PostgreSQL schema."""
    if url.startswith("sqlite"):
        engine = create_database_engine(
            Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
        )
        try:
            yield engine
        finally:
            await engine.dispose()
        return
    admin = create_async_engine(url, poolclass=sa.pool.NullPool)
    schema = f"engine_contract_{uuid4().hex}"
    async with admin.begin() as connection:
        await connection.execute(sa.text(f"CREATE SCHEMA {schema}"))
    engine = create_async_engine(
        url,
        poolclass=sa.pool.NullPool,
        # Do not include public: its alembic_version must never be mistaken
        # for the isolated schema's migration state.
        connect_args={"server_settings": {"search_path": schema}},
    )
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            # This schema was created above solely for this test.
            await connection.execute(sa.text(f"DROP SCHEMA {schema} CASCADE"))
        await admin.dispose()


async def migrate(engine, revision):
    async with engine.connect() as connection:

        def upgrade(sync):
            config = Config("alembic.ini")
            config.attributes["connection"] = sync
            command.upgrade(config, revision)

        await connection.run_sync(upgrade)


async def test_populated_0028_upgrade_preserves_history_checkpoint_usage_and_legacy_keys(
    contract_url,
    tmp_path,
    monkeypatch,
):
    from openclass_server.persistence.tables import (
        ClassifierRow,
        ObservationRow,
        OntologyRow,
        RunRow,
        UnknownRow,
    )

    async with migration_engine(contract_url, tmp_path) as engine:
        await migrate(engine, "0028_checkpoint_revision_and_lease_fencing")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        repo = SQLProjectRepository(factory)
        service, project, _, _, run = await fixture_run(repo)

        async def old_rollup(*args, **kwargs):
            # The legacy index lacks model, so seed its actual recorded rollup
            # rather than calling the post-upgrade upsert against old DDL.
            return None

        with monkeypatch.context() as patch:
            patch.setattr(repo, "_roll_up_usage", old_rollup)
            evidence = await service.record_decision_run(run)
        assert evidence is not None
        await service.submit_run_feedback(str(project.id), run.id, FeedbackAction.NOTE)
        classifier_id, ontology_id, observation_id, classification_id, unknown_id = (
            str(uuid4()) for _ in range(5)
        )
        async with factory.begin() as session:
            session.add(ClassifierRow(id=classifier_id, slug="legacy-classifier", payload={}))
            session.add(ObservationRow(id=observation_id, payload={"retained": "observation"}))
            await session.flush()
            session.add(
                OntologyRow(
                    id=ontology_id,
                    classifier_id=classifier_id,
                    version_number=1,
                    parent_version_id=None,
                    payload={},
                )
            )
            await session.flush()
            session.add(
                RunRow(
                    id=classification_id,
                    observation_id=observation_id,
                    classifier_id=classifier_id,
                    ontology_version_id=ontology_id,
                    payload={"retained": "classification"},
                )
            )
            await session.flush()
            session.add(
                UnknownRow(
                    id=unknown_id,
                    classifier_id=classifier_id,
                    run_id=classification_id,
                    payload={"retained": "UNKNOWN"},
                )
            )
            session.add(
                ProviderUsageRow(
                    project_id=str(project.id),
                    provider="mock",
                    model="legacy-recorded-model",
                    usage_date=datetime.now(UTC).date(),
                    calls=7,
                    errors=2,
                    input_tokens=100,
                    output_tokens=50,
                    estimated_cost=1.25,
                    latency_ms_total=75.0,
                )
            )
        # Legacy identity cannot be inferred from the response. Preserve the
        # record, fail closed while live, and allow ordinary expiry reuse.
        async with factory.begin() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO idempotency_keys "
                    "(project_id, key, response_hash, response, created_at, expires_at) "
                    "VALUES (:pid, 'legacy-key', :hash, :response, :created, :expires)"
                ),
                {
                    "pid": str(project.id),
                    "hash": "0" * 64,
                    "response": '{"old": true}',
                    "created": datetime.now(UTC),
                    "expires": datetime.now(UTC) + timedelta(hours=24),
                },
            )
        tables = (
            "observations",
            "classification_runs",
            "unknown_events",
            "raw_events",
            "decision_runs",
            "run_feedback",
            "audit_events",
            "service_versions",
            "decision_run_checkpoints",
            "evidence_items",
            "provider_usage",
        )

        async def snapshot():
            async with engine.connect() as connection:
                return {
                    table: [
                        tuple(row)
                        for row in await connection.execute(
                            sa.text(f"SELECT * FROM {table} ORDER BY 1")
                        )
                    ]
                    for table in tables
                }

        before = await snapshot()
        await migrate(engine, "head")
        assert await snapshot() == before
        with pytest.raises(ConflictError, match="legacy identity"):
            await IdempotencyStore(factory).execute(
                project.id,
                "legacy-key",
                method="POST",
                path="/events",
                body={},
                ttl_hours=24,
                operation=lambda: asyncio.sleep(0, result={}),
            )
        rows = await repo.provider_usage(project.id, "2020-01-01", "2100-01-01")
        assert rows[0]["model"] == "legacy-recorded-model"
        assert (rows[0]["calls"], rows[0]["errors"], rows[0]["estimated_cost"]) == (7, 2, 1.25)
        for table in (
            "observations",
            "classification_runs",
            "unknown_events",
            "decision_runs",
            "run_feedback",
        ):
            for operation in ("UPDATE", "DELETE"):
                with pytest.raises(sa.exc.DBAPIError):
                    async with factory.begin() as session:
                        await session.execute(
                            sa.text(
                                f"UPDATE {table} SET payload = payload"
                                if operation == "UPDATE"
                                else f"DELETE FROM {table}"
                            )
                        )
        with pytest.raises(ConflictError):
            await repo.create_evidence_item(
                evidence.model_copy(update={"id": uuid4()}),
                ProjectAuditEvent(
                    project_id=project.id,
                    event_type="evidence.created",
                    actor="test",
                ),
            )


async def test_duplicate_legacy_evidence_blocks_upgrade_without_silent_data_loss(
    contract_url,
    tmp_path,
    monkeypatch,
):
    async with migration_engine(contract_url, tmp_path) as engine:
        await migrate(engine, "0028_checkpoint_revision_and_lease_fencing")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        repo = SQLProjectRepository(factory)
        service, project, _, _, run = await fixture_run(repo)

        async def old_rollup(*args, **kwargs):
            return None

        monkeypatch.setattr(repo, "_roll_up_usage", old_rollup)
        evidence = await service.record_decision_run(run)
        assert evidence is not None
        await repo.create_evidence_item(
            evidence.model_copy(update={"id": uuid4(), "human_note": "retained second history"}),
            ProjectAuditEvent(
                project_id=project.id,
                event_type="evidence.created",
                actor="legacy",
            ),
        )
        before = await repo.count_audit_events(project.id)
        with pytest.raises(RuntimeError, match="duplicate decision_run_id evidence"):
            await migrate(engine, "head")
        assert await count(repo, EvidenceItemRow, project.id) == 2
        assert await repo.count_audit_events(project.id) == before
        async with engine.connect() as connection:
            assert (
                await connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "0028_checkpoint_revision_and_lease_fencing"
            )
            columns = await connection.run_sync(
                lambda sync: sa.inspect(sync).get_columns("idempotency_keys")
            )
            assert "request_hash" not in {column["name"] for column in columns}


async def test_joined_failure_is_rollback_only_and_tasks_cannot_share_a_session(contract_url):
    async with persistence(contract_url) as (repo, service):
        project = await service.create(f"Rollback only {uuid4()}")
        with pytest.raises(RuntimeError, match="must roll back"):
            async with repo.transaction():
                await service.ingest_event(str(project.id), "outer write")
                try:
                    async with repo.transaction():
                        await service.ingest_event(str(project.id), "inner write")
                        raise ValueError("caught by intermediate caller")
                except ValueError:
                    pass
        assert await repo.count_raw_events(project.id) == 0
        async with repo.transaction():
            with pytest.raises(RuntimeError, match="concurrent tasks"):
                await asyncio.create_task(repo.get_project(str(project.id)))


async def test_locked_legacy_candidate_approval_revalidates_and_has_one_winner(contract_url):
    from openclass_core.models import (
        Candidate,
        Classifier,
        DiscoveryProposalType,
        DomainEvent,
        OntologyClass,
        OntologyVersion,
    )
    from openclass_server.persistence.repository import SQLRepository
    from openclass_server.persistence.tables import CandidateRow

    async with persistence(contract_url) as (projects, _):
        repository = SQLRepository(projects._session_factory)
        classifier_id = uuid4()
        initial = OntologyVersion(
            classifier_id=classifier_id,
            version_number=1,
            created_by="test",
            classes=(OntologyClass(canonical_name="billing", display_name="Billing"),),
        )
        classifier = Classifier(
            id=classifier_id,
            slug=f"approval-{uuid4().hex}",
            name="Approval fixture",
            active_ontology_version_id=initial.id,
        )
        event = DomainEvent(
            classifier_id=classifier.id,
            type="OntologyCreated",
            actor="test",
            payload={},
        )
        await repository.create_classifier(classifier, initial, event)
        candidate = Candidate(
            classifier_id=classifier.id,
            base_ontology_version_id=initial.id,
            proposal_type=DiscoveryProposalType.NEW_CLASS,
            canonical_name="refund",
            display_name="Refund",
            confidence=0.9,
            rationale="Persistence fixture",
            discovery_provider="mock",
            discovery_model="simulated",
            evidence_ids=(uuid4(),),
            evaluation_passed=True,
        )
        # Seed an already-evaluated record to exercise persistence revalidation;
        # no HTTP/domain evaluation or promotion gate is bypassed in production.
        async with repository.sessions.begin() as session:
            session.add(
                CandidateRow(
                    id=str(candidate.id),
                    classifier_id=str(classifier.id),
                    base_ontology_version_id=str(initial.id),
                    payload=candidate.model_dump(mode="json"),
                )
            )
        proposed = OntologyVersion(
            classifier_id=classifier.id,
            version_number=2,
            parent_version_id=initial.id,
            created_by="test",
            classes=(
                *initial.classes,
                OntologyClass(
                    canonical_name="refund",
                    display_name="Refund",
                ),
            ),
        )
        with pytest.raises(ConflictError, match="changed before approval"):
            await repository.approve_candidate(
                candidate.model_copy(update={"canonical_name": "tampered"}),
                proposed,
                classifier,
                (),
            )
        contenders = (repository, SQLRepository(projects._session_factory))
        outcomes = await asyncio.gather(
            *[
                contender.approve_candidate(candidate, proposed, classifier, ())
                for contender in contenders
            ],
            return_exceptions=True,
        )
        assert sum(value is None for value in outcomes) == 1
        assert sum(isinstance(value, ConflictError) for value in outcomes) == 1
        assert len(await repository.versions(classifier.id)) == 2
        assert (await repository.get_candidate(classifier.id, candidate.id)).status == "approved"


def test_http_atomic_idempotency_across_independent_apps_and_restart(contract_url):
    from concurrent.futures import ThreadPoolExecutor

    settings = Settings(
        database_url=contract_url,
        decision_provider="mock",
        rate_limits_enabled=False,
    )
    with TestClient(create_app(settings)) as client:
        project = client.post(
            "/api/v1/projects", json={"name": f"Concurrent HTTP {uuid4()}"}
        ).json()["id"]
    path = f"/api/v1/projects/{project}/events/batch"
    headers = {"Idempotency-Key": "parallel-batch"}
    body = {"items": [{"content": "one"}, {"content": "two"}]}

    def deliver(_):
        with TestClient(create_app(settings)) as client:
            response = client.post(path, headers=headers, json=body)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=4) as executor:
        replies = list(executor.map(deliver, range(4)))
    assert sorted(status for status, _ in replies) == [200, 200, 200, 207]
    assert (
        len({tuple(entry["event"]["id"] for entry in payload["items"]) for _, payload in replies})
        == 1
    )
    with TestClient(create_app(settings)) as client:
        replay = client.post(path, headers=headers, json=body)
        assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
        assert (
            client.post(
                path,
                headers=headers,
                json={
                    "items": [{"content": "changed"}],
                },
            ).status_code
            == 409
        )
        assert len(client.get(f"/api/v1/projects/{project}/events").json()) == 2


async def test_locked_idempotency_replay_and_run_commit_recheck_workspace(contract_url):
    from openclass_core.projects import reset_current_workspace_id, set_current_workspace_id

    async with persistence(contract_url) as (repo, service):
        _, project, _, _, run = await fixture_run(repo)
        await repo.claim_unassigned_project(str(project.id), "tenant-a")
        with pytest.raises(NotFoundError):
            await service.record_decision_run(run)
        store = IdempotencyStore(repo._session_factory)
        token = set_current_workspace_id("tenant-a")
        try:
            await store.execute(
                project.id,
                "tenant-key",
                method="POST",
                path="/events",
                body={},
                ttl_hours=24,
                operation=lambda: asyncio.sleep(0, result={"private": True}),
            )
        finally:
            reset_current_workspace_id(token)
        token = set_current_workspace_id("tenant-b")
        try:
            with pytest.raises(NotFoundError):
                await store.execute(
                    project.id,
                    "tenant-key",
                    method="POST",
                    path="/events",
                    body={},
                    ttl_hours=24,
                    operation=lambda: asyncio.sleep(0, result={}),
                )
        finally:
            reset_current_workspace_id(token)
        assert await repo.count_decision_runs(project.id) == 0


async def test_evidence_transitions_synchronize_unknown_state_without_scans(contract_url):
    from openclass_core.evidence import EvidenceStatus
    from openclass_server.persistence.unknown_triage import UnknownTriageStore

    async with persistence(contract_url) as (repo, service):
        _, project, _, _, run = await fixture_run(repo)
        evidence = await service.record_decision_run(run)
        assert evidence is not None
        triage = UnknownTriageStore(repo._session_factory)
        await service.transition_evidence(str(project.id), evidence.id, EvidenceStatus.TRIAGED)
        assert (await triage.get(run.id)).status == "triaged"
        await service.transition_evidence(str(project.id), evidence.id, EvidenceStatus.DISMISSED)
        assert (await triage.get(run.id)).status == "dismissed"
        assert (await repo.get_decision_run(project.id, run.id)).selected_choice == "UNKNOWN"


async def test_unknown_transition_fault_rolls_back_triage_evidence_and_audit(
    contract_url,
    monkeypatch,
):
    from openclass_server.persistence.unknown_triage import UnknownTriageStore

    async with persistence(contract_url) as (repo, service):
        _, project, _, _, run = await fixture_run(repo)
        evidence = await service.record_decision_run(run)
        assert evidence is not None
        before = await repo.count_audit_events(project.id)
    original = UnknownTriageStore.append_audit

    async def fail_after_append(self, *args, **kwargs):
        await original(self, *args, **kwargs)
        raise RuntimeError("injected after triage audit")

    monkeypatch.setattr(UnknownTriageStore, "append_audit", fail_after_append)
    settings = Settings(
        database_url=contract_url,
        decision_provider="mock",
        rate_limits_enabled=False,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.post(
            f"/api/v1/projects/{project.id}/unknowns/{run.id}/transition",
            json={"to": "triaged"},
        )
        assert response.status_code == 500
    async with persistence(contract_url) as (repo, _):
        assert (await repo.get_evidence_item(project.id, evidence.id)).status == "pending"
        assert await UnknownTriageStore(repo._session_factory).get(run.id) is None
        assert await repo.count_audit_events(project.id) == before


async def test_failed_upgrade_restores_foreign_keys_on_reacquired_physical_connection(
    tmp_path,
    monkeypatch,
):
    url = f"sqlite+aiosqlite:///{tmp_path / 'pooled-legacy.db'}"
    engine = create_database_engine(Settings(database_url=url), pool_size=1, max_overflow=0)
    try:
        await migrate(engine, "0028_checkpoint_revision_and_lease_fencing")
        repo = SQLProjectRepository(async_sessionmaker(engine, expire_on_commit=False))
        service, project, _, _, run = await fixture_run(repo)

        async def old_rollup(*args, **kwargs):
            return None

        monkeypatch.setattr(repo, "_roll_up_usage", old_rollup)
        evidence = await service.record_decision_run(run)
        assert evidence is not None
        await repo.create_evidence_item(
            evidence.model_copy(update={"id": uuid4()}),
            ProjectAuditEvent(project_id=project.id, event_type="evidence.created", actor="legacy"),
        )
        async with engine.connect() as connection:
            physical = await connection.run_sync(lambda sync: id(sync.connection.driver_connection))
        with pytest.raises(RuntimeError, match="duplicate decision_run_id evidence"):
            await migrate(engine, "head")
        async with engine.connect() as connection:
            assert (
                await connection.run_sync(lambda sync: id(sync.connection.driver_connection))
                == physical
            )
            assert await connection.scalar(sa.text("PRAGMA foreign_keys")) == 1
            with pytest.raises(sa.exc.IntegrityError, match="FOREIGN KEY"):
                await connection.execute(
                    sa.update(EvidenceItemRow)
                    .where(EvidenceItemRow.id == str(evidence.id))
                    .values(project_id=str(uuid4()))
                )
            await connection.rollback()
        async with engine.connect() as connection:
            assert await connection.scalar(sa.text("PRAGMA foreign_keys")) == 1
            assert await connection.scalar(
                sa.select(EvidenceItemRow.project_id).where(EvidenceItemRow.id == str(evidence.id))
            ) == str(project.id)
    finally:
        await engine.dispose()


async def test_http_unknown_detail_and_listing_have_the_same_recurrence(contract_url):
    async with persistence(contract_url) as (repo, service):
        _, project, _, _, run = await fixture_run(repo)
        await service.record_decision_run(run)
        await service.record_decision_run(run.model_copy(update={"id": uuid4()}))
    with TestClient(
        create_app(
            Settings(
                database_url=contract_url,
                decision_provider="mock",
                rate_limits_enabled=False,
            )
        )
    ) as client:
        base = f"/api/v1/projects/{project.id}/unknowns"
        listing = client.get(base)
        assert listing.status_code == 200, listing.text
        assert len(listing.json()["items"]) == 2
        for item in listing.json()["items"]:
            detail = client.get(f"{base}/{item['run_id']}")
            assert detail.status_code == 200, detail.text
            assert detail.json()["recurrence"] == item["recurrence"] == 2


async def test_usage_latency_averages_all_attempts_and_exposes_empty_denominators(contract_url):
    async with persistence(contract_url) as (repo, service):
        _, project, _, _, run = await fixture_run(repo, unknown=False)
        await service.record_decision_run(run)  # 10 ms success
        await repo.record_provider_error(project.id, run.provider, run.model, 20.0)
        await repo.record_provider_error(project.id, run.provider, "error-only", 20.0)
        async with repo.sessions.begin() as session:
            session.add(
                ProviderUsageRow(
                    project_id=str(project.id),
                    provider=run.provider,
                    model="empty",
                    usage_date=datetime.now(UTC).date(),
                    calls=0,
                    errors=0,
                    input_tokens=0,
                    output_tokens=0,
                    estimated_cost=0.0,
                    latency_ms_total=0.0,
                )
            )
        rows = {
            row["model"]: row
            for row in await repo.provider_usage(project.id, "2020-01-01", "2100-01-01")
        }
        assert rows[run.model]["avg_latency_ms"] == 15.0
        assert rows[run.model]["attempts"] == 2
        assert rows[run.model]["latency_basis"] == "attempt"
        assert rows["error-only"]["avg_latency_ms"] == 20.0
        assert rows["error-only"]["attempts"] == 1
        assert rows["empty"]["avg_latency_ms"] is None
        assert rows["empty"]["attempts"] == 0


async def test_exact_cost_windows_do_not_attribute_whole_boundary_days(contract_url):
    async with persistence(contract_url) as (repo, service):
        _, project, _, _, template = await fixture_run(repo, unknown=False)
        boundary = datetime(2026, 5, 25, 12, tzinfo=UTC)
        for stamp, amount in (
            (boundary - timedelta(hours=3), 100.0),
            (boundary - timedelta(hours=1), 2.0),  # inclusive lower boundary
            (boundary - timedelta(minutes=30), 3.0),
            (boundary, 50.0),  # exclusive upper boundary
        ):
            await service.record_decision_run(
                template.model_copy(
                    update={
                        "id": uuid4(),
                        "created_at": stamp,
                        "provider_metadata": {"estimated_cost": amount},
                    }
                )
            )
        measured = await repo.run_measurements(
            str(project.id),
            boundary - timedelta(hours=1),
            boundary,
        )
        assert measured.cost == measured.cost_window.declared_cost == 5.0
        assert measured.cost_window.status == "complete"
        assert measured.cost_window.timestamped_attempts == 2
        previous = await repo.run_measurements(
            str(project.id),
            boundary - timedelta(hours=4),
            boundary - timedelta(hours=1),
        )
        assert previous.cost == 100.0
        following = await repo.run_measurements(
            str(project.id),
            boundary,
            boundary + timedelta(hours=1),
        )
        assert following.cost == 50.0
        empty = await repo.run_measurements(
            str(project.id),
            boundary - timedelta(hours=2),
            boundary - timedelta(hours=1),
        )
        assert empty.cost == 0.0
        assert empty.cost_window.status == "complete"
        assert empty.cost_window.timestamped_attempts == 0
        assert (await repo.provider_usage(project.id, "2026-05-25", "2026-05-25"))[0][
            "estimated_cost"
        ] == 155.0  # daily endpoint remains explicitly daily
        await service.record_decision_run(
            template.model_copy(
                update={
                    "id": uuid4(),
                    "created_at": boundary - timedelta(minutes=15),
                    "provider_metadata": {},
                }
            )
        )
        partial = await repo.run_measurements(
            str(project.id),
            boundary - timedelta(hours=1),
            boundary,
        )
        assert partial.cost is None
        assert partial.cost_window.status == "partial"
        assert partial.cost_window.declared_cost == 5.0
        assert partial.cost_window.missing_cost_attempts == 1
        assert partial.cost_window.reasons == ("declared_cost_missing",)


async def test_cost_missing_failure_charges_are_unknown_not_free(contract_url):
    async with persistence(contract_url) as (repo, service):
        _, project, _, _, template = await fixture_run(repo, unknown=False)
        now = datetime.now(UTC)
        await service.record_decision_run(
            template.model_copy(
                update={
                    "created_at": now - timedelta(hours=3),
                    "provider_metadata": {},
                }
            )
        )
        priced = template.model_copy(
            update={
                "id": uuid4(),
                "created_at": now - timedelta(seconds=30),
                "provider_metadata": {"estimated_cost": 2.0},
            }
        )
        await service.record_decision_run(priced)
        before_error = await repo.run_measurements(
            str(project.id),
            now - timedelta(minutes=1),
            now + timedelta(minutes=1),
        )
        assert before_error.cost == 2.0  # missing price outside cohort is irrelevant
        await repo.record_provider_error(project.id, template.provider, template.model, 20.0)
        after_error = await repo.run_measurements(
            str(project.id),
            now - timedelta(minutes=1),
            now + timedelta(minutes=1),
        )
        assert after_error.cost is None
        assert after_error.cost_window.status == "partial"
        assert after_error.cost_window.declared_cost == 2.0
        assert after_error.cost_window.timestamped_attempts == 2
        assert after_error.cost_window.missing_cost_attempts == 1
        assert after_error.cost_window.legacy_unlocated_attempts == 0
        other = await service.create(f"Unpriced failures {uuid4()}")
        await repo.record_provider_error(other.id, "mock", "error-only", 20.0)
        unpriced = await repo.run_measurements(
            str(other.id),
            now - timedelta(minutes=1),
            now + timedelta(minutes=1),
        )
        assert unpriced.cost is None and unpriced.cost_window.status == "unavailable"
        assert unpriced.cost_window.declared_cost == 0.0
        assert unpriced.cost_window.missing_cost_attempts == 1


async def test_legacy_daily_cost_has_no_invented_exact_timestamp_or_zero_price(contract_url):
    async with persistence(contract_url) as (repo, service):
        project = await service.create(f"Legacy costs {uuid4()}")
        now = datetime.now(UTC)
        async with repo.sessions.begin() as session:
            session.add(
                ProviderUsageRow(
                    project_id=str(project.id),
                    provider="legacy",
                    model="recorded-model",
                    usage_date=now.date(),
                    calls=1,
                    errors=1,
                    input_tokens=10,
                    output_tokens=3,
                    estimated_cost=99.0,
                    latency_ms_total=30.0,
                )
            )
        measured = await repo.run_measurements(
            str(project.id),
            now - timedelta(minutes=1),
            now + timedelta(minutes=1),
        )
        assert measured.cost is None
        assert measured.cost_window.status == "unavailable"
        assert measured.cost_window.declared_cost == 0.0
        assert measured.cost_window.timestamped_attempts == 0
        assert measured.cost_window.legacy_unlocated_attempts == 2
        assert measured.cost_window.reasons == ("legacy_attempt_timestamps_missing",)
        persisted = await repo.provider_usage(project.id, "2020-01-01", "2100-01-01")
        assert persisted[0]["estimated_cost"] == 99.0
        assert (persisted[0]["calls"], persisted[0]["errors"]) == (1, 1)
