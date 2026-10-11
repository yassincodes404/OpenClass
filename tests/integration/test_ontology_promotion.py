"""Phase 14 guarded promotion: guards, immutability, diff, rollback."""

from __future__ import annotations

from fastapi.testclient import TestClient
from openclass_core.promotion import PromotionBlocked, diff_choices, ensure_promotion_guards

import pytest


def test_guard_logic_blocks_unapproved_and_unevaluated():
    with pytest.raises(PromotionBlocked, match="approved"):
        ensure_promotion_guards(
            candidate_status="candidate",
            evidence_count=8,
            evaluation_passed=True,
            rationale="looks good",
            reviewer="reviewer@x.test",
        )
    with pytest.raises(PromotionBlocked, match="evaluation"):
        ensure_promotion_guards(
            candidate_status="approved",
            evidence_count=8,
            evaluation_passed=None,
            rationale="looks good",
            reviewer="reviewer@x.test",
        )
    with pytest.raises(PromotionBlocked, match="failed"):
        ensure_promotion_guards(
            candidate_status="approved",
            evidence_count=8,
            evaluation_passed=False,
            rationale="looks good",
            reviewer="reviewer@x.test",
        )
    with pytest.raises(PromotionBlocked, match="evidence"):
        ensure_promotion_guards(
            candidate_status="approved",
            evidence_count=2,
            evaluation_passed=True,
            rationale="looks good",
            reviewer="reviewer@x.test",
        )
    ensure_promotion_guards(
        candidate_status="approved",
        evidence_count=5,
        evaluation_passed=True,
        rationale="verified end to end",
        reviewer="reviewer@x.test",
    )


def test_diff_choices_added_removed_modified():
    before = [{"key": "BILLING", "label": "Billing"}]
    after = [
        {"key": "BILLING", "label": "Billing!"},
        {"key": "CANCEL_PLAN", "label": "Cancel Plan"},
    ]
    changes = diff_choices(before, after)
    assert changes["added"] == ["CANCEL_PLAN"]
    assert changes["removed"] == []
    assert changes["modified"] == ["BILLING"]


def _full_pipeline(client: TestClient) -> tuple[str, str, str, str]:
    """known→unknown→cluster→candidate→collect→approve→evaluate (passing)."""
    slug = client.post("/api/v1/projects", json={"name": "Promote Co"}).json()["slug"]
    service = client.post(
        f"/api/v1/projects/{slug}/decision-services",
        json={
            "name": "Router",
            "instructions": "Route the request.",
            "choices": [{"key": "BILLING", "label": "Billing"}],
        },
    ).json()["id"]
    for text in [
        "Cancel my plan immediately",
        "Cancel my plan today please",
        "Cancel my plan once and for all",
        "Cancel my subscription plan now",
        "Cancel plan next month",
    ]:
        client.post(
            f"/api/v1/projects/{slug}/decision-services/{service}/runs", json={"content": text}
        )
    client.post(f"/api/v1/projects/{slug}/unknowns/cluster", json={"threshold": 0.2})
    clusters = client.get(f"/api/v1/projects/{slug}/unknowns/clusters").json()
    biggest = max(clusters, key=lambda entry: entry["size"])
    candidate = client.post(f"/api/v1/projects/{slug}/clusters/{biggest['id']}/discover").json()
    label = candidate["canonical_name"].upper()
    detail = client.get(f"/api/v1/projects/{slug}/discovery-candidates/{candidate['id']}").json()
    collected = set(detail.get("evidence_run_ids", []))
    pool = client.get(f"/api/v1/projects/{slug}/unknowns?limit=50").json()["items"]
    extras = [item["run_id"] for item in pool if item["run_id"] not in collected]
    need = max(0, 5 - len(collected))
    if need > 0:
        collected_resp = client.post(
            f"/api/v1/projects/{slug}/discovery-candidates/{candidate['id']}/collect",
            json={"unknown_ids": extras[:need]},
        )
        assert collected_resp.status_code == 200, collected_resp.text
    client.post(f"/api/v1/projects/{slug}/discovery-candidates/{candidate['id']}/request-review")
    client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate['id']}/review",
        json={"decision": "approve", "rationale": "five verified observations"},
    )
    dataset = client.post(
        f"/api/v1/projects/{slug}/eval-datasets", json={"name": "promo-gold"}
    ).json()["id"]
    for text, gold in [
        ("Cancel my plan immediately", label),
        ("Cancel my plan today please", label),
        ("I have a billing question", "BILLING"),
    ]:
        client.post(
            f"/api/v1/projects/{slug}/eval-datasets/{dataset}/examples",
            json={"text": text, "label": gold, "source": "human", "annotator": "a@b.test"},
        )
    client.post(f"/api/v1/projects/{slug}/eval-datasets/{dataset}/seal")
    evaluation = client.post(
        f"/api/v1/projects/{slug}/evaluations",
        json={"dataset_id": dataset, "candidate_id": candidate["id"]},
    ).json()
    assert evaluation["overall_passed"], evaluation
    return slug, service, candidate["id"], evaluation["id"]


