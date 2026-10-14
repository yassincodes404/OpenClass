"""Authenticated, isolated ingestion with persistent replay protection."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openclass_server.main import create_app
from openclass_server.settings import Settings
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture
def webhook(mock_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> tuple[str, dict[str, str]]:
    monkeypatch.setenv("TEST_WEBHOOK_TOKEN", "only-a-test-credential")
    project = mock_client.post("/api/v1/projects", json={"name": "Webhook project"}).json()
    base = f"/api/v1/projects/{project['id']}/integrations"
    integration = mock_client.post(
        base,
        json={
            "name": "External events",
            "type": "webhook",
            "secret_ref": "TEST_WEBHOOK_TOKEN",
        },
    )
    assert integration.status_code == 201
    return f"{base}/{integration.json()['id']}/webhook", {
        "X-OpenClass-Token": "only-a-test-credential"
    }


def delivery(**changes: object) -> dict[str, object]:
    return {
        "event_key": "ticket:829:revision:14",
        "source": "helpdesk",
        "content": "I cannot sign in",
        "metadata": {"ticket_id": "829"},
        **changes,
    }


def test_delivery_retries_survive_restart(
    mock_client: TestClient,
    webhook: tuple[str, dict[str, str]],
    database_url: str,
) -> None:
    url, headers = webhook
    first = mock_client.post(url, headers=headers, json=delivery())
    assert first.status_code == 201
    with TestClient(
        create_app(Settings(database_url=database_url, decision_provider="mock"))
    ) as fresh:
        retry = fresh.post(url, headers=headers, json=delivery())
        assert retry.status_code == 200
        assert retry.json()["status"] == "duplicate"
        assert retry.json()["event_id"] == first.json()["event_id"]
        project_base = url.split("/integrations/")[0]
        events = fresh.get(f"{project_base}/events").json()
        assert len(events) == 1
        audit = fresh.get(f"{project_base}/audit").json()
        ingested = [a for a in audit if a["event_type"] == "integration.webhook_ingested"]
        assert len(ingested) == 1
        assert "only-a-test-credential" not in str(audit)


@pytest.mark.parametrize(
    "change",
    [
        {"content": "A different ticket"},
        {"metadata": {"ticket_id": "830"}},
        {"source": "another-source"},
    ],
)
def test_conflicting_replays_do_not_write(
    mock_client: TestClient,
    webhook: tuple[str, dict[str, str]],
    change: dict[str, object],
) -> None:
    url, headers = webhook
    assert mock_client.post(url, headers=headers, json=delivery()).status_code == 201
    assert mock_client.post(url, headers=headers, json=delivery(**change)).status_code == 409
    assert len(mock_client.get(url.split("/integrations/")[0] + "/events").json()) == 1


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-OpenClass-Token": "TEST_WEBHOOK_TOKEN"},
        {"Authorization": "Basic invalid"},
        {"X-OpenClass-Token": "only-a-test-credential", "Authorization": "Bearer different"},
    ],
)
def test_bad_credentials_cannot_ingest(
    mock_client: TestClient,
    webhook: tuple[str, dict[str, str]],
    headers: dict[str, str],
) -> None:
    url, _ = webhook
    response = mock_client.post(url, headers=headers, json=delivery())
    assert response.status_code == 401
    assert "only-a-test-credential" not in response.text
    assert mock_client.get(url.split("/integrations/")[0] + "/events").json() == []


def test_missing_secret_fails_closed(
    mock_client: TestClient,
    webhook: tuple[str, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url, headers = webhook
    monkeypatch.delenv("TEST_WEBHOOK_TOKEN")
    response = mock_client.post(url, headers=headers, json=delivery())
    assert response.status_code == 503
    assert mock_client.get(url.split("/integrations/")[0] + "/events").json() == []
    check = mock_client.post(url.removesuffix("/webhook") + "/test").json()
    assert check["status"] == "disconnected"
    assert check["capabilities"] == []


def test_secret_content_rejected_and_source_identity_cannot_be_spoofed(
    mock_client: TestClient,
    webhook: tuple[str, dict[str, str]],
) -> None:
    url, headers = webhook
    assert (
        mock_client.patch(
            url.removesuffix("/webhook"), json={"metadata": {"token": headers["X-OpenClass-Token"]}}
        ).status_code
        == 400
    )
    assert (
        mock_client.post(
            url.split("/integrations/")[0] + "/integrations",
            json={
                "name": "Unsafe credential storage",
                "type": "webhook",
                "secret_ref": "TEST_WEBHOOK_TOKEN",
                "metadata": {"token": headers["X-OpenClass-Token"]},
            },
        ).status_code
        == 400
    )
    response = mock_client.post(
        url, headers=headers, json=delivery(content=headers["X-OpenClass-Token"])
    )
    assert response.status_code == 400
    assert headers["X-OpenClass-Token"] not in response.text
    response = mock_client.post(
        url,
        headers={"Authorization": f"Bearer {headers['X-OpenClass-Token']}"},
        json=delivery(metadata={"integration_id": "spoofed", "external_event_key": "spoofed"}),
    )
    assert response.status_code == 201
    event = mock_client.get(url.split("/integrations/")[0] + "/events").json()[0]
    assert event["metadata"]["integration_id"] == response.json()["integration_id"]
    assert event["metadata"]["external_event_key"] == "ticket:829:revision:14"


def test_cross_project_access_and_namespace_isolation(
    mock_client: TestClient,
    webhook: tuple[str, dict[str, str]],
) -> None:
    url, headers = webhook
    other = mock_client.post("/api/v1/projects", json={"name": "Other project"}).json()["id"]
    integration_id = url.split("/integrations/")[1].split("/")[0]
    other_base = f"/api/v1/projects/{other}/integrations"
    for suffix in ("", "/test", "/webhook"):
        response = mock_client.request(
            "GET" if not suffix else "POST",
            f"{other_base}/{integration_id}{suffix}",
            headers=headers,
            json=delivery() if suffix == "/webhook" else None,
        )
        assert response.status_code == 404
    new = mock_client.post(
        other_base, json={"name": "Other", "type": "webhook", "secret_ref": "TEST_WEBHOOK_TOKEN"}
    ).json()
    a = mock_client.post(url, headers=headers, json=delivery())
    b = mock_client.post(f"{other_base}/{new['id']}/webhook", headers=headers, json=delivery())
    assert a.status_code == b.status_code == 201
    assert a.json()["event_id"] != b.json()["event_id"]


@pytest.mark.parametrize(
    "body", [{"content": "missing identity"}, delivery(event_key=" "), delivery(content=" ")]
)
def test_invalid_delivery_rejected(
    mock_client: TestClient,
    webhook: tuple[str, dict[str, str]],
    body: dict[str, object],
) -> None:
    url, headers = webhook
    assert mock_client.post(url, headers=headers, json=body).status_code == 422


def test_configuration_is_not_verified_capability_execution(mock_client: TestClient) -> None:
    project = mock_client.post("/api/v1/projects", json={"name": "Health checks"}).json()["id"]
    base = f"/api/v1/projects/{project}/integrations"
    assert (
        mock_client.post(base, json={"name": "Missing auth", "type": "webhook"}).status_code == 422
    )
    for kind in ("mcp", "provider", "database"):
        integration = mock_client.post(
            base, json={"name": kind, "type": kind, "capabilities": ["imagined_tool"]}
        ).json()
        url = f"{base}/{integration['id']}"
        report = mock_client.post(url + "/test").json()
        assert report["status"] == "pending"
        assert report["capabilities"] == []
        assert "not implemented" in report["error_message"]
        assert mock_client.patch(url, json={"status": "connected"}).status_code == 422
        assert mock_client.patch(url, json={}).status_code == 422


async def test_receipt_source_and_audit_are_immutable(
    mock_client: TestClient,
    webhook: tuple[str, dict[str, str]],
    database_url: str,
) -> None:
    url, headers = webhook
    assert mock_client.post(url, headers=headers, json=delivery()).status_code == 201
    engine = create_async_engine(database_url)
    try:
        for table in ("webhook_receipts", "raw_events", "audit_events"):
            for operation in (
                f"DELETE FROM {table}",
                f"UPDATE {table} SET project_id = '{uuid4()}'",
            ):
                with pytest.raises(IntegrityError):
                    async with engine.begin() as connection:
                        await connection.execute(text(operation))
    finally:
        await engine.dispose()


async def test_failed_audit_rolls_back_observation_and_receipt(
    mock_client: TestClient,
    webhook: tuple[str, dict[str, str]],
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TRIGGER reject_webhook_audit BEFORE INSERT ON audit_events "
                    "WHEN NEW.event_type = 'integration.webhook_ingested' BEGIN "
                    "SELECT RAISE(ABORT, 'test audit failure'); END"
                )
            )
        url, headers = webhook
        assert mock_client.post(url, headers=headers, json=delivery()).status_code == 409
        assert mock_client.get(url.split("/integrations/")[0] + "/events").json() == []
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT COUNT(*) FROM webhook_receipts")) == 0
    finally:
        await engine.dispose()


def test_changed_credentials_invalidate_health_and_old_tokens(
    mock_client: TestClient,
    webhook: tuple[str, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url, headers = webhook
    base = url.removesuffix("/webhook")
    assert mock_client.post(base + "/test").json()["status"] == "connected"
    monkeypatch.setenv("TEST_ROTATED_SECRET", "test-rotated-token")
    changed = mock_client.patch(base, json={"secret_ref": "TEST_ROTATED_SECRET"}).json()
    assert changed["status"] == "pending"
    assert changed["last_health_check"] is None
    assert mock_client.post(url, headers=headers, json=delivery()).status_code == 401
    assert (
        mock_client.post(
            url, headers={"X-OpenClass-Token": "test-rotated-token"}, json=delivery()
        ).status_code
        == 201
    )


def test_distinct_event_keys_with_identical_content_succeed_independently(
    mock_client: TestClient,
    webhook: tuple[str, dict[str, str]],
) -> None:
    url, headers = webhook
    first = mock_client.post(
        url,
        headers=headers,
        json=delivery(event_key="ticket:829:revision:14", metadata={"ticket_id": "829"}),
    )
    assert first.status_code == 201
    second = mock_client.post(
        url,
        headers=headers,
        json=delivery(event_key="ticket:830:revision:1", metadata={"ticket_id": "830"}),
    )
    assert second.status_code == 201
    assert second.json()["status"] == "ingested"
    assert second.json()["event_id"] != first.json()["event_id"]
    project_base = url.split("/integrations/")[0]
    events = mock_client.get(f"{project_base}/events").json()
    assert len(events) == 2
    audit = mock_client.get(f"{project_base}/audit").json()
    ingested = [a for a in audit if a["event_type"] == "integration.webhook_ingested"]
    assert len(ingested) == 2
