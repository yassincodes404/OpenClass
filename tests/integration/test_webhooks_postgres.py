"""Concurrent delivery proof on a disposable, migrated PostgreSQL database."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openclass_server.main import create_app
from openclass_server.settings import Settings


@pytest.mark.postgres
def test_concurrent_webhooks_commit_once_and_survive_restart(
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_PG_WEBHOOK_SECRET", "test-only-postgres-token")

    def fresh_client() -> TestClient:
        return TestClient(create_app(Settings(database_url=postgres_url, decision_provider="mock")))

    with fresh_client() as client:
        project_id = client.post("/api/v1/projects", json={"name": f"Webhook {uuid4()}"}).json()[
            "id"
        ]
        base = f"/api/v1/projects/{project_id}"
        integration = client.post(
            f"{base}/integrations",
            json={
                "name": "Helpdesk",
                "type": "webhook",
                "secret_ref": "TEST_PG_WEBHOOK_SECRET",
            },
        ).json()["id"]
    url = f"{base}/integrations/{integration}/webhook"
    body = {"event_key": "external:ticket:revision:1", "content": "A real external observation"}
    headers = {"X-OpenClass-Token": "test-only-postgres-token"}

    def deliver(_: int) -> tuple[int, str]:
        with fresh_client() as client:
            response = client.post(url, headers=headers, json=body)
            return response.status_code, response.json()["event_id"]

    with ThreadPoolExecutor(max_workers=6) as executor:
        responses = list(executor.map(deliver, range(6)))
    assert [code for code, _ in responses].count(201) == 1
    assert [code for code, _ in responses].count(200) == 5
    assert len({event_id for _, event_id in responses}) == 1

    with fresh_client() as client:
        assert len(client.get(f"{base}/events").json()) == 1
        audits = client.get(f"{base}/audit").json()
        assert sum(a["event_type"] == "integration.webhook_ingested" for a in audits) == 1
        assert client.post(url, headers=headers, json=body).status_code == 200
        assert (
            client.post(url, headers=headers, json={**body, "content": "Changed"}).status_code
            == 409
        )
