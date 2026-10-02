"""Phase 5 observation ingestion: content-hash dedup, limits, batch 207."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _make_project(client: TestClient) -> str:
    response = client.post("/api/v1/projects", json={"name": "Observe Co"})
    assert response.status_code == 201, response.text
    return response.json()["slug"]


def test_identical_content_dedups_to_original_event(mock_client: TestClient):
    slug = _make_project(mock_client)
    first = mock_client.post(
        f"/api/v1/projects/{slug}/events", json={"content": "I was charged twice"}
    )
    assert first.status_code == 201
    assert first.json()["deduped"] is False
    second = mock_client.post(
        f"/api/v1/projects/{slug}/events", json={"content": "I was charged twice"}
    )
    assert second.status_code == 200
    assert second.json()["deduped"] is True
    assert second.json()["id"] == first.json()["id"]
    listed = mock_client.get(f"/api/v1/projects/{slug}/events")
    assert len(listed.json()) == 1


def test_same_content_across_projects_is_not_deduped(mock_client: TestClient):
    slug_a = _make_project(mock_client)
    slug_b = _make_project(mock_client)
    first = mock_client.post(f"/api/v1/projects/{slug_a}/events", json={"content": "shared text"})
    second = mock_client.post(f"/api/v1/projects/{slug_b}/events", json={"content": "shared text"})
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]


def test_oversized_content_returns_413(mock_client: TestClient):
    slug = _make_project(mock_client)
    response = mock_client.post(f"/api/v1/projects/{slug}/events", json={"content": "x" * 10_001})
    assert response.status_code == 413


def test_blank_content_is_rejected(mock_client: TestClient):
    slug = _make_project(mock_client)
    response = mock_client.post(f"/api/v1/projects/{slug}/events", json={"content": "   "})
    # Engine convention: validation errors are a generic 422 (never echo values).
    # The control-plane proxy maps this to 400 for portal clients.
    assert response.status_code == 422


def test_batch_returns_207_with_per_item_status(mock_client: TestClient):
    slug = _make_project(mock_client)
    response = mock_client.post(
        f"/api/v1/projects/{slug}/events/batch",
        json={
            "items": [
                {"content": "good row"},
                {"content": "   "},
                {"content": "y" * 10_001},
                {"content": "good row"},  # duplicate inside the same batch
            ]
        },
    )
    assert response.status_code == 207
    entries = response.json()["items"]
    by_index = {entry["index"]: entry for entry in entries}
    assert by_index[0]["status"] == 201
    assert by_index[1]["status"] == 400
    assert by_index[2]["status"] == 413
    assert by_index[3]["status"] == 200
    assert by_index[3]["deduped"] is True
    assert by_index[3]["event"]["id"] == by_index[0]["event"]["id"]


def test_batch_over_500_items_returns_413(mock_client: TestClient):
    slug = _make_project(mock_client)
    items = [{"content": f"row {i}"} for i in range(501)]
    response = mock_client.post(f"/api/v1/projects/{slug}/events/batch", json={"items": items})
    assert response.status_code == 413
