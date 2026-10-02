"""Seed deterministic, simulated Phase 1 portal data through the public HTTP API.

Usage: OPENCLASS_SERVER_URL=http://127.0.0.1:7331 uv run python scripts/seed_phase_01.py
"""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SERVER_URL = os.getenv("OPENCLASS_SERVER_URL", "http://127.0.0.1:7331").rstrip("/")
PROJECT = {
    "name": "Acme Support — Phase 1 demo",
    "description": "Simulated local project for portal navigation and project-route testing.",
}


def request(path: str, payload: dict[str, str] | None = None) -> object:
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(
        f"{SERVER_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"} if body else {},
        method="GET" if body is None else "POST",
    )
    with urlopen(req, timeout=10) as response:  # noqa: S310 -- local/operator-selected endpoint
        return json.loads(response.read())


def main() -> int:
    try:
        projects = request("/api/v1/projects")
        assert isinstance(projects, list)
        existing = next(
            (project for project in projects if project.get("name") == PROJECT["name"]), None
        )
        project = existing or request("/api/v1/projects", PROJECT)
        assert isinstance(project, dict)
    except (HTTPError, URLError, TimeoutError, AssertionError, json.JSONDecodeError) as exc:
        print(f"Phase 1 seed failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "ready",
                "seed": "phase-01",
                "simulated": True,
                "project": {"name": project["name"], "slug": project["slug"]},
                "login_required": False,
                "routes": ["/", "/projects", f"/projects/{project['slug']}"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
