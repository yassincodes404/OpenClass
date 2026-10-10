"""Seed Phase 11: one reviewable candidate (8 evidence) + one below threshold (3).

Local-only. Reviewer credentials review; viewer cannot (enforced server-side).
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

    status, candidates = request(f"{base}/candidates", "GET", token)
    if len(candidates or []) >= 2:  # type: ignore[arg-type]
        print(
            json.dumps(
                {"simulated": True, "already_seeded": True, "candidates": len(candidates)}, indent=2
            )
        )  # type: ignore[arg-type]
        return 0

    status, pool = request(f"{base}?limit=50", "GET", token)
    run_ids = [item["run_id"] for item in pool]  # type: ignore[union-attr]
    if len(run_ids) < 8:
        print("run seed:portal-phase-8 first (need >=8 unknowns)", file=sys.stderr)
        return 1

    status, result = request(f"{base}/cluster", "POST", token, {"threshold": 0.5})
    if status not in (200, 201):
        print(f"clustering failed ({status}): {result}", file=sys.stderr)
        return 1
    status, clusters = request(f"{base}/clusters", "GET", token)
    ranked = sorted(clusters, key=lambda c: c["size"], reverse=True)  # type: ignore[union-attr]

    created: list[dict] = []
    for label, cluster, attach in (
        ("reviewable", ranked[0], 8),
        ("below-threshold", ranked[-1], 3),
    ):
        status, candidate = request(f"{base}/clusters/{cluster['id']}/discover", "POST", token)  # type: ignore[index]
        if status != 201:
            print(f"discovery failed ({status}): {candidate}", file=sys.stderr)
            return 1
        if attach:
            status, collect = request(
                f"{base}/candidates/{candidate['id']}/collect",  # type: ignore[index]
                "POST",
                token,
                {"unknown_ids": run_ids[:attach]},
            )
            if status != 200:
                print(f"collect failed ({status}): {collect}", file=sys.stderr)
                return 1
            candidate["evidence"] = collect.get("evidence")  # type: ignore[index]
        created.append(
            {"label": label, "type": candidate["type"], "evidence": candidate.get("evidence")}
        )  # type: ignore[index]

    print(json.dumps({"simulated": True, "candidates": created}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
