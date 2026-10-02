"""Phase 9 embeddings & clustering: determinism, provenance, isolation."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from openclass_core.embeddings import (
    EmbeddedItem,
    cosine_similarity,
    group_into_clusters,
)
from openclass_server.embeddings_local import HashLexicalEmbedder


def _vec(text: str) -> list[float]:
    import asyncio

    return asyncio.run(HashLexicalEmbedder().embed([text]))[0]


def test_cosine_groups_related_and_separates_unrelated():
    cancel_a = _vec("Cancel my plan immediately")
    cancel_b = _vec("Cancel my subscription plan now")
    account = _vec("Someone changed my account email without permission")
    assert cosine_similarity(cancel_a, cancel_b) > 0.6
    assert cosine_similarity(cancel_a, account) < 0.35


def test_grouping_is_deterministic():
    items = [
        EmbeddedItem(item_id="a", text="x", vector=_vec("cancel my plan")),
        EmbeddedItem(item_id="b", text="y", vector=_vec("cancel my subscription")),
        EmbeddedItem(item_id="c", text="z", vector=_vec("account email changed")),
    ] * 1
    first = group_into_clusters(items, 0.5)
    second = group_into_clusters(list(reversed(items)), 0.5)
    assert [g.member_ids for g in first] == [g.member_ids for g in second]


def test_threshold_edge_cases():
    items = [EmbeddedItem(item_id="a", text="x", vector=_vec("alpha"))]
    with pytest.raises(ValueError):
        group_into_clusters(items, 0.0)
    with pytest.raises(ValueError):
        group_into_clusters(items, 1.5)


def test_singleton_forms_own_cluster():
    items = [
        EmbeddedItem(item_id="a", text="x", vector=_vec("billing refund")),
        EmbeddedItem(item_id="b", text="y", vector=_vec("totally unrelated words")),
    ]
    groups = group_into_clusters(items, 0.99)
    assert len(groups) == 2
    assert all(len(g.member_ids) == 1 for g in groups)


def _setup_project_with_unknowns(client: TestClient) -> str:
    slug = client.post("/api/v1/projects", json={"name": "Cluster Co"}).json()["slug"]
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
        "Cancel my subscription now",
        "Cancel the plan please",
        "Stop my subscription renewal",
        "Someone changed my account email",
        "My account was hijacked overnight",
        "Random unrelated words here",
    ]
    for text in texts:
        client.post(
            f"/api/v1/projects/{slug}/decision-services/{service}/runs", json={"content": text}
        )
    return slug


def test_cluster_run_persists_provenance_and_is_idempotent(mock_client: TestClient):
    slug = _setup_project_with_unknowns(mock_client)
    first = mock_client.post(f"/api/v1/projects/{slug}/unknowns/cluster", json={"threshold": 0.5})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["simulated"] is True
    assert body["model"] == "hash-lexical-v1"
    assert body["cluster_count"] >= 2
    clusters = mock_client.get(f"/api/v1/projects/{slug}/unknowns/clusters").json()
    assert any(entry["size"] >= 2 for entry in clusters)
    detail = mock_client.get(
        f"/api/v1/projects/{slug}/unknowns/clusters/{clusters[0]['id']}"
    ).json()
    assert detail["algorithm"] == "greedy-cosine-first-fit"
    assert detail["threshold"] == 0.5
    assert detail["members"]
    # Rerun replaces clusters (idempotent, no duplicates).
    second = mock_client.post(f"/api/v1/projects/{slug}/unknowns/cluster", json={"threshold": 0.5})
    assert second.status_code == 200
    clusters_after = mock_client.get(f"/api/v1/projects/{slug}/unknowns/clusters").json()
    assert len(clusters_after) == len(clusters)


def test_clustering_requires_two_unknowns(mock_client: TestClient):
    slug = mock_client.post("/api/v1/projects", json={"name": "Tiny Co"}).json()["slug"]
    response = mock_client.post(f"/api/v1/projects/{slug}/unknowns/cluster", json={})
    assert response.status_code == 400


def test_no_cross_project_leakage(mock_client: TestClient):
    slug_a = _setup_project_with_unknowns(mock_client)
    slug_b = _setup_project_with_unknowns(mock_client)
    mock_client.post(f"/api/v1/projects/{slug_a}/unknowns/cluster", json={"threshold": 0.5})
    clusters_b = mock_client.get(f"/api/v1/projects/{slug_b}/unknowns/clusters").json()
    assert clusters_b == []
