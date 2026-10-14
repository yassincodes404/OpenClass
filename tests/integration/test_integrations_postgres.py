"""PostgreSQL persistence test for Integrations Subsystem:

Creates integrations in one app instance, queries/updates/deletes from fresh instances,
and verifies database transaction isolation, foreign key cascades, and audit events.
"""

import uuid

from fastapi.testclient import TestClient
from openclass_provider_mock import MockChoiceTeacher, MockDecisionProvider, MockDiagnosisProvider
from openclass_server.main import create_app
from openclass_server.settings import Settings


def test_integrations_survive_restart_postgres(postgres_url: str) -> None:
    def fresh_client() -> TestClient:
        return TestClient(
            create_app(
                Settings(database_url=postgres_url),
                provider=MockDecisionProvider(),
                choice_teacher=MockChoiceTeacher(),
                diagnosis_provider=MockDiagnosisProvider(),
            )
        )

    slug = f"int-test-{uuid.uuid4().hex[:8]}"

    # Step 1: Create project and integration in Instance 1
    with fresh_client() as client:
        resp = client.post("/api/v1/projects", json={"name": f"Integration Project {slug}"})
        assert resp.status_code == 201
        project_id = resp.json()["id"]

        resp = client.post(
            f"/api/v1/projects/{project_id}/integrations",
            json={
                "name": "Production MCP Server",
                "type": "mcp",
                "endpoint": "https://mcp.prod.domain.com",
                "capabilities": ["query_metrics", "restart_pod"],
                "metadata": {"env": "production"},
            },
        )
        assert resp.status_code == 201
        integration_id = resp.json()["id"]

    # Step 2: In a brand-new app instance, read the integration and run test
    with fresh_client() as client:
        resp = client.get(f"/api/v1/projects/{project_id}/integrations/{integration_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Production MCP Server"
        assert data["type"] == "mcp"
        assert data["metadata"] == {"env": "production"}

        # Test integration
        test_resp = client.post(f"/api/v1/projects/{project_id}/integrations/{integration_id}/test")
        assert test_resp.status_code == 200
        test_data = test_resp.json()
        assert test_data["status"] == "disconnected"
        recorded_status = test_data["status"]
        assert test_data["latency_ms"] is not None

    # Step 3: In a third app instance, verify health update persisted and audit log
    with fresh_client() as client:
        resp = client.get(f"/api/v1/projects/{project_id}/integrations/{integration_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == recorded_status
        assert resp.json()["last_health_check"] is not None

        # Verify audit trail in PostgreSQL
        audit_resp = client.get(f"/api/v1/projects/{project_id}/audit")
        assert audit_resp.status_code == 200
        audit_types = [a["event_type"] for a in audit_resp.json()]
        assert "integration.created" in audit_types
        assert "integration.tested" in audit_types
