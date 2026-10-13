"""Integration tests for project-scoped Evidence and Evolution Inbox API."""

import pytest
from httpx import ASGITransport, AsyncClient
from openclass_core.evidence import DiagnosisCategory
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


@pytest.fixture
def app(database_url: str):
    settings = Settings(database_url=database_url)
    return create_app(
        settings=settings,
        provider=MockForcedUnknownProvider(),
        diagnosis_provider=MockDiagnosisProvider(),
    )


async def test_evidence_api_full_lifecycle(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create project
        resp = await client.post("/api/v1/projects", json={"name": "SaaS Platform"})
        assert resp.status_code == 201
        project_id = resp.json()["id"]

        # 2. Ingest raw event
        resp = await client.post(
            f"/api/v1/projects/{project_id}/events",
            json={"content": "Can we get shared workspaces for our team?", "source_type": "text"},
        )
        assert resp.status_code == 201
        raw_event_id = resp.json()["id"]

        # 3. Create decision service
        resp = await client.post(
            f"/api/v1/projects/{project_id}/decision-services",
            json={
                "name": "Customer Intent",
                "instructions": "Determine intent",
                "choices": [{"key": "SUPPORT", "label": "Support"}],
            },
        )
        assert resp.status_code == 201
        service_id = resp.json()["id"]

        # 4. Execute decision run (uses MockForcedUnknownProvider -> UNKNOWN choice)
        resp = await client.post(
            f"/api/v1/projects/{project_id}/decision-services/{service_id}/runs",
            json={"raw_event_ids": [raw_event_id]},
        )
        assert resp.status_code == 201
        runs = resp.json()
        assert len(runs) == 1
        run_id = runs[0]["id"]
        assert runs[0]["selected_choice"] == "UNKNOWN"

        # 5. Verify evidence was automatically created
        resp = await client.get(f"/api/v1/projects/{project_id}/evidence")
        assert resp.status_code == 200
        evidence_list = resp.json()
        assert len(evidence_list) == 1
        ev = evidence_list[0]
        assert ev["trigger_type"] == "semantic_unknown"
        assert ev["status"] == "pending"
        assert ev["decision_run_id"] == run_id
        evidence_id = ev["id"]

        # 6. Test AI Failure Diagnosis endpoint
        resp = await client.post(
            f"/api/v1/projects/{project_id}/evidence/{evidence_id}/ai-diagnose"
        )
        assert resp.status_code == 200
        ai_diag = resp.json()
        assert ai_diag["diagnosis"] in [cat.value for cat in DiagnosisCategory]
        assert len(ai_diag["rationale"]) > 0

        # 7. Triage evidence
        resp = await client.patch(
            f"/api/v1/projects/{project_id}/evidence/{evidence_id}/triage",
            json={
                "diagnosis": "decision_space",
                "rationale": "Missing team workspace capability category",
            },
        )
        assert resp.status_code == 200
        triaged = resp.json()
        assert triaged["status"] == "triaged"
        assert triaged["diagnosis"] == "decision_space"

        # 8. Transition evidence to ready_for_evolution (using SDK 'note' field)
        resp = await client.post(
            f"/api/v1/projects/{project_id}/evidence/{evidence_id}/transition",
            json={
                "target_status": "ready_for_evolution",
                "note": "Confirmed recurring enterprise request",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready_for_evolution"
        assert resp.json()["diagnosis_rationale"] == "Confirmed recurring enterprise request"

        # 9. Create Evidence Case grouping (initially empty, with description)
        resp = await client.post(
            f"/api/v1/projects/{project_id}/evidence-cases",
            json={
                "title": "Team Workspace Requests",
                "description": "Enterprise team sharing requests",
                "decision_service_id": service_id,
            },
        )
        assert resp.status_code == 201
        case = resp.json()
        case_id = case["id"]
        assert case["title"] == "Team Workspace Requests"

        # 10. Attach evidence item to case via POST /evidence-cases/{case_id}/evidence
        resp = await client.post(
            f"/api/v1/projects/{project_id}/evidence-cases/{case_id}/evidence",
            json={"evidence_id": evidence_id},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == case_id

        # 10b. Verify case evidence
        resp = await client.get(f"/api/v1/projects/{project_id}/evidence-cases/{case_id}/evidence")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["id"] == evidence_id

        # 11. Submit run feedback
        resp = await client.post(
            f"/api/v1/projects/{project_id}/runs/{run_id}/feedback",
            json={"action": "confirm", "note": "Verified by lead reviewer"},
        )
        assert resp.status_code == 201
        assert resp.json()["action"] == "confirm"

        # 12. Check evolution summary
        resp = await client.get(f"/api/v1/projects/{project_id}/evolution/summary")
        assert resp.status_code == 200
        summary = resp.json()
        assert summary["ready_for_evolution"] == 1
        assert summary["total_evidence"] == 1
        assert summary["open_cases"] == 1
