"""Bounded real Jev calls through OpenClass HTTP routes, services and migrated storage.

Run with uv run --env-file .env python scripts/jev_pilot.py --smoke.
Labels are read locally and never sent to the provider or written into run metadata.
"""

import argparse
import csv
import hashlib
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from openclass_server.main import create_app
from openclass_server.settings import Settings


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    return values[low] + (values[high] - values[low]) * (index - low)


def summarize(rows: list[dict], labels: dict[str, str] | None) -> dict:
    successful = [row for row in rows if "result" in row]
    decisions = [row["result"]["decision"] for row in successful]
    summary = {
        "attempted": len(rows),
        "completed": len(successful),
        "failed": len(rows) - len(successful),
        "models": sorted({d["model"] for d in decisions}),
        "latency_ms_p50": percentile([d["latency_ms"] for d in decisions], 0.5),
        "latency_ms_p95": percentile([d["latency_ms"] for d in decisions], 0.95),
    }
    for field in ("input_tokens", "output_tokens", "estimated_cost"):
        values = [d[field] for d in decisions]
        summary[field] = sum(values) if values and all(v is not None for v in values) else None
        summary[f"{field}_reported_calls"] = sum(v is not None for v in values)
        summary[f"average_{field}_per_completed_call"] = (
            sum(values) / len(values) if values and all(v is not None for v in values) else None
        )
    if labels is not None:
        known = [r for r in rows if labels[r["id"]] != "UNKNOWN"]
        unknown = [r for r in rows if labels[r["id"]] == "UNKNOWN"]
        correct = sum(r.get("result", {}).get("selected_class") == labels[r["id"]] for r in known)
        summary.update(
            {
                "known_examples_attempted": len(known),
                "known_correct": correct,
                "known_accuracy": correct / len(known) if known else None,
                "unknown_examples_attempted": len(unknown),
                "correct_unknown_detections": sum(
                    "result" in r and r["result"]["selected_class"] is None for r in unknown
                ),
                "forced_known_errors": sum(
                    "result" in r and r["result"]["selected_class"] is not None for r in unknown
                ),
                "false_unknowns": sum(
                    "result" in r and r["result"]["selected_class"] is None for r in known
                ),
                "confident_mistakes": [
                    r["id"]
                    for r in successful
                    if (r["result"]["selected_class"] or "UNKNOWN") != labels[r["id"]]
                    and max(
                        [
                            *r["result"]["decision"]["probabilities"].values(),
                            r["result"]["decision"]["unknown_probability"],
                        ]
                    )
                    >= 0.8
                ],
                "confident_mistake_threshold": 0.8,
            }
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="One call; no accuracy claims")
    parser.add_argument(
        "--allow-proposed-labels",
        action="store_true",
        help="Run with labels marked proposed; results are diagnostic, not benchmark evidence",
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Record provider failures and continue through the frozen dataset",
    )
    parser.add_argument(
        "--labels", type=Path, default=Path("examples/jev-pilot/labels.proposed.json")
    )
    parser.add_argument("--output", type=Path, default=Path("build/jev-pilot"))
    args = parser.parse_args()
    if os.getenv("OPENCLASS_RUN_LIVE_TESTS") != "1":
        parser.error("Set OPENCLASS_RUN_LIVE_TESTS=1 to opt in to real inference")
    labels_document = {} if args.smoke else json.loads(args.labels.read_text())
    if (
        not args.smoke
        and not args.allow_proposed_labels
        and (
            labels_document.get("status") != "human_reviewed"
            or not labels_document.get("reviewed_by")
        )
    ):
        parser.error(
            "Experiment requires independently human-reviewed labels with reviewed_by provenance"
        )
    dataset_path = Path("examples/jev-pilot/observations.csv")
    with dataset_path.open(newline="") as source:
        rows = list(csv.DictReader(source))
    if args.smoke:
        rows = rows[:1]
    if not 1 <= len(rows) <= 50 or len({r["id"] for r in rows}) != len(rows):
        parser.error("Dataset must contain 1–50 distinct examples")
    labels = None if args.smoke else labels_document["labels"]
    if labels is not None and (
        set(labels) != {r["id"] for r in rows}
        or not set(labels.values()) <= {"phone", "laptop", "UNKNOWN"}
    ):
        parser.error("Labels must exactly match dataset IDs and the pilot label space")
    # Validate provider settings before creating a database or making a call.
    config = Settings(decision_provider="jev", supervisor_provider="mock", provider_max_retries=0)
    output = args.output.resolve() / (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    )
    output.mkdir(parents=True)
    database_url = f"sqlite+aiosqlite:///{output / 'pilot.db'}"
    os.environ["OPENCLASS_DATABASE_URL"] = database_url
    command.upgrade(Config("alembic.ini"), "head")
    config = config.model_copy(update={"database_url": database_url})
    classifier = json.loads(Path("examples/jev-pilot/classifier.json").read_text())
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "mode": "smoke" if args.smoke else "pilot",
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "labels_sha256": None
        if args.smoke
        else hashlib.sha256(args.labels.read_bytes()).hexdigest(),
        "label_provenance": None if args.smoke else labels_document,
        "requested_model": config.jev_model,
        "provider_base_url": config.jev_base_url,
        "novelty_policy": config.novelty.model_dump(),
        "call_limit": len(rows),
        "max_retries": 0,
        "cost_stop_threshold_usd": 0.10,
        "qualification": (
            "Diagnostic pilot, not a general benchmark. "
            "Cost stop applies only to reported cost after each call."
        ),
        "rows": [],
    }
    with TestClient(create_app(config)) as client:
        created = client.post("/api/v1/classifiers", json=classifier)
        if created.status_code != 201:
            raise RuntimeError("Pilot classifier creation failed")
        base = f"/api/v1/classifiers/{created.json()['id']}"
        ontology_before = client.get(f"{base}/ontology/versions").content
        report["ontology"] = client.get(f"{base}/ontology").json()
        for row in rows:
            response = client.post(f"{base}/classify", json={"observation": row["observation"]})
            recorded = {**row, "http_status": response.status_code}
            if response.status_code == 200:
                result = response.json()
                persisted = client.get(f"{base}/runs/{result['id']}").json()
                if persisted["result"] != result:
                    raise RuntimeError("Persistence verification failed")
                recorded["result"] = result
            report["rows"].append(recorded)
            report["summary"] = summarize(report["rows"], labels)
            (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(f"{row['id']}: HTTP {response.status_code}", flush=True)
            if response.status_code != 200 and not args.continue_on_failure:
                break
            if (
                sum(
                    r["result"]["decision"]["estimated_cost"] or 0
                    for r in report["rows"]
                    if "result" in r
                )
                >= 0.10
            ):
                break
        if client.get(f"{base}/ontology/versions").content != ontology_before:
            raise RuntimeError("Ontology changed during inference")
        report["unknown_count"] = len(client.get(f"{base}/unknowns").json())
        report["events"] = client.get(f"{base}/events?limit=200").json()
    # Restart the actual app and prove history remains accessible.
    with TestClient(create_app(config)) as client:
        if len(client.get(f"{base}/runs?limit=200").json()) != report["summary"]["completed"]:
            raise RuntimeError("Restart persistence verification failed")
    report["finished_at"] = datetime.now(UTC).isoformat()
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report: {output / 'report.json'}")
    return 0 if len(report["rows"]) == len(rows) and report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
