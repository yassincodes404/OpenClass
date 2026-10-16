"""Offline artifact contracts. Metadata assertions are not independent model proof."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .dataset import CONFIGS, LABELS, POLICY, ExperimentError, cases, digest, file_hash, metadata
from .metrics import grouped


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text("utf-8"))
    if not isinstance(value, dict):
        raise ExperimentError("expected JSON object")
    return value


def checkpoint_identity(proof: dict[str, Any]) -> dict[str, Any]:
    return {key: proof[key] for key in ("checkpoint", "revision", "weight_files", "model")}


def validate_proof(proof: dict[str, Any]) -> None:
    """Check driver claims structurally; operator must review actual forward evidence."""
    if not all(
        isinstance(proof.get(k), str) and proof[k]
        for k in ("checkpoint", "revision", "device", "backend", "model")
    ):
        raise ExperimentError("runtime proof missing identity or execution environment")
    if not re.fullmatch(r"[0-9a-f]{40}", proof["revision"]):
        raise ExperimentError("checkpoint revision must be a pinned commit")
    weights = proof.get("weight_files")
    if (
        not isinstance(weights, dict)
        or not weights
        or not all(
            isinstance(k, str) and isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v)
            for k, v in weights.items()
        )
    ):
        raise ExperimentError("runtime proof missing weight hashes")
    if (
        type(proof.get("forward_calls")) is not int
        or proof["forward_calls"] < 1
        or not isinstance(proof.get("packages"), dict)
        or not proof["packages"]
        or not isinstance(proof.get("forward_instrumentation"), dict)
        or not proof["forward_instrumentation"]
    ):
        raise ExperimentError("runtime proof missing actual forward instrumentation claims")
    for key in ("cold_start_ms",):
        value = proof.get(key)
        if value is not None and (
            type(value) not in (int, float) or not math.isfinite(value) or value < 0
        ):
            raise ExperimentError("invalid optional runtime measurement")


def verify_result(directory: Path) -> dict[str, Any]:
    manifest = read_json(directory / "manifest.json")
    frozen_cases = cases()
    frozen = metadata(frozen_cases)
    if (
        manifest.get("split") not in {"development", "holdout"}
        or manifest.get("variant") not in CONFIGS
        or manifest.get("languages") not in [["en"], ["ar"], ["ar", "en"]]
    ):
        raise ExperimentError("invalid result cohort")
    cohort = {
        c["id"]: c
        for c in frozen_cases
        if c["split"] == manifest["split"] and c["language"] in manifest["languages"]
    }
    if (
        manifest.get("dataset_sha256") != frozen["dataset_sha256"]
        or manifest.get("split_sha256") != frozen["splits"][manifest["split"]]["sha256"]
        or sorted(manifest["expected_ids"]) != sorted(cohort)
    ):
        raise ExperimentError("result cohort differs from frozen dataset")
    expected_config = {
        "instructions": CONFIGS[manifest["variant"]],
        "choices": [
            {"key": key, "label": key, "description": POLICY[key]}
            for key in LABELS
            if key != "UNKNOWN"
        ],
        "provider_override": "laya",
    }
    if manifest.get("config_sha256") != digest(expected_config):
        raise ExperimentError("result configuration differs from registered instructions")
    rows = [
        json.loads(line) for line in (directory / "examples.jsonl").read_text("utf-8").splitlines()
    ]
    if file_hash(directory / "examples.jsonl") != manifest["examples_file_sha256"]:
        raise ExperimentError("result file hash mismatch")
    if digest(rows) != manifest["examples_sha256"] or len(rows) != manifest["actual_count"]:
        raise ExperimentError("result count or canonical hash mismatch")
    if len({r["id"] for r in rows}) != len(rows):
        raise ExperimentError("duplicate result examples")
    if sorted(r["id"] for r in rows) != sorted(manifest["expected_ids"]):
        raise ExperimentError("missing or unexpected result examples")
    for row in rows:
        if digest({k: v for k, v in row.items() if k != "sha256"}) != row["sha256"]:
            raise ExperimentError("per-example result hash mismatch")
        if row.get("error") is None and (
            row.get("predicted") not in LABELS or not row.get("persisted_verified")
        ):
            raise ExperimentError("success without persisted semantic result")
        case = cohort[row["id"]]
        if (
            row.get("case_sha256") != case["sha256"]
            or any(row.get(k) != case[k] for k in ("expected", "language", "split", "category"))
            or row.get("checkpoint") != manifest["checkpoint_identity"]["checkpoint"]
        ):
            raise ExperimentError("result example does not match frozen label or cohort")
        if row.get("error") is not None and (
            row.get("predicted") is not None or row.get("trusted") is not None
        ):
            raise ExperimentError("infrastructure failure carries semantic result")
        if row.get("error") is None:
            run = row["run"]
            if (
                row["predicted"] != run["selected_choice"]
                or row["trusted"] != (run["supervision_outcome"] == "TRUSTED")
                or run["instructions_snapshot"] != expected_config["instructions"]
                or run["model"] != manifest["checkpoint_identity"]["model"]
            ):
                raise ExperimentError("semantic result differs from persisted run")
    proof = read_json(directory / "runtime-proof.json")
    validate_proof(proof)
    if file_hash(directory / "runtime-proof.json") != manifest["runtime_proof_file_sha256"]:
        raise ExperimentError("runtime proof file hash mismatch")
    if checkpoint_identity(proof) != manifest["checkpoint_identity"]:
        raise ExperimentError("runtime checkpoint mismatch")
    metrics = grouped(rows)
    if metrics != read_json(directory / "metrics.json"):
        raise ExperimentError("metrics do not reproduce")
    if manifest["split"] == "holdout":
        lock = read_json(directory / "lock.json")
        if digest(lock) != manifest["lock_sha256"]:
            raise ExperimentError("holdout lock hash mismatch")
        for field in (
            "dataset_sha256",
            "split_sha256",
            "config_sha256",
            "source",
            "checkpoint_identity",
            "languages",
            "variant",
        ):
            if lock[field] != manifest[field]:
                raise ExperimentError("holdout manifest does not match selection lock")
    return {
        "verified": True,
        "count": len(rows),
        "metrics": metrics,
        "model_execution_independently_verified": False,
    }
