"""Loopback-only public HTTP experiment runner. Never imports model/backend code."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx

from .dataset import (
    CONFIGS,
    LABELS,
    POLICY,
    ExperimentError,
    canonical,
    digest,
    file_hash,
    load_dataset,
    prepare,
    save_new,
)
from .metrics import grouped
from .verify import checkpoint_identity, read_json, validate_proof, verify_result

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = ROOT / "artifacts/laya-live-experiments/dataset"
DEFAULT_RUNS = ROOT / "artifacts/laya-live-experiments/runs"
RUN_FIELDS = (
    "id",
    "project_id",
    "raw_event_id",
    "decision_service_id",
    "decision_node_id",
    "decision_service_version_id",
    "service_hash",
    "provider",
    "model",
    "execution_mode",
    "real_inference",
    "selected_choice",
    "probabilities",
    "top_probability",
    "second_probability",
    "margin",
    "unknown_probability",
    "supervision_outcome",
    "supervision_reason",
    "latency_ms",
    "instructions_snapshot",
    "choices_snapshot",
    "run_status",
    "pinned_version_id",
    "pinned_version_number",
    "pinned_service_hash",
)
EVIDENCE_FIELDS = (
    "id",
    "project_id",
    "raw_event_id",
    "decision_run_id",
    "decision_service_id",
    "trigger_type",
    "status",
    "selected_choice",
    "probabilities_snapshot",
    "unknown_probability",
    "margin",
    "supervision_outcome",
    "provider",
    "model",
    "execution_mode",
)


def loopback_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.port is None
    ):
        raise ExperimentError("explicit HTTP loopback IP and port required")
    return value.rstrip("/")


def safe_id(value: Any) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ExperimentError("invalid public resource UUID") from exc


class LocalAPI:
    """Bounded httpx instead of SDK: disable environment proxies explicitly.

    The SDK's constructor does not expose trust_env; we additionally require
    controlled errors without server bodies and a strict route allowlist.
    """

    def __init__(
        self, base_url: str, *, owned_target: bool, transport: httpx.BaseTransport | None = None
    ) -> None:
        if not owned_target:
            raise ExperimentError("owned disposable target acknowledgement required")
        headers = {}
        token = os.environ.get("LAYA_EXPERIMENT_INTERNAL_TOKEN")
        if token:
            headers["X-OpenClass-Internal-Token"] = token
        self.client = httpx.Client(
            base_url=loopback_url(base_url),
            headers=headers,
            timeout=180,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        # All callers build paths from validated UUIDs, never observations/URLs.
        resource = r"[0-9a-f-]{36}"
        route = (
            rf"/api/v1/projects(?:/{resource}"
            rf"(?:/decision-services(?:/{resource}/runs)?|/events(?:/{resource})?"
            rf"|/runs/{resource}|/evidence(?:/{resource})?)?)?"
        )
        if method not in {"GET", "POST"} or not re.fullmatch(
            route + r"(?:\?limit=100&offset=[0-9]+)?", path
        ):
            raise ExperimentError("HTTP route outside experiment scope")
        try:
            response = self.client.request(method, path, json=body)
        except httpx.HTTPError as exc:
            raise ExperimentError("http_transport_failure") from exc
        if not 200 <= response.status_code < 300:
            raise ExperimentError(f"http_status_{response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise ExperimentError("http_invalid_json") from exc


def source_identity() -> dict[str, Any]:
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    names = ("__init__.py", "dataset.py", "metrics.py", "runner.py", "verify.py")
    return {
        "commit": commit,
        "files": {name: file_hash(Path(__file__).with_name(name)) for name in names},
    }


def packages() -> dict[str, str]:
    return {
        str(d.metadata["Name"]): d.version
        for d in importlib.metadata.distributions()
        if d.metadata["Name"]
    }


def validate_run(
    run: dict[str, Any], *, project: str, service: str, event: str, model: str, instructions: str
) -> None:
    if (
        run.get("project_id") != project
        or run.get("decision_service_id") != service
        or run.get("raw_event_id") != event
        or run.get("provider") != "laya"
        or run.get("model") != model
        or run.get("real_inference") is not True
        or run.get("execution_mode") not in {"daemon", "api", "in_process"}
        or run.get("run_status") not in {"completed", "paused"}
        or run.get("instructions_snapshot") != instructions
        or run.get("selected_choice") not in LABELS
        or run.get("supervision_outcome") not in {"TRUSTED", "REVIEW", "UNKNOWN"}
    ):
        raise ExperimentError("run_identity_or_execution_contract_mismatch")
    probabilities = run.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != set(LABELS):
        raise ExperimentError("run_distribution_contract_mismatch")
    if (
        any(
            type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1
            for p in probabilities.values()
        )
        or not math.isclose(sum(probabilities.values()), 1, abs_tol=1e-5)
        or not math.isclose(
            run.get("unknown_probability", -1), probabilities["UNKNOWN"], abs_tol=1e-5
        )
    ):
        raise ExperimentError("run_distribution_contract_mismatch")
    winner = max(probabilities, key=lambda key: (probabilities[key], key == "UNKNOWN", key))
    if run["selected_choice"] != winner:
        raise ExperimentError("run_selected_choice_distribution_mismatch")
    snapshot = run.get("choices_snapshot")
    if not isinstance(snapshot, list) or {c.get("key") for c in snapshot} != set(LABELS):
        raise ExperimentError("run_choices_snapshot_mismatch")
    for choice in snapshot:
        if choice["key"] != "UNKNOWN" and (
            choice.get("label") != choice["key"]
            or choice.get("description") != POLICY[choice["key"]]
        ):
            raise ExperimentError("run_choices_snapshot_mismatch")
    markers = json.dumps(run.get("provider_metadata", {})).casefold()
    if any(
        word in markers
        for word in (
            "deterministic_test_fallback",
            '"simulated": true',
            '"mock"',
            '"fallback": true',
        )
    ):
        raise ExperimentError("simulated_or_fallback_marker")


def execute_case(
    api: LocalAPI,
    case: dict[str, Any],
    *,
    project: str,
    service: str,
    model: str,
    instructions: str,
    checkpoint: str,
    warm: bool,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        **{k: case[k] for k in ("id", "language", "split", "category", "expected")},
        "case_sha256": case["sha256"],
        "checkpoint": checkpoint,
        "predicted": None,
        "trusted": None,
        "error": None,
        "api_elapsed_ms": None,
        "warm": warm,
        "persisted_verified": False,
    }
    prefix = f"/api/v1/projects/{project}"
    start: float | None = None
    try:
        event = api.request(
            "POST",
            prefix + "/events",
            {
                "content": case["text"],
                "source_type": "text",
                "metadata": {
                    "synthetic_experiment": True,
                    "case_id": case["id"],
                    "case_sha256": case["sha256"],
                },
            },
        )
        event_id = safe_id(event["id"])
        row["raw_event_id"] = event_id
        persisted_event = api.request("GET", prefix + f"/events/{event_id}")
        if (
            persisted_event.get("content") != case["text"]
            or persisted_event.get("id") != event_id
            or persisted_event.get("project_id") != project
            or persisted_event.get("content_hash")
            != hashlib.sha256(case["text"].strip().encode()).hexdigest()
        ):
            raise ExperimentError("persisted_event_mismatch")
        row["event"] = {
            k: persisted_event.get(k)
            for k in ("id", "project_id", "source_type", "content", "content_hash", "created_at")
        }
        start = time.perf_counter()
        results = api.request(
            "POST", prefix + f"/decision-services/{service}/runs", {"raw_event_ids": [event_id]}
        )
        row["api_elapsed_ms"] = (time.perf_counter() - start) * 1000
        if not isinstance(results, list) or len(results) != 1:
            raise ExperimentError("execution_result_count_mismatch")
        run = results[0]
        run_id = safe_id(run["id"])
        row["run_id"] = run_id
        persisted_run = api.request("GET", prefix + f"/runs/{run_id}")
        if persisted_run != run:
            raise ExperimentError("persisted_run_mismatch")
        validate_run(
            run,
            project=project,
            service=service,
            event=event_id,
            model=model,
            instructions=instructions,
        )
        row["run"] = {k: run.get(k) for k in RUN_FIELDS}
        evidence: list[dict[str, Any]] = []
        # Fresh project is bounded by 72 examples, but allow multiple triggers per run.
        for offset in range(0, 1000, 100):
            page = api.request("GET", prefix + f"/evidence?limit=100&offset={offset}")
            if not isinstance(page, list):
                raise ExperimentError("invalid_evidence_list")
            evidence.extend(page)
            if len(page) < 100:
                break
        else:
            raise ExperimentError("evidence_pagination_bound_exceeded")
        linked = [e for e in evidence if e.get("decision_run_id") == run_id]
        if run["supervision_outcome"] != "TRUSTED" and not linked:
            raise ExperimentError("missing_persisted_unknown_or_low_trust_evidence")
        verified_evidence: list[dict[str, Any]] = []
        for item in linked:
            evidence_id = safe_id(item["id"])
            readback = api.request("GET", prefix + f"/evidence/{evidence_id}")
            if (
                readback != item
                or item.get("project_id") != project
                or item.get("raw_event_id") != event_id
                or item.get("decision_service_id") != service
                or item.get("provider") != "laya"
                or item.get("model") != model
                or item.get("probabilities_snapshot") != run["probabilities"]
                or item.get("selected_choice") != run["selected_choice"]
            ):
                raise ExperimentError("persisted_evidence_mismatch")
            verified_evidence.append({k: item.get(k) for k in EVIDENCE_FIELDS})
        row.update(
            predicted=run["selected_choice"],
            trusted=run["supervision_outcome"] == "TRUSTED",
            persisted_verified=True,
            evidence=verified_evidence,
        )
    except (ExperimentError, KeyError, TypeError, AttributeError, httpx.HTTPError) as exc:
        if start is not None and row["api_elapsed_ms"] is None:
            row["api_elapsed_ms"] = (time.perf_counter() - start) * 1000
        # Only our own fixed-message errors are persisted, never arbitrary upstream bodies.
        row["error"] = str(exc) if isinstance(exc, ExperimentError) else "invalid_http_contract"
        row.update(predicted=None, trusted=None, persisted_verified=False)
    row["sha256"] = digest(row)
    return row


def create_lock(dataset: Path, development: list[Path], destination: Path) -> dict[str, Any]:
    _, frozen = load_dataset(dataset)
    if not 1 <= len(development) <= 2:
        raise ExperimentError("one baseline and at most one development variant required")
    candidates: list[tuple[tuple[float, float, int], dict[str, Any], Path]] = []
    seen: set[str] = set()
    reference: dict[str, Any] | None = None
    for directory in development:
        verify_result(directory)
        manifest = read_json(directory / "manifest.json")
        if (
            manifest["split"] != "development"
            or manifest["dataset_sha256"] != frozen["dataset_sha256"]
            or manifest["source"] != source_identity()
            or manifest["variant"] not in CONFIGS
            or manifest["variant"] in seen
        ):
            raise ExperimentError("invalid development selection input")
        seen.add(manifest["variant"])
        if reference is not None and any(
            manifest[field] != reference[field]
            for field in ("checkpoint_identity", "languages", "dataset_sha256", "source")
        ):
            raise ExperimentError("development cohorts do not match")
        reference = manifest
        metrics = read_json(directory / "metrics.json")
        if any(m["failures"] for m in metrics.values()):
            raise ExperimentError("cannot select configuration from failed development run")
        # Equal-language macro-F1, then accuracy; exact ties retain baseline.
        score = (
            sum(m["macro_f1"] for m in metrics.values()) / len(metrics),
            sum(m["accuracy"] for m in metrics.values()) / len(metrics),
            int(manifest["variant"] == "baseline"),
        )
        candidates.append((score, manifest, directory))
    if "baseline" not in seen:
        raise ExperimentError("baseline development is mandatory")
    _, selected, _ = max(candidates, key=lambda candidate: candidate[0])
    lock = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": frozen["dataset_sha256"],
        "split_sha256": frozen["splits"]["holdout"]["sha256"],
        "source": source_identity(),
        "variant": selected["variant"],
        "config_sha256": selected["config_sha256"],
        "checkpoint_identity": selected["checkpoint_identity"],
        "languages": selected["languages"],
        "selection_rule": "development equal-language macro-F1, accuracy, baseline tie-break",
        "development_manifests": {
            str(directory.resolve()): file_hash(directory / "manifest.json")
            for directory in development
        },
        "no_holdout_results_consulted": True,
    }
    registry = cohort_directory(frozen, selected["checkpoint_identity"], selected["languages"])
    if (registry / "holdout.started.json").exists():
        raise ExperimentError("holdout already started; selection cannot change")
    # Claim the unique cohort lock before publishing it. Never silently replace either file.
    save_new(
        registry / "selection.json",
        {"lock_sha256": digest(lock), "lock_path": str(destination.resolve())},
    )
    save_new(destination, lock)
    return lock


def check_lock(
    lock: dict[str, Any],
    frozen: dict[str, Any],
    *,
    variant: str,
    proof: dict[str, Any],
    languages: list[str],
) -> None:
    if (
        lock.get("dataset_sha256") != frozen["dataset_sha256"]
        or lock.get("split_sha256") != frozen["splits"]["holdout"]["sha256"]
        or lock.get("source") != source_identity()
        or lock.get("variant") != variant
        or lock.get("config_sha256") != digest(configuration(variant))
        or lock.get("checkpoint_identity") != checkpoint_identity(proof)
        or lock.get("languages") != languages
    ):
        raise ExperimentError("holdout lock missing or mismatched frozen inputs")
    for directory, expected in lock["development_manifests"].items():
        if file_hash(Path(directory) / "manifest.json") != expected:
            raise ExperimentError("development manifest changed after lock")
        verify_result(Path(directory))
    registry = cohort_directory(frozen, checkpoint_identity(proof), languages)
    selection = read_json(registry / "selection.json")
    if selection.get("lock_sha256") != digest(lock):
        raise ExperimentError("holdout lock is not the unique registered selection")


def cohort_directory(
    frozen: dict[str, Any], identity: dict[str, Any], languages: list[str]
) -> Path:
    return (
        DEFAULT_RUNS
        / "cohorts"
        / digest(
            {
                "dataset": frozen["dataset_sha256"],
                "checkpoint": identity,
                "languages": languages,
            }
        )
    )


def claim_phase(
    frozen: dict[str, Any],
    proof: dict[str, Any],
    languages: list[str],
    phase: str,
    variant: str,
    output: Path,
) -> None:
    registry = cohort_directory(frozen, checkpoint_identity(proof), languages)
    if phase == "development" and (registry / "selection.json").exists():
        raise ExperimentError("development is closed after selection lock")
    name = f"development-{variant}" if phase == "development" else "holdout"
    try:
        save_new(
            registry / f"{name}.started.json",
            {
                "output": str(output.resolve()),
                "source": source_identity(),
                "started_at": datetime.now(UTC).isoformat(),
            },
        )
    except FileExistsError as exc:
        raise ExperimentError("phase already attempted; automatic rerun prohibited") from exc


def configuration(variant: str) -> dict[str, Any]:
    if variant not in CONFIGS:
        raise ExperimentError("unregistered instruction variant")
    return {
        "instructions": CONFIGS[variant],
        "choices": [
            {"key": key, "label": key, "description": POLICY[key]}
            for key in LABELS
            if key != "UNKNOWN"
        ],
        "provider_override": "laya",
    }


def run_phase(
    *,
    dataset: Path,
    output: Path,
    phase: str,
    variant: str,
    proof_path: Path,
    languages: list[str],
    base_url: str,
    owned_target: bool,
    lock_path: Path | None = None,
) -> dict[str, Any]:
    items, frozen = load_dataset(dataset)
    proof = read_json(proof_path)
    validate_proof(proof)
    if (
        phase not in {"development", "holdout"}
        or not languages
        or (len(set(languages)) != len(languages) or set(languages) - {"en", "ar"})
    ):
        raise ExperimentError("invalid phase or language cohort")
    languages = sorted(languages)
    config = configuration(variant)
    lock: dict[str, Any] | None = None
    if phase == "holdout":
        if lock_path is None:
            raise ExperimentError("holdout requires immutable development selection lock")
        lock = read_json(lock_path)
        check_lock(lock, frozen, variant=variant, proof=proof, languages=languages)
    selected = [c for c in items if c["split"] == phase and c["language"] in languages]
    # Validate everything before creating HTTP effects; exclusive output prevents overwrite.
    api = LocalAPI(base_url, owned_target=owned_target)
    try:
        output.mkdir(parents=True, exist_ok=False)
        claim_phase(frozen, proof, languages, phase, variant, output)
        save_new(output / "runtime-proof.json", proof)
        if lock is not None:
            save_new(output / "lock.json", lock)
        preregistration = {
            "phase": phase,
            "variant": variant,
            "dataset_sha256": frozen["dataset_sha256"],
            "expected_ids": [c["id"] for c in selected],
            "source": source_identity(),
            "config": config,
            "config_sha256": digest(config),
            "checkpoint_identity": checkpoint_identity(proof),
            "created_at": datetime.now(UTC).isoformat(),
        }
        save_new(output / "preregistration.json", preregistration)
        project = api.request(
            "POST",
            "/api/v1/projects",
            {
                "name": f"Laya synthetic {phase} {variant} {uuid4().hex[:12]}",
                "description": (
                    "Owned local synthetic inference experiment. No expert truth claims."
                ),
            },
        )
        project_id = safe_id(project["id"])
        service = api.request(
            "POST",
            f"/api/v1/projects/{project_id}/decision-services",
            {
                "name": "Frozen support routing",
                **config,
            },
        )
        service_id = safe_id(service["id"])
        if service.get("provider_override") != "laya":
            raise ExperimentError("service_laya_override_not_persisted")
        rows: list[dict[str, Any]] = []
        with (output / "examples.jsonl").open("xb") as stream:
            for index, case in enumerate(selected):
                row = execute_case(
                    api,
                    case,
                    project=project_id,
                    service=service_id,
                    model=proof["model"],
                    instructions=config["instructions"],
                    checkpoint=proof["checkpoint"],
                    warm=index > 0,
                )
                rows.append(row)
                stream.write(canonical(row) + b"\n")
                stream.flush()
        summary = grouped(rows)
        manifest = {
            **{k: v for k, v in preregistration.items() if k not in {"phase", "config"}},
            "split": phase,
            "split_sha256": frozen["splits"][phase]["sha256"],
            "languages": languages,
            "project_id": project_id,
            "service_id": service_id,
            "actual_count": len(rows),
            "failures": sum(r["error"] is not None for r in rows),
            "examples_sha256": digest(rows),
            "examples_file_sha256": file_hash(output / "examples.jsonl"),
            "runtime_proof_file_sha256": file_hash(output / "runtime-proof.json"),
            "lock_sha256": digest(lock) if lock is not None else None,
            "packages": packages(),
            "python": platform.python_version(),
            "cold_start_ms": proof.get("cold_start_ms"),
            "memory": proof.get("memory"),
            "first_api_request_excluded_from_warm": True,
            "runtime_proof_is_driver_claim_not_independent_verification": True,
            "historical_65_reports": "unverified; this experiment is not a replacement",
        }
        save_new(output / "metrics.json", summary)
        save_new(output / "manifest.json", manifest)
        verify_result(output)
        return {
            "output": str(output.resolve()),
            "count": len(rows),
            "failures": manifest["failures"],
        }
    finally:
        api.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase", choices=["prepare", "development", "lock", "holdout", "report", "verify"]
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--development", type=Path, action="append", default=[])
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--runtime-proof", type=Path)
    parser.add_argument("--variant", choices=list(CONFIGS), default="baseline")
    parser.add_argument("--languages", nargs="+", choices=["en", "ar"], default=["en", "ar"])
    parser.add_argument("--base-url", default="http://127.0.0.1:7331")
    parser.add_argument("--owned-local-target", action="store_true")
    args = parser.parse_args()
    try:
        if args.phase == "prepare":
            result = prepare(args.dataset)
        elif args.phase == "lock":
            if args.lock is None:
                raise ExperimentError("--lock path is required")
            result = create_lock(args.dataset, args.development, args.lock)
        elif args.phase in {"verify", "report"}:
            if args.output is None:
                raise ExperimentError("--output path is required")
            result = verify_result(args.output)
        else:
            if args.output is None or args.runtime_proof is None:
                raise ExperimentError("--output and --runtime-proof paths are required")
            result = run_phase(
                dataset=args.dataset,
                output=args.output,
                phase=args.phase,
                variant=args.variant,
                proof_path=args.runtime_proof,
                languages=args.languages,
                base_url=args.base_url,
                owned_target=args.owned_local_target,
                lock_path=args.lock,
            )
        print(canonical(result).decode("utf-8"))
    except (ExperimentError, OSError, ValueError, KeyError, TypeError) as exc:
        # Never print arbitrary network/server bodies, filesystem paths or environment values.
        message = str(exc) if isinstance(exc, ExperimentError) else "artifact_contract_failure"
        parser.exit(2, f"{message}\n")


if __name__ == "__main__":
    main()
