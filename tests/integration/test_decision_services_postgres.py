"""PostgreSQL persistence proof for Decision Services and Decision Runs:
create and execute in one app instance, read from a brand-new instance, and verify
decision services and immutable decision run history survive application restart.

Requires OPENCLASS_TEST_DATABASE_URL pointing at a PostgreSQL database;
the Alembic head is applied by the conftest fixture.
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openclass_server.main import create_app
from openclass_server.settings import Settings

from tests.integration import test_checkpoint_lease_fencing as checkpoints

pytestmark = pytest.mark.postgres


def test_decision_services_and_runs_survive_application_restart(postgres_url: str) -> None:
    def fresh_client() -> TestClient:
        # A new app builds a new engine: anything read through it came from
        # PostgreSQL, not from in-memory state.
        return TestClient(
            create_app(
                Settings(
                    database_url=postgres_url,
                    decision_provider="laya",
                    laya_allow_fallback=True,
                )
            )
        )

    slug_suffix = uuid.uuid4().hex[:8]
    project_name = f"Decision Persistence Test {slug_suffix}"

    # Instance 1: Create Project and Ingest Event
    with fresh_client() as client:
        created = client.post(
            "/api/v1/projects",
            json={"name": project_name, "description": "decisions restart proof"},
        )
        assert created.status_code == 201
        project = created.json()
        server_slug = project["slug"]

        evt_resp = client.post(
            f"/api/v1/projects/{server_slug}/events",
            json={
                "content": "Enterprise inquiry: Need 500 licenses with SSO integration.",
                "source_type": "text",
                "metadata": {"deal_size": "enterprise", "run": slug_suffix},
            },
        )
        assert evt_resp.status_code == 201
        event_id = evt_resp.json()["id"]

    # Instance 2: Create Decision Service with choices
    with fresh_client() as client:
        svc_resp = client.post(
            f"/api/v1/projects/{server_slug}/decision-services",
            json={
                "name": "Lead Triage",
                "description": "Route inbound sales opportunities",
                "instructions": "Determine if inbound lead is enterprise or smb",
                "choices": [
                    {"key": "ENTERPRISE", "label": "Enterprise Deal", "description": "50+ seats"},
                    {"key": "SMB", "label": "SMB Deal", "description": "Under 50 seats"},
                ],
            },
        )
        assert svc_resp.status_code == 201
        service_id = svc_resp.json()["id"]

    # Instance 3: Execute Decision Run against event
    with fresh_client() as client:
        run_resp = client.post(
            f"/api/v1/projects/{server_slug}/decision-services/{service_id}/runs",
            json={"raw_event_ids": [event_id]},
        )
        assert run_resp.status_code == 201
        runs = run_resp.json()
        assert len(runs) == 1
        run_id = runs[0]["id"]
        assert runs[0]["selected_choice"] in ("ENTERPRISE", "SMB", "UNKNOWN")

    # Instance 4: Verify complete persistent state from fresh instance
    with fresh_client() as client:
        # 1. Verify summary counts
        summary = client.get(f"/api/v1/projects/{server_slug}/summary").json()
        assert summary["events"] == 1
        assert summary["decision_runs"] == 1

        # 2. Verify Decision Service
        services = client.get(f"/api/v1/projects/{server_slug}/decision-services").json()
        assert len(services) == 1
        svc = services[0]
        assert svc["id"] == service_id
        assert svc["name"] == "Lead Triage"
        choice_keys = [c["key"] for c in svc["nodes"][0]["choices"]]
        assert "UNKNOWN" in choice_keys
        assert "ENTERPRISE" in choice_keys

        # 3. Verify Decision Run immutable history
        run_data = client.get(f"/api/v1/projects/{server_slug}/runs/{run_id}").json()
        assert run_data["id"] == run_id
        assert run_data["raw_event_id"] == event_id
        assert run_data["decision_service_id"] == service_id
        assert run_data["provider"] == "laya"
        assert run_data["supervision_outcome"] in ("TRUSTED", "REVIEW", "UNKNOWN")
        assert "UNKNOWN" in run_data["probabilities"]

        # 4. Verify Snapshots survive reload perfectly
        expected_content = "Enterprise inquiry: Need 500 licenses with SSO integration."
        assert run_data["input_snapshot"]["content"] == expected_content
        assert run_data["input_snapshot"]["metadata"]["run"] == slug_suffix
        assert run_data["instructions_snapshot"] == "Determine if inbound lead is enterprise or smb"
        assert len(run_data["choices_snapshot"]) == 3


def test_postgres_stale_checkpoint_race_across_separate_repositories(postgres_url: str) -> None:
    from tests.integration.test_decision_service_runs import (
        test_stale_checkpoint_race_delayed_before_claim_across_multi_pause_stages,
    )

    test_stale_checkpoint_race_delayed_before_claim_across_multi_pause_stages(postgres_url)


def test_postgres_active_worker_recovery_and_fencing_across_separate_repositories(
    postgres_url: str,
) -> None:
    from tests.integration.test_decision_service_runs import (
        test_active_worker_recovery_enforces_lease_timeout_and_fences_superseded_worker,
    )

    test_active_worker_recovery_enforces_lease_timeout_and_fences_superseded_worker(postgres_url)


@pytest.mark.parametrize(
    "scenario, options",
    [
        pytest.param(
            checkpoints.test_claim_snapshot_is_materialized_before_commit_and_lock_release,
            {},
            id="transaction-captured-snapshot",
        ),
        pytest.param(
            checkpoints.test_resume_validates_actual_claimed_node_and_releases_invalid_approval,
            {},
            id="actual-paused-node",
        ),
        pytest.param(
            checkpoints.test_renewal_keeps_generation_and_rejects_wrong_revision_or_token,
            {},
            id="renewal-generation-expiry",
        ),
        pytest.param(
            checkpoints.test_worker_heartbeat_protects_work_beyond_original_ttl,
            {},
            id="heartbeat-beyond-original-ttl",
        ),
        pytest.param(
            checkpoints.test_provider_call_is_preceded_by_renewal_without_generation_bump,
            {},
            id="pre-provider-renewal",
        ),
        *[
            pytest.param(
                checkpoints.test_heartbeat_ownership_loss_stops_local_execution_and_fences_late_provider,
                {"ignores_cancellation": ignores_cancellation},
                id=f"ownership-loss-ignores-cancel-{ignores_cancellation}",
            )
            for ignores_cancellation in (False, True)
        ],
        pytest.param(
            checkpoints.test_request_cancellation_stops_heartbeat_and_preserves_recoverable_checkpoint,
            {},
            id="cancel-stop-heartbeat-restart",
        ),
        *[
            pytest.param(
                checkpoints.test_stale_worker_repository_writes_cannot_change_checkpoint_or_audit,
                {"ownership": ownership, "operation": operation},
                id=f"{ownership}-{operation}",
            )
            for ownership in ("expired", "superseded", "same-token-new-generation")
            for operation in ("renew", "save", "fail", "release")
        ],
    ],
)
def test_postgres_checkpoint_repository_schedules(
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
    scenario: Callable[..., None],
    options: dict[str, Any],
) -> None:
    scenario(database_url=postgres_url, monkeypatch=monkeypatch, **options)


@pytest.mark.parametrize(
    "scenario, options",
    [
        *[
            pytest.param(
                checkpoints.test_resume_expected_checkpoint_precondition_is_atomic,
                {"precondition": precondition},
                id=name,
            )
            for name, precondition in (
                ("next-generation", {"expected_checkpoint_revision": 2}),
                ("future-generation", {"expected_checkpoint_revision": 99}),
                ("wrong-node", {"expected_node_key": "finance"}),
            )
        ],
        *[
            pytest.param(
                checkpoints.test_repeated_pauses_require_current_node_and_revision,
                {"finish": finish},
                id=f"repeated-pauses-{finish}",
            )
            for finish in ("approve", "cancel")
        ],
        *[
            pytest.param(
                checkpoints.test_forged_force_privilege_without_internal_token_cannot_mutate_checkpoint,
                {
                    "auth_required": auth_required,
                    "privilege": privilege,
                    "endpoint": endpoint,
                },
                id=f"forged-{auth_required}-{privilege}-{endpoint}",
            )
            for auth_required in (False, True)
            for privilege in ("role", "scope")
            for endpoint in ("recover-checkpoint", "resume")
        ],
        *[
            pytest.param(
                checkpoints.test_verified_privileged_force_requires_rationale_and_preserves_actor,
                {"endpoint": endpoint},
                id=f"trusted-force-{endpoint}",
            )
            for endpoint in ("recover-checkpoint", "resume")
        ],
        *[
            pytest.param(
                checkpoints.test_trusted_scope_force_uses_verified_actor_not_body_operator,
                {"endpoint": endpoint, "auth_required": auth_required},
                id=f"trusted-scope-{auth_required}-{endpoint}",
            )
            for auth_required in (False, True)
            for endpoint in ("recover-checkpoint", "resume")
        ],
        *[
            pytest.param(
                checkpoints.test_stale_lifecycle_write_cannot_rewind_newer_checkpoint,
                {"operation": operation},
                id=f"stale-lifecycle-{operation}",
            )
            for operation in ("recover", "cancel")
        ],
        *[
            pytest.param(
                checkpoints.test_force_rejects_invalid_token_or_missing_verified_actor,
                {"endpoint": endpoint, "context_error": context_error},
                id=f"force-{context_error}-{endpoint}",
            )
            for context_error in ("wrong-token", "missing-actor")
            for endpoint in ("recover-checkpoint", "resume")
        ],
    ],
)
def test_postgres_checkpoint_http_schedules(
    postgres_url: str, scenario: Callable[..., None], options: dict[str, Any]
) -> None:
    scenario(database_url=postgres_url, **options)
