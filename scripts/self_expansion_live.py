"""Run one durable Jev -> UNKNOWN -> Qwen discovery experiment.

The run stops after candidate creation. It never approves or mutates the ontology.
Credentials are environment-only and never enter the report.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from openclass_server.main import create_app
from openclass_server.settings import Settings
from pydantic import SecretStr


def main() -> int:
    jev_key = os.environ["OPENCLASS_JEV_API_KEY"]
    gateway_key = os.environ["AI_GATEWAY_API_KEY"]
    run = Path("build/self-expansion") / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run.mkdir(parents=True, exist_ok=False)
    database_url = f"sqlite+aiosqlite:///{run / 'experiment.db'}"
    os.environ["OPENCLASS_DATABASE_URL"] = database_url
    command.upgrade(Config("alembic.ini"), "head")
    discovery_model = os.getenv("OPENCLASS_DISCOVERY_MODEL", "alibaba/qwen-3-32b")
    settings = Settings(
        database_url=database_url,
        decision_provider="jev",
        jev_api_key=SecretStr(jev_key),
        discovery_provider="openai-compatible",
        discovery_api_key=SecretStr(gateway_key),
        discovery_base_url="https://ai-gateway.vercel.sh/v1",
        discovery_model=discovery_model,
        provider_max_retries=0,
    )
    report: dict[str, Any] = {
        "experiment": "new_durable_self_expansion_run",
        "started_at": datetime.now(UTC).isoformat(),
        "decision_provider": {"provider": "jev", "model": settings.jev_model},
        "discovery_provider": {
            "provider": "openai-compatible",
            "base_url": settings.discovery_base_url,
            "model": settings.discovery_model,
        },
        "ontology_v1": None,
        "classifications": [],
        "unknowns": [],
        "discovery": None,
        "candidate": None,
    }
    classifier = {
        "slug": "device-type",
        "name": "Device type",
        "classes": [
            {"canonical_name": "phone", "display_name": "Phone"},
            {"canonical_name": "laptop", "display_name": "Laptop"},
        ],
    }
    observations = [
        "Samsung Galaxy Tab",
        "iPad Pro",
        "Google Pixel Tablet",
        "Android tablet with 11-inch touchscreen",
        "Lenovo Tab P12",
    ]
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/v1/classifiers", json=classifier)
        created.raise_for_status()
        identifier = created.json()["slug"]
        base = f"/api/v1/classifiers/{identifier}"
        ontology = client.get(f"{base}/ontology")
        ontology.raise_for_status()
        report["ontology_v1"] = ontology.json()
        for content in observations:
            response = client.post(f"{base}/classify", json={"observation": content})
            item = {"content": content, "http_status": response.status_code}
            if response.status_code == 200:
                item["result"] = response.json()
            report["classifications"].append(item)
        unknowns = client.get(f"{base}/unknowns")
        unknowns.raise_for_status()
        report["unknowns"] = unknowns.json()
        if len(report["unknowns"]) < 3:
            report["error"] = "Fewer than three genuine UNKNOWN observations were persisted."
            (run / "discovery.json").write_text(json.dumps(report, indent=2) + "\n")
            return 2
        discovery = client.post(
            f"{base}/discoveries",
            json={"unknown_ids": [item["id"] for item in report["unknowns"]]},
        )
        if discovery.status_code != 201:
            report["error"] = {"http_status": discovery.status_code, "detail": discovery.json()}
            (run / "discovery.json").write_text(json.dumps(report, indent=2) + "\n")
            return 3
        candidate = discovery.json()
        report["candidate"] = candidate
        report["discovery"] = {
            "proposal_type": candidate["proposal_type"],
            "canonical_name": candidate["canonical_name"],
            "display_name": candidate["display_name"],
            "description": candidate["description"],
            "confidence": candidate["confidence"],
            "rationale": candidate["rationale"],
            "discovery_provider": candidate["discovery_provider"],
            "discovery_model": candidate["discovery_model"],
        }
        report["active_ontology_after_discovery"] = client.get(f"{base}/ontology").json()
        report["finished_at"] = datetime.now(UTC).isoformat()
        (run / "discovery.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report["discovery"], indent=2))
        print(f"Report: {run / 'discovery.json'}")
        print(f"Database: {run / 'experiment.db'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
