"""Seed Phase 14: promote the approved + evaluated cancel candidate to v2.

Verifies the canonical phrase now classifies known. Idempotent: skips when the
candidate is already active.
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
    root = f"{CONTROL_PLANE}/control/workspaces/{workspace['id']}/projects/{project['id']}"  # type: ignore[index]

    status, candidates = request(f"{root}/unknowns/candidates", "GET", token)
    active = next((c for c in candidates if c["status"] == "active"), None)  # type: ignore[union-attr]
    if active is not None:
        print(
            json.dumps(
                {"simulated": True, "already_active": True, "candidate": active["id"][:8]}, indent=2
            )
        )  # type: ignore[index]
        return 0

    candidate = next(
        (c for c in candidates if c["type"] == "NEW_CLASS" and c["status"] == "approved"), None
    )  # type: ignore[union-attr]
    if candidate is None:
        print("run seed:portal-phase-11 then approve the candidate first", file=sys.stderr)
        return 1
    candidate_id = candidate["id"]  # type: ignore[index]

    status, evaluations = request(f"{root}/evaluations", "GET", token)
    passing = next(
        (e for e in evaluations if e["candidate_id"] == candidate_id and e["overall_passed"]),
        None,  # type: ignore[union-attr]
    )
    if passing is None:
        print("run seed:portal-phase-13 first (no passing evaluation)", file=sys.stderr)
        return 1

    status, promoted = request(
        f"{root}/unknowns/candidates/{candidate_id}/promote",
        "POST",
        token,
        {
            "evaluation_id": passing["id"],  # type: ignore[index]
            "reviewer": "owner@acme.openclass.test",
            "rationale": "verified improvement on sealed gold set with no billing regression",
        },
    )
    if status != 201 and status != 200:
        print(f"promotion failed ({status}): {promoted}", file=sys.stderr)
        return 1

    status, detail = request(f"{root}/unknowns/candidates/{candidate_id}", "GET", token)
    canonical = str(detail.get("canonical_name", "") or "").upper()  # type: ignore[union-attr]
    probe = canonical.replace("_", " ").lower()
    status, services = request(f"{root}/decision-services", "GET", token)
    service = next((s for s in services if "intake" not in s["slug"]), None)  # type: ignore[union-attr]
    verified = None
    if service is not None:
        status, runs = request(
            f"{root}/decision-services/{service['id']}/runs",  # type: ignore[index]
            "POST",
            token,
            {"content": probe.capitalize()},
        )
        if status == 201 and runs:
            verified = runs[0].get("selected_choice")  # type: ignore[index]

    print(
        json.dumps(
            {
                "simulated": True,
                "promoted": promoted.get("added_class"),  # type: ignore[union-attr]
                "version": promoted.get("version"),  # type: ignore[union-attr]
                "reclassify_probe": probe,
                "now_classifies": verified,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
