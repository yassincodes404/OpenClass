"""Deterministic checkpoint schedules shared by SQLite and PostgreSQL tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from openclass_core.models import ChoiceRequest, ChoiceResult
from openclass_core.providers import DecisionProvider
from openclass_core.repositories import ConflictError
from openclass_server.checkpoint_lease import CheckpointLease
from openclass_server.main import create_app
from openclass_server.persistence import project_repository as repository_module
from openclass_server.settings import Settings
from sqlalchemy.orm import Session

INTERNAL_TOKEN = "checkpoint-test-internal-token"
WORKER_HEADERS = {
    "X-OpenClass-Internal-Token": INTERNAL_TOKEN,
    "X-OpenClass-Actor": "regular-worker",
}
ADMIN_HEADERS = {"X-OpenClass-Role": "admin", "X-OpenClass-Actor": "recovery-admin"}


@dataclass
class CheckpointSchedule:
    app_a: FastAPI
    app_b: FastAPI
    client_a: httpx.AsyncClient
    client_b: httpx.AsyncClient
    project_id: UUID
    service: dict[str, Any]
    run: dict[str, Any]
    project_path: str

    @property
    def run_path(self) -> str:
        return f"{self.project_path}/runs/{self.run['id']}"

    async def persisted(self) -> dict[str, Any]:
        response = await self.client_b.get(self.run_path)
        assert response.status_code == 200, response.text
        return dict(response.json())

    async def audit(self) -> list[dict[str, Any]]:
        response = await self.client_b.get(f"{self.project_path}/audit")
        assert response.status_code == 200, response.text
        return [
            event
            for event in response.json()
            if self.run["id"]
            in (event["payload"].get("run_id"), event["payload"].get("decision_run_id"))
        ]


def _settings(database_url: str, *, ttl: float = 300, auth_required: bool = True) -> Settings:
    return Settings(
        database_url=database_url,
        decision_provider="mock",
        internal_token=INTERNAL_TOKEN,
        auth_required=auth_required,
        decision_run_resume_claim_ttl_seconds=ttl,
    )


@asynccontextmanager
async def checkpoint_schedule(
    database_url: str, *, ttl: float = 300, auth_required: bool = True
) -> AsyncIterator[CheckpointSchedule]:
    """Each side has its own app, engine and repository; only the database is shared."""
    app_a = create_app(_settings(database_url, ttl=ttl, auth_required=auth_required))
    app_b = create_app(_settings(database_url, ttl=ttl, auth_required=auth_required))
    async with (
        app_a.router.lifespan_context(app_a),
        app_b.router.lifespan_context(app_b),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_a),
            base_url="http://testserver",
            headers=WORKER_HEADERS,
        ) as client_a,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_b),
            base_url="http://testserver",
            headers=WORKER_HEADERS,
        ) as client_b,
    ):
        assert app_a.state.project_repository is not app_b.state.project_repository
        assert (
            app_a.state.project_repository.sessions is not app_b.state.project_repository.sessions
        )
        project = await client_a.post(
            "/api/v1/projects", json={"name": f"Checkpoint Schedule {uuid4().hex[:10]}"}
        )
        assert project.status_code == 201, project.text
        project_path = f"/api/v1/projects/{project.json()['slug']}"
        nodes = [
            {
                "name": name,
                "instructions": f"Choose the next action at {name}.",
                "pause_on_review": True,
                "choices": [{"key": key, "label": key} for key in keys],
            }
            for name, keys in (
                ("intake", ("BILLING", "ARCHIVE")),
                ("finance", ("REFUND", "INVOICE")),
                ("compliance", ("CLEARED", "BLOCKED")),
            )
        ]
        service = await client_a.post(
            f"{project_path}/decision-services",
            json={
                "name": "Three checkpoint graph",
                "instructions": "Keep approvals scoped to the actual paused node.",
                "nodes": nodes,
                "transitions": [
                    {
                        "from_node_key": source,
                        "choice_key": choice,
                        "to_node_key": target,
                        "require_approval": True,
                    }
                    for source, choice, target in (
                        ("intake", "BILLING", "finance"),
                        ("finance", "REFUND", "compliance"),
                    )
                ],
            },
        )
        assert service.status_code == 201, service.text
        run = await client_a.post(
            f"{project_path}/decision-services/{service.json()['id']}/runs",
            json={"content": "The weather on Mars is lovely this time of year"},
        )
        assert run.status_code == 201, run.text
        initial = run.json()[0]
        assert (initial["run_status"], initial["current_node_key"]) == ("paused", "intake")
        assert initial["checkpoint_revision"] == 1
        yield CheckpointSchedule(
            app_a,
            app_b,
            client_a,
            client_b,
            UUID(project.json()["id"]),
            service.json(),
            initial,
            project_path,
        )


class GatedProvider:
    def __init__(self, inner: DecisionProvider) -> None:
        self.inner = inner
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.calls = 0

    async def choice(self, request: ChoiceRequest) -> ChoiceResult:
        self.calls += 1
        self.entered.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return await self.inner.choice(request)


class CancellationResistantProvider(GatedProvider):
    """A remote provider can finish even after its local await was cancelled."""

    def __init__(self, inner: DecisionProvider) -> None:
        super().__init__(inner)
        self.finished = asyncio.Event()

    async def choice(self, request: ChoiceRequest) -> ChoiceResult:
        self.calls += 1
        self.entered.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            await self.release.wait()
        try:
            return await self.inner.choice(request)
        finally:
            self.finished.set()


class RepositoryClock:
    """Control SQL clock inputs, retaining real database expiry/CAS expressions."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.current = datetime.now(UTC)
        clock = self

        class ControlledDatetime(datetime):
            @classmethod
            def now(cls, tz: Any = None) -> datetime:
                return clock.current if tz is not None else clock.current.replace(tzinfo=None)

        functions = repository_module.func

        class ControlledSQLFunctions:
            def __getattr__(self, name: str) -> Any:
                return getattr(functions, name)

            def clock_timestamp(self) -> Any:
                return sa.literal(clock.current, type_=sa.DateTime(timezone=True))

            def strftime(self, format_string: str, value: Any) -> Any:
                if isinstance(value, str) and value == "now":
                    value = self.clock_timestamp()
                return functions.strftime(format_string, value)

            def julianday(self, value: Any) -> Any:
                if isinstance(value, str) and value == "now":
                    value = self.clock_timestamp()
                return functions.julianday(value)

        monkeypatch.setattr(repository_module, "datetime", ControlledDatetime)
        monkeypatch.setattr(repository_module, "func", ControlledSQLFunctions())

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


