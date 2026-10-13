"""Integration tests for the OpenClass Integrations Subsystem and System Health."""

import pytest
from httpx import ASGITransport, AsyncClient
from openclass_provider_mock import MockChoiceTeacher, MockDecisionProvider, MockDiagnosisProvider
from openclass_server.main import create_app
from openclass_server.settings import Settings


@pytest.fixture
def app(database_url: str):
    settings = Settings(database_url=database_url)
    return create_app(
        settings=settings,
        provider=MockDecisionProvider(),
        choice_teacher=MockChoiceTeacher(),
        diagnosis_provider=MockDiagnosisProvider(),
    )


async def test_integrations_lifecycle_api(app, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_TEST_SECRET", "test-only-token-value")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. System health check
        health_resp = await client.get("/api/v1/system/health")
        assert health_resp.status_code == 200
        health_data = health_resp.json()
        assert health_data["status"] == "healthy"
        assert health_data["database"]["connected"] is True
        assert health_data["database"]["migration_current"] is True
        assert health_data["version"] == "0.0.1"
        assert "latency_ms" in health_data["database"]

        # 2. Create project
        proj_resp = await client.post(
            "/api/v1/projects",
            json={"name": "SaaS Platform Project", "description": "Production integration testing"},
        )
        assert proj_resp.status_code == 201
        slug = proj_resp.json()["slug"]

        # 3. Create MCP Integration
        mcp_resp = await client.post(
            f"/api/v1/projects/{slug}/integrations",
            json={
                "name": "DevOps MCP",
                "type": "mcp",
                "endpoint": "https://mcp.internal.dev",
                "capabilities": ["read_logs", "restart_service"],
            },
        )
        assert mcp_resp.status_code == 201
        mcp_data = mcp_resp.json()
        assert mcp_data["name"] == "DevOps MCP"
        assert mcp_data["type"] == "mcp"
        assert mcp_data["status"] == "pending"
        mcp_id = mcp_data["id"]

        # 4. Create Inbound Webhook Integration
        webhook_resp = await client.post(
            f"/api/v1/projects/{slug}/integrations",
            json={
                "name": "Stripe Events Webhook",
                "type": "webhook",
                "secret_ref": "STRIPE_TEST_SECRET",
                "capabilities": ["event_ingestion"],
            },
        )
        assert webhook_resp.status_code == 201
        webhook_id = webhook_resp.json()["id"]

        # 5. List Integrations
        list_resp = await client.get(f"/api/v1/projects/{slug}/integrations")
        assert list_resp.status_code == 200
        integrations = list_resp.json()
        assert len(integrations) == 2
        names = {i["name"] for i in integrations}
        assert "DevOps MCP" in names
        assert "Stripe Events Webhook" in names

        # 6. Get Integration by ID
        get_resp = await client.get(f"/api/v1/projects/{slug}/integrations/{mcp_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == mcp_id

        # 7. Update Integration
        patch_resp = await client.patch(
            f"/api/v1/projects/{slug}/integrations/{mcp_id}",
            json={"name": "Production DevOps MCP", "status": "pending"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["name"] == "Production DevOps MCP"
        assert patch_resp.json()["status"] == "pending"

        # 8. Test Integration Connectivity
        test_resp = await client.post(f"/api/v1/projects/{slug}/integrations/{webhook_id}/test")
        assert test_resp.status_code == 200
        test_data = test_resp.json()
        assert test_data["status"] == "connected"
        assert test_data["latency_ms"] is not None
        assert "event_ingestion" in test_data["capabilities"]

        # 9. Ingest Event via Webhook
        ingest_resp = await client.post(
            f"/api/v1/projects/{slug}/integrations/{webhook_id}/webhook",
            json={
                "event_key": "stripe:subscription:revision:1",
                "source": "stripe",
                "content": '{"event": "customer.subscription.updated", "status": "active"}',
                "metadata": {"customer_id": "cus_123"},
            },
            headers={"X-OpenClass-Token": "test-only-token-value"},
        )
        assert ingest_resp.status_code == 201
        ingest_data = ingest_resp.json()
        assert ingest_data["status"] == "ingested"
        event_id = ingest_data["event_id"]

        # 10. Verify event exists in project events
        events_resp = await client.get(f"/api/v1/projects/{slug}/events")
        assert events_resp.status_code == 200
        events = events_resp.json()
        assert any(e["id"] == event_id for e in events)

        # 11. Delete Integration
        del_resp = await client.delete(f"/api/v1/projects/{slug}/integrations/{mcp_id}")
        assert del_resp.status_code == 204

        # 12. Verify audit events recorded
        audit_resp = await client.get(f"/api/v1/projects/{slug}/audit")
        assert audit_resp.status_code == 200
        audit_types = [a["event_type"] for a in audit_resp.json()]
        assert "integration.created" in audit_types
        assert "integration.updated" in audit_types
        assert "integration.tested" in audit_types
        assert "integration.deleted" in audit_types

        # 13. Reject forbidden system secret_ref and SSRF REST endpoints at API boundary
        bad_secret = await client.post(
            f"/api/v1/projects/{slug}/integrations",
            json={
                "name": "Exfil Attempt",
                "type": "webhook",
                "secret_ref": "OPENCLASS_DATABASE_URL",
            },
        )
        assert bad_secret.status_code == 422

        ssrf_endpoint = await client.post(
            f"/api/v1/projects/{slug}/integrations",
            json={
                "name": "Metadata SSRF",
                "type": "rest_api",
                "endpoint": "http://169.254.169.254/latest/meta-data/",
            },
        )
        assert ssrf_endpoint.status_code == 422

