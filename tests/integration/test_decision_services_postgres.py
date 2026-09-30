"""PostgreSQL persistence proof for Decision Services and Decision Runs:
create and execute in one app instance, read from a brand-new instance, and verify
decision services and immutable decision run history survive application restart.

Requires OPENCLASS_TEST_DATABASE_URL pointing at a PostgreSQL database;
the Alembic head is applied by the conftest fixture.
"""

import uuid

from fastapi.testclient import TestClient
from openclass_server.main import create_app
from openclass_server.settings import Settings


def test_decision_services_and_runs_survive_application_restart(postgres_url: str) -> None:
    def fresh_client() -> TestClient:
        # A new app builds a new engine: anything read through it came from
        # PostgreSQL, not from in-memory state.
        return TestClient(
            create_app(
                Settings(
                    database_url=postgres_url,
                    decision_provider="laya",
                    laya_allow_fallback=True,
                )
            )
        )

    slug_suffix = uuid.uuid4().hex[:8]
    project_name = f"Decision Persistence Test {slug_suffix}"

    # Instance 1: Create Project and Ingest Event
    with fresh_client() as client:
        created = client.post(
            "/api/v1/projects",
            json={"name": project_name, "description": "decisions restart proof"},
        )
        assert created.status_code == 201
        project = created.json()
        server_slug = project["slug"]

        evt_resp = client.post(
            f"/api/v1/projects/{server_slug}/events",
            json={
                "content": "Enterprise inquiry: Need 500 licenses with SSO integration.",
                "source_type": "text",
                "metadata": {"deal_size": "enterprise", "run": slug_suffix},
            },
        )
        assert evt_resp.status_code == 201
        event_id = evt_resp.json()["id"]

    # Instance 2: Create Decision Service with choices
    with fresh_client() as client:
        svc_resp = client.post(
            f"/api/v1/projects/{server_slug}/decision-services",
            json={
                "name": "Lead Triage",
                "description": "Route inbound sales opportunities",
                "instructions": "Determine if inbound lead is enterprise or smb",
                "choices": [
                    {"key": "ENTERPRISE", "label": "Enterprise Deal", "description": "50+ seats"},
                    {"key": "SMB", "label": "SMB Deal", "description": "Under 50 seats"},
                ],
            },
        )
        assert svc_resp.status_code == 201
        service_id = svc_resp.json()["id"]

    # Instance 3: Execute Decision Run against event
    with fresh_client() as client:
        run_resp = client.post(
            f"/api/v1/projects/{server_slug}/decision-services/{service_id}/runs",
            json={"raw_event_ids": [event_id]},
        )
        assert run_resp.status_code == 201
        runs = run_resp.json()
        assert len(runs) == 1
        run_id = runs[0]["id"]
        assert runs[0]["selected_choice"] in ("ENTERPRISE", "SMB", "UNKNOWN")

    # Instance 4: Verify complete persistent state from fresh instance
    with fresh_client() as client:
        # 1. Verify summary counts
        summary = client.get(f"/api/v1/projects/{server_slug}/summary").json()
        assert summary["events"] == 1
        assert summary["decision_runs"] == 1

        # 2. Verify Decision Service
        services = client.get(f"/api/v1/projects/{server_slug}/decision-services").json()
        assert len(services) == 1
        svc = services[0]
        assert svc["id"] == service_id
        assert svc["name"] == "Lead Triage"
        choice_keys = [c["key"] for c in svc["nodes"][0]["choices"]]
        assert "UNKNOWN" in choice_keys
        assert "ENTERPRISE" in choice_keys

        # 3. Verify Decision Run immutable history
        run_data = client.get(f"/api/v1/projects/{server_slug}/runs/{run_id}").json()
        assert run_data["id"] == run_id
        assert run_data["raw_event_id"] == event_id
        assert run_data["decision_service_id"] == service_id
        assert run_data["provider"] == "laya"
        assert run_data["supervision_outcome"] in ("TRUSTED", "REVIEW", "UNKNOWN")
        assert "UNKNOWN" in run_data["probabilities"]

        # 4. Verify Snapshots survive reload perfectly
        expected_content = "Enterprise inquiry: Need 500 licenses with SSO integration."
        assert run_data["input_snapshot"]["content"] == expected_content
        assert run_data["input_snapshot"]["metadata"]["run"] == slug_suffix
        assert run_data["instructions_snapshot"] == "Determine if inbound lead is enterprise or smb"
        assert len(run_data["choices_snapshot"]) == 3