async def _claim(schedule: CheckpointSchedule, *, token: str = "owner-a") -> Any:
    return await schedule.app_a.state.project_repository.claim_decision_run_for_resume(
        schedule.project_id,
        schedule.run["id"],
        operator="worker-a",
        claim_token=token,
        expected_checkpoint_revision=1,
        expected_node_key="intake",
        require_expected_node_match=True,
    )


def test_claim_snapshot_is_materialized_before_commit_and_lock_release(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        async with checkpoint_schedule(database_url) as schedule:
            repo = schedule.app_a.state.project_repository
            committed = False
            snapshots = []
            apply_checkpoint = repo._apply_checkpoint

            def after_commit(session: Session) -> None:
                nonlocal committed
                committed = True

            def capture_snapshot(run: Any, checkpoint: Any) -> Any:
                assert not committed, "Claim snapshot was read after its transaction committed"
                assert repo._claim_lock.locked(), "Claim lock was released before snapshot capture"
                assert sa.inspect(checkpoint).session.in_transaction()
                snapshot = apply_checkpoint(run, checkpoint)
                snapshots.append(snapshot)
                return snapshot

            monkeypatch.setattr(repo, "_apply_checkpoint", capture_snapshot)
            sa.event.listen(Session, "after_commit", after_commit)
            try:
                claimed = await _claim(schedule)
            finally:
                sa.event.remove(Session, "after_commit", after_commit)
                monkeypatch.setattr(repo, "_apply_checkpoint", apply_checkpoint)
            assert committed
            assert snapshots == [claimed]
            assert claimed.claim_token == "owner-a"
            assert claimed.checkpoint_revision == 2
            assert claimed.current_node_key == "intake"
            assert claimed.steps == schedule.run["steps"]

            # Recovery through a different engine cannot mutate the returned snapshot.
            recovered = await schedule.client_b.post(
                f"{schedule.run_path}/recover-checkpoint",
                headers=ADMIN_HEADERS,
                json={"force": True, "operator": "recovery-admin", "rationale": "Snapshot check"},
            )
            assert recovered.status_code == 200, recovered.text
            assert recovered.json()["checkpoint_revision"] == 3
            assert claimed.claim_token == "owner-a" and claimed.checkpoint_revision == 2

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "precondition",
    [
        {"expected_checkpoint_revision": 2},
        {"expected_checkpoint_revision": 99},
        {"expected_node_key": "finance"},
    ],
    ids=["next-generation", "future-generation", "wrong-node"],
)
def test_resume_expected_checkpoint_precondition_is_atomic(
    database_url: str, precondition: dict[str, Any]
) -> None:
    async def scenario() -> None:
        async with checkpoint_schedule(database_url) as schedule:
            before = await schedule.persisted()
            audit_before = await schedule.audit()
            provider = GatedProvider(schedule.app_a.state.decision_provider)
            schedule.app_a.state.decision_provider = provider
            response = await schedule.client_a.post(
                f"{schedule.run_path}/resume",
                json={"approved_choice": "BILLING", "operator": "worker-a", **precondition},
            )
            assert response.status_code == 409, response.text
            assert await schedule.persisted() == before
            assert await schedule.audit() == audit_before
            assert provider.calls == 0

    asyncio.run(scenario())


