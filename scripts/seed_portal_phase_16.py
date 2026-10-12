"""Seed Phase 16: mock Zendesk connection, 2 routing rules, 3 deliveries.

Requires OPENCLASS_WEBHOOK_TOKEN_ZENDESK in the engine env for deliveries.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

CONTROL_PLANE = os.environ.get("CONTROL_PLANE_URL", "http://127.0.0.1:7400")
KEYCLOAK_TOKEN_URL = os.environ.get(
    "KEYCLOAK_TOKEN_URL",
    "http://127.0.0.1:55808/realms/openclass-local/protocol/openid-connect/token",
)
ENGINE = os.environ.get("ENGINE_BASE_URL", "http://127.0.0.1:7331")
WEBHOOK_TOKEN = os.environ.get("OPENCLASS_WEBHOOK_TOKEN_ZENDESK", "openclass-local-zendesk-token")
OWNER_USERNAME = "owner@acme.openclass.test"
OWNER_PASSWORD = "OpenClass-Local-Owner-2026"


def request(
    url: str,
    method: str,
    token: str | None = None,
    body: dict | None = None,
    headers: dict | None = None,
) -> tuple[int, object]:
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=payload, method=method)
    if payload is not None:
        req.add_header("content-type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as response:
            data = response.read().decode() if response.status != 204 else "null"
            return response.status, json.loads(data) if data else None
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read().decode())
        except json.JSONDecodeError:
            return error.code, None


def owner_token() -> str:
    form = (
        f"grant_type=password&client_id=openclass-portal&username={OWNER_USERNAME}&password={OWNER_PASSWORD}"
    ).encode()
    req = urllib.request.Request(KEYCLOAK_TOKEN_URL, data=form, method="POST")
    req.add_header("content-type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())["access_token"]


def main() -> int:
    token = owner_token()
    status, workspaces = request(f"{CONTROL_PLANE}/control/workspaces", "GET", token)
    workspace = next((w for w in workspaces if w["slug"] == "acme-support"), None)  # type: ignore[union-attr]
    status, projects = request(
        f"{CONTROL_PLANE}/control/workspaces/{workspace['id']}/projects",
        "GET",
        token,  # type: ignore[index]
    )
    project = next((p for p in projects if p["slug"] == "acme-support"), None)  # type: ignore[union-attr]
    if workspace is None or project is None:
        print("run seed:portal-phase-3 first", file=sys.stderr)
        return 1
    root = f"{CONTROL_PLANE}/control/workspaces/{workspace['id']}/projects/{project['id']}"  # type: ignore[index]
    engine_project = project["engine_project_id"]  # type: ignore[index]

    status, integrations = request(f"{root}/integrations", "GET", token)
    zendesk = next((i for i in integrations if i["name"] == "zendesk"), None)  # type: ignore[union-attr]
    if zendesk is None:
        status, zendesk = request(
            f"{root}/integrations",
            "POST",
            token,
            {"name": "zendesk", "type": "webhook", "secret_ref": "OPENCLASS_WEBHOOK_TOKEN_ZENDESK"},
        )
        if status != 201:
            print(f"connect failed ({status}): {zendesk}", file=sys.stderr)
            return 1

    status, routes = request(f"{root}/integrations/routes", "GET", token)
    if len(routes or []) == 0:  # type: ignore[arg-type]
        for choice, action, value in (
            ("BILLING", "tag", "billing"),
            ("REFUND", "assign_queue", "refunds"),
        ):
            request(
                f"{root}/integrations/routes",
                "POST",
                token,
                {
                    "integration_id": zendesk["id"],
                    "match_choice": choice,
                    "action": action,
                    "action_value": value,
                },  # type: ignore[index]
            )

    deliveries = [
        {"content": "I have a billing question about my invoice", "event_key": "seed16-1"},
        {"content": "Refund my last order please", "event_key": "seed16-2"},
        {"content": "Something completely novel arrived", "event_key": "seed16-3"},
    ]
    results = []
    for delivery in deliveries:
        status, body = request(
            f"{ENGINE}/api/v1/projects/{engine_project}/webhooks/zendesk",
            "POST",
            None,
            delivery,
            {"authorization": f"Bearer {WEBHOOK_TOKEN}"},
        )
        results.append(
            {
                "key": delivery["event_key"],
                "status": status,
                "choice": body.get("selected_choice") if isinstance(body, dict) else None,  # type: ignore[union-attr]
                "routing": body.get("routing", {}).get("action")
                if isinstance(body, dict)
                else None,  # type: ignore[union-attr]
            }
        )

    print(json.dumps({"simulated": True, "deliveries": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
