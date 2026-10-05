"""Seed Phase 8: 30 UNKNOWN runs (15 cancel variants, 8 account-compromise,
7 ambiguous) via an intake service whose ontology lacks those intents;
2 triaged and assigned to the reviewer.

Local-only, idempotent (content dedup).
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

CANCEL_TEXTS = [
    "Cancel my plan immediately",
    "How do I cancel this plan?",
    "Please close my subscription account",
    "I want to end my membership",
    "Terminate my recurring plan",
    "How do I cancel my subscription online?",
    "Stop charging me, cancel everything",
    "I need to unsubscribe from the service",
    "Please shut down my account for good",
    "Cancel the auto-renewal on my plan",
    "I want out of my current subscription",
    "End my service at the end of the cycle",
    "Remove me from the plan I signed up for",
    "Cancel it now please",
    "How to quit this subscription thing",
]

ACCOUNT_TEXTS = [
    "Someone changed my account email without permission",
    "I got logged out and my password no longer works",
    "My account shows another person's name",
    "There is weird activity in my account that I did not do",
    "An unknown device accessed my dashboard yesterday",
    "I think my account got hijacked",
    "Two-factor codes arrive but I did not request them",
    "My recovery phone number was changed overnight",
]

AMBIGUOUS_TEXTS = [
    "It does not work",
    "Something is wrong with the thing",
    "Help me with the issue I mentioned before",
    "The page is broken on my side",
    "Nothing happens when I press the button",
    "Error appears sometimes and then goes away",
    "Is this the right place to ask about that?",
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
    service = next((s for s in services if s["slug"] == "intake-router"), None)  # type: ignore[union-attr]
    if service is None:
        # Intake ontology deliberately lacks cancel/account intents so those
        # texts land in the UNKNOWN pool (mock provider, lexical, simulated).
        status, service = request(
            f"{base}/decision-services",
            "POST",
            token,
            {
                "name": "Intake router",
                "instructions": "First-pass routing for incoming requests.",
                "choices": [
                    {"key": "BILLING", "label": "Billing"},
                    {"key": "REFUND", "label": "Refund"},
                    {"key": "DELIVERY", "label": "Delivery"},
                ],
            },
        )
        if status != 201:
            print(f"service create failed ({status}): {service}", file=sys.stderr)
            return 1

    unknown_ids: list[str] = []
    for text in CANCEL_TEXTS + ACCOUNT_TEXTS + AMBIGUOUS_TEXTS:
        status, runs = request(
            f"{base}/decision-services/{service['id']}/runs",  # type: ignore[index]
            "POST",
            token,
            {"content": text},
        )
        if status != 201 or not runs:
            print(f"run failed ({status}): {runs}", file=sys.stderr)
            return 1
        run = runs[0]
        if run["selected_choice"] == "UNKNOWN" or run["supervision_outcome"] == "UNKNOWN":
            unknown_ids.append(run["id"])

    # Triage two of the cancel unknowns as missing_info, assigned to reviewer.
    triaged = 0
    for run_id in unknown_ids[:2]:
        status, _body = request(
            f"{base}/unknowns/{run_id}/triage",
            "POST",
            token,
            {"category": "missing_info", "assignee": "reviewer@acme.openclass.test"},
        )
        if status == 200:
            triaged += 1

    print(
        json.dumps(
            {
                "simulated": True,
                "unknown_pool": len(unknown_ids),
                "expected_pool": 30,
                "triaged_assigned": triaged,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
