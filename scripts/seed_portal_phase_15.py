"""Seed Phase 15: UNKNOWN spike fixture + breached alert rule.

Backdates a slice of engine runs across 7 days (direct SQL on the local dev
database — simulated fixture, clearly labeled) and creates an unknown_rate
alert rule that the spike breaches.
"""

from __future__ import annotations

import json
import os
import subprocess
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
PG_CONTAINER = os.environ.get("OPENCCLASS_PG_CONTAINER", "openclass-portal-pg")
PG_DB = os.environ.get("OPENCCLASS_ENGINE_DB", "openclass_engine")


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


def backdate_spike(engine_project_id: str) -> bool:
    """Spread this project's runs over the past week with a late UNKNOWN spike."""
    # Postgres: spread known runs across the week, push UNKNOWN runs into the
    # last two days (the "spike" — older windows stay low).
    sql = f"""
    UPDATE decision_runs
    SET created_at = now() - (CASE WHEN selected_choice = 'UNKNOWN'
                                   THEN interval '2 days'
                                   ELSE interval '7 days' END) * random()
    WHERE project_id = '{engine_project_id}';
    """
    result = subprocess.run(
        ["docker", "exec", PG_CONTAINER, "psql", "-U", "openclass", "-d", PG_DB, "-c", sql],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


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

    status, rules = request(f"{root}/alerts/rules", "GET", token)
    if not any(r["metric"] == "unknown_rate" for r in rules):  # type: ignore[union-attr]
        status, body = request(
            f"{root}/alerts/rules", "POST", token, {"metric": "unknown_rate", "threshold": 0.10}
        )
        if status != 201:
            print(f"rule create failed ({status}): {body}", file=sys.stderr)
            return 1

    backdated = backdate_spike(project["engine_project_id"])  # type: ignore[index]
    # Fresh spike: a few UNKNOWN-classified runs right now so the 1h window has data.
    status, services = request(f"{root}/decision-services", "GET", token)
    intake = next((srv for srv in services if "intake" in srv["slug"]), None)  # type: ignore[union-attr]
    if intake is not None:
        for text in [
            "Weird new thing happened",
            "Something odd again",
            "Unhandled case right here",
        ]:
            request(
                f"{root}/decision-services/{intake['id']}/runs",  # type: ignore[index]
                "POST",
                token,
                {"content": text},
            )
    status, evaluated = request(f"{root}/alerts/evaluate", "POST", token)
    fired = evaluated.get("fired", 0) if isinstance(evaluated, dict) else 0  # type: ignore[union-attr]
    rate = None
    if isinstance(evaluated, dict):
        rate = evaluated.get("measurements", {}).get("unknown_rate")  # type: ignore[union-attr]

    print(
        json.dumps(
            {
                "simulated": True,
                "backdated_fixture_applied": backdated,
                "unknown_rate_1h": rate,
                "alerts_fired": fired,
                "note": "run timestamps spread over 7 days via local dev SQL (simulated spike)",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
