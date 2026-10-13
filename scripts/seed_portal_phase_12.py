"""Seed Phase 12: support-gold-v1 — 40 verified examples with slice coverage.

30 known (incl. rare/hard) + 10 UNKNOWN/adversarial, all source=human.
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

KNOWN: list[tuple[str, str, str]] = [
    # (text, label, slice)
    ("I have a billing question about my last invoice", "BILLING", "historical"),
    ("My billing statement looks wrong this month", "BILLING", "recent"),
    ("Why was my card billed twice?", "BILLING", "historical"),
    ("Charge appears without a receipt", "BILLING", "rare"),
    ("Invoice shows a phantom line item dated last year", "BILLING", "hard"),
    ("Refund my last order please", "REFUND", "historical"),
    ("How do I get my money back?", "REFUND", "recent"),
    ("The refund amount is less than what I paid", "REFUND", "hard"),
    ("Partial refund for a two-item shipment", "REFUND", "rare"),
    ("When will my refund arrive on my card?", "REFUND", "recent"),
    ("My delivery is three days late", "DELIVERY", "recent"),
    ("Where is my order? It never came", "DELIVERY", "historical"),
    ("The courier lost my shipment", "DELIVERY", "historical"),
    ("Delivery to the wrong address twice", "DELIVERY", "rare"),
    ("The package arrived opened and resealed", "DELIVERY", "hard"),
    ("I have a billing question about the annual plan", "BILLING", "historical"),
    ("Refund for the annual charge please", "REFUND", "rare"),
    ("My delivery tracking has not updated in a week", "DELIVERY", "recent"),
    ("Billing cycle changed without notice", "BILLING", "hard"),
    ("Refund policy question for damaged goods", "REFUND", "hard"),
    ("Delivery window missed three times", "DELIVERY", "hard"),
    ("Billing address update did not stick", "BILLING", "rare"),
    ("Refund promised but never processed", "REFUND", "hard"),
    ("Delivery to a pickup point failed", "DELIVERY", "rare"),
    ("Double billing on two cards", "BILLING", "hard"),
    ("Refund for a cancelled subscription month", "REFUND", "rare"),
    ("Delivery signature was forged", "DELIVERY", "hard"),
    ("Billing in the wrong currency", "BILLING", "rare"),
    ("Refund escalated from last month", "REFUND", "historical"),
    ("Delivery rescheduled four times", "DELIVERY", "recent"),
]

UNKNOWN: list[tuple[str, str, str]] = [
    ("Someone changed my account email without permission", "UNKNOWN", "unknown"),
    ("My account shows another person's name", "UNKNOWN", "unknown"),
    ("Two-factor codes arrive but I did not request them", "UNKNOWN", "unknown"),
    ("The page is broken on my side", "UNKNOWN", "adversarial"),
    ("It does not work", "UNKNOWN", "adversarial"),
    ("Nothing happens when I press the button", "UNKNOWN", "adversarial"),
    ("Is this the right place to ask about that?", "UNKNOWN", "adversarial"),
    ("Error appears sometimes and then goes away", "UNKNOWN", "adversarial"),
    ("Something is wrong with the thing", "UNKNOWN", "adversarial"),
    ("Help me with the issue I mentioned before", "UNKNOWN", "adversarial"),
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
    base = (  # type: ignore[index]
        f"{CONTROL_PLANE}/control/workspaces/{workspace['id']}"
        f"/projects/{project['id']}/eval-datasets"
    )

    status, datasets = request(base, "GET", token)
    existing = next((d for d in datasets if d["name"] == "support-gold-v1"), None)  # type: ignore[union-attr]
    if existing is None:
        status, dataset = request(
            base,
            "POST",
            token,
            {
                "name": "support-gold-v1",
                "description": "Human-verified gold set (simulated dev data)",
            },
        )
        if status != 201:
            print(f"dataset create failed ({status}): {dataset}", file=sys.stderr)
            return 1
        dataset_id = dataset["id"]  # type: ignore[index]
        added = 0
        for text, label, slice_tag in KNOWN + UNKNOWN:
            status, _body = request(
                f"{base}/{dataset_id}/examples",
                "POST",
                token,
                {
                    "text": text,
                    "label": label,
                    "source": "human",
                    "annotator": "owner@acme.openclass.test",
                    "rationale": "verified from support history",
                    "slice_tag": slice_tag,
                },
            )
            if status == 201:
                added += 1
            else:
                print(f"example failed ({status}): {_body}", file=sys.stderr)
                return 1
    else:
        dataset_id = existing["id"]  # type: ignore[index]
        added = existing.get("size", 0)  # type: ignore[index]

    print(
        json.dumps(
            {
                "simulated": True,
                "dataset": "support-gold-v1",
                "examples": added,
                "all_sources": "human",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