def test_resume_validates_actual_claimed_node_and_releases_invalid_approval(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even a valid pre-read choice must be rechecked against the claimed snapshot."""

    async def scenario() -> None:
        async with checkpoint_schedule(database_url) as schedule:
            repo = schedule.app_a.state.project_repository
            winner = await schedule.client_b.post(
                f"{schedule.run_path}/resume",
                headers={"X-OpenClass-Actor": "winner"},
                json={"approved_choice": "BILLING", "operator": "winner"},
            )
            assert winner.status_code == 200, winner.text
            assert winner.json()["current_node_key"] == "finance"
            claim = repo.claim_decision_run_for_resume
            read = repo.get_decision_run
            actual_claims = []

            async def stale_node_read(*args: Any, **kwargs: Any) -> Any:
                actual = await read(*args, **kwargs)
                # The caller supplies correct CAS preconditions, but its pre-read view
                # of the node is stale. Only the claim result is authoritative.
                return actual.model_copy(
                    update={
                        "current_node_key": "intake",
                        "decision_node_id": UUID(schedule.service["nodes"][0]["id"]),
                    }
                )

            async def observe_claim(*args: Any, **kwargs: Any) -> Any:
                actual = await claim(*args, **kwargs)
                actual_claims.append(actual)
                return actual

            monkeypatch.setattr(repo, "get_decision_run", stale_node_read)
            monkeypatch.setattr(repo, "claim_decision_run_for_resume", observe_claim)
            provider = GatedProvider(schedule.app_a.state.decision_provider)
            schedule.app_a.state.decision_provider = provider
            response = await schedule.client_a.post(
                f"{schedule.run_path}/resume",
                json={
                    "approved_choice": "BILLING",
                    "operator": "stale-intake-operator",
                    "expected_checkpoint_revision": 3,
                    "expected_node_key": "finance",
                },
            )
            assert response.status_code == 409, response.text
            assert "finance" in response.json()["detail"]
            assert len(actual_claims) == 1
            assert actual_claims[0].current_node_key == "finance"
            assert provider.calls == 0
            persisted = await schedule.persisted()
            assert persisted["run_status"] == "paused"
            assert persisted["claim_token"] is None
            assert persisted["checkpoint_revision"] == 5  # claim and safe release each advance
            assert persisted["resumed_by"] == "winner"
            assert len(persisted["steps"]) == 2
            events = await schedule.audit()
            assert sum(event["event_type"] == "decision_run_resumed" for event in events) == 1
            assert sum(event["event_type"] == "feedback.submitted" for event in events) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("finish", ["approve", "cancel"])
def test_repeated_pauses_require_current_node_and_revision(database_url: str, finish: str) -> None:
    async def scenario() -> None:
        async with checkpoint_schedule(database_url) as schedule:
            first = await schedule.client_a.post(
                f"{schedule.run_path}/resume",
                json={
                    "approved_choice": "BILLING",
                    "operator": "intake-lead",
                    "expected_checkpoint_revision": 1,
                    "expected_node_key": "intake",
                },
            )
            assert first.status_code == 200, first.text
            stage2 = await schedule.persisted()
            assert (stage2["current_node_key"], stage2["checkpoint_revision"]) == ("finance", 3)
            assert len(stage2["steps"]) == 2 and stage2["resumed_at"] is not None
            for body in (
                {"approved_choice": "BILLING"},
                {"approved_choice": "REFUND", "expected_checkpoint_revision": 1},
                {"approved_choice": "REFUND", "expected_node_key": "intake"},
            ):
                rejected = await schedule.client_b.post(
                    f"{schedule.run_path}/resume", json={"operator": "stale-operator", **body}
                )
                assert rejected.status_code == 409, rejected.text
                assert await schedule.persisted() == stage2
            if finish == "cancel":
                cancelled = await schedule.client_b.post(
                    f"{schedule.run_path}/cancel",
                    json={"operator": "finance-lead", "reason": "Withdrawn at second gate"},
                )
                assert cancelled.status_code == 200, cancelled.text
                final = await schedule.persisted()
                assert final["run_status"] == "cancelled"
                assert final["checkpoint_revision"] == 4
                assert final["steps"] == stage2["steps"]
                assert final["pending_operation"] is None
            else:
                for choice, node, revision, next_node, next_revision in (
                    ("REFUND", "finance", 3, "compliance", 5),
                    ("CLEARED", "compliance", 5, "compliance", 7),
                ):
                    approved = await schedule.client_b.post(
                        f"{schedule.run_path}/resume",
                        json={
                            "approved_choice": choice,
                            "operator": f"{node}-lead",
                            "expected_checkpoint_revision": revision,
                            "expected_node_key": node,
                        },
                    )
                    assert approved.status_code == 200, approved.text
                    current = await schedule.persisted()
                    assert current["current_node_key"] == next_node
                    assert current["checkpoint_revision"] == next_revision
                    assert len(current["steps"]) == 3
                final = await schedule.persisted()
                assert final["run_status"] == "completed"
                assert [step["selected_choice"] for step in final["steps"]] == [
                    "BILLING",
                    "REFUND",
                    "CLEARED",
                ]
            duplicate = await schedule.client_a.post(
                f"{schedule.run_path}/resume",
                json={"approved_choice": "REFUND", "operator": "duplicate"},
            )
            assert duplicate.status_code == 409, duplicate.text
            assert await schedule.persisted() == final

    asyncio.run(scenario())


@pytest.mark.parametrize("auth_required", [False, True], ids=["local", "authenticated"])
@pytest.mark.parametrize("privilege", ["role", "scope"])
@pytest.mark.parametrize("endpoint", ["recover-checkpoint", "resume"])
def test_forged_force_privilege_without_internal_token_cannot_mutate_checkpoint(
    database_url: str, auth_required: bool, privilege: str, endpoint: str
) -> None:
    async def scenario() -> None:
        async with checkpoint_schedule(database_url, auth_required=auth_required) as schedule:
            await _claim(schedule)
            before, audit_before = await schedule.persisted(), await schedule.audit()
            forged_headers = {
                "X-OpenClass-Actor": "forged-admin",
                **(
                    {"X-OpenClass-Role": "admin"}
                    if privilege == "role"
                    else {"X-OpenClass-Scopes": "operator checkpoint:force-recover"}
                ),
            }
            body = {"operator": "forged-admin", "rationale": "Untrusted force attempt"}
            body.update(
                {"force": True}
                if endpoint == "recover-checkpoint"
                else {"force_recover_stale_claim": True, "approved_choice": "BILLING"}
            )
            # A fresh client intentionally does not inherit the trusted client's token.
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=schedule.app_b),
                base_url="http://testserver",
                headers=forged_headers,
            ) as untrusted:
                response = await untrusted.post(f"{schedule.run_path}/{endpoint}", json=body)
            assert response.status_code == (401 if auth_required else 403), response.text
            assert await schedule.persisted() == before
            assert await schedule.audit() == audit_before

    asyncio.run(scenario())


@pytest.mark.parametrize("endpoint", ["recover-checkpoint", "resume"])
def test_verified_privileged_force_requires_rationale_and_preserves_actor(
    database_url: str, endpoint: str
) -> None:
    async def scenario() -> None:
        async with checkpoint_schedule(database_url) as schedule:
            await _claim(schedule)
            before = await schedule.persisted()
            body = {"operator": "recovery-admin"}
            body.update(
                {"force": True}
                if endpoint == "recover-checkpoint"
                else {"force_recover_stale_claim": True, "approved_choice": "BILLING"}
            )
            for rationale in ("", "   ", "x"):
                rejected = await schedule.client_b.post(
                    f"{schedule.run_path}/{endpoint}",
                    headers=ADMIN_HEADERS,
                    json={**body, "rationale": rationale},
                )
                assert rejected.status_code == 422, rejected.text
                assert await schedule.persisted() == before
            rationale = "Explicitly preempt wedged upstream worker"
            accepted = await schedule.client_b.post(
                f"{schedule.run_path}/{endpoint}",
                headers=ADMIN_HEADERS,
                json={**body, "rationale": rationale},
            )
            assert accepted.status_code == 200, accepted.text
            events = await schedule.audit()
            force_events = [
                event
                for event in events
                if event["event_type"] == "decision_run_resumed"
                or event["payload"].get("force_recovered")
            ]
            assert force_events
            assert sum(event["event_type"] == "decision_run_resumed" for event in force_events) == (
                1 if endpoint == "resume" else 0
            )
            assert all(event["actor"] == "recovery-admin" for event in force_events)
            assert all(event["payload"]["rationale"] == rationale for event in force_events)
            assert INTERNAL_TOKEN not in str(events)

    asyncio.run(scenario())


def test_renewal_keeps_generation_and_rejects_wrong_revision_or_token(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        async with checkpoint_schedule(database_url) as schedule:
            clock = RepositoryClock(monkeypatch)
            claimed = await _claim(schedule)
            repo = schedule.app_b.state.project_repository
            audit_before = await schedule.audit()
            clock.advance(200)
            await repo.renew_decision_run_claim(
                schedule.project_id,
                claimed.id,
                claim_token="owner-a",
                expected_checkpoint_revision=2,
                stale_claim_timeout_seconds=300,
            )
            renewed = await schedule.persisted()
            assert renewed["checkpoint_revision"] == 2
            assert renewed["claim_token"] == "owner-a"
            assert datetime.fromisoformat(renewed["claimed_at"]) > claimed.claimed_at
            for token, revision in (("wrong-owner", 2), ("owner-a", 1), ("owner-a", 3)):
                with pytest.raises(ConflictError):
                    await repo.renew_decision_run_claim(
                        schedule.project_id,
                        claimed.id,
                        claim_token=token,
                        expected_checkpoint_revision=revision,
                    )
                assert await schedule.persisted() == renewed
            clock.advance(200)  # beyond original TTL, still inside renewed lease
            blocked = await schedule.client_b.post(
                f"{schedule.run_path}/recover-checkpoint", json={}
            )
            assert blocked.status_code == 409, blocked.text
            assert await schedule.audit() == audit_before
            clock.advance(101)
            with pytest.raises(ConflictError):
                await repo.renew_decision_run_claim(
                    schedule.project_id,
                    claimed.id,
                    claim_token="owner-a",
                    expected_checkpoint_revision=2,
                )
            assert await schedule.persisted() == renewed
            recovered = await schedule.client_b.post(
                f"{schedule.run_path}/recover-checkpoint", json={}
            )
            assert recovered.status_code == 200, recovered.text
            assert recovered.json()["checkpoint_revision"] == 3

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["renew", "save", "fail", "release"])
@pytest.mark.parametrize("ownership", ["expired", "superseded", "same-token-new-generation"])
def test_stale_worker_repository_writes_cannot_change_checkpoint_or_audit(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    ownership: str,
) -> None:
    async def scenario() -> None:
        async with checkpoint_schedule(database_url) as schedule:
            clock = RepositoryClock(monkeypatch)
            claimed = await _claim(schedule)
            repo_a = schedule.app_a.state.project_repository
            if ownership == "expired":
                clock.advance(301)
            else:
                repo_b = schedule.app_b.state.project_repository
                await repo_b.recover_stale_decision_run_checkpoint(
                    schedule.project_id,
                    claimed.id,
                    operator="recovery-admin",
                    rationale="Supersede original worker",
                    force=True,
                )
                await repo_b.claim_decision_run_for_resume(
                    schedule.project_id,
                    claimed.id,
                    operator="worker-b",
                    claim_token="owner-a"
                    if ownership == "same-token-new-generation"
                    else "owner-b",
                    expected_checkpoint_revision=3,
                )
            before, audit_before = await schedule.persisted(), await schedule.audit()
            kwargs = {"claim_token": "owner-a", "expected_checkpoint_revision": 2}

            async def stale_write() -> None:
                if operation == "renew":
                    await repo_a.renew_decision_run_claim(schedule.project_id, claimed.id, **kwargs)
                elif operation == "save":
                    await repo_a.save_resumed_decision_run(
                        claimed.model_copy(update={"run_status": "completed"}),
                        operator="stale-worker",
                        rationale="Must not persist",
                        **kwargs,
                    )
                elif operation == "fail":
                    await repo_a.mark_decision_run_failed(
                        schedule.project_id,
                        claimed.id,
                        operator="stale-worker",
                        failure_reason="Must not persist",
                        **kwargs,
                    )
                else:
                    await repo_a.release_decision_run_claim(
                        schedule.project_id, claimed.id, **kwargs
                    )

            if operation == "release":
                # Cleanup is permitted to be an idempotent no-op or an explicit conflict.
                try:
                    await stale_write()
                except ConflictError:
                    pass
            else:
                with pytest.raises(ConflictError):
                    await stale_write()
            assert await schedule.persisted() == before
            assert await schedule.audit() == audit_before

    asyncio.run(scenario())


def test_worker_heartbeat_protects_work_beyond_original_ttl(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        async with checkpoint_schedule(database_url, ttl=0.3) as schedule:
            clock = RepositoryClock(monkeypatch)
            repo = schedule.app_a.state.project_repository
            renew = repo.renew_decision_run_claim
            heartbeat_twice = asyncio.Event()
            renewals = 0
            provider = GatedProvider(schedule.app_a.state.decision_provider)
            schedule.app_a.state.decision_provider = provider

            async def observed_renewal(*args: Any, **kwargs: Any) -> None:
                nonlocal renewals
                # Pre-provider renewal stays in the original time slice. Only actual
                # heartbeat renewals advance time, each by less than the lease TTL.
                if provider.entered.is_set():
                    clock.advance(0.2)
                await renew(*args, **kwargs)
                if provider.entered.is_set():
                    renewals += 1
                    if renewals >= 2:
                        heartbeat_twice.set()

            monkeypatch.setattr(repo, "renew_decision_run_claim", observed_renewal)
            original_claimed_at = clock.current
            worker = asyncio.create_task(
                schedule.client_a.post(
                    f"{schedule.run_path}/resume",
                    json={"approved_choice": "BILLING", "operator": "long-running-worker"},
                )
            )
            try:
                await asyncio.wait_for(provider.entered.wait(), timeout=5)
                await asyncio.wait_for(heartbeat_twice.wait(), timeout=5)
                assert clock.current > original_claimed_at + timedelta(seconds=0.3)
                protected = await schedule.persisted()
                assert protected["checkpoint_revision"] == 2
                response = await schedule.client_b.post(
                    f"{schedule.run_path}/recover-checkpoint",
                    json={"stale_after_seconds": 0, "operator": "impatient-worker"},
                )
                assert response.status_code == 409, response.text
                concurrent = await schedule.client_b.post(
                    f"{schedule.run_path}/resume",
                    json={"approved_choice": "BILLING", "operator": "duplicate-worker"},
                )
                assert concurrent.status_code == 409, concurrent.text
                provider.release.set()
                completed = await asyncio.wait_for(worker, timeout=5)
                assert completed.status_code == 200, completed.text
                assert (await schedule.persisted())["checkpoint_revision"] == 3
                assert provider.calls == 1
            finally:
                provider.release.set()
                if not worker.done():
                    worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(scenario())


def test_request_cancellation_stops_heartbeat_and_preserves_recoverable_checkpoint(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        async with checkpoint_schedule(database_url) as schedule:
            clock = RepositoryClock(monkeypatch)
            provider = GatedProvider(schedule.app_a.state.decision_provider)
            schedule.app_a.state.decision_provider = provider
            repo = schedule.app_a.state.project_repository
            renew = repo.renew_decision_run_claim
            request_cancelled = False
            heartbeat_stopped = asyncio.Event()
            heartbeat = CheckpointLease._heartbeat

            async def observed_heartbeat(lease: CheckpointLease) -> None:
                try:
                    await heartbeat(lease)
                finally:
                    heartbeat_stopped.set()

            async def guard_renewal(*args: Any, **kwargs: Any) -> None:
                assert not request_cancelled, "Heartbeat outlived cancelled request"
                await renew(*args, **kwargs)

            monkeypatch.setattr(repo, "renew_decision_run_claim", guard_renewal)
            monkeypatch.setattr(CheckpointLease, "_heartbeat", observed_heartbeat)
            worker = asyncio.create_task(
                schedule.client_a.post(
                    f"{schedule.run_path}/resume",
                    json={"approved_choice": "BILLING", "operator": "cancelled-request"},
                )
            )
            try:
                await asyncio.wait_for(provider.entered.wait(), timeout=5)
                in_flight = await schedule.persisted()
                audit_before = await schedule.audit()
                worker.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await worker
                request_cancelled = True
                await asyncio.wait_for(provider.cancelled.wait(), timeout=5)
                await asyncio.wait_for(heartbeat_stopped.wait(), timeout=5)
                after = await schedule.persisted()
                assert after["run_status"] == "resuming"
                assert after["checkpoint_revision"] == in_flight["checkpoint_revision"] == 2
                assert after["steps"] == in_flight["steps"]
                assert await schedule.audit() == audit_before
                blocked = await schedule.client_b.post(
                    f"{schedule.run_path}/recover-checkpoint", json={}
                )
                assert blocked.status_code == 409, blocked.text
                clock.advance(301)

                # A third process can recover after expiry; no local task/lock is needed.
                restarted = create_app(_settings(database_url))
                async with (
                    restarted.router.lifespan_context(restarted),
                    httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=restarted),
                        base_url="http://testserver",
                        headers=WORKER_HEADERS,
                    ) as client,
                ):
                    recovered = await client.post(
                        f"{schedule.run_path}/recover-checkpoint",
                        json={"operator": "restart-worker", "rationale": "Heartbeat stopped"},
                    )
                    assert recovered.status_code == 200, recovered.text
                    assert recovered.json()["checkpoint_revision"] == 3
                    resumed = await client.post(
                        f"{schedule.run_path}/resume",
                        json={"approved_choice": "BILLING", "operator": "restart-worker"},
                    )
                    assert resumed.status_code == 200, resumed.text
                    assert resumed.json()["checkpoint_revision"] == 5
                    assert len(resumed.json()["steps"]) == 2
                assert provider.calls == 1
            finally:
                provider.release.set()
                if not worker.done():
                    worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(scenario())


def test_provider_call_is_preceded_by_renewal_without_generation_bump(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        async with checkpoint_schedule(database_url) as schedule:
            repo = schedule.app_a.state.project_repository
            renew = repo.renew_decision_run_claim
            renewals = []
            inner = schedule.app_a.state.decision_provider

            async def record_renewal(*args: Any, **kwargs: Any) -> None:
                await renew(*args, **kwargs)
                renewals.append(kwargs)

            class CheckRenewedProvider:
                async def choice(self, request: ChoiceRequest) -> ChoiceResult:
                    # Initial executor renewal plus the immediate pre-provider renewal.
                    assert len(renewals) >= 2
                    assert all(item["expected_checkpoint_revision"] == 2 for item in renewals)
                    assert (await schedule.persisted())["checkpoint_revision"] == 2
                    return await inner.choice(request)

            monkeypatch.setattr(repo, "renew_decision_run_claim", record_renewal)
            schedule.app_a.state.decision_provider = CheckRenewedProvider()
            response = await schedule.client_a.post(
                f"{schedule.run_path}/resume",
                json={"approved_choice": "BILLING", "operator": "worker-a"},
            )
            assert response.status_code == 200, response.text
            assert (await schedule.persisted())["checkpoint_revision"] == 3

    asyncio.run(scenario())


@pytest.mark.parametrize("ignores_cancellation", [False, True])
def test_heartbeat_ownership_loss_stops_local_execution_and_fences_late_provider(
    database_url: str, monkeypatch: pytest.MonkeyPatch, ignores_cancellation: bool
) -> None:
    async def scenario() -> None:
        async with checkpoint_schedule(database_url) as schedule:
            check_ownership = asyncio.Event()

            async def gated_heartbeat(lease: CheckpointLease) -> None:
                await check_ownership.wait()
                await lease.renew()

            monkeypatch.setattr(CheckpointLease, "_heartbeat", gated_heartbeat)
            provider_type = CancellationResistantProvider if ignores_cancellation else GatedProvider
            provider = provider_type(schedule.app_a.state.decision_provider)
            schedule.app_a.state.decision_provider = provider
            worker = asyncio.create_task(
                schedule.client_a.post(
                    f"{schedule.run_path}/resume",
                    json={"approved_choice": "BILLING", "operator": "superseded-worker"},
                )
            )
            try:
                await asyncio.wait_for(provider.entered.wait(), timeout=5)
                recovered = await schedule.client_b.post(
                    f"{schedule.run_path}/recover-checkpoint",
                    headers=ADMIN_HEADERS,
                    json={
                        "force": True,
                        "operator": "recovery-admin",
                        "rationale": "Preempt while old provider is blocked",
                    },
                )
                assert recovered.status_code == 200, recovered.text
                takeover = await schedule.client_b.post(
                    f"{schedule.run_path}/resume",
                    json={"approved_choice": "BILLING", "operator": "takeover-worker"},
                )
                assert takeover.status_code == 200, takeover.text
                before, audit_before = await schedule.persisted(), await schedule.audit()
                check_ownership.set()
                # Do not release the provider: the heartbeat itself must discover loss,
                # cancel local execution, and return without waiting for a remote result.
                await asyncio.wait_for(provider.cancelled.wait(), timeout=5)
                fenced = await asyncio.wait_for(worker, timeout=5)
                assert fenced.status_code == 409, fenced.text
                assert await schedule.persisted() == before
                assert await schedule.audit() == audit_before
                assert before["checkpoint_revision"] == 5
                provider.release.set()
                if isinstance(provider, CancellationResistantProvider):
                    await asyncio.wait_for(provider.finished.wait(), timeout=5)
                assert await schedule.persisted() == before
                assert await schedule.audit() == audit_before
                assert provider.calls == 1
            finally:
                provider.release.set()
                if not worker.done():
                    worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(scenario())


@pytest.mark.parametrize("endpoint", ["recover-checkpoint", "resume"])
@pytest.mark.parametrize("auth_required", [False, True], ids=["local", "authenticated"])
def test_trusted_scope_force_uses_verified_actor_not_body_operator(
    database_url: str, endpoint: str, auth_required: bool
) -> None:
    async def scenario() -> None:
        async with checkpoint_schedule(database_url, auth_required=auth_required) as schedule:
            await _claim(schedule)
            body = {
                "operator": "spoofed-body-operator",
                "rationale": "Verified scope holder authorizes takeover",
                **(
                    {"force": True}
                    if endpoint == "recover-checkpoint"
                    else {"force_recover_stale_claim": True, "approved_choice": "BILLING"}
                ),
            }
            response = await schedule.client_b.post(
                f"{schedule.run_path}/{endpoint}",
                headers={
                    "X-OpenClass-Scopes": "checkpoint:force-recover",
                    "X-OpenClass-Actor": "scope-recovery-admin",
                },
                json=body,
            )
            assert response.status_code == 200, response.text
            force_events = [
                event
                for event in await schedule.audit()
                if event["event_type"] == "decision_run_resumed"
                or event["payload"].get("force_recovered")
            ]
            assert force_events
            assert all(event["actor"] == "scope-recovery-admin" for event in force_events)
            assert all(event["payload"]["rationale"] == body["rationale"] for event in force_events)
            assert "spoofed-body-operator" not in str(force_events)

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["recover", "cancel"])
def test_stale_lifecycle_write_cannot_rewind_newer_checkpoint(
    database_url: str, operation: str
) -> None:
    async def scenario() -> None:
        async with checkpoint_schedule(database_url) as schedule:
            advanced = await schedule.client_a.post(
                f"{schedule.run_path}/resume",
                json={"approved_choice": "BILLING", "operator": "winner"},
            )
            assert advanced.status_code == 200, advanced.text
            before, audit_before = await schedule.persisted(), await schedule.audit()
            repo = schedule.app_b.state.project_repository
            with pytest.raises(ConflictError):
                if operation == "cancel":
                    await repo.cancel_decision_run_checkpoint(
                        schedule.project_id,
                        UUID(schedule.run["id"]),
                        operator="stale-canceller",
                        reason="Old revision must not cancel new checkpoint",
                        expected_checkpoint_revision=1,
                        record_feedback=True,
                    )
                else:
                    await repo.recover_stale_decision_run_checkpoint(
                        schedule.project_id,
                        schedule.run["id"],
                        operator="stale-recoverer",
                        rationale="Cannot recover a newer paused generation",
                        force=True,
                    )
            assert await schedule.persisted() == before
            assert await schedule.audit() == audit_before

    asyncio.run(scenario())


@pytest.mark.parametrize("endpoint", ["recover-checkpoint", "resume"])
@pytest.mark.parametrize("context_error", ["wrong-token", "missing-actor"])
def test_force_rejects_invalid_token_or_missing_verified_actor(
    database_url: str, endpoint: str, context_error: str
) -> None:
    async def scenario() -> None:
        async with checkpoint_schedule(database_url, auth_required=False) as schedule:
            await _claim(schedule)
            before, audit_before = await schedule.persisted(), await schedule.audit()
            headers = {
                "X-OpenClass-Internal-Token": (
                    "incorrect-checkpoint-test-token"
                    if context_error == "wrong-token"
                    else INTERNAL_TOKEN
                ),
                "X-OpenClass-Role": "admin",
            }
            if context_error != "missing-actor":
                headers["X-OpenClass-Actor"] = "unverified-admin"
            body = {
                "operator": "body-operator-is-not-authentication",
                "rationale": "Attempt with incomplete trusted context",
                **(
                    {"force": True}
                    if endpoint == "recover-checkpoint"
                    else {"force_recover_stale_claim": True, "approved_choice": "BILLING"}
                ),
            }
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=schedule.app_b),
                base_url="http://testserver",
                headers=headers,
            ) as client:
                response = await client.post(f"{schedule.run_path}/{endpoint}", json=body)
            assert response.status_code == 403, response.text
            assert await schedule.persisted() == before
            assert await schedule.audit() == audit_before

    asyncio.run(scenario())