def test_promotion_requires_passing_evaluation(mock_client: TestClient):
    slug, service, candidate_id, evaluation_id = _full_pipeline(mock_client)
    blocked = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/promote",
        json={"evaluation_id": "0" * 36, "reviewer": "reviewer@x.test", "rationale": "no eval"},
    )
    assert blocked.status_code == 409


def test_guarded_promotion_creates_v2_and_activates(mock_client: TestClient):
    slug, service, candidate_id, evaluation_id = _full_pipeline(mock_client)
    promoted = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/promote",
        json={
            "evaluation_id": evaluation_id,
            "reviewer": "reviewer@acme.test",
            "rationale": "verified improvement with no billing regression",
        },
    )
    assert promoted.status_code == 200, promoted.text
    body = promoted.json()
    assert body["status"] == "active"
    assert body["version"]["version_number"] == 2
    # v1 unchanged, v2 has the class; diff shows the addition.
    ontology = mock_client.get(f"/api/v1/projects/{slug}/ontology").json()
    assert len(ontology["versions"]) == 2
    diff = mock_client.get(
        f"/api/v1/projects/{slug}/ontology/diff?from_version=1&to_version=2"
    ).json()
    assert body["added_class"] in diff["changes"]["added"]
    # A text containing the promoted canonical phrase now classifies known.
    # (Other phrasings may still be UNKNOWN — the lexical mock matches the
    # canonical phrase only; that limitation is honest and visible.)
    runs = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services/{service}/runs",
        json={"content": "Cancel plan next month"},
    ).json()
    assert runs[0]["selected_choice"] == body["added_class"]
    # Second promotion of an active candidate conflicts.
    again = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/promote",
        json={
            "evaluation_id": evaluation_id,
            "reviewer": "reviewer@acme.test",
            "rationale": "again",
        },
    )
    assert again.status_code == 409


def test_unapproved_candidate_cannot_promote(mock_client: TestClient):
    slug = mock_client.post("/api/v1/projects", json={"name": "Guard Co"}).json()["slug"]
    service = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services",
        json={
            "name": "Router",
            "instructions": "Route the request.",
            "choices": [{"key": "BILLING", "label": "Billing"}],
        },
    ).json()["id"]
    for text in [
        "Cancel my plan immediately",
        "Cancel my plan today please",
        "Cancel my plan once and for all",
        "Cancel my subscription plan now",
        "Cancel plan next month",
    ]:
        client_run(mock_client, slug, service, text)
    client_cluster(mock_client, slug)
    clusters = mock_client.get(f"/api/v1/projects/{slug}/unknowns/clusters").json()
    biggest = max(clusters, key=lambda entry: entry["size"])
    candidate = client_discover(mock_client, slug, biggest["id"])
    blocked = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate['id']}/promote",
        json={"evaluation_id": "0" * 36, "reviewer": "reviewer@x.test", "rationale": "skip gates"},
    )
    assert blocked.status_code in (404, 409)


def test_rollback_creates_new_version_from_older(mock_client: TestClient):
    slug, service, candidate_id, evaluation_id = _full_pipeline(mock_client)
    mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/promote",
        json={
            "evaluation_id": evaluation_id,
            "reviewer": "reviewer@acme.test",
            "rationale": "verified improvement, promoting",
        },
    )
    rollback = mock_client.post(
        f"/api/v1/projects/{slug}/ontology/rollback",
        json={"from_version": 1, "rationale": "restoring pre-promotion ontology"},
    )
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["version"]["version_number"] == 3
    ontology = mock_client.get(f"/api/v1/projects/{slug}/ontology").json()
    assert len(ontology["versions"]) == 3  # history intact; v3 derived from v1
    # Post-rollback classification returns to UNKNOWN for the rolled-back class.
    runs = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services/{service}/runs",
        json={"content": "Cancel my plan immediately"},
    ).json()
    assert runs[0]["selected_choice"] == "UNKNOWN" or runs[0]["supervision_outcome"] == "UNKNOWN"
    # Rolling back to the current version is rejected.
    repeat = mock_client.post(
        f"/api/v1/projects/{slug}/ontology/rollback",
        json={"from_version": 3, "rationale": "no-op rollback"},
    )
    assert repeat.status_code == 409


def client_run(client: TestClient, slug: str, service: str, text: str) -> None:
    client.post(f"/api/v1/projects/{slug}/decision-services/{service}/runs", json={"content": text})


def client_cluster(client: TestClient, slug: str) -> None:
    client.post(f"/api/v1/projects/{slug}/unknowns/cluster", json={"threshold": 0.2})


def client_discover(client: TestClient, slug: str, cluster_id: str) -> dict:
    return client.post(f"/api/v1/projects/{slug}/clusters/{cluster_id}/discover").json()
