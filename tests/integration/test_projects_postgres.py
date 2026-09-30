"""PostgreSQL persistence proof for Projects: create in one app instance,
read from a brand-new instance, mutate, and verify audit history survives.

Requires OPENCLASS_TEST_DATABASE_URL pointing at a disposable PostgreSQL
database; the Alembic head is applied by the conftest fixture.
"""

import uuid

from fastapi.testclient import TestClient
from openclass_server.main import create_app
from openclass_server.settings import Settings


def test_projects_survive_application_restart(postgres_url: str) -> None:
    def fresh_client() -> TestClient:
        # A new app builds a new engine: anything read through it came from
        # PostgreSQL, not from in-memory state.
        return TestClient(create_app(Settings(database_url=postgres_url)))

    slug = f"gymholic-{uuid.uuid4().hex[:8]}"
    with fresh_client() as client:
        created = client.post(
            "/api/v1/projects",
            json={"name": f"GymHolic {slug}", "description": "restart proof"},
        )
        assert created.status_code == 201
        project = created.json()

    server_slug = project["slug"]
    with fresh_client() as client:
        fetched = client.get(f"/api/v1/projects/{server_slug}")
        assert fetched.status_code == 200
        assert fetched.json()["name"] == f"GymHolic {slug}"

        updated = client.patch(
            f"/api/v1/projects/{server_slug}",
            json={"description": "survives restarts"},
        )
        assert updated.status_code == 200

    with fresh_client() as client:
        final = client.get(f"/api/v1/projects/{server_slug}").json()
        assert final["description"] == "survives restarts"
        audit = client.get(f"/api/v1/projects/{server_slug}/audit").json()
        assert [event["event_type"] for event in audit] == [
            "project.created",
            "project.updated",
        ]
        summary = client.get(f"/api/v1/projects/{server_slug}/summary").json()
        assert summary["audit_events"] == 2

    # The migrated v4 schema carries the owner column for future isolation.
    with fresh_client() as client:
        listing = client.get("/api/v1/projects").json()
        assert any(p["slug"] == server_slug for p in listing)
        assert project["id"] not in ("", None)
