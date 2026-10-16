"""Simulated HTTP smoke for the no-key base or authenticated workspace engine."""

import json
import os
from pathlib import Path
from uuid import uuid4

import httpx


def main() -> None:
    token = os.environ.get("OPENCLASS_INTERNAL_TOKEN", "")
    classifier = json.loads(Path("examples/support-intents/classifier.json").read_text())
    classifier["slug"] = f"support-http-smoke-{uuid4().hex[:8]}"
    with httpx.Client(
        base_url=os.environ.get("OPENCLASS_SMOKE_BASE_URL", "http://127.0.0.1:7331"),
        headers={"X-OpenClass-Internal-Token": token} if token else {},
        timeout=20,
    ) as client:
        created = client.post(
            "/api/v1/classifiers",
            json=classifier,
        )
        assert created.status_code == 201, created.status_code
        response = client.post(
            f"/api/v1/classifiers/{classifier['slug']}/classify",
            json={"observation": "Cancel my plan"},
        )
        assert response.status_code == 200, response.status_code
        mode = "internal-token" if token else "local-anonymous"
        print(f"HTTP classification persisted ({mode}; simulated mock inference).")


if __name__ == "__main__":
    main()
