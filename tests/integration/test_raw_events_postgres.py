"""PostgreSQL persistence proof for Raw Events: ingest in one app instance,
read from a brand-new instance, and verify event integrity and counts survive.

Requires OPENCLASS_TEST_DATABASE_URL pointing at a PostgreSQL database;
the Alembic head is applied by the conftest fixture.
"""

import uuid

from fastapi.testclient import TestClient
from openclass_server.main import create_app
from openclass_server.settings import Settings


def test_raw_events_survive_application_restart(postgres_url: str) -> None:
    def fresh_client() -> TestClient:
        # A new app builds a new engine: anything read through it came from
        # PostgreSQL, not from in-memory state.
        return TestClient(create_app(Settings(database_url=postgres_url)))

    slug_suffix = uuid.uuid4().hex[:8]
    project_name = f"Ingestion Test {slug_suffix}"

    with fresh_client() as client:
        created = client.post(
            "/api/v1/projects",
            json={"name": project_name, "description": "raw events restart proof"},
        )
        assert created.status_code == 201
        project = created.json()

    server_slug = project["slug"]

    # Ingest a single event in instance 1
    with fresh_client() as client:
        resp = client.post(
            f"/api/v1/projects/{server_slug}/events",
            json={
                "content": "Single event text payload",
                "source_type": "text",
                "metadata": {"source": "manual_entry", "run": slug_suffix},
            },
        )
        assert resp.status_code == 201
        single_event_id = resp.json()["id"]

    # Ingest a batch of events in instance 2
    with fresh_client() as client:
        resp = client.post(
            f"/api/v1/projects/{server_slug}/events/batch",
            json={
                "items": [
                    {"content": "CSV row 1 data", "metadata": {"line": 1}},
                    {"content": "CSV row 2 data", "metadata": {"line": 2}},
                ],
                "source_type": "csv",
            },
        )
        # Batch ingestion uses the phase-5 contract: 207 with per-item receipts.
        assert resp.status_code == 207
        items = resp.json()["items"]
        assert len(items) == 2
        assert all(item["status"] == 201 for item in items)

    # Verify everything from a completely fresh instance 3
    with fresh_client() as client:
        summary = client.get(f"/api/v1/projects/{server_slug}/summary").json()
        assert summary["events"] == 3

        events = client.get(f"/api/v1/projects/{server_slug}/events").json()
        assert len(events) == 3

        single = client.get(f"/api/v1/projects/{server_slug}/events/{single_event_id}").json()
        assert single["content"] == "Single event text payload"
        assert single["metadata"]["run"] == slug_suffix
        assert single["source_type"] == "text"
