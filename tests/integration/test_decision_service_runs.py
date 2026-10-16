"""Phase 6 decision services & runs: UNKNOWN locked, run-by-content, persistence."""

from __future__ import annotations

import math
from typing import Any

from fastapi.testclient import TestClient

CHOICES = [
    {"key": "BILLING", "label": "Billing"},
    {"key": "REFUND", "label": "Refund"},
    {"key": "DELIVERY", "label": "Delivery"},
]


def _make_service(client: TestClient) -> tuple[str, dict[str, Any]]:
    created = client.post("/api/v1/projects", json={"name": "Decide Co"})
    assert created.status_code == 201, created.text
    slug = created.json()["slug"]
    body = {
        "name": "Support router",
        "instructions": "Route each customer message to the best-fitting intent.",
        "choices": CHOICES,
    }
    service = client.post(f"/api/v1/projects/{slug}/decision-services", json=body)
    assert service.status_code == 201, service.text
    return slug, service.json()


def test_unknown_choice_is_auto_appended_and_locked(mock_client: TestClient):
    _slug, service = _make_service(mock_client)
    node = service["nodes"][0]
    keys = [choice["key"] for choice in node["choices"]]
    assert "UNKNOWN" in keys
    assert keys.count("UNKNOWN") == 1


def test_run_by_content_persists_full_distribution(mock_client: TestClient):
    slug, service = _make_service(mock_client)
    run_response = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
        json={"content": "I was charged twice for my subscription"},
    )
    assert run_response.status_code == 201, run_response.text
    runs = run_response.json()
    assert len(runs) == 1
    run = runs[0]
    node = service["nodes"][0]
    assert set(run["probabilities"].keys()) == {c["key"] for c in node["choices"]}
    total = math.fsum(run["probabilities"].values())
    assert math.isclose(total, 1.0, abs_tol=1e-6)
    assert run["selected_choice"] in {c["key"] for c in node["choices"]}
    assert run["provider"] and run["latency_ms"] is not None
    # The run is persisted and listable.
    listed = mock_client.get(f"/api/v1/projects/{slug}/runs")
    assert listed.status_code == 200
    assert any(item["id"] == run["id"] for item in listed.json())


def test_run_by_event_id_matches_content_run_semantics(mock_client: TestClient):
    slug, service = _make_service(mock_client)
    event = mock_client.post(
        f"/api/v1/projects/{slug}/events", json={"content": "Where is my package?"}
    ).json()
    runs = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
        json={"raw_event_ids": [event["id"]]},
    )
    assert runs.status_code == 201, runs.text
    assert runs.json()[0]["raw_event_id"] == event["id"]


def test_unmatched_input_is_never_forced_into_a_choice(mock_client: TestClient):
    slug, service = _make_service(mock_client)
    runs = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
        json={"content": "The weather on Mars is lovely this time of year"},
    )
    assert runs.status_code == 201
    run = runs.json()[0]
    assert run["selected_choice"] == "UNKNOWN" or run["supervision_outcome"] == "UNKNOWN"


def test_run_requires_input(mock_client: TestClient):
    slug, service = _make_service(mock_client)
    runs = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs", json={}
    )
    assert runs.status_code == 422


def test_resume_checkpointed_run_records_feedback_and_completes(mock_client: TestClient):
    slug, service = _make_service(mock_client)
    runs = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
        json={"content": "The weather on Mars is lovely this time of year"},
    )
    assert runs.status_code == 201
    run = runs.json()[0]
    assert run["supervision_outcome"] in {"REVIEW", "ESCALATE", "UNKNOWN"}

    resumed = mock_client.post(
        f"/api/v1/projects/{slug}/runs/{run['id']}/resume",
        json={
            "approved_choice": "BILLING",
            "operator": "ops-lead",
            "rationale": "Manually triaged to billing queue.",
        },
    )
    assert resumed.status_code == 200, resumed.text
    payload = resumed.json()
    assert payload == {
        "run_id": run["id"],
        "status": "completed",
        "checkpoint_revision": 3,
        "selected_choice": "BILLING",
        "supervision_outcome": "TRUSTED",
        "resumed_by": "ops-lead",
        "rationale": "Manually triaged to billing queue.",
    }

    invalid_choice = mock_client.post(
        f"/api/v1/projects/{slug}/runs/{run['id']}/resume",
        json={"approved_choice": "NOT_A_CHOICE", "operator": "ops-lead"},
    )
    assert invalid_choice.status_code == 422


