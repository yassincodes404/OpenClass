"""Phase 16 support integrations: safe routing, source webhooks, idempotency."""

from __future__ import annotations

from fastapi.testclient import TestClient
from openclass_core.routing import RoutingRule, adapter_status, decide_routing


def test_unknown_path_is_fixed_escalation():
    rules = [
        RoutingRule(
            id="r1",
            project_id="p",
            integration_id="i",
            match_choice="BILLING",
            action="tag",
            action_value="billing",
        )
    ]
    outcome = decide_routing(rules, "UNKNOWN")
    assert outcome["action"] == "escalate"
    assert outcome["queue"] == "triage"
    assert "no auto-reply" in outcome["detail"]


def test_known_choice_applies_first_matching_rule():
    rules = [
        RoutingRule(
            id="r1",
            project_id="p",
            integration_id="i",
            match_choice="BILLING",
            action="tag",
            action_value="billing",
        ),
        RoutingRule(
            id="r2",
            project_id="p",
            integration_id="i",
            match_choice="REFUND",
            action="assign_queue",
            action_value="refunds",
        ),
    ]
    assert decide_routing(rules, "BILLING")["tag"] == "billing"
    assert decide_routing(rules, "REFUND")["queue"] == "refunds"
    assert decide_routing(rules, "DELIVERY")["action"] == "tag"  # default


def test_adapter_status_is_honest():
    assert adapter_status("zendesk")["implemented"] is True
    assert adapter_status("salesforce")["implemented"] is False
    assert "not implemented" in adapter_status("slack")["note"]


def _setup(client: TestClient, monkeypatch_token: str | None = None) -> tuple[str, str, str]:
    import os

    if monkeypatch_token:
        os.environ["OPENCLASS_WEBHOOK_TOKEN_ZENDESK"] = monkeypatch_token
    slug = client.post("/api/v1/projects", json={"name": "Support Co"}).json()["slug"]
    integration = client.post(
        f"/api/v1/projects/{slug}/integrations",
        json={
            "name": "zendesk",
            "type": "webhook",
            "secret_ref": "OPENCLASS_WEBHOOK_TOKEN_ZENDESK",
        },
    ).json()
    service = client.post(
        f"/api/v1/projects/{slug}/decision-services",
        json={
            "name": "Router",
            "instructions": "Route the request.",
            "choices": [{"key": "BILLING", "label": "Billing"}],
        },
    ).json()["id"]
    return slug, integration["id"], service


def test_known_delivery_tags_and_routes(mock_client: TestClient, monkeypatch):
    monkeypatch.setenv("OPENCLASS_WEBHOOK_TOKEN_ZENDESK", "zk-secret-1")
    slug, integration_id, service = _setup(mock_client)
    created = mock_client.post(
        f"/api/v1/projects/{slug}/integrations/{integration_id}/routes",
        json={"match_choice": "BILLING", "action": "tag", "action_value": "billing"},
    )
    assert created.status_code == 201
    delivered = mock_client.post(
        f"/api/v1/projects/{slug}/webhooks/zendesk",
        json={"content": "I have a billing question", "event_key": "zd-1"},
        headers={"authorization": "Bearer zk-secret-1"},
    )
    assert delivered.status_code == 201, delivered.text
    body = delivered.json()
    assert body["selected_choice"] == "BILLING"
    assert body["routing"]["action"] == "tag"
    assert body["routing"]["tag"] == "billing"
    assert body["simulated"] is True
    outcomes = mock_client.get(f"/api/v1/projects/{slug}/integrations/outcomes").json()
    assert outcomes[0]["action"] == "tag"


def test_unknown_delivery_escalates_without_auto_reply(mock_client: TestClient, monkeypatch):
    monkeypatch.setenv("OPENCLASS_WEBHOOK_TOKEN_ZENDESK", "zk-secret-2")
    slug, integration_id, _service = _setup(mock_client)
    delivered = mock_client.post(
        f"/api/v1/projects/{slug}/webhooks/zendesk",
        json={"content": "Something completely novel happened", "event_key": "zd-2"},
        headers={"authorization": "Bearer zk-secret-2"},
    )
    assert delivered.status_code == 201
    body = delivered.json()
    assert body["selected_choice"] == "UNKNOWN"
    assert body["routing"]["action"] == "escalate"
    assert body["routing"]["queue"] == "triage"


def test_bad_token_is_rejected(mock_client: TestClient, monkeypatch):
    monkeypatch.setenv("OPENCLASS_WEBHOOK_TOKEN_ZENDESK", "zk-secret-3")
    slug, _integration, _service = _setup(mock_client)
    delivered = mock_client.post(
        f"/api/v1/projects/{slug}/webhooks/zendesk",
        json={"content": "hello", "event_key": "zd-3"},
        headers={"authorization": "Bearer wrong-token"},
    )
    assert delivered.status_code == 401


def test_concurrent_identical_delivery_commits_once(mock_client: TestClient, monkeypatch):
    monkeypatch.setenv("OPENCLASS_WEBHOOK_TOKEN_ZENDESK", "zk-secret-4")
    slug, _integration, _service = _setup(mock_client)
    headers = {"authorization": "Bearer zk-secret-4"}
    first = mock_client.post(
        f"/api/v1/projects/{slug}/webhooks/zendesk",
        json={"content": "Refund my order please billing", "event_key": "zd-4"},
        headers=headers,
    )
    second = mock_client.post(
        f"/api/v1/projects/{slug}/webhooks/zendesk",
        json={"content": "Refund my order please billing", "event_key": "zd-4"},
        headers=headers,
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    changed = mock_client.post(
        f"/api/v1/projects/{slug}/webhooks/zendesk",
        json={"content": "Different content entirely", "event_key": "zd-4"},
        headers=headers,
    )
    assert changed.status_code == 409


def test_unknown_rule_configuration_rejected(mock_client: TestClient, monkeypatch):
    monkeypatch.setenv("OPENCLASS_WEBHOOK_TOKEN_ZENDESK", "zk-secret-5")
    slug, integration_id, _service = _setup(mock_client)
    created = mock_client.post(
        f"/api/v1/projects/{slug}/integrations/{integration_id}/routes",
        json={"match_choice": "UNKNOWN", "action": "tag", "action_value": "x"},
    )
    assert created.status_code == 400


def test_adapter_listing(mock_client: TestClient):
    slug = mock_client.post("/api/v1/projects", json={"name": "Adapters Co"}).json()["slug"]
    adapters = mock_client.get(f"/api/v1/projects/{slug}/integrations/adapters").json()
    by_name = {entry["source"]: entry for entry in adapters}
    assert by_name["zendesk"]["implemented"] is True
    assert by_name["slack"]["implemented"] is False
