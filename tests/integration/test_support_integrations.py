"""Phase 16 support integrations: safe routing, source webhooks, idempotency."""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from openclass_core.integrations import IntegrationConfig, IntegrationStatus, IntegrationType
from openclass_core.routing import (
    RouteOutcome,
    RoutingRule,
    adapter_status,
    decide_routing,
    evaluate_routing,
)
from openclass_server.integration_adapters import EnvironmentSecrets, HTTPIntegrationProbe


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
    outcome = decide_routing(rules, "UNKNOWN", run_id="run-u1")
    assert outcome["action"] == "escalate"
    assert outcome["queue"] == "triage"
    assert "no auto-reply" in outcome["detail"]
    assert outcome["delivery_mode"] == "simulated"
    assert outcome["idempotency_key"] == "run-u1:escalate"


def test_route_outcome_model_defaults_and_idempotency_key():
    rules = [
        RoutingRule(
            id="route-billing",
            project_id="p",
            integration_id="i",
            match_choice="BILLING",
            action="tag",
            action_value="billing",
        )
    ]
    typed = evaluate_routing(rules, "BILLING", run_id="run-123")
    assert isinstance(typed, RouteOutcome)
    assert typed.delivery_mode == "simulated"
    assert typed.idempotency_key == "run-123:route-billing"
    assert typed.tag == "billing"

    verified = RouteOutcome(
        run_id="run-456",
        route_id="route-q",
        selected_choice="REFUND",
        action="assign_queue",
        queue="refunds",
        delivery_mode="webhook_verified",
    )
    assert verified.delivery_mode == "webhook_verified"
    assert verified.idempotency_key == "run-456:route-q"


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


def test_repeated_route_evaluation_for_same_run_is_idempotent(mock_client: TestClient, monkeypatch):
    monkeypatch.setenv("OPENCLASS_WEBHOOK_TOKEN_ZENDESK", "zk-secret-idem")
    slug, integration_id, service_id = _setup(mock_client)
    route_resp = mock_client.post(
        f"/api/v1/projects/{slug}/integrations/{integration_id}/routes",
        json={"match_choice": "BILLING", "action": "tag", "action_value": "billing"},
    )
    assert route_resp.status_code == 201
    route_id = route_resp.json()["id"]

    event_resp = mock_client.post(
        f"/api/v1/projects/{slug}/events",
        json={"content": "Billing question about my invoice", "source_type": "text"},
    )
    assert event_resp.status_code == 201
    event_id = event_resp.json()["id"]

    run_resp = mock_client.post(
        f"/api/v1/projects/{slug}/decision-services/{service_id}/runs",
        json={"raw_event_ids": [event_id]},
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()[0]["id"]

    first_eval = mock_client.post(
        f"/api/v1/projects/{slug}/integrations/routes/evaluate",
        json={"run_id": run_id, "integration_id": integration_id},
    )
    assert first_eval.status_code == 201, first_eval.text
    first_body = first_eval.json()
    assert first_body["deduplicated"] is False
    assert first_body["routed"] is True
    assert first_body["delivery_mode"] == "simulated"
    assert first_body["idempotency_key"] == f"{run_id}:{route_id}"

    second_eval = mock_client.post(
        f"/api/v1/projects/{slug}/integrations/routes/evaluate",
        json={"run_id": run_id, "integration_id": integration_id},
    )
    assert second_eval.status_code == 200, second_eval.text
    second_body = second_eval.json()
    assert second_body["deduplicated"] is True
    assert second_body["routed"] is False
    assert second_body["idempotency_key"] == f"{run_id}:{route_id}"

    outcomes = mock_client.get(f"/api/v1/projects/{slug}/integrations/outcomes").json()
    assert len(outcomes) == 1
    assert outcomes[0]["idempotency_key"] == f"{run_id}:{route_id}"
    assert outcomes[0]["delivery_mode"] == "simulated"


async def test_mcp_probe_discovers_tools_and_falls_back_on_405() -> None:
    seen_requests: list[httpx.Request] = []

    def handle_tools_list(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        assert request.method == "POST"
        payload = json.loads(request.content.decode())
        assert payload == {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "tools": [
                        {"name": "lookup_customer"},
                        {"name": "create_ticket"},
                    ]
                },
            },
        )

    probe = HTTPIntegrationProbe(EnvironmentSecrets(), httpx.MockTransport(handle_tools_list))
    report = await probe.check(
        IntegrationConfig(
            project_id=uuid4(),
            name="Support MCP",
            type=IntegrationType.MCP,
            endpoint="https://mcp.example.invalid/rpc",
        )
    )
    assert report.status == IntegrationStatus.CONNECTED
    assert report.capabilities == ("lookup_customer", "create_ticket")
    assert report.error_message is None
    assert len(seen_requests) == 1

    # Fallback to GET on 405 with default MCP capabilities when tools list not returned
    fallback_methods: list[str] = []

    def handle_fallback(request: httpx.Request) -> httpx.Response:
        fallback_methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(405)
        return httpx.Response(200, json={"status": "ok"})

    fallback_probe = HTTPIntegrationProbe(
        EnvironmentSecrets(), httpx.MockTransport(handle_fallback)
    )
    fallback_report = await fallback_probe.check(
        IntegrationConfig(
            project_id=uuid4(),
            name="Fallback MCP",
            type=IntegrationType.MCP,
            endpoint="https://mcp.example.invalid/health",
        )
    )
    assert fallback_report.status == IntegrationStatus.CONNECTED
    assert fallback_report.capabilities == ("mcp_tools", "context_fetch")
    assert fallback_methods == ["POST", "GET"]


@pytest.mark.parametrize(
    "status_code,expected_status,expected_caps",
    [
        (200, IntegrationStatus.CONNECTED, ("model_inference",)),
        (401, IntegrationStatus.CONNECTED, ("model_inference",)),
        (403, IntegrationStatus.CONNECTED, ("model_inference",)),
        (502, IntegrationStatus.DEGRADED, ()),
    ],
)
async def test_provider_probe_reports_reachability_and_capabilities(
    status_code: int,
    expected_status: IntegrationStatus,
    expected_caps: tuple[str, ...],
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(status_code)

    probe = HTTPIntegrationProbe(EnvironmentSecrets(), httpx.MockTransport(handle))
    report = await probe.check(
        IntegrationConfig(
            project_id=uuid4(),
            name="Gateway Provider",
            type=IntegrationType.PROVIDER,
            endpoint="https://provider.example.invalid/v1/models",
        )
    )
    assert report.status == expected_status
    assert report.capabilities == expected_caps


@pytest.mark.parametrize("integration_type", [IntegrationType.MCP, IntegrationType.PROVIDER])
async def test_mcp_and_provider_probes_enforce_ssrf_protection(
    integration_type: IntegrationType,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        pytest.fail("SSRF endpoint must not be contacted")

    probe = HTTPIntegrationProbe(EnvironmentSecrets(), httpx.MockTransport(handle))
    report = await probe.check(
        IntegrationConfig(
            project_id=uuid4(),
            name="SSRF Attempt",
            type=integration_type,
            endpoint="http://169.254.169.254/latest/meta-data/",
        )
    )
    assert report.status == IntegrationStatus.DISCONNECTED
