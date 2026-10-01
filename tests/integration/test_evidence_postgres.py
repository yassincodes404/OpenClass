"""PostgreSQL persistence proof for Evidence and Evolution Inbox:
create evidence, feedback, cases in one app instance, read and mutate
from fresh instances, and verify audit history and state survives restart.
"""

import uuid

from fastapi.testclient import TestClient
from openclass_core.models import ChoiceResult
from openclass_provider_mock import MockDiagnosisProvider
from openclass_server.main import create_app
from openclass_server.settings import Settings


class MockForcedUnknownProvider:
    async def choice(self, request) -> ChoiceResult:
        return ChoiceResult(
            provider="mock-forced",
            model="forced-v1",
            probabilities={"support": 0.1},
            unknown_probability=0.9,
        )


def test_evidence_survives_application_restart(postgres_url: str) -> None:
    def fresh_client() -> TestClient:
        return TestClient(
            create_app(
                Settings(database_url=postgres_url),
                provider=MockForcedUnknownProvider(),
                diagnosis_provider=MockDiagnosisProvider(),
            )
        )

    slug = f"ev-test-{uuid.uuid4().hex[:8]}"
    with fresh_client() as client:
        # 1. Create project
        resp = client.post("/api/v1/projects", json={"name": f"Evidence Project {slug}"})
        assert resp.status_code == 201
        project_id = resp.json()["id"]

        # 2. Ingest raw event
        resp = client.post(
            f"/api/v1/projects/{project_id}/events",
            json={"content": "Need multi-region data residency option", "source_type": "text"},
        )
        assert resp.status_code == 201
        raw_event_id = resp.json()["id"]

        # 3. Create decision service
        resp = client.post(
            f"/api/v1/projects/{project_id}/decision-services",
            json={
                "name": "Customer Requests",
                "instructions": "Classify requests",
                "choices": [{"key": "BILLING", "label": "Billing"}],
            },
        )
        assert resp.status_code == 201
        service_id = resp.json()["id"]

        # 4. Execute decision run (triggers UNKNOWN -> auto-evidence)
        resp = client.post(
            f"/api/v1/projects/{project_id}/decision-services/{service_id}/runs",
            json={"raw_event_ids": [raw_event_id]},
        )
        assert resp.status_code == 201
        run_id = resp.json()[0]["id"]

    # In a brand new instance, verify evidence exists
    with fresh_client() as client:
        resp = client.get(f"/api/v1/projects/{project_id}/evidence")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        ev_id = items[0]["id"]
        assert items[0]["status"] == "pending"
        assert items[0]["decision_run_id"] == run_id

        # AI-diagnose evidence
        resp = client.post(f"/api/v1/projects/{project_id}/evidence/{ev_id}/ai-diagnose")
        assert resp.status_code == 200
        assert resp.json()["diagnosis"] in ["decision_space", "ambiguous_or_insufficient"]

        # Triage evidence
        resp = client.patch(
            f"/api/v1/projects/{project_id}/evidence/{ev_id}/triage",
            json={"diagnosis": "decision_space", "rationale": "Enterprise data compliance request"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "triaged"

    # In another fresh instance, transition and group into case
    with fresh_client() as client:
        resp = client.post(
            f"/api/v1/projects/{project_id}/evidence/{ev_id}/transition",
            json={"target_status": "ready_for_evolution"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready_for_evolution"

        # Create case
        resp = client.post(
            f"/api/v1/projects/{project_id}/evidence-cases",
            json={
                "title": "Data Residency Requests",
                "decision_service_id": service_id,
                "evidence_ids": [ev_id],
            },
        )
        assert resp.status_code == 201
        case_id = resp.json()["id"]

        # Submit run feedback
        resp = client.post(
            f"/api/v1/projects/{project_id}/runs/{run_id}/feedback",
            json={"action": "correct", "corrected_choice": "UNKNOWN", "note": "Accurate unknown"},
        )
        assert resp.status_code == 201

    # In final fresh instance, verify complete persistence and summary
    with fresh_client() as client:
        # Check evidence item
        resp = client.get(f"/api/v1/projects/{project_id}/evidence/{ev_id}")
        assert resp.status_code == 200
        ev_data = resp.json()
        assert ev_data["status"] == "ready_for_evolution"
        assert ev_data["diagnosis"] == "decision_space"
        assert ev_data["evidence_case_id"] == case_id

        # Check case
        resp = client.get(f"/api/v1/projects/{project_id}/evidence-cases/{case_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Data Residency Requests"

        # Check case evidence list
        resp = client.get(f"/api/v1/projects/{project_id}/evidence-cases/{case_id}/evidence")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # Check feedback list
        resp = client.get(f"/api/v1/projects/{project_id}/runs/{run_id}/feedback")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["action"] == "correct"

        # Check evolution summary
        resp = client.get(f"/api/v1/projects/{project_id}/evolution/summary")
        assert resp.status_code == 200
        summary = resp.json()
        assert summary["ready_for_evolution"] == 1
        assert summary["open_cases"] == 1

        # Check audit trail survives
        resp = client.get(f"/api/v1/projects/{project_id}/audit")
        assert resp.status_code == 200
        event_types = [e["event_type"] for e in resp.json()]
        for expected in [
            "evidence.created",
            "evidence.triaged",
            "evidence.ready_for_evolution",
            "evidence.grouped",
            "feedback.submitted",
        ]:
            assert expected in event_types
