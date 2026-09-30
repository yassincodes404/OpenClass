"""Approve the persisted tablet candidate and verify the exact Jev replay."""

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from openclass_server.main import create_app
from openclass_server.settings import Settings
from pydantic import SecretStr

RUN = Path(os.environ["OPENCLASS_EXPERIMENT_RUN"])


def app_settings() -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{RUN / 'experiment.db'}",
        decision_provider="jev",
        jev_api_key=SecretStr(os.environ["OPENCLASS_JEV_API_KEY"]),
        provider_max_retries=1,
    )


def main() -> int:
    discovery = json.loads((RUN / "discovery.json").read_text())
    evaluation = json.loads((RUN / "evaluation.json").read_text())
    candidate_id = evaluation["candidate"]["id"]
    base = "/api/v1/classifiers/device-type"

    with TestClient(create_app(app_settings())) as client:
        versions_before = client.get(f"{base}/ontology/versions").json()
        before = next(
            version
            for version in versions_before
            if version["id"] == discovery["ontology_v1"]["id"]
        )
        v1_bytes_before = json.dumps(before, sort_keys=True, separators=(",", ":"))
        candidate_before = next(
            item for item in client.get(f"{base}/candidates").json() if item["id"] == candidate_id
        )
        if candidate_before["status"] == "approved":
            v2 = client.get(f"{base}/ontology").json()
        else:
            approved = client.post(f"{base}/candidates/{candidate_id}/approve")
            approved.raise_for_status()
            v2 = approved.json()
        replay = client.post(f"{base}/classify", json={"observation": "Samsung Galaxy Tab"})
        replay.raise_for_status()
        events = client.get(f"{base}/events").json()
        candidate_after = client.get(f"{base}/candidates").json()
        candidate = next(item for item in candidate_after if item["id"] == candidate_id)

    with TestClient(create_app(app_settings())) as client:
        after_restart = client.get(f"{base}/ontology").json()
        versions = client.get(f"{base}/ontology/versions").json()
        replay_after_restart = next(
            run
            for run in client.get(f"{base}/runs").json()
            if run["observation"]["content"] == "Samsung Galaxy Tab"
            and run["result"]["ontology_version_id"] == after_restart["id"]
        )

    v1_after = next(version for version in versions if version["id"] == before["id"])
    v1_bytes_after = json.dumps(v1_after, sort_keys=True, separators=(",", ":"))
    v1_immutable = v1_bytes_before == v1_bytes_after
    report = {
        "report_type": "self_expansion_complete",
        "before": {
            "ontology": before,
            "input": "Samsung Galaxy Tab",
            "historical_unknown": next(
                item["result"]
                for item in discovery["classifications"]
                if item["content"] == "Samsung Galaxy Tab"
            ),
        },
        "approval": {
            "candidate_id": candidate_id,
            "candidate": candidate,
            "evaluation_passed": candidate["evaluation_passed"],
            "approval_event_present": any(
                item["event"]["type"] == "candidate.approved"
                and item["event"]["payload"].get("candidate_id") == candidate_id
                for item in events
            ),
        },
        "after": {"ontology": v2, "replay": replay.json()},
        "restart": {
            "active_ontology": after_restart,
            "replay_persisted": replay_after_restart,
            "v1_byte_identical": v1_immutable,
        },
    }
    (RUN / "final.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "v1": before["id"],
                "v2": v2["id"],
                "replay_class": replay.json()["selected_class"],
                "replay_novelty": replay.json()["novelty"]["state"],
                "v1_byte_identical": v1_immutable,
                "restart_persisted": (
                    replay_after_restart["result"]["ontology_version_id"] == v2["id"]
                    and replay_after_restart["result"]["selected_class"] == "tablet"
                    and replay_after_restart["result"]["novelty"]["state"] == "known"
                ),
            },
            indent=2,
        )
    )
    print(f"Report: {RUN / 'final.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
