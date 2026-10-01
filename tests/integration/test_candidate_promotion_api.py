"""Integration tests for Choice Candidate synthesis, evaluation replay, and safe promotion."""

import pytest
from httpx import ASGITransport, AsyncClient
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


@pytest.fixture
def app(database_url: str):
    settings = Settings(database_url=database_url)
    return create_app(
        settings=settings,
        provider=MockForcedUnknownProvider(),
        choice_teacher=MockChoiceTeacher(),
        diagnosis_provider=MockDiagnosisProvider(),
    )


async def test_proposals_cannot_bypass_verified_evaluation_api(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create project
        resp = await client.post("/api/v1/projects", json={"name": "Billing Operations"})
        assert resp.status_code == 201
        project_id = resp.json()["id"]

        # 2. Ingest 3 raw events with 'pause' keyword to trigger mock teacher
        event_ids = []
        for i in range(3):
            resp = await client.post(
                f"/api/v1/projects/{project_id}/events",
                json={
                    "content": f"User {i} requesting to pause subscription for vacation month",
                    "source_type": "text",
                },
            )
            assert resp.status_code == 201
            event_ids.append(resp.json()["id"])

        # 3. Create decision service
        resp = await client.post(
            f"/api/v1/projects/{project_id}/decision-services",
            json={
                "name": "Subscription Router",
                "instructions": "Route subscription inquiries",
                "choices": [
                    {"key": "CANCEL", "label": "Cancellation"},
                    {"key": "UPGRADE", "label": "Upgrade"},
                ],
            },
        )
        assert resp.status_code == 201
        service_id = resp.json()["id"]

        # 4. Execute decision runs
        resp = await client.post(
            f"/api/v1/projects/{project_id}/decision-services/{service_id}/runs",
            json={"raw_event_ids": event_ids},
        )
        assert resp.status_code == 201
        runs = resp.json()
        assert len(runs) == 3
        for r in runs:
            assert r["selected_choice"] == "UNKNOWN"

        # 5. Fetch generated evidence items
        resp = await client.get(f"/api/v1/projects/{project_id}/evidence")
        assert resp.status_code == 200
        evidence_items = resp.json()
        assert len(evidence_items) == 3
        evidence_ids = [e["id"] for e in evidence_items]

        # 6. Triage & transition all 3 to ready_for_evolution
        for eid in evidence_ids:
            await client.patch(
                f"/api/v1/projects/{project_id}/evidence/{eid}/triage",
                json={
                    "diagnosis": "decision_space",
                    "rationale": "Missing temporary pause capability",
                },
            )
            await client.post(
                f"/api/v1/projects/{project_id}/evidence/{eid}/transition",
                json={"target_status": "ready_for_evolution"},
            )

        # 7. Propose candidate from evidence items
        resp = await client.post(
            f"/api/v1/projects/{project_id}/evolution/propose",
            json={
                "service_id": service_id,
                "evidence_ids": evidence_ids,
            },
        )
        assert resp.status_code == 201
        candidate = resp.json()
        candidate_id = candidate["id"]
        assert candidate["status"] == "candidate"
        assert candidate["proposal"]["key"] == "SUBSCRIPTION_PAUSE"

        base = f"/api/v1/projects/{project_id}"
        before = {
            path: (await client.get(f"{base}/{path}")).json()
            for path in ("decision-services", "candidates", "evidence", "audit", "runs")
        }
        for action in ("evaluate", "promote", "promote"):
            resp = await client.post(
                f"{base}/candidates/{candidate_id}/{action}",
                json={"note": "Human approval cannot replace evaluation"}
                if action == "promote"
                else None,
            )
            assert resp.status_code == 409
            assert "Verified replay evaluation" in resp.json()["detail"]
        after = {path: (await client.get(f"{base}/{path}")).json() for path in before}
        assert after == before
