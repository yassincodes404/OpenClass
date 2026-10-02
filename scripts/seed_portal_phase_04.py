"""Seed Phase 4 security demo state: strict redaction + one rate-limit test key.

Local-only, deterministic, idempotent. Requires the Phase 2/3 stack running
(Keycloak, control-plane, engine). Credentials are simulated development
accounts only.
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
    "http://127.0.0.1:8080/realms/openclass-local/protocol/openid-connect/token",
)
OWNER_USERNAME = "owner@acme.openclass.test"
OWNER_PASSWORD = "OpenClass-Local-Owner-2026"


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
    if status != 200:
        print(f"control-plane unreachable ({status})", file=sys.stderr)
        return 1
    workspace = next((w for w in workspaces if w["slug"] == "acme-support"), None)  # type: ignore[union-attr]
    if workspace is None:
        print("run seed:portal-phase-3 first (workspace acme-support missing)", file=sys.stderr)
        return 1

    status, projects = request(
        f"{CONTROL_PLANE}/control/workspaces/{workspace['id']}/projects",
        "GET",
        token,  # type: ignore[index]
    )
    project = next((p for p in projects if p["slug"] == "acme-support"), None)  # type: ignore[union-attr]
    if project is None:
        print("run seed:portal-phase-3 first (project acme-support missing)", file=sys.stderr)
        return 1

    report: dict[str, object] = {"simulated": True}

    status, _ = request(
        f"{CONTROL_PLANE}/control/workspaces/{workspace['id']}/projects/{project['id']}/settings",  # type: ignore[index]
        "PATCH",
        token,
        {"redaction_enabled": True, "retention_days": 30},
    )
    if status != 200:
        print(f"settings update failed ({status})", file=sys.stderr)
        return 1
    report["redaction"] = "strict (enabled, 30d retention)"

    status, keys = request(
        f"{CONTROL_PLANE}/control/workspaces/{workspace['id']}/projects/{project['id']}/keys",
        "GET",
        token,  # type: ignore[index]
    )
    existing = [k for k in keys if not k["revoked_at"] and "ingest" in k["scopes"]]  # type: ignore[union-attr]
    if not existing:
        status, key_body = request(
            f"{CONTROL_PLANE}/control/workspaces/{workspace['id']}/projects/{project['id']}/keys",  # type: ignore[index]
            "POST",
            token,
            {"scopes": ["ingest", "classify", "read"]},
        )
        if status != 201:
            print(f"key create failed ({status})", file=sys.stderr)
            return 1
        print(json.dumps(report, indent=2))
        print("\nLOCAL-ONLY SIMULATED RATE-LIMIT TEST KEY (shown once, stored as hash):")
        print(key_body["key"])  # type: ignore[index]
        return 0
    report["rate_limit_key"] = f"reusing {existing[0]['prefix']}…"
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
