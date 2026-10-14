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