def test_cancel_decision_run_and_prevent_subsequent_resume(mock_client: TestClient):
    slug, service = _make_service(mock_client)
    runs = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
        json={"content": "The weather on Mars is lovely this time of year"},
    )
    assert runs.status_code == 201
    run = runs.json()[0]

    cancelled = mock_client.post(
        f"/api/v1/projects/{slug}/runs/{run['id']}/cancel",
        json={"operator": "ops-lead", "reason": "Duplicate upstream event."},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json() == {
        "run_id": run["id"],
        "status": "cancelled",
        "cancelled_by": "ops-lead",
        "reason": "Duplicate upstream event.",
    }

    resumed_after_cancel = mock_client.post(
        f"/api/v1/projects/{slug}/runs/{run['id']}/resume",
        json={"approved_choice": "BILLING", "operator": "ops-lead"},
    )
    assert resumed_after_cancel.status_code == 409

    # Cancelling an already-cancelled run also returns 409 Conflict
    second_cancel = mock_client.post(
        f"/api/v1/projects/{slug}/runs/{run['id']}/cancel",
        json={"operator": "ops-lead", "reason": "Try cancelling again."},
    )
    assert second_cancel.status_code == 409

    # Verify decision_run_cancelled audit event is recorded
    audit_events = mock_client.get(f"/api/v1/projects/{slug}/audit").json()
    assert any(
        ev["event_type"] == "decision_run_cancelled" and ev["payload"].get("run_id") == run["id"]
        for ev in audit_events
    )


def _make_multi_node_supervised_service(client: TestClient) -> tuple[str, dict[str, Any]]:
    created = client.post("/api/v1/projects", json={"name": "MultiNode Corp"})
    assert created.status_code == 201, created.text
    slug = created.json()["slug"]
    body = {
        "name": "Two-Stage Support Graph",
        "instructions": "Route and resolve customer tickets across two stages.",
        "runtime_config": {
            "state_schema": {
                "id": "ticket_state",
                "version": 1,
                "features": [
                    {
                        "id": "ticket_priority",
                        "kind": "string",
                        "sensor_field": "ticket_priority",
                        "required": False,
                    }
                ],
            }
        },
        "nodes": [
            {
                "name": "triage-router",
                "instructions": "Route ticket to department",
                "pause_on_review": True,
                "choices": [
                    {"key": "BILLING", "label": "Billing Department"},
                    {"key": "DELIVERY", "label": "Delivery Department"},
                ],
            },
            {
                "name": "billing-specialist",
                "instructions": "Select billing resolution action",
                "pause_on_review": False,
                "choices": [
                    {"key": "REFUND", "label": "Issue Refund"},
                    {"key": "INVOICE", "label": "Resend Invoice"},
                ],
            },
        ],
        "transitions": [
            {
                "from_node_key": "triage-router",
                "choice_key": "BILLING",
                "to_node_key": "billing-specialist",
                "require_approval": True,
            }
        ],
    }
    service = client.post(f"/api/v1/projects/{slug}/decision-services", json=body)
    assert service.status_code == 201, service.text
    return slug, service.json()


def test_durable_graph_pause_restart_inspect_and_resume_executes_downstream_nodes(
    database_url: str,
) -> None:
    from openclass_server.main import create_app
    from openclass_server.settings import Settings

    app1 = create_app(Settings(database_url=database_url, decision_provider="mock"))
    with TestClient(app1) as client1:
        slug, service = _make_multi_node_supervised_service(client1)
        event_resp = client1.post(
            f"/api/v1/projects/{slug}/events",
            json={
                "content": "The weather on Mars is lovely this time of year",
                "metadata": {"ticket_priority": "urgent"},
            },
        )
        assert event_resp.status_code == 201, event_resp.text
        event_id = event_resp.json()["id"]

        run_resp = client1.post(
            f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
            json={"raw_event_ids": [event_id]},
        )
        assert run_resp.status_code == 201, run_resp.text
        paused_run = run_resp.json()[0]
        run_id = paused_run["id"]

        assert paused_run["run_status"] == "paused"
        assert paused_run["current_node_key"] == "triage-router"
        assert paused_run["decision_node_id"] == service["nodes"][0]["id"]
        assert len(paused_run["steps"]) == 1
        assert paused_run["steps"][0]["node_name"] == "triage-router"
        assert paused_run["pending_operation"]["node_key"] == "triage-router"
        assert len(paused_run["pending_operation"]["candidate_transitions"]) == 1

    # Simulate service restart with a completely fresh FastAPI app & SQL engine
    app2 = create_app(Settings(database_url=database_url, decision_provider="mock"))
    with TestClient(app2) as client2:
        inspected = client2.get(f"/api/v1/projects/{slug}/runs/{run_id}")
        assert inspected.status_code == 200, inspected.text
        inspected_run = inspected.json()
        assert inspected_run["run_status"] == "paused"
        assert inspected_run["current_node_key"] == "triage-router"
        assert inspected_run["pending_operation"]["node_key"] == "triage-router"
        assert len(inspected_run["steps"]) == 1

        # Resume the paused run with BILLING approval -> triggers Node 2 (billing-specialist)
        resumed = client2.post(
            f"/api/v1/projects/{slug}/runs/{run_id}/resume",
            json={
                "approved_choice": "BILLING",
                "operator": "triage-supervisor",
                "rationale": "Escalated to billing specialist after human review.",
            },
        )
        assert resumed.status_code == 200, resumed.text
        resumed_payload = resumed.json()
        assert resumed_payload["run_id"] == run_id
        assert resumed_payload["status"] in ("completed", "paused")
        assert resumed_payload["resumed_by"] == "triage-supervisor"
        assert len(resumed_payload["steps"]) == 2
        assert resumed_payload["steps"][0]["node_name"] == "triage-router"
        assert resumed_payload["steps"][0]["selected_choice"] == "BILLING"
        assert resumed_payload["steps"][0]["supervision_outcome"] == "TRUSTED"
        assert resumed_payload["steps"][1]["node_name"] == "billing-specialist"
        assert resumed_payload["state_snapshot"]["facts"] == {"ticket_priority": "urgent"}
        assert resumed_payload["state_snapshot"]["resolved_decisions"][0]["choice"] == "BILLING"

        # Verify persisted run state via GET /runs/{run_id}
        after_resume = client2.get(f"/api/v1/projects/{slug}/runs/{run_id}").json()
        assert after_resume["current_node_key"] == "billing-specialist"
        assert after_resume["resumed_by"] == "triage-supervisor"
        assert len(after_resume["steps"]) == 2

        # If Node 2 also paused due to Mars input, approve it to complete the run
        if after_resume["run_status"] == "paused":
            resumed_stage2 = client2.post(
                f"/api/v1/projects/{slug}/runs/{run_id}/resume",
                json={
                    "approved_choice": "REFUND",
                    "operator": "billing-lead",
                    "rationale": "Approved refund in stage 2.",
                },
            )
            assert resumed_stage2.status_code == 200, resumed_stage2.text
            assert resumed_stage2.json()["status"] == "completed"

        # Duplicate resume attempt on already-completed run returns 409 Conflict
        duplicate_resume = client2.post(
            f"/api/v1/projects/{slug}/runs/{run_id}/resume",
            json={
                "approved_choice": "REFUND",
                "operator": "triage-supervisor",
                "rationale": "Duplicate click.",
            },
        )
        assert duplicate_resume.status_code == 409

        # Audit log contains both decision_run_paused and decision_run_resumed
        audit_events = client2.get(f"/api/v1/projects/{slug}/audit").json()
        run_event_types = [
            ev["event_type"] for ev in audit_events if ev["payload"].get("run_id") == run_id
        ]
        assert "decision_run_paused" in run_event_types
        assert "decision_run_resumed" in run_event_types


def test_operator_permission_checks_reject_viewer_role_on_resume_and_cancel(
    mock_client: TestClient,
) -> None:
    slug, service = _make_multi_node_supervised_service(mock_client)
    run = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
        json={"content": "The weather on Mars is lovely this time of year"},
    ).json()[0]

    forbidden_resume = mock_client.post(
        f"/api/v1/projects/{slug}/runs/{run['id']}/resume",
        headers={"X-OpenClass-Role": "viewer"},
        json={"approved_choice": "BILLING", "operator": "readonly-user"},
    )
    assert forbidden_resume.status_code == 403

    forbidden_cancel = mock_client.post(
        f"/api/v1/projects/{slug}/runs/{run['id']}/cancel",
        headers={"X-OpenClass-Role": "read_only"},
        json={"operator": "readonly-user", "reason": "Should not be allowed"},
    )
    assert forbidden_cancel.status_code == 403


