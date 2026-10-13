"""Seed Phase 13: one passing evaluation (cancel improves, billing holds) and
one blocked evaluation (false-novelty gate fails on a hard gold set).

Local-only. Deterministic mock replay (simulated).
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


def add_examples(token: str, base: str, dataset_id: str, rows: list[tuple[str, str]]) -> None:
    for text, label in rows:
        status, body = request(
            f"{base}/{dataset_id}/examples",
            "POST",
            token,
            {
                "text": text,
                "label": label,
                "source": "human",
                "annotator": "owner@acme.openclass.test",
                "rationale": "seed fixture",
            },
        )
        if status != 201:
            print(f"example failed ({status}): {body}", file=sys.stderr)
            sys.exit(1)


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
    base = f"{root}/eval-datasets"

    # The approved NEW_CLASS candidate from phase 11 (status approved).
    status, candidates = request(f"{root}/unknowns/candidates", "GET", token)
    candidate = next((c for c in candidates if c["type"] == "NEW_CLASS"), None)  # type: ignore[union-attr]
    if candidate is None:
        print("run seed:portal-phase-10/11 first (no NEW_CLASS candidate)", file=sys.stderr)
        return 1
    candidate_id = candidate["id"]  # type: ignore[index]
    status, detail = request(f"{root}/unknowns/candidates/{candidate_id}", "GET", token)
    label = str(detail["canonical_name"]).upper()  # type: ignore[index]

    # 1) Passing gold set: cancel improves, billing/refund hold.
    status, datasets = request(base, "GET", token)
    if not any(d["name"] == "cancel-gold-v1" for d in datasets):  # type: ignore[union-attr]
        status, dataset = request(
            base,
            "POST",
            token,
            {"name": "cancel-gold-v1", "description": "Cancel intent gold (simulated)"},
        )
        dataset_id = dataset["id"]  # type: ignore[index]
        add_examples(
            token,
            base,
            dataset_id,
            [
                ("Cancel my plan immediately", label),
                ("Cancel my plan today please", label),
                ("Cancel my plan once and for all", label),
                ("Cancel my subscription plan now", label),
                ("Cancel plan next month", label),
                ("Cancel the plan after this cycle", label),
                ("I have a billing question", "BILLING"),
                ("Billing statement looks wrong", "BILLING"),
                ("Refund my last order", "REFUND"),
                ("How do I get my money back refund", "REFUND"),
            ],
        )
        request(f"{base}/{dataset_id}/seal", "POST", token)
    else:
        dataset_id = next(d for d in datasets if d["name"] == "cancel-gold-v1")["id"]  # type: ignore[index]
    status, passing = request(
        f"{root}/evaluations",
        "POST",
        token,
        {"dataset_id": dataset_id, "candidate_id": candidate_id},
    )
    if status != 201:
        print(f"passing eval failed ({status}): {passing}", file=sys.stderr)
        return 1

    # 2) Blocked gold set: hard examples the lexical matcher cannot resolve —
    #    false novelty on baseline labels fails the gate honestly.
    status, datasets = request(base, "GET", token)
    if not any(d["name"] == "hard-gold-v1" for d in datasets):  # type: ignore[union-attr]
        status, dataset = request(
            base,
            "POST",
            token,
            {"name": "hard-gold-v1", "description": "Hard negatives (simulated)"},
        )
        hard_id = dataset["id"]  # type: ignore[index]
        add_examples(
            token,
            base,
            hard_id,
            [
                ("Charged twice on my statement", "BILLING"),
                ("Card statement shows an old charge", "BILLING"),
                ("Money went out twice last week", "BILLING"),
                ("Send my money back for the broken item", "REFUND"),
                ("Item arrived damaged, want compensation", "REFUND"),
            ],
        )
        request(f"{base}/{hard_id}/seal", "POST", token)
    else:
        hard_id = next(d for d in datasets if d["name"] == "hard-gold-v1")["id"]  # type: ignore[index]
    status, blocked = request(
        f"{root}/evaluations", "POST", token, {"dataset_id": hard_id, "candidate_id": candidate_id}
    )
    if status != 201:
        print(f"blocked eval failed ({status}): {blocked}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "simulated": True,
                "passing_evaluation": {
                    "id": passing["id"],
                    "overall_passed": passing["overall_passed"],
                },  # type: ignore[index]
                "blocked_evaluation": {
                    "id": blocked["id"],
                    "overall_passed": blocked["overall_passed"],
                },  # type: ignore[index]
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
