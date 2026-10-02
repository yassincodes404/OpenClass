"""Seed Phase 5 observations: 25 deterministic support texts.

Local-only, idempotent via fixed idempotency keys and content-hash dedup.
Requires the Phase 2–4 stack (Keycloak, control-plane, engine) running.
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

TEXTS = [
    "I was charged twice this month",
    "Why was my card billed again?",
    "Double charge on my latest invoice",
    "You charged my credit card two times",
    "Refund my last order please",
    "I want a refund for the broken item",
    "How do I get my money back?",
    "My package has not arrived",
    "Delivery is late by two weeks",
    "Where is my order? It never came",
    "The courier lost my shipment",
    "Cancel my subscription immediately",
    "How do I cancel this plan?",
    "Please close my subscription account",
    "I want to end my membership",
    "Terminate my recurring plan",
    "How do I cancel my subscription online?",
    "I cannot log in to my account",
    "Password reset email never arrives",
    "Login fails with error 403",
    "Someone changed my account email without permission",
    "I got logged out and my password no longer works",
    "My account shows another person's name",
    "There is weird activity in my account that I did not do",
    "An unknown device accessed my dashboard yesterday",
]


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
    if workspace is None:
        print("run seed:portal-phase-3 first", file=sys.stderr)
        return 1
    status, projects = request(
        f"{CONTROL_PLANE}/control/workspaces/{workspace['id']}/projects",
        "GET",
        token,  # type: ignore[index]
    )
    project = next((p for p in projects if p["slug"] == "acme-support"), None)  # type: ignore[union-attr]
    if project is None:
        print("run seed:portal-phase-3 first", file=sys.stderr)
        return 1

    base = f"{CONTROL_PLANE}/control/workspaces/{workspace['id']}/projects/{project['id']}/events"  # type: ignore[index]
    created = deduped = 0
    for index, text in enumerate(TEXTS):
        status, body = request(
            base,
            "POST",
            token,
            {"content": text, "source_type": "text"},
            {"Idempotency-Key": f"seed-phase-05-{index}"},
        )
        if status in (200, 201) and isinstance(body, dict):
            if body.get("deduped"):
                deduped += 1
            else:
                created += 1
        else:
            print(f"ingest failed ({status}): {body}", file=sys.stderr)
            return 1

    print(
        json.dumps(
            {"simulated": True, "ingested": created, "deduped": deduped, "total_texts": len(TEXTS)},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
