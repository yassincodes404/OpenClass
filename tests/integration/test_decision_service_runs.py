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
