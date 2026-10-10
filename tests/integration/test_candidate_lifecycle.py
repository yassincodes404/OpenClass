"""Phase 11 candidate lifecycle: state machine, evidence gate, append-only reviews."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from openclass_core.candidates import (
    MIN_DISTINCT_EVIDENCE,
    review_gaps,
    validate_candidate_transition,
)


def test_state_machine_legal_and_illegal_moves():
    validate_candidate_transition("discovered", "candidate")
    validate_candidate_transition("candidate", "collecting_evidence")
    validate_candidate_transition("collecting_evidence", "validating")
    validate_candidate_transition("validating", "approved")
    validate_candidate_transition("approved", "active")
    with pytest.raises(ValueError):
        validate_candidate_transition("candidate", "approved")
    with pytest.raises(ValueError):
        validate_candidate_transition("rejected", "candidate")
    with pytest.raises(ValueError):
        validate_candidate_transition("active", "rejected")


def test_evidence_gap_message():
    assert review_gaps(3) == f"collect more evidence (3/{MIN_DISTINCT_EVIDENCE})"
    assert review_gaps(5) is None


def _seed_small_cluster_candidate(
    client: TestClient, cluster_threshold: float = 0.95
) -> tuple[str, str]:
    """Candidate from a small cluster (evidence = cluster members < 5)."""
    slug = client.post("/api/v1/projects", json={"name": "Review Co"}).json()["slug"]
    service = client.post(
        f"/api/v1/projects/{slug}/decision-services",
        json={
            "name": "Router",
            "instructions": "Route the request.",
            "choices": [{"key": "BILLING", "label": "Billing"}],
        },
    ).json()["id"]
    texts = [
        "Cancel my plan immediately",
        "How do I cancel this plan?",
        "Please close my subscription",
        "I want to unsubscribe",
        "Terminate my recurring plan",
        "Stop renewing my plan",
        "Cancel the auto renewal",
        "End the subscription now",
    ]
    for text in texts:
        client.post(
            f"/api/v1/projects/{slug}/decision-services/{service}/runs", json={"content": text}
        )
    client.post(f"/api/v1/projects/{slug}/unknowns/cluster", json={"threshold": cluster_threshold})
    clusters = client.get(f"/api/v1/projects/{slug}/unknowns/clusters").json()
    small = min(clusters, key=lambda entry: entry["size"])
    assert small["size"] < 5, "expected a small cluster below the evidence threshold"
    candidate = client.post(f"/api/v1/projects/{slug}/clusters/{small['id']}/discover").json()
    return slug, candidate["id"]


def test_review_blocked_below_evidence_threshold(mock_client: TestClient):
    slug, candidate_id = _seed_small_cluster_candidate(mock_client)
    review = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/review",
        json={"decision": "approve", "rationale": "looks like a real intent"},
    )
    assert review.status_code == 409
    assert f"/{MIN_DISTINCT_EVIDENCE})" in review.json()["detail"]


def test_collect_more_evidence_then_approve(mock_client: TestClient):
    slug, candidate_id = _seed_small_cluster_candidate(mock_client)
    pool = mock_client.get(f"/api/v1/projects/{slug}/unknowns?limit=50").json()["items"]
    detail = mock_client.get(f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}").json()
    collected = set(detail.get("evidence_run_ids", []))
    extras = [item["run_id"] for item in pool if item["run_id"] not in collected]
    need = MIN_DISTINCT_EVIDENCE - len(collected)
    assert len(extras) >= need
    collect = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/collect",
        json={"unknown_ids": extras[:need]},
    )
    assert collect.status_code == 200, collect.text
    assert collect.json()["evidence"] >= MIN_DISTINCT_EVIDENCE
    requested = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/request-review"
    )
    assert requested.status_code == 200
    review = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/review",
        json={"decision": "approve", "rationale": "five distinct observations verified"},
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "approved"
    # Approved is still inactive; no activation route exists.
    activate = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/activate"
    )
    assert activate.status_code in (404, 405)


def test_duplicate_evidence_is_deduped(mock_client: TestClient):
    slug, candidate_id = _seed_small_cluster_candidate(mock_client)
    detail = mock_client.get(f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}").json()
    collected = sorted(set(detail.get("evidence_run_ids", [])))
    again = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/collect",
        json={"unknown_ids": collected},
    )
    assert again.status_code == 200
    assert again.json()["evidence"] == len(collected)


def test_cross_project_evidence_rejected(mock_client: TestClient):
    slug_a, candidate_a = _seed_small_cluster_candidate(mock_client)
    slug_b, _candidate_b = _seed_small_cluster_candidate(mock_client)
    pool_b = mock_client.get(f"/api/v1/projects/{slug_b}/unknowns?limit=5").json()["items"]
    collect = mock_client.post(
        f"/api/v1/projects/{slug_a}/discovery-candidates/{candidate_a}/collect",
        json={"unknown_ids": [pool_b[0]["run_id"]]},
    )
    assert collect.status_code == 404


def test_rejection_is_audited_and_terminal(mock_client: TestClient):
    slug, candidate_id = _seed_small_cluster_candidate(mock_client, cluster_threshold=0.5)
    reject = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/reject",
        json={"reason": "already covered by an existing intent"},
    )
    assert reject.status_code == 200
    history = mock_client.get(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/history"
    ).json()
    events = [entry["event"] for entry in history["events"]]
    assert "candidate.rejected" in events
    # Terminal: further transitions 409.
    again = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/request-review"
    )
    assert again.status_code == 409


def test_illegal_transition_returns_409(mock_client: TestClient):
    slug, candidate_id = _seed_small_cluster_candidate(mock_client)
    review = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/review",
        json={"decision": "approve", "rationale": "skipping the pipeline"},
    )
    assert review.status_code == 409
