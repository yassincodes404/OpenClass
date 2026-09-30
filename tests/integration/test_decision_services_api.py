"""API tests for Decision Services and Decision Runs endpoints (sqlite, migrated via Alembic)."""

from fastapi.testclient import TestClient

CREATE_PROJECT = {
    "name": "Customer Support Operations",
    "description": "Decision routing for support requests",
}


def test_create_and_list_decision_services(client: TestClient) -> None:
    proj = client.post("/api/v1/projects", json=CREATE_PROJECT).json()
    slug = proj["slug"]

    # Create Decision Service
    resp = client.post(
        f"/api/v1/projects/{slug}/decision-services",
        json={
            "name": "Ticket Routing",
            "description": "Route incoming customer issues",
            "instructions": "Classify user inquiry by urgency and department",
            "choices": [
                {"key": "BILLING", "label": "Billing issue", "description": "Refunds, charges"},
                {"key": "TECH", "label": "Technical issue", "description": "Bug reports, crashes"},
            ],
        },
    )
    assert resp.status_code == 201
    service = resp.json()
    assert service["name"] == "Ticket Routing"
    assert service["slug"] == "ticket-routing"
    assert service["status"] == "active"
    assert len(service["nodes"]) == 1
    choice_keys = [c["key"] for c in service["nodes"][0]["choices"]]
    assert "UNKNOWN" in choice_keys
    assert "BILLING" in choice_keys
    assert "TECH" in choice_keys

    # List Decision Services
    list_resp = client.get(f"/api/v1/projects/{slug}/decision-services")
    assert list_resp.status_code == 200
    services = list_resp.json()
    assert len(services) == 1
    assert services[0]["id"] == service["id"]

    # Get single Decision Service
    get_resp = client.get(f"/api/v1/projects/{slug}/decision-services/{service['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == service["id"]

    # Patch Decision Service
    patch_resp = client.patch(
        f"/api/v1/projects/{slug}/decision-services/{service['id']}",
        json={"name": "Urgent Ticket Routing", "status": "draft"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Urgent Ticket Routing"
    assert patch_resp.json()["status"] == "draft"


def test_execute_decision_runs_via_api(client: TestClient) -> None:
    proj = client.post("/api/v1/projects", json=CREATE_PROJECT).json()
    slug = proj["slug"]

    # Create Decision Service
    service = client.post(
        f"/api/v1/projects/{slug}/decision-services",
        json={
            "name": "Billing Routing",
            "instructions": "Determine if billing or tech",
            "choices": [
                {"key": "BILLING", "label": "Billing", "description": "Payment issues"},
                {"key": "TECH", "label": "Technical", "description": "Software bugs"},
            ],
        },
    ).json()

    # Ingest event
    event = client.post(
        f"/api/v1/projects/{slug}/events",
        json={
            "content": "Billing question: I was double billed for my subscription.",
            "source_type": "text",
        },
    ).json()

    # Execute run
    run_resp = client.post(
        f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
        json={"raw_event_ids": [event["id"]]},
    )
    assert run_resp.status_code == 201
    runs = run_resp.json()
    assert len(runs) == 1
    run = runs[0]
    assert run["decision_service_id"] == service["id"]
    assert run["raw_event_id"] == event["id"]
    assert run["selected_choice"] == "BILLING"
    assert run["supervision_outcome"] in ("TRUSTED", "REVIEW")
    assert "top_probability" in run
    assert "margin" in run
    assert "UNKNOWN" in run["probabilities"]
    assert run["input_snapshot"]["content"] == event["content"]

    # List runs
    runs_list_resp = client.get(f"/api/v1/projects/{slug}/runs")
    assert runs_list_resp.status_code == 200
    assert len(runs_list_resp.json()) == 1

    # Get run by ID
    run_by_id = client.get(f"/api/v1/projects/{slug}/runs/{run['id']}")
    assert run_by_id.status_code == 200
    assert run_by_id.json()["id"] == run["id"]

    # Check summary count updated
    summary = client.get(f"/api/v1/projects/{slug}/summary").json()
    assert summary["events"] == 1
    assert summary["decision_runs"] == 1


def test_unknown_run_updates_only_its_project_summary(mock_client: TestClient) -> None:
    first = mock_client.post("/api/v1/projects", json={"name": "Unknown Counter One"}).json()
    second = mock_client.post("/api/v1/projects", json={"name": "Unknown Counter Two"}).json()
    slug = first["slug"]
    service = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services",
        json={
            "name": "Support Topic",
            "instructions": "Choose the support topic",
            "provider_override": "mock",
            "choices": [{"key": "BILLING", "label": "Billing", "description": "Invoices"}],
        },
    ).json()
    event = mock_client.post(
        f"/api/v1/projects/{slug}/events", json={"content": "Cancel my plan"}
    ).json()
    response = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
        json={"raw_event_ids": [event["id"]]},
    )
    assert response.status_code == 201
    assert response.json()[0]["selected_choice"] == "UNKNOWN"
    assert mock_client.get(f"/api/v1/projects/{slug}/summary").json()["unknowns"] == 1
    assert mock_client.get(f"/api/v1/projects/{second['slug']}/summary").json()["unknowns"] == 0