def test_version_conflict_and_pinned_version_execution_on_resume(
    mock_client: TestClient,
) -> None:
    slug, service = _make_multi_node_supervised_service(mock_client)
    run = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
        json={"content": "The weather on Mars is lovely this time of year"},
    ).json()[0]
    assert run["run_status"] == "paused"
    assert run["pinned_version_number"] == 1

    # Update the decision service to version 2 (removing node 2)
    updated = mock_client.patch(
        f"/api/v1/projects/{slug}/decision-services/{service['id']}",
        json={
            "instructions": "Updated single-node instructions v2",
            "nodes": [
                {
                    "name": "triage-router",
                    "instructions": "Updated single-node instructions v2",
                    "choices": [
                        {"key": "BILLING", "label": "Billing Department"},
                        {"key": "DELIVERY", "label": "Delivery Department"},
                    ],
                }
            ],
            "transitions": [],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version_number"] == 2

    # Resuming with strict_version_check=True fails with 409 Conflict
    conflict = mock_client.post(
        f"/api/v1/projects/{slug}/runs/{run['id']}/resume",
        json={
            "approved_choice": "BILLING",
            "operator": "ops-lead",
            "strict_version_check": True,
        },
    )
    assert conflict.status_code == 409

    # Resuming with use_pinned_version=True succeeds using the pinned v1 2-node graph
    resumed = mock_client.post(
        f"/api/v1/projects/{slug}/runs/{run['id']}/resume",
        json={
            "approved_choice": "BILLING",
            "operator": "ops-lead",
            "use_pinned_version": True,
            "strict_version_check": False,
        },
    )
    assert resumed.status_code == 200, resumed.text
    payload = resumed.json()
    assert len(payload["steps"]) == 2
    assert payload["steps"][1]["node_name"] == "billing-specialist"


def test_concurrent_resume_requests_allow_only_one_winner_and_single_downstream_call(
    database_url: str,
) -> None:
    import asyncio

    import httpx
    from openclass_core.models import ChoiceRequest, ChoiceResult
    from openclass_core.providers import DecisionProvider
    from openclass_server.main import create_app
    from openclass_server.settings import Settings

    class GatedCountingDecisionProvider:
        def __init__(self, inner: DecisionProvider) -> None:
            self._inner = inner
            self.call_count = 0
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def choice(self, request: ChoiceRequest) -> ChoiceResult:
            self.call_count += 1
            self.entered.set()
            await self.release.wait()
            return await self._inner.choice(request)

    app = create_app(Settings(database_url=database_url, decision_provider="mock"))
    with TestClient(app) as client:
        slug, service = _make_multi_node_supervised_service(client)
        run = client.post(
            f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
            json={"content": "The weather on Mars is lovely this time of year"},
        ).json()[0]
        assert run["run_status"] == "paused"
        run_id = run["id"]

        gated_provider = GatedCountingDecisionProvider(app.state.decision_provider)
        app.state.decision_provider = gated_provider

        async def _fire_concurrent_resumes() -> tuple[httpx.Response, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as async_client:
                req_body = {
                    "approved_choice": "BILLING",
                    "operator": "concurrent-op",
                    "rationale": "Concurrent approval race test",
                }
                first = asyncio.create_task(
                    async_client.post(
                        f"/api/v1/projects/{slug}/runs/{run_id}/resume", json=req_body
                    )
                )
                try:
                    await asyncio.wait_for(gated_provider.entered.wait(), timeout=5)
                    second = await asyncio.wait_for(
                        async_client.post(
                            f"/api/v1/projects/{slug}/runs/{run_id}/resume", json=req_body
                        ),
                        timeout=5,
                    )
                finally:
                    gated_provider.release.set()
                    winner = await asyncio.wait_for(first, timeout=5)
                return winner, second

        resp_a, resp_b = asyncio.run(_fire_concurrent_resumes())
        statuses = sorted([resp_a.status_code, resp_b.status_code])
        assert statuses == [200, 409], (resp_a.text, resp_b.text)
        assert gated_provider.call_count == 1


def test_crash_recovery_for_stuck_resuming_checkpoint_across_restarts(
    database_url: str,
) -> None:
    import asyncio

    from openclass_server.main import create_app
    from openclass_server.settings import Settings

    app1 = create_app(
        Settings(
            database_url=database_url,
            decision_provider="mock",
            decision_run_resume_claim_ttl_seconds=300.0,
        )
    )
    with TestClient(app1) as client1:
        slug, service = _make_multi_node_supervised_service(client1)
        project_id = client1.get(f"/api/v1/projects/{slug}").json()["id"]
        run = client1.post(
            f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
            json={"content": "The weather on Mars is lovely this time of year"},
        ).json()[0]
        run_id = run["id"]
        assert run["run_status"] == "paused"

        # Simulate a worker claiming the checkpoint and crashing before completion
        repo = app1.state.project_repository
        asyncio.run(
            repo.claim_decision_run_for_resume(
                project_id,
                run_id,
                operator="crashed-worker",
                claim_token="crashed-claim-token-1",
                stale_claim_timeout_seconds=300.0,
            )
        )

        # While the claim is fresh, an ordinary resume is rejected with 409 Conflict
        blocked = client1.post(
            f"/api/v1/projects/{slug}/runs/{run_id}/resume",
            json={"approved_choice": "BILLING", "operator": "second-worker"},
        )
        assert blocked.status_code == 409

        # A stopped heartbeat ages durably; do not depend on scheduler timing.
        from datetime import UTC, datetime, timedelta

        import sqlalchemy as sa
        from openclass_server.persistence.tables import DecisionRunCheckpointRow

        async def expire_crashed_claim() -> None:
            async with repo.sessions.begin() as session:
                await session.execute(
                    sa.update(DecisionRunCheckpointRow)
                    .where(DecisionRunCheckpointRow.run_id == run_id)
                    .values(claimed_at=datetime.now(UTC) - timedelta(seconds=301))
                )

        asyncio.run(expire_crashed_claim())

    # Restart with the same lease policy and recover the expired durable claim.
    app2 = create_app(
        Settings(
            database_url=database_url,
            decision_provider="mock",
            decision_run_resume_claim_ttl_seconds=300.0,
        )
    )
    with TestClient(app2) as client2:
        inspected = client2.get(f"/api/v1/projects/{slug}/runs/{run_id}").json()
        assert inspected["run_status"] == "resuming"
        assert inspected["claimed_by"] == "crashed-worker"

        # Operator can explicitly recover the stuck checkpoint back to 'paused'
        recovered = client2.post(
            f"/api/v1/projects/{slug}/runs/{run_id}/recover-checkpoint",
            json={
                "operator": "sre-oncall",
                "rationale": "Worker crashed during downstream node execution",
                "stale_after_seconds": 0.0,
            },
        )
        assert recovered.status_code == 200, recovered.text
        recovered_body = recovered.json()
        assert recovered_body["run_status"] == "paused"
        assert recovered_body["claim_token"] is None

        # And now resume executes cleanly without losing prior step history
        resumed = client2.post(
            f"/api/v1/projects/{slug}/runs/{run_id}/resume",
            json={
                "approved_choice": "BILLING",
                "operator": "sre-oncall",
                "rationale": "Resuming after checkpoint recovery",
            },
        )
        assert resumed.status_code == 200, resumed.text
        resumed_payload = resumed.json()
        assert len(resumed_payload["steps"]) == 2
        assert resumed_payload["steps"][0]["node_name"] == "triage-router"
        assert resumed_payload["steps"][1]["node_name"] == "billing-specialist"


def test_multi_pause_graph_can_be_cancelled_after_first_resume_pauses_at_stage_two(
    mock_client: TestClient,
) -> None:
    created = mock_client.post("/api/v1/projects", json={"name": "ThreeStage Co"})
    assert created.status_code == 201, created.text
    slug = created.json()["slug"]

    service_resp = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services",
        json={
            "name": "Three-Stage Approval Graph",
            "instructions": "Three stage workflow with human gates at stage 1 and stage 2.",
            "nodes": [
                {
                    "name": "stage-1-intake",
                    "instructions": "Classify intake request",
                    "pause_on_review": True,
                    "choices": [
                        {"key": "ESCALATE_FINANCE", "label": "Escalate to Finance"},
                        {"key": "ARCHIVE", "label": "Archive"},
                    ],
                },
                {
                    "name": "stage-2-finance",
                    "instructions": "Determine finance action",
                    "pause_on_review": True,
                    "choices": [
                        {"key": "WIRE_REVERSAL", "label": "Wire Reversal"},
                        {"key": "CREDIT_MEMO", "label": "Credit Memo"},
                    ],
                },
                {
                    "name": "stage-3-compliance",
                    "instructions": "Final compliance sign-off",
                    "pause_on_review": False,
                    "choices": [
                        {"key": "CLEARED", "label": "Cleared"},
                        {"key": "BLOCKED", "label": "Blocked"},
                    ],
                },
            ],
            "transitions": [
                {
                    "from_node_key": "stage-1-intake",
                    "choice_key": "ESCALATE_FINANCE",
                    "to_node_key": "stage-2-finance",
                    "require_approval": True,
                },
                {
                    "from_node_key": "stage-2-finance",
                    "choice_key": "WIRE_REVERSAL",
                    "to_node_key": "stage-3-compliance",
                    "require_approval": True,
                },
            ],
        },
    )
    assert service_resp.status_code == 201, service_resp.text
    service = service_resp.json()

    # Step 1: Initial execution pauses at stage-1-intake
    run_resp = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
        json={"content": "The weather on Mars is lovely this time of year"},
    )
    assert run_resp.status_code == 201, run_resp.text
    run = run_resp.json()[0]
    run_id = run["id"]
    assert run["run_status"] == "paused"
    assert run["current_node_key"] == "stage-1-intake"

    # Step 2: Resume stage-1-intake -> transitions to stage-2-finance and pauses AGAIN
    resume_stage1 = mock_client.post(
        f"/api/v1/projects/{slug}/runs/{run_id}/resume",
        json={
            "approved_choice": "ESCALATE_FINANCE",
            "operator": "intake-lead",
            "rationale": "Approved escalation to finance stage.",
        },
    )
    assert resume_stage1.status_code == 200, resume_stage1.text
    stage2_state = resume_stage1.json()
    assert stage2_state["status"] == "paused"
    assert stage2_state["run_status"] == "paused"
    assert stage2_state["current_node_key"] == "stage-2-finance"
    assert len(stage2_state["steps"]) == 2

    # Verify persisted run has resumed_at populated AND run_status == 'paused'
    persisted_stage2 = mock_client.get(f"/api/v1/projects/{slug}/runs/{run_id}").json()
    assert persisted_stage2["run_status"] == "paused"
    assert persisted_stage2["resumed_at"] is not None
    assert persisted_stage2["current_node_key"] == "stage-2-finance"

    # Step 3: Cancel the run while paused at stage-2-finance (Defect 3 regression test)
    cancelled = mock_client.post(
        f"/api/v1/projects/{slug}/runs/{run_id}/cancel",
        json={
            "operator": "finance-director",
            "reason": "Customer withdrew wire dispute before stage 2 approval.",
        },
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json() == {
        "run_id": run_id,
        "status": "cancelled",
        "cancelled_by": "finance-director",
        "reason": "Customer withdrew wire dispute before stage 2 approval.",
    }

    # Verify final state is cancelled and cannot be resumed
    final_run = mock_client.get(f"/api/v1/projects/{slug}/runs/{run_id}").json()
    assert final_run["run_status"] == "cancelled"
    assert final_run["cancelled_by"] == "finance-director"
    assert len(final_run["steps"]) == 2

    resume_after_cancel = mock_client.post(
        f"/api/v1/projects/{slug}/runs/{run_id}/resume",
        json={"approved_choice": "WIRE_REVERSAL", "operator": "finance-director"},
    )
    assert resume_after_cancel.status_code == 409


def test_stale_checkpoint_race_delayed_before_claim_across_multi_pause_stages(
    database_url: str,
) -> None:
    """Defect 1 regression: Request B reads stage-1 checkpoint before claiming,
    Request A advances the run to stage-2 (also paused), and Request B must fail
    atomically at claim time with 409 Conflict instead of re-executing stage-1->stage-2."""
    import asyncio
    from uuid import uuid4

    import httpx
    from openclass_core.models import ChoiceRequest, ChoiceResult
    from openclass_core.providers import DecisionProvider
    from openclass_server.main import create_app
    from openclass_server.settings import Settings

    stage2_calls = 0

    class StageCountingProvider:
        def __init__(self, inner: DecisionProvider) -> None:
            self._inner = inner

        async def choice(self, request: ChoiceRequest) -> ChoiceResult:
            nonlocal stage2_calls
            class_names = {c.canonical_name.upper() for c in request.ontology.classes}
            if "WIRE_REVERSAL" in class_names:
                stage2_calls += 1
            return await self._inner.choice(request)

    app_a = create_app(Settings(database_url=database_url, decision_provider="mock"))
    app_b = create_app(Settings(database_url=database_url, decision_provider="mock"))

    async def _scenario() -> None:
        async with (
            app_a.router.lifespan_context(app_a),
            app_b.router.lifespan_context(app_b),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_a), base_url="http://testserver"
            ) as async_a,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_b), base_url="http://testserver"
            ) as async_b,
        ):
            proj_resp = await async_a.post(
                "/api/v1/projects",
                json={"name": f"MultiStage CAS Race {uuid4().hex[:8]}"},
            )
            assert proj_resp.status_code == 201, proj_resp.text
            slug = proj_resp.json()["slug"]

            service_resp = await async_a.post(
                f"/api/v1/projects/{slug}/decision-services",
                json={
                    "name": "Three-Stage CAS Graph",
                    "instructions": "Three stage workflow with human gates at stage 1 and stage 2.",
                    "nodes": [
                        {
                            "name": "stage-1-intake",
                            "instructions": "Classify intake request",
                            "pause_on_review": True,
                            "choices": [
                                {"key": "ESCALATE_FINANCE", "label": "Escalate to Finance"},
                                {"key": "ARCHIVE", "label": "Archive"},
                            ],
                        },
                        {
                            "name": "stage-2-finance",
                            "instructions": "Determine finance action",
                            "pause_on_review": True,
                            "choices": [
                                {"key": "WIRE_REVERSAL", "label": "Wire Reversal"},
                                {"key": "CREDIT_MEMO", "label": "Credit Memo"},
                            ],
                        },
                        {
                            "name": "stage-3-compliance",
                            "instructions": "Final compliance sign-off",
                            "pause_on_review": False,
                            "choices": [
                                {"key": "CLEARED", "label": "Cleared"},
                                {"key": "BLOCKED", "label": "Blocked"},
                            ],
                        },
                    ],
                    "transitions": [
                        {
                            "from_node_key": "stage-1-intake",
                            "choice_key": "ESCALATE_FINANCE",
                            "to_node_key": "stage-2-finance",
                            "require_approval": True,
                        },
                        {
                            "from_node_key": "stage-2-finance",
                            "choice_key": "WIRE_REVERSAL",
                            "to_node_key": "stage-3-compliance",
                            "require_approval": True,
                        },
                    ],
                },
            )
            assert service_resp.status_code == 201, service_resp.text
            service = service_resp.json()

            run_resp = await async_a.post(
                f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
                json={"content": "The weather on Mars is lovely this time of year"},
            )
            assert run_resp.status_code == 201, run_resp.text
            initial_run = run_resp.json()[0]
            run_id = initial_run["id"]
            assert initial_run["run_status"] == "paused"
            assert initial_run["current_node_key"] == "stage-1-intake"
            assert initial_run["checkpoint_revision"] == 1

            app_a.state.decision_provider = StageCountingProvider(app_a.state.decision_provider)
            app_b.state.decision_provider = StageCountingProvider(app_b.state.decision_provider)

            repo_b = app_b.state.project_repository
            orig_claim_b = repo_b.claim_decision_run_for_resume

            b_ready_to_claim = asyncio.Event()
            release_b = asyncio.Event()
            intercepted = False

            async def delayed_claim_b(*args: Any, **kwargs: Any) -> Any:
                nonlocal intercepted
                if not intercepted:
                    intercepted = True
                    b_ready_to_claim.set()
                    await release_b.wait()
                return await orig_claim_b(*args, **kwargs)

            repo_b.claim_decision_run_for_resume = delayed_claim_b
            try:
                task_b = asyncio.create_task(
                    async_b.post(
                        f"/api/v1/projects/{slug}/runs/{run_id}/resume",
                        json={
                            "approved_choice": "ESCALATE_FINANCE",
                            "operator": "operator-b-stale",
                            "rationale": "Delayed stage-1 approval from stale reader B",
                        },
                    )
                )
                await asyncio.wait_for(b_ready_to_claim.wait(), timeout=5.0)

                # While Request B is paused right before claiming (holding stage-1 snapshot),
                # Request A claims stage-1, executes stage-2-finance, and pauses at stage-2!
                resp_a = await async_a.post(
                    f"/api/v1/projects/{slug}/runs/{run_id}/resume",
                    json={
                        "approved_choice": "ESCALATE_FINANCE",
                        "operator": "operator-a-winner",
                        "rationale": "Stage-1 approval by winner A",
                    },
                )
                release_b.set()
                resp_b = await asyncio.wait_for(task_b, timeout=5.0)

                # Also verify a subsequent stale stage-1 approval request is rejected with 409
                resp_c = await async_b.post(
                    f"/api/v1/projects/{slug}/runs/{run_id}/resume",
                    json={
                        "approved_choice": "ESCALATE_FINANCE",
                        "operator": "operator-c-stale",
                        "rationale": "Late stage-1 approval after run moved to stage-2",
                    },
                )
            finally:
                repo_b.claim_decision_run_for_resume = orig_claim_b

            assert resp_a.status_code == 200, resp_a.text
            assert resp_b.status_code == 409, resp_b.text
            assert "changed concurrently" in resp_b.json()["detail"]
            assert resp_c.status_code == 409, resp_c.text

            # Downstream stage-2-finance provider was invoked strictly ONCE
            assert stage2_calls == 1

            persisted = (await async_a.get(f"/api/v1/projects/{slug}/runs/{run_id}")).json()
            assert persisted["run_status"] == "paused"
            assert persisted["current_node_key"] == "stage-2-finance"
            assert persisted["resumed_by"] == "operator-a-winner"
            assert persisted["checkpoint_revision"] == 3
            assert len(persisted["steps"]) == 2

    asyncio.run(_scenario())


