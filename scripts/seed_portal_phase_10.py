"""Seed Phase 10: run discovery on the two largest clusters.

Local-only, idempotent-ish (each run creates new candidates; re-running adds
one candidate per cluster again — documented). Mock provider, simulated.
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
    base = f"{CONTROL_PLANE}/control/workspaces/{workspace['id']}/projects/{project['id']}/unknowns"  # type: ignore[index]

    status, clusters = request(f"{base}/clusters", "GET", token)
    if not clusters:
        print("run seed:portal-phase-9 first (no clusters)", file=sys.stderr)
        return 1
    ranked = sorted(clusters, key=lambda c: c["size"], reverse=True)  # type: ignore[union-attr]

    created: list[dict] = []
    for cluster in ranked[:2]:
        status, candidate = request(f"{base}/clusters/{cluster['id']}/discover", "POST", token)  # type: ignore[index]
        if status != 201:
            print(f"discovery failed ({status}): {candidate}", file=sys.stderr)
            return 1
        created.append({"type": candidate["type"], "name": candidate.get("canonical_name")})  # type: ignore[index]

    print(json.dumps({"simulated": True, "discovered": created}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
