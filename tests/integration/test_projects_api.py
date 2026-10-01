"""API contract tests for the Projects slice (sqlite, migrated via Alembic)."""

from fastapi.testclient import TestClient

CREATE_BODY = {
    "name": "GymHolic Intelligence",
    "description": "Customer intelligence experiment",
}


def test_create_list_get_roundtrip(client: TestClient) -> None:
    created = client.post("/api/v1/projects", json=CREATE_BODY)
    assert created.status_code == 201
    project = created.json()
    assert project["name"] == "GymHolic Intelligence"
    assert project["slug"] == "gymholic-intelligence"
    assert project["status"] == "active"
    assert project["description"] == "Customer intelligence experiment"

    listed = client.get("/api/v1/projects").json()
    assert [p["slug"] for p in listed] == ["gymholic-intelligence"]

    fetched = client.get("/api/v1/projects/gymholic-intelligence").json()
    assert fetched["id"] == project["id"]
    by_id = client.get(f"/api/v1/projects/{project['id']}")
    assert by_id.status_code == 200


def test_create_rejects_blank_and_oversized_names(client: TestClient) -> None:
    assert client.post("/api/v1/projects", json={"name": "   "}).status_code == 422
    assert client.post("/api/v1/projects", json={"name": "x" * 201}).status_code == 422
    assert (
        client.post("/api/v1/projects", json={"name": "ok", "description": "x" * 2001}).status_code
        == 422
    )


def test_update_patch_semantics_and_audit(client: TestClient) -> None:
    slug = client.post("/api/v1/projects", json={"name": "Migration Study"}).json()["slug"]

    empty = client.patch(f"/api/v1/projects/{slug}", json={})
    assert empty.status_code == 422

    updated = client.patch(
        f"/api/v1/projects/{slug}",
        json={"name": "Migration Study v2", "status": "archived"},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "Migration Study v2"
    assert body["status"] == "archived"

    audit = client.get(f"/api/v1/projects/{slug}/audit").json()
    assert [event["event_type"] for event in audit] == ["project.created", "project.updated"]
    assert audit[-1]["payload"]["changes"] == {
        "name": "Migration Study v2",
        "status": "archived",
    }

    summary = client.get(f"/api/v1/projects/{slug}/summary").json()
    assert summary == {
        "events": 0,
        "decision_runs": 0,
        "unknowns": 0,
        "pending_evidence": 0,
        "active_policy": None,
        "pending_candidates": 0,
        "audit_events": 2,
    }


def test_not_found_for_missing_projects(client: TestClient) -> None:
    assert client.get("/api/v1/projects/missing-project").status_code == 404
    assert client.patch("/api/v1/projects/missing-project", json={"name": "x"}).status_code == 404
    assert client.get("/api/v1/projects/missing-project/summary").status_code == 404


def test_projects_are_isolated_from_classifier_state(client: TestClient) -> None:
    client.post("/api/v1/projects", json=CREATE_BODY)
    # Project state must not leak into classifier resources or vice versa.
    assert all(
        "projects" not in path
        for path in client.get("/openapi.json").json()["paths"]
        if "classifiers" in path
    )
