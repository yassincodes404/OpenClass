"""Seed Phase 7: provider config refs (mock default, unconfigured jev) + usage.

Local-only, idempotent. Mock output is simulated; Jev stays honestly
unconfigured without a key.
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
    base = (
        f"{CONTROL_PLANE}/control/workspaces/{workspace['id']}/projects/{project['id']}/providers"  # type: ignore[index]
    )

    status, existing = request(base, "GET", token)
    types = {c["type"] for c in (existing or {}).get("configs", [])}  # type: ignore[union-attr]
    report: dict[str, object] = {"simulated": True}

    if "mock" not in types:
        status, body = request(
            base,
            "POST",
            token,
            {"type": "mock", "is_default": True},
        )
        if status != 201:
            print(f"mock config failed ({status}): {body}", file=sys.stderr)
            return 1
        report["mock"] = "default (simulated)"

    if "jev" not in types:
        status, body = request(
            base,
            "POST",
            token,
            {"type": "jev", "endpoint_ref": "OPENCLASS_JEV_API_KEY", "is_default": False},
        )
        if status != 201:
            print(f"jev config failed ({status}): {body}", file=sys.stderr)
            return 1
        report["jev"] = "configured by env ref only (unconfigured locally, honest status)"

    status, usage = request(f"{base}/usage", "GET", token)
    report["usage_rows"] = len(usage) if isinstance(usage, list) else 0  # type: ignore[arg-type]
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
