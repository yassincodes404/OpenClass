"""PostgreSQL proof: proposals persist; unsupported activation never mutates history."""

import uuid

from fastapi.testclient import TestClient
from openclass_core.models import ChoiceResult
from openclass_provider_mock import MockChoiceTeacher, MockDiagnosisProvider
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


def test_candidate_activation_stays_blocked_after_restart_postgres(postgres_url: str) -> None:
    def fresh_client() -> TestClient:
        return TestClient(
            create_app(
                Settings(database_url=postgres_url),
                provider=MockForcedUnknownProvider(),
                choice_teacher=MockChoiceTeacher(),
                diagnosis_provider=MockDiagnosisProvider(),
            )
        )

    slug = f"cand-test-{uuid.uuid4().hex[:8]}"

    # Step 1: Create project, events, service, and runs
    with fresh_client() as client:
        resp = client.post("/api/v1/projects", json={"name": f"Promotion Project {slug}"})
        assert resp.status_code == 201
        project_id = resp.json()["id"]

        event_ids = []
        for i in range(3):
            resp = client.post(
                f"/api/v1/projects/{project_id}/events",
                json={
                    "content": f"User {i} needs pause feature for vacation month",
                    "source_type": "text",
                },
            )
            assert resp.status_code == 201
            event_ids.append(resp.json()["id"])

        resp = client.post(
            f"/api/v1/projects/{project_id}/decision-services",
            json={
                "name": "Customer Care",
                "instructions": "Route care tickets",
                "choices": [{"key": "BILLING", "label": "Billing"}],
            },
        )
        assert resp.status_code == 201
        service_id = resp.json()["id"]

        resp = client.post(
            f"/api/v1/projects/{project_id}/decision-services/{service_id}/runs",
            json={"raw_event_ids": event_ids},
        )
        assert resp.status_code == 201

        resp = client.get(f"/api/v1/projects/{project_id}/evidence")
        assert resp.status_code == 200
        ev_items = resp.json()
        assert len(ev_items) == 3
        evidence_ids = [e["id"] for e in ev_items]

        for eid in evidence_ids:
            client.patch(
                f"/api/v1/projects/{project_id}/evidence/{eid}/triage",
                json={"diagnosis": "decision_space", "rationale": "Missing pause choice"},
            )
            client.post(
                f"/api/v1/projects/{project_id}/evidence/{eid}/transition",
                json={"target_status": "ready_for_evolution"},
            )

    # Step 2: In a fresh client instance, synthesize candidate and evaluate replay
    with fresh_client() as client:
        resp = client.post(
            f"/api/v1/projects/{project_id}/evolution/propose",
            json={"service_id": service_id, "evidence_ids": evidence_ids},
        )
        assert resp.status_code == 201
        candidate = resp.json()
        candidate_id = candidate["id"]
        assert candidate["status"] == "candidate"
        assert candidate["proposal"]["key"] == "SUBSCRIPTION_PAUSE"

        resp = client.post(f"/api/v1/projects/{project_id}/candidates/{candidate_id}/evaluate")
        assert resp.status_code == 409

    # A fresh instance cannot treat a previous attempted evaluation as approval.
    with fresh_client() as client:
        base = f"/api/v1/projects/{project_id}"
        before = {
            path: client.get(f"{base}/{path}").json()
            for path in ("decision-services", "candidates", "evidence", "audit", "runs")
        }
        resp = client.post(
            f"{base}/candidates/{candidate_id}/promote", json={"note": "Human approval"}
        )
        assert resp.status_code == 409

    with fresh_client() as client:
        after = {path: client.get(f"{base}/{path}").json() for path in before}
        assert after == before
        assert client.get(f"{base}/candidates/{candidate_id}").json()["status"] == "candidate"
