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


def test_workspace_isolation_across_projects_and_resources(client: TestClient) -> None:
    alpha_headers = {"X-OpenClass-Workspace-Id": "ws-alpha"}
    beta_headers = {"X-OpenClass-Workspace-Id": "ws-beta"}

    alpha_resp = client.post(
        "/api/v1/projects",
        headers=alpha_headers,
        json={"name": "Alpha Hub", "description": "Alpha workspace project"},
    )
    assert alpha_resp.status_code == 201
    alpha_project = alpha_resp.json()
    assert alpha_project["workspace_id"] == "ws-alpha"
    alpha_slug = alpha_project["slug"]

    beta_resp = client.post(
        "/api/v1/projects",
        headers=beta_headers,
        json={"name": "Beta Hub", "description": "Beta workspace project"},
    )
    assert beta_resp.status_code == 201
    beta_project = beta_resp.json()
    assert beta_project["workspace_id"] == "ws-beta"
    beta_slug = beta_project["slug"]

    # Listing is strictly scoped to the caller's workspace
    alpha_list = client.get("/api/v1/projects", headers=alpha_headers).json()
    assert [p["slug"] for p in alpha_list] == [alpha_slug]

    beta_list = client.get("/api/v1/projects", headers=beta_headers).json()
    assert [p["slug"] for p in beta_list] == [beta_slug]

    # Cross-workspace read/write/resource endpoints return 404 Not Found
    assert client.get(f"/api/v1/projects/{alpha_slug}", headers=beta_headers).status_code == 404
    assert (
        client.patch(
            f"/api/v1/projects/{alpha_slug}",
            headers=beta_headers,
            json={"name": "Hijacked Alpha"},
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/projects/{alpha_slug}/summary", headers=beta_headers).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/projects/{alpha_slug}/events",
            headers=beta_headers,
            json={"content": "Cross-workspace event injection"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/projects/{alpha_slug}/decision-services",
            headers=beta_headers,
            json={
                "name": "Cross-workspace router",
                "instructions": "Should not be created",
                "choices": [{"key": "A", "label": "A"}],
            },
        ).status_code
        == 404
    )

    # Owner workspace still has full access
    assert client.get(f"/api/v1/projects/{alpha_slug}", headers=alpha_headers).status_code == 200


def test_legacy_unassigned_project_discovery_and_explicit_claiming(client: TestClient) -> None:
    alpha_headers = {"X-OpenClass-Workspace-Id": "ws-alpha"}
    beta_headers = {"X-OpenClass-Workspace-Id": "ws-beta"}

    # Create a legacy project without a workspace header (workspace_id = None)
    legacy_resp = client.post("/api/v1/projects", json={"name": "Legacy Unassigned"})
    assert legacy_resp.status_code == 201
    legacy_project = legacy_resp.json()
    assert legacy_project["workspace_id"] is None
    legacy_slug = legacy_project["slug"]

    # Un-headered listing sees unassigned projects
    unheadered_list = client.get("/api/v1/projects").json()
    assert [p["slug"] for p in unheadered_list] == [legacy_slug]

    # Workspace-scoped listing hides unassigned projects by default
    assert client.get("/api/v1/projects", headers=alpha_headers).json() == []

    # Opt-in discovery via include_unassigned=true exposes legacy unassigned projects
    with_unassigned = client.get(
        "/api/v1/projects?include_unassigned=true", headers=alpha_headers
    ).json()
    assert [p["slug"] for p in with_unassigned] == [legacy_slug]

    # Direct access from ws-alpha is blocked until claimed
    assert client.get(f"/api/v1/projects/{legacy_slug}", headers=alpha_headers).status_code == 404

    # Claiming the legacy unassigned project into ws-alpha succeeds
    claimed_resp = client.post(
        f"/api/v1/projects/{legacy_slug}/claim",
        headers=alpha_headers,
        json={},
    )
    assert claimed_resp.status_code == 200, claimed_resp.text
    claimed_project = claimed_resp.json()
    assert claimed_project["workspace_id"] == "ws-alpha"

    # Now ws-alpha sees it in standard listing and direct GET
    assert [p["slug"] for p in client.get("/api/v1/projects", headers=alpha_headers).json()] == [
        legacy_slug
    ]
    assert client.get(f"/api/v1/projects/{legacy_slug}", headers=alpha_headers).status_code == 200

    # Another workspace attempting to claim the already-claimed project gets 409 Conflict
    competing_claim = client.post(
        f"/api/v1/projects/{legacy_slug}/claim",
        headers=beta_headers,
        json={},
    )
    assert competing_claim.status_code == 409
    assert client.get(f"/api/v1/projects/{legacy_slug}", headers=beta_headers).status_code == 404
