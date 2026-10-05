"""API tests for the Raw Events ingestion slice (sqlite, migrated via Alembic)."""

from fastapi.testclient import TestClient

CREATE_PROJECT = {
    "name": "Customer Support Triage",
    "description": "Incoming support requests",
}


def test_ingest_single_raw_event(client: TestClient) -> None:
    proj = client.post("/api/v1/projects", json=CREATE_PROJECT).json()
    slug = proj["slug"]

    # Ingest text event
    resp = client.post(
        f"/api/v1/projects/{slug}/events",
        json={
            "content": "My subscription was charged twice this morning.",
            "source_type": "text",
            "metadata": {"customer_tier": "gold"},
        },
    )
    assert resp.status_code == 201
    event = resp.json()
    assert event["project_id"] == proj["id"]
    assert event["content"] == "My subscription was charged twice this morning."
    assert event["source_type"] == "text"
    assert event["metadata"] == {"customer_tier": "gold"}
    assert "id" in event
    assert "created_at" in event

    # Fetch event by id
    by_id = client.get(f"/api/v1/projects/{slug}/events/{event['id']}")
    assert by_id.status_code == 200
    assert by_id.json()["id"] == event["id"]

    # Verify summary count updated
    summary = client.get(f"/api/v1/projects/{slug}/summary").json()
    assert summary["events"] == 1


def test_ingest_raw_events_batch(client: TestClient) -> None:
    slug = client.post("/api/v1/projects", json=CREATE_PROJECT).json()["slug"]

    batch_resp = client.post(
        f"/api/v1/projects/{slug}/events/batch",
        json={
            "items": [
                {"content": "Error code 500 when saving invoice", "metadata": {"source": "log"}},
                {"content": "Can I upgrade my plan to enterprise?", "metadata": {"source": "chat"}},
                {
                    "content": "Feature request: dark mode in dashboard",
                    "metadata": {"source": "email"},
                },
            ],
            "source_type": "json",
        },
    )
    assert batch_resp.status_code == 207
    entries = batch_resp.json()["items"]
    assert len(entries) == 3
    assert all(entry["status"] == 201 for entry in entries)
    assert all(entry["event"]["source_type"] == "json" for entry in entries)

    # List events with pagination
    list_resp = client.get(f"/api/v1/projects/{slug}/events?limit=2&offset=0")
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert len(listed) == 2

    # Check summary count
    summary = client.get(f"/api/v1/projects/{slug}/summary").json()
    assert summary["events"] == 3


def test_ingest_rejects_blank_content(client: TestClient) -> None:
    slug = client.post("/api/v1/projects", json=CREATE_PROJECT).json()["slug"]
    url = f"/api/v1/projects/{slug}/events"
    assert client.post(url, json={"content": ""}).status_code == 422
    assert client.post(url, json={"content": "   "}).status_code == 422


def test_get_missing_event_returns_404(client: TestClient) -> None:
    slug = client.post("/api/v1/projects", json=CREATE_PROJECT).json()["slug"]
    from uuid import uuid4

    missing_id = str(uuid4())
    assert client.get(f"/api/v1/projects/{slug}/events/{missing_id}").status_code == 404


def test_providers_status_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/providers/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "default_provider" in data
    assert data["default_provider"] == "laya"
    assert "laya" in data
    assert data["laya"]["status"] in {"configured", "ready", "loading", "unavailable"}
    assert data["laya"]["model"] == "laya-router"
    assert "jev" in data
    assert "status" in data["jev"]
