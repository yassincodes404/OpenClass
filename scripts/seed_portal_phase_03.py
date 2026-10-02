"""Seed Phase 3 demo data: workspace, project, classifier, and one scoped dev key.

Local-only, deterministic, idempotent. Requires Keycloak, control-plane, and the
engine to be running. Credentials are simulated development accounts only.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

CONTROL_PLANE = os.environ.get("CONTROL_PLANE_URL", "http://127.0.0.1:7400")
KEYCLOAK_TOKEN_URL = os.environ.get(
    "KEYCLOAK_TOKEN_URL",
    "http://127.0.0.1:8080/realms/openclass-local/protocol/openid-connect/token",
)
OWNER_USERNAME = "owner@acme.openclass.test"
OWNER_PASSWORD = "OpenClass-Local-Owner-2026"

CLASSES = ["billing", "refund", "delivery", "cancel_subscription", "account_access"]


def request(
    url: str, method: str, token: str | None = None, body: dict | None = None
) -> tuple[int, object]:
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=payload, method=method)
    if payload is not None:
        req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as response:
            data = response.read().decode() if response.status != 204 else "null"
            return response.status, json.loads(data) if data else None
    except urllib.error.HTTPError as error:
        detail = error.read().decode()
        try:
            parsed = json.loads(detail)
        except json.JSONDecodeError:
            parsed = detail
        return error.code, parsed


def owner_token() -> str:
    form = (
        f"grant_type=password&client_id=openclass-portal&username={OWNER_USERNAME}&password={OWNER_PASSWORD}"
    ).encode()
    req = urllib.request.Request(KEYCLOAK_TOKEN_URL, data=form, method="POST")
    req.add_header("content-type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req) as response:
        payload = json.loads(response.read().decode())
    return payload["access_token"]


def main() -> int:
    token = owner_token()
    created: dict[str, object] = {"simulated": True}

    status, workspaces = request(f"{CONTROL_PLANE}/control/workspaces", "GET", token)
    if status != 200:
        print(
            f"control-plane unreachable or unauthorized ({status}): {workspaces}", file=sys.stderr
        )
        return 1
    workspace = next((w for w in workspaces if w["slug"] == "acme-support"), None)  # type: ignore[union-attr]
    if workspace is None:
        status, workspace = request(
            f"{CONTROL_PLANE}/control/workspaces", "POST", token, {"name": "Acme Support"}
        )
        if status != 201:
            print(f"workspace create failed ({status}): {workspace}", file=sys.stderr)
            return 1
        created["workspace"] = workspace["slug"]
    workspace_id = workspace["id"]  # type: ignore[index]

    status, projects = request(
        f"{CONTROL_PLANE}/control/workspaces/{workspace_id}/projects", "GET", token
    )
    project = next((p for p in projects if p["slug"] == "acme-support"), None)  # type: ignore[union-attr]
    if project is None:
        status, project = request(
            f"{CONTROL_PLANE}/control/workspaces/{workspace_id}/projects",
            "POST",
            token,
            {"name": "Acme Support", "description": "Support intent routing demo (simulated)"},
        )
        if status != 201:
            print(f"project create failed ({status}): {project}", file=sys.stderr)
            return 1
        created["project"] = project["slug"]
    project_id = project["id"]  # type: ignore[index]

    status, classifiers = request(
        f"{CONTROL_PLANE}/control/workspaces/{workspace_id}/projects/{project_id}/classifiers",
        "GET",
        token,
    )
    classifier = next((c for c in classifiers if c["slug"] == "support-intent"), None)  # type: ignore[union-attr]
    if classifier is None:
        status, classifier = request(
            f"{CONTROL_PLANE}/control/workspaces/{workspace_id}/projects/{project_id}/classifiers",
            "POST",
            token,
            {
                "name": "Support intent",
                "classes": [
                    {"canonical_name": name, "display_name": name.replace("_", " ").title()}
                    for name in CLASSES
                ],
                "unknown_fallback": True,
            },
        )
        if status != 201:
            print(f"classifier create failed ({status}): {classifier}", file=sys.stderr)
            return 1
        created["classifier"] = classifier["slug"]  # type: ignore[index]

    status, keys = request(
        f"{CONTROL_PLANE}/control/workspaces/{workspace_id}/projects/{project_id}/keys",
        "GET",
        token,
    )
    active = [k for k in keys if not k["revoked_at"]]  # type: ignore[union-attr]
    api_key = None
    if not active:
        status, key_body = request(
            f"{CONTROL_PLANE}/control/workspaces/{workspace_id}/projects/{project_id}/keys",
            "POST",
            token,
            {"scopes": ["ingest", "read"]},
        )
        if status != 201:
            print(f"key create failed ({status}): {key_body}", file=sys.stderr)
            return 1
        api_key = key_body["key"]  # type: ignore[index]
        created["api_key"] = "created"

    print(json.dumps({**created, "workspace_id": workspace_id, "project_id": project_id}, indent=2))
    if api_key:
        print("\nLOCAL-ONLY SIMULATED DEV KEY (shown once, stored as hash):")
        print(api_key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
