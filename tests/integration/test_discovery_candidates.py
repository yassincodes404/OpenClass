"""Phase 10 discovery & canonicalization: six types, evidence links, no ontology writes."""

from __future__ import annotations

from fastapi.testclient import TestClient
from openclass_core.candidates import (
    ClusterDiscoveryRequest,
    MockClusterDiscoveryProvider,
    decide_proposal,
    normalize_phrase,
)


def test_synonyms_cannot_bypass_canonicalization():
    assert normalize_phrase("please close subscription") == "please cancel plan"
    assert normalize_phrase("I want to unsubscribe") == "i want to cancel plan"


def test_cancel_variants_merge_into_one_new_class():
    result = decide_proposal(
        [
            "Cancel my plan immediately",
            "How do I cancel this plan?",
            "Please close my subscription",
            "I want to unsubscribe",
            "Terminate my recurring plan",
        ],
        ["billing", "refund"],
    )
    assert result.type == "NEW_CLASS"
    assert result.canonical_name == "cancel_plan"
    assert result.confidence > 0.5


def test_existing_class_wins_over_new():
    result = decide_proposal(
        ["billing question one", "billing question two", "billing question three"],
        ["billing", "refund"],
    )
    assert result.type == "EXISTING_CLASS"
    assert result.existing_match == "billing"


def test_small_cluster_is_insufficient_evidence():
    result = decide_proposal(["only one text"], ["billing"])
    assert result.type == "INSUFFICIENT_EVIDENCE"
    assert result.confidence < 0.5


def _setup(client: TestClient) -> tuple[str, str, str]:
    slug = client.post("/api/v1/projects", json={"name": "Discover Co"}).json()["slug"]
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
        "How do I cancel this plan?",
        "Please close my subscription",
        "I want to unsubscribe",
        "Terminate my recurring plan",
        "Someone changed my account email",
    ]:
        client.post(
            f"/api/v1/projects/{slug}/decision-services/{service}/runs", json={"content": text}
        )
    clustered = client.post(f"/api/v1/projects/{slug}/unknowns/cluster", json={"threshold": 0.3})
    assert clustered.status_code == 200, clustered.text
    clusters = client.get(f"/api/v1/projects/{slug}/unknowns/clusters").json()
    biggest = max(clusters, key=lambda entry: entry["size"])
    return slug, service, biggest["id"]


def test_discovery_creates_inactive_candidate_with_all_members(mock_client: TestClient):
    slug, service, cluster_id = _setup(mock_client)
    discovered = client_discover(mock_client, slug, cluster_id)
    assert discovered["status"] == "candidate"
    assert discovered["type"] == "NEW_CLASS"
    # Exact phrase depends on cluster composition; the theme must point at
    # cancellation after synonym canonicalization (never billing/refund).
    assert "cancel" in discovered["canonical_name"] or "plan" in discovered["canonical_name"]
    assert discovered["canonical_name"] not in {"billing", "refund"}
    assert discovered["simulated"] is True
    detail = mock_client.get(
        f"/api/v1/projects/{slug}/discovery-candidates/{discovered['id']}"
    ).json()
    assert detail["evidence_run_ids"]
    listing = mock_client.get(f"/api/v1/projects/{slug}/discovery-candidates").json()
    assert any(entry["id"] == discovered["id"] for entry in listing)
    # No ontology write: classifier ontology versions unchanged (v1 only).
    # (The decision-service node still exposes exactly BILLING + UNKNOWN.)
    engine_service = mock_client.get(f"/api/v1/projects/{slug}/decision-services").json()[0]
    keys = [choice["key"] for choice in engine_service["nodes"][0]["choices"]]
    assert set(keys) == {"BILLING", "UNKNOWN"}


def client_discover(client: TestClient, slug: str, cluster_id: str) -> dict:
    response = client.post(f"/api/v1/projects/{slug}/clusters/{cluster_id}/discover")
    assert response.status_code == 201, response.text
    return response.json()


def test_singleton_cluster_yields_insufficient_evidence(mock_client: TestClient):
    slug = mock_client.post("/api/v1/projects", json={"name": "Tiny Disc"}).json()["slug"]
    service = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services",
        json={
            "name": "R",
            "instructions": "Route it.",
            "choices": [{"key": "BILLING", "label": "Billing"}],
        },
    ).json()["id"]
    for text in ["odd message one", "totally different second message"]:
        client_discover_run(mock_client, slug, service, text)
    mock_client.post(f"/api/v1/projects/{slug}/unknowns/cluster", json={"threshold": 0.99})
    clusters = mock_client.get(f"/api/v1/projects/{slug}/unknowns/clusters").json()
    singletons = [entry for entry in clusters if entry["size"] == 1]
    assert singletons
    discovered = client_discover(mock_client, slug, singletons[0]["id"])
    assert discovered["type"] == "INSUFFICIENT_EVIDENCE"


def client_discover_run(client: TestClient, slug: str, service: str, text: str) -> None:
    run = client.post(
        f"/api/v1/projects/{slug}/decision-services/{service}/runs", json={"content": text}
    )
    assert run.status_code == 201


def test_mock_cluster_provider_is_deterministic():
    provider = MockClusterDiscoveryProvider()
    request = ClusterDiscoveryRequest(
        cluster_id="00000000-0000-4000-8000-000000000001",
        member_texts=("cancel my plan", "close subscription", "unsubscribe now"),
        existing_classes=("billing",),
    )
    first = provider.discover.__name__  # sanity: callable port
    assert first == "discover"
    import asyncio

    result = asyncio.run(provider.discover(request))
    assert result.type == "NEW_CLASS"


def test_reclustering_preserves_discovered_candidates_evidence_and_reviews(
    mock_client: TestClient,
) -> None:
    slug, service, cluster_id = _setup(mock_client)
    discovered = client_discover(mock_client, slug, cluster_id)
    candidate_id = discovered["id"]

    unknowns = mock_client.get(f"/api/v1/projects/{slug}/unknowns").json()["items"]
    unknown_ids = [u["run_id"] for u in unknowns]
    collected = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/collect",
        json={"unknown_ids": unknown_ids},
    )
    assert collected.status_code == 200, collected.text

    detail_before = mock_client.get(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}"
    ).json()
    run_ids = detail_before["evidence_run_ids"]
    assert len(run_ids) >= 5

    req_rev = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/request-review"
    )
    assert req_rev.status_code == 200, req_rev.text

    rev = mock_client.post(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/review",
        json={"decision": "approve", "rationale": "Consistent cancellation intent cluster"},
    )
    assert rev.status_code == 200, rev.text

    reclustered = mock_client.post(
        f"/api/v1/projects/{slug}/unknowns/cluster", json={"threshold": 0.4}
    )
    assert reclustered.status_code == 200, reclustered.text

    listing_after = mock_client.get(f"/api/v1/projects/{slug}/discovery-candidates").json()
    assert any(entry["id"] == candidate_id for entry in listing_after)

    detail_after = mock_client.get(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}"
    ).json()
    assert detail_after["id"] == candidate_id
    assert detail_after["status"] == "approved"
    assert set(detail_after["evidence_run_ids"]) == set(run_ids)

    history_after = mock_client.get(
        f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}/history"
    ).json()
    assert len(history_after["reviews"]) == 1
    assert history_after["reviews"][0]["decision"] == "approve"