def test_active_worker_recovery_enforces_lease_timeout_and_fences_superseded_worker(
    database_url: str,
) -> None:
    """Defect 2 regression:
    1. /recover-checkpoint enforces the configured lease timeout by default and rejects
       recovery of an active in-flight worker (even if stale_after_seconds=0.0 is passed).
    2. Force recovery requires privileged admin role/scope and non-empty rationale.
    3. When a privileged admin force-recovers a wedged worker and Worker B takes over,
       the superseded Worker A is fenced on both save_resumed_decision_run and
       mark_decision_run_failed, preventing duplicate feedback/audit or state corruption."""
    import asyncio
    from uuid import uuid4

    import httpx
    from openclass_core.models import ChoiceRequest, ChoiceResult
    from openclass_core.providers import DecisionProvider, ProviderError
    from openclass_server.main import create_app
    from openclass_server.settings import Settings

    app_a = create_app(
        Settings(
            database_url=database_url,
            decision_provider="mock",
            decision_run_resume_claim_ttl_seconds=300.0,
            internal_token="checkpoint-test-internal-token",
            auth_required=True,
        )
    )
    app_b = create_app(
        Settings(
            database_url=database_url,
            decision_provider="mock",
            decision_run_resume_claim_ttl_seconds=300.0,
            internal_token="checkpoint-test-internal-token",
            auth_required=True,
        )
    )

    class GatedProvider:
        def __init__(
            self,
            inner: DecisionProvider,
            entered: asyncio.Event,
            release: asyncio.Event,
            *,
            fail_on_release: bool = False,
        ) -> None:
            self._inner = inner
            self.entered = entered
            self.release = release
            self.fail_on_release = fail_on_release
            self.call_count = 0

        async def choice(self, request: ChoiceRequest) -> ChoiceResult:
            self.call_count += 1
            self.entered.set()
            await self.release.wait()
            if self.fail_on_release:
                raise ProviderError("Simulated provider failure in superseded worker")
            return await self._inner.choice(request)

    class CountingProvider:
        def __init__(self, inner: DecisionProvider) -> None:
            self._inner = inner
            self.call_count = 0

        async def choice(self, request: ChoiceRequest) -> ChoiceResult:
            self.call_count += 1
            return await self._inner.choice(request)

    async def _scenario() -> None:
        worker_headers = {
            "X-OpenClass-Internal-Token": "checkpoint-test-internal-token",
            "X-OpenClass-Actor": "regular-worker",
        }
        async with (
            app_a.router.lifespan_context(app_a),
            app_b.router.lifespan_context(app_b),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_a),
                base_url="http://testserver",
                headers=worker_headers,
            ) as async_a,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_b),
                base_url="http://testserver",
                headers=worker_headers,
            ) as async_b,
        ):
            proj_resp = await async_a.post(
                "/api/v1/projects",
                json={"name": f"Lease Fencing Corp {uuid4().hex[:8]}"},
            )
            assert proj_resp.status_code == 201, proj_resp.text
            slug = proj_resp.json()["slug"]

            svc_resp = await async_a.post(
                f"/api/v1/projects/{slug}/decision-services",
                json={
                    "name": "Two-Stage Support Graph",
                    "instructions": "Route and resolve customer tickets across two stages.",
                    "nodes": [
                        {
                            "name": "triage-router",
                            "instructions": "Route ticket to department",
                            "pause_on_review": True,
                            "choices": [
                                {"key": "BILLING", "label": "Billing Department"},
                                {"key": "DELIVERY", "label": "Delivery Department"},
                            ],
                        },
                        {
                            "name": "billing-specialist",
                            "instructions": "Select billing resolution action",
                            "pause_on_review": False,
                            "choices": [
                                {"key": "REFUND", "label": "Issue Refund"},
                                {"key": "INVOICE", "label": "Resend Invoice"},
                            ],
                        },
                    ],
                    "transitions": [
                        {
                            "from_node_key": "triage-router",
                            "choice_key": "BILLING",
                            "to_node_key": "billing-specialist",
                            "require_approval": True,
                        }
                    ],
                },
            )
            assert svc_resp.status_code == 201, svc_resp.text
            service = svc_resp.json()

            async def _create_paused_run(tag: str) -> str:
                r = await async_a.post(
                    f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
                    json={"content": f"The weather on Mars is lovely this time of year ({tag})"},
                )
                assert r.status_code == 201, r.text
                run_obj = r.json()[0]
                assert run_obj["run_status"] == "paused"
                return str(run_obj["id"])

            run_1 = await _create_paused_run("part-a-lease-protection")
            run_2 = await _create_paused_run("part-b-fenced-success")
            run_3 = await _create_paused_run("part-c-fenced-error")

            base_provider_a = app_a.state.decision_provider
            base_provider_b = app_b.state.decision_provider

            # ── Part A: Active worker is protected by configured lease timeout ──
            entered_a = asyncio.Event()
            release_a = asyncio.Event()
            gated_a = GatedProvider(base_provider_a, entered_a, release_a)
            counting_b = CountingProvider(base_provider_b)
            app_a.state.decision_provider = gated_a
            app_b.state.decision_provider = counting_b

            worker_a_task = asyncio.create_task(
                async_a.post(
                    f"/api/v1/projects/{slug}/runs/{run_1}/resume",
                    json={
                        "approved_choice": "BILLING",
                        "operator": "worker-a",
                        "rationale": "Active worker A resume",
                    },
                )
            )
            await asyncio.wait_for(entered_a.wait(), timeout=5.0)

            # 1. Default /recover-checkpoint with {} must fail with 409 (lease not expired)
            rec_default = await async_b.post(
                f"/api/v1/projects/{slug}/runs/{run_1}/recover-checkpoint",
                json={},
            )
            assert rec_default.status_code == 409, rec_default.text
            assert "not yet stale" in rec_default.json()["detail"]

            # 2. /recover-checkpoint with stale_after_seconds=0.0 (no force) fails with 409
            rec_zero = await async_b.post(
                f"/api/v1/projects/{slug}/runs/{run_1}/recover-checkpoint",
                json={"stale_after_seconds": 0.0, "operator": "impatient-op"},
            )
            assert rec_zero.status_code == 409, rec_zero.text

            # 3. Unprivileged force=True on /recover-checkpoint must fail with 403 Forbidden
            rec_unpriv = await async_b.post(
                f"/api/v1/projects/{slug}/runs/{run_1}/recover-checkpoint",
                json={
                    "force": True,
                    "operator": "regular-op",
                    "rationale": "Trying force recovery without admin role",
                },
            )
            assert rec_unpriv.status_code == 403, rec_unpriv.text

            # 4. Unprivileged force_recover_stale_claim=True on /resume fails with 403
            res_unpriv = await async_b.post(
                f"/api/v1/projects/{slug}/runs/{run_1}/resume",
                json={
                    "approved_choice": "BILLING",
                    "operator": "regular-op",
                    "rationale": "Trying force resume without admin role",
                    "force_recover_stale_claim": True,
                },
            )
            assert res_unpriv.status_code == 403, res_unpriv.text

            # 5. Concurrent normal /resume on app_b must fail with 409 Conflict
            res_conflict = await async_b.post(
                f"/api/v1/projects/{slug}/runs/{run_1}/resume",
                json={"approved_choice": "BILLING", "operator": "worker-b"},
            )
            assert res_conflict.status_code == 409, res_conflict.text

            release_a.set()
            resp_a = await asyncio.wait_for(worker_a_task, timeout=5.0)
            assert resp_a.status_code == 200, resp_a.text
            assert gated_a.call_count == 1
            assert counting_b.call_count == 0

            # ── Part B: Privileged force recovery + fencing superseded worker on completion ──
            entered_b_part = asyncio.Event()
            release_b_part = asyncio.Event()
            gated_a_2 = GatedProvider(base_provider_a, entered_b_part, release_b_part)
            counting_b_2 = CountingProvider(base_provider_b)
            app_a.state.decision_provider = gated_a_2
            app_b.state.decision_provider = counting_b_2

            worker_a_task_2 = asyncio.create_task(
                async_a.post(
                    f"/api/v1/projects/{slug}/runs/{run_2}/resume",
                    json={
                        "approved_choice": "BILLING",
                        "operator": "worker-a-wedged",
                        "rationale": "Worker A initial resume",
                    },
                )
            )
            await asyncio.wait_for(entered_b_part.wait(), timeout=5.0)

            # Privileged admin force-recovers the checkpoint on app_b
            rec_admin = await async_b.post(
                f"/api/v1/projects/{slug}/runs/{run_2}/recover-checkpoint",
                headers={"X-OpenClass-Role": "admin", "X-OpenClass-Actor": "sre-admin"},
                json={
                    "operator": "sre-admin",
                    "rationale": "Worker A wedged in upstream provider call",
                    "force": True,
                },
            )
            assert rec_admin.status_code == 200, rec_admin.text
            rec_body = rec_admin.json()
            assert rec_body["run_status"] == "paused"
            assert rec_body["checkpoint_revision"] == 3

            # Worker B claims and completes the run on app_b
            resp_b = await async_b.post(
                f"/api/v1/projects/{slug}/runs/{run_2}/resume",
                headers={"X-OpenClass-Actor": "worker-b-takeover"},
                json={
                    "approved_choice": "BILLING",
                    "operator": "worker-b-takeover",
                    "rationale": "Completed by Worker B after force recovery",
                },
            )
            assert resp_b.status_code == 200, resp_b.text

            # Now release superseded Worker A -> must be fenced with 409 Conflict
            release_b_part.set()
            resp_a_2 = await asyncio.wait_for(worker_a_task_2, timeout=5.0)
            assert resp_a_2.status_code == 409, resp_a_2.text
            assert "claim is no longer valid" in resp_a_2.json()["detail"]

            persisted_2 = (await async_b.get(f"/api/v1/projects/{slug}/runs/{run_2}")).json()
            assert persisted_2["resumed_by"] == "worker-b-takeover"
            assert persisted_2["resume_rationale"] == "Completed by Worker B after force recovery"
            assert persisted_2["checkpoint_revision"] == 5
            assert len(persisted_2["steps"]) == 2

            audit_2 = [
                ev
                for ev in (await async_b.get(f"/api/v1/projects/{slug}/audit")).json()
                if ev["payload"].get("run_id") == run_2
                or ev["payload"].get("decision_run_id") == run_2
            ]
            resumed_events_2 = [ev for ev in audit_2 if ev["event_type"] == "decision_run_resumed"]
            feedback_events_2 = [ev for ev in audit_2 if ev["event_type"] == "feedback.submitted"]
            assert len(resumed_events_2) == 1
            assert resumed_events_2[0]["actor"] == "worker-b-takeover"
            assert len(feedback_events_2) == 1

            # ── Part C: Superseded worker failing with ProviderError is fenced ──
            entered_c_part = asyncio.Event()
            release_c_part = asyncio.Event()
            gated_a_3 = GatedProvider(
                base_provider_a, entered_c_part, release_c_part, fail_on_release=True
            )
            counting_b_3 = CountingProvider(base_provider_b)
            app_a.state.decision_provider = gated_a_3
            app_b.state.decision_provider = counting_b_3

            worker_a_task_3 = asyncio.create_task(
                async_a.post(
                    f"/api/v1/projects/{slug}/runs/{run_3}/resume",
                    json={
                        "approved_choice": "BILLING",
                        "operator": "worker-a-failing",
                        "rationale": "Worker A resume that will fail after preemption",
                    },
                )
            )
            await asyncio.wait_for(entered_c_part.wait(), timeout=5.0)

            # Privileged admin takes over via force_recover_stale_claim=True on /resume
            resp_b_3 = await async_b.post(
                f"/api/v1/projects/{slug}/runs/{run_3}/resume",
                headers={"X-OpenClass-Role": "admin", "X-OpenClass-Actor": "worker-b-admin"},
                json={
                    "approved_choice": "BILLING",
                    "operator": "worker-b-admin",
                    "rationale": "Force takeover by admin Worker B",
                    "force_recover_stale_claim": True,
                },
            )
            assert resp_b_3.status_code == 200, resp_b_3.text

            # Release Worker A -> mark_decision_run_failed is fenced with 409 Conflict
            release_c_part.set()
            resp_a_3 = await asyncio.wait_for(worker_a_task_3, timeout=5.0)
            assert resp_a_3.status_code == 409, resp_a_3.text

            persisted_3 = (await async_b.get(f"/api/v1/projects/{slug}/runs/{run_3}")).json()
            assert persisted_3["run_status"] != "failed"
            assert persisted_3["failure_reason"] is None
            assert persisted_3["resumed_by"] == "worker-b-admin"
            assert len(persisted_3["steps"]) == 2

    asyncio.run(_scenario())
