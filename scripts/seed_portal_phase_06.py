"""Seed Phase 6: decision service + 15 runs (10 known, 5 UNKNOWN).

Local-only, idempotent. Requires the Phase 2–5 stack running. Mock provider
output is simulated (clearly labeled).
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

CHOICES = [
    {"key": "BILLING", "label": "Billing"},
    {"key": "REFUND", "label": "Refund"},
    {"key": "DELIVERY", "label": "Delivery"},
    {"key": "CANCEL_SUBSCRIPTION", "label": "Cancel subscription"},
    {"key": "ACCOUNT_ACCESS", "label": "Account access"},
]

# Mock provider matching is lexical (canonical names as whole words), so the
# known texts deliberately contain the intent words.
KNOWN_TEXTS = [
    "I have a billing question about my last invoice",
    "My billing statement looks wrong this month",
    "I need a refund for the damaged product",
    "When will my refund arrive on my card?",
    "The delivery is three days late",
    "My delivery tracking has not updated",
    "Please help me cancel subscription payments",
    "How do I cancel subscription renewal?",
    "I lost account access after the update",
    "Account access fails on my phone but works on desktop",
]

UNKNOWN_TEXTS = [
    "Someone changed my account email without permission",
    "I got logged out and my password no longer works",
    "My account shows another person's name",
    "There is weird activity in my account that I did not do",
    "An unknown device accessed my dashboard yesterday",
]


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
    base = f"{CONTROL_PLANE}/control/workspaces/{workspace['id']}/projects/{project['id']}"  # type: ignore[index]

    status, services = request(f"{base}/decision-services", "GET", token)
    service = next((s for s in services if s["slug"] == "support-router"), None)  # type: ignore[union-attr]
    if service is None:
        status, service = request(
            f"{base}/decision-services",
            "POST",
            token,
            {
                "name": "Support router",
                "instructions": "Route each customer message to the best-fitting intent.",
                "choices": CHOICES,
            },
        )
        if status != 201:
            print(f"service create failed ({status}): {service}", file=sys.stderr)
            return 1

    known = unknown = 0
    for text in KNOWN_TEXTS + UNKNOWN_TEXTS:
        status, runs = request(
            f"{base}/decision-services/{service['id']}/runs",  # type: ignore[index]
            "POST",
            token,
            {"content": text},
        )
        if status != 201 or not runs:
            print(f"run failed ({status}): {runs}", file=sys.stderr)
            return 1
        if runs[0]["selected_choice"] == "UNKNOWN" or runs[0]["supervision_outcome"] == "UNKNOWN":
            unknown += 1
        else:
            known += 1

    print(
        json.dumps(
            {
                "simulated": True,
                "provider": "mock (simulated)",
                "service": service["slug"],  # type: ignore[index]
                "known_runs": known,
                "unknown_runs": unknown,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
