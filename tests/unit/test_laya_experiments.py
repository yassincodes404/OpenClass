"""Offline SIMULATED fixtures only. No model imports, inference, or holdout predictions."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from scripts.laya_experiments import runner
from scripts.laya_experiments.dataset import (
    LABELS,
    ExperimentError,
    canonical,
    cases,
    digest,
    file_hash,
    load_dataset,
    metadata,
    prepare,
    save_new,
    validate_cases,
)
from scripts.laya_experiments.metrics import grouped, quantile, summarize
from scripts.laya_experiments.verify import (
    checkpoint_identity,
    validate_proof,
    verify_result,
)


def metric_row(
    actual: str,
    predicted: str,
    *,
    trusted: bool = False,
    error: str | None = None,
    latency: float | None = None,
) -> dict[str, Any]:
    return dict(
        id="simulated-fixture",
        expected=actual,
        predicted=predicted,
        trusted=trusted,
        error=error,
        api_elapsed_ms=latency,
        warm=True,
        category="fixture",
    )


def simulated_proof() -> dict[str, Any]:
    return {
        "checkpoint": "SIMULATED-offline-checkpoint",
        "revision": "a" * 40,
        "weight_files": {"SIMULATED.safetensors": "b" * 64},
        "model": "SIMULATED-model",
        "device": "SIMULATED-cpu",
        "backend": "SIMULATED",
        "forward_calls": 1,
        "forward_instrumentation": {"SIMULATED": "no actual forward performed"},
        "packages": {"SIMULATED": "0"},
        "cold_start_ms": None,
        "memory": None,
    }


def test_hand_computed_metrics() -> None:
    rows = [
        metric_row("BILLING", "BILLING", trusted=True, latency=10),
        metric_row("BILLING", "UNKNOWN", latency=20),
        metric_row("TECHNICAL", "TECHNICAL", trusted=True, latency=30),
        metric_row("SALES", "BILLING", trusted=True, latency=40),
        metric_row("UNKNOWN", "UNKNOWN", latency=50),
        metric_row("UNKNOWN", "SALES", latency=60),
    ]
    result = summarize(rows)
    assert result["accuracy"] == 0.5
    assert result["macro_f1"] == pytest.approx(0.5)
    assert result["unknown_precision"] == 0.5
    assert result["unknown_recall"] == 0.5
    assert result["semantic_coverage"] == pytest.approx(4 / 6)
    assert result["trusted_sample_coverage"] == 0.5
    assert result["errors_among_trusted"] == 1
    assert result["trusted_error_rate"] == pytest.approx(1 / 3)
    assert result["confusion_matrix"]["BILLING"]["UNKNOWN"] == 1
    assert result["api_warm_latency_ms"]["p50"] == 35
    assert result["api_warm_latency_ms"]["p95"] == pytest.approx(57.5)


def test_empty_unknown_and_trusted_are_undefined() -> None:
    empty = summarize([])
    for key in (
        "accuracy",
        "macro_f1",
        "unknown_precision",
        "unknown_recall",
        "semantic_coverage",
        "trusted_sample_coverage",
        "errors_among_trusted",
    ):
        assert empty[key] is None
    result = summarize([metric_row("BILLING", "BILLING")])
    assert result["unknown_precision"] is None
    assert result["unknown_recall"] is None
    assert result["errors_among_trusted"] is None
    assert result["trusted_error_rate"] is None
    assert result["trusted_sample_coverage"] == 0
    assert result["macro_f1"] == 0.25  # Fixed four-class macro, not supported-only.
    assert result["api_warm_latency_ms"]["p50"] is None


def test_failures_are_not_unknown_or_zero_latency() -> None:
    row = metric_row("UNKNOWN", "UNKNOWN", error="http_status_503")
    result = summarize([row])
    assert result["failures"] == 1
    assert result["accuracy"] is None
    assert result["accuracy_all_attempts"] == 0
    assert result["confusion_matrix"]["UNKNOWN"]["UNKNOWN"] == 0
    assert result["api_warm_latency_ms"]["p95"] is None
    assert result["errors"] == {"http_status_503": 1}


def test_quantile_and_label_validation() -> None:
    assert quantile([7], 0.95) == 7
    assert quantile([], 0.5) is None
    with pytest.raises(ExperimentError):
        quantile([float("nan")], 0.5)
    with pytest.raises(ExperimentError):
        summarize([metric_row("NEW", "BILLING")])


def test_frozen_dataset_balance_and_translation_groups() -> None:
    items = cases()
    validate_cases(items)
    manifest = metadata(items)
    assert len(items) == 120
    assert len(manifest["group_membership"]) == 60
    for split, count in (("development", 6), ("holdout", 9)):
        for language in ("en", "ar"):
            assert Counter(
                c["expected"] for c in items if c["split"] == split and c["language"] == language
            ) == {label: count for label in LABELS}
    for members in manifest["group_membership"].values():
        pair = [c for c in items if c["id"] in members]
        assert {c["language"] for c in pair} == {"en", "ar"}
        assert len({c["split"] for c in pair}) == 1
        assert len({c["expected"] for c in pair}) == 1
    assert manifest["dataset_sha256"] == (
        "a98c3697ef2df8c2f5038277bcacab44bfeea8288e0e7409b8a2397424220073"
    )


@pytest.mark.parametrize("change", ["group", "text", "label", "hash"])
def test_dataset_leakage_and_tampering_rejected(change: str) -> None:
    items = deepcopy(cases())
    if change == "group":
        items[-1]["group"] = items[0]["group"]
    elif change == "text":
        items[-1]["text"] = "  " + items[0]["text"].upper() + " "
    elif change == "label":
        items[-1]["expected"] = "NOVEL"
    else:
        items[-1]["sha256"] = "bad"
    if change != "hash":
        items[-1]["sha256"] = digest({k: v for k, v in items[-1].items() if k != "sha256"})
    with pytest.raises(ExperimentError):
        validate_cases(items)


def test_prepare_is_idempotent_but_never_overwrites(tmp_path: Path) -> None:
    frozen = prepare(tmp_path)
    assert prepare(tmp_path) == frozen
    assert load_dataset(tmp_path)[0] == cases()
    (tmp_path / "cases.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises((ExperimentError, KeyError)):
        prepare(tmp_path)
    assert (tmp_path / "cases.jsonl").read_text("utf-8") == "{}\n"


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:7331",
        "http://example.com:7331",
        "http://localhost:7331",
        "http://127.0.0.1:7331/path",
        "http://secret@127.0.0.1:7331",
        "http://127.0.0.1",
        "http://127.0.0.1:7331?secret=x",
    ],
)
def test_nonowned_or_outward_targets_rejected(url: str) -> None:
    with pytest.raises(ExperimentError):
        runner.loopback_url(url)


def test_token_is_header_only_and_redirect_never_followed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAYA_EXPERIMENT_INTERNAL_TOKEN", "SIMULATED-secret-never-persist")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.headers["X-OpenClass-Internal-Token"] == "SIMULATED-secret-never-persist"
        return httpx.Response(307, headers={"location": "https://example.com"})

    api = runner.LocalAPI(
        "http://127.0.0.1:7331", owned_target=True, transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(ExperimentError, match="http_status_307") as error:
            api.request("POST", "/api/v1/projects", {"name": "synthetic"})
        assert "secret" not in str(error.value)
        assert len(seen) == 1
        with pytest.raises(ExperimentError):
            api.request("POST", "/api/v1/projects/../../outside")
    finally:
        api.close()
    with pytest.raises(ExperimentError):
        runner.LocalAPI("http://127.0.0.1:7331", owned_target=False)


class SimulatedHTTPFixture:
    """Claims API flags solely to exercise validation; never real inference proof."""

    def __init__(self, fault: str | None = None) -> None:
        self.fault = fault
        self.project, self.service, self.event, self.run_id, self.evidence_id = (
            str(uuid4()) for _ in range(5)
        )
        self.case = cases()[0]  # Development only.
        self.instructions = runner.configuration("baseline")["instructions"]
        self.run = {
            "id": self.run_id,
            "project_id": self.project,
            "decision_service_id": self.service,
            "raw_event_id": self.event,
            "provider": "laya",
            "model": "SIMULATED-model",
            "execution_mode": "daemon",
            "real_inference": True,
            "run_status": "paused",
            "instructions_snapshot": self.instructions,
            "choices_snapshot": runner.configuration("baseline")["choices"]
            + [{"key": "UNKNOWN", "label": "UNKNOWN", "description": "Permanent UNKNOWN"}],
            "selected_choice": "BILLING",
            "probabilities": dict(BILLING=0.7, TECHNICAL=0.1, SALES=0.1, UNKNOWN=0.1),
            "unknown_probability": 0.1,
            "supervision_outcome": "REVIEW",
        }
        if fault == "mock":
            self.run["execution_mode"] = "mock"
        if fault == "distribution":
            self.run["probabilities"] = {"BILLING": 1.0}
        if fault == "selected":
            self.run["selected_choice"] = "SALES"
        if fault == "choices":
            self.run["choices_snapshot"] = []
        if fault == "fallback_marker":
            self.run["provider_metadata"] = {"simulated": True}

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if self.fault == "http":
            return httpx.Response(503, json={"detail": "SIMULATED-private-error-secret"})
        if path.endswith("/events") and request.method == "POST":
            assert json.loads(request.content)["content"] == self.case["text"]
            return httpx.Response(201, json={"id": self.event})
        if path.endswith(f"/events/{self.event}"):
            return httpx.Response(
                200,
                json={
                    "id": self.event,
                    "project_id": self.project,
                    "content": self.case["text"],
                    "content_hash": hashlib.sha256(self.case["text"].encode()).hexdigest(),
                },
            )
        if path.endswith(f"/decision-services/{self.service}/runs"):
            assert json.loads(request.content) == {"raw_event_ids": [self.event]}
            return httpx.Response(200, json=[self.run])
        if path.endswith(f"/runs/{self.run_id}"):
            value = deepcopy(self.run)
            if self.fault == "persist":
                value["model"] = "mismatched"
            return httpx.Response(200, json=value)
        evidence = {
            "id": self.evidence_id,
            "project_id": self.project,
            "decision_run_id": self.run_id,
            "raw_event_id": self.event,
            "decision_service_id": self.service,
            "provider": "laya",
            "model": "SIMULATED-model",
            "selected_choice": "BILLING",
            "probabilities_snapshot": self.run["probabilities"],
        }
        if self.fault == "evidence_mismatch":
            evidence["model"] = "wrong"
        if path.endswith("/evidence"):
            return httpx.Response(200, json=[] if self.fault == "missing_evidence" else [evidence])
        if path.endswith(f"/evidence/{self.evidence_id}"):
            return httpx.Response(200, json=evidence)
        raise AssertionError("Unexpected simulated route")

    def execute(self) -> dict[str, Any]:
        api = runner.LocalAPI(
            "http://127.0.0.1:7331", owned_target=True, transport=httpx.MockTransport(self.handler)
        )
        try:
            return runner.execute_case(
                api,
                self.case,
                project=self.project,
                service=self.service,
                model="SIMULATED-model",
                instructions=self.instructions,
                checkpoint="SIMULATED-offline-checkpoint",
                warm=True,
            )
        finally:
            api.close()


def test_ingestion_execution_and_persisted_evidence_contract() -> None:
    row = SimulatedHTTPFixture().execute()
    assert row["error"] is None
    assert row["persisted_verified"] is True
    assert row["trusted"] is False
    assert row["run"]["run_status"] == "paused"  # Not an infrastructure failure.
    assert row["evidence"]
    assert row["api_elapsed_ms"] is not None
    assert digest({k: v for k, v in row.items() if k != "sha256"}) == row["sha256"]


@pytest.mark.parametrize(
    "fault",
    [
        "http",
        "persist",
        "mock",
        "distribution",
        "selected",
        "choices",
        "fallback_marker",
        "missing_evidence",
        "evidence_mismatch",
    ],
)
def test_fail_closed_http_and_persistence(fault: str) -> None:
    row = SimulatedHTTPFixture(fault).execute()
    assert row["error"] is not None
    assert row["predicted"] is None
    assert row["persisted_verified"] is False
    assert "private-error-secret" not in canonical(row).decode()


def development_artifact(directory: Path, variant: str) -> None:
    """Complete simulated development cohort, never a holdout result."""
    directory.mkdir()
    proof = simulated_proof()
    rows = []
    for case in cases():
        if case["split"] != "development":
            continue
        fixture = SimulatedHTTPFixture()
        fixture.case = case
        fixture.instructions = runner.configuration(variant)["instructions"]
        fixture.run["instructions_snapshot"] = fixture.instructions
        rows.append(fixture.execute())
    (directory / "examples.jsonl").write_bytes(b"".join(canonical(r) + b"\n" for r in rows))
    save_new(directory / "runtime-proof.json", proof)
    save_new(directory / "metrics.json", grouped(rows))
    save_new(
        directory / "manifest.json",
        {
            "split": "development",
            "variant": variant,
            "dataset_sha256": metadata(cases())["dataset_sha256"],
            "split_sha256": metadata(cases())["splits"]["development"]["sha256"],
            "source": runner.source_identity(),
            "config_sha256": digest(runner.configuration(variant)),
            "checkpoint_identity": checkpoint_identity(proof),
            "languages": ["ar", "en"],
            "expected_ids": [row["id"] for row in rows],
            "actual_count": len(rows),
            "examples_sha256": digest(rows),
            "examples_file_sha256": file_hash(directory / "examples.jsonl"),
            "runtime_proof_file_sha256": file_hash(directory / "runtime-proof.json"),
        },
    )


def test_proof_claim_validation_does_not_certify_execution() -> None:
    proof = simulated_proof()
    validate_proof(proof)
    proof["forward_calls"] = 0
    with pytest.raises(ExperimentError):
        validate_proof(proof)


def test_result_hashes_and_offline_metrics_reproduce(tmp_path: Path) -> None:
    directory = tmp_path / "simulated-development"
    development_artifact(directory, "baseline")
    result = verify_result(directory)
    assert result["model_execution_independently_verified"] is False
    with (directory / "examples.jsonl").open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises((ExperimentError, ValueError)):
        verify_result(directory)


def test_lock_selection_gating_and_no_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner, "DEFAULT_RUNS", tmp_path / "cohort-registry")
    data = tmp_path / "dataset"
    frozen = prepare(data)
    baseline, clarified = tmp_path / "baseline", tmp_path / "clarified"
    development_artifact(baseline, "baseline")
    development_artifact(clarified, "clarified")
    lock = runner.create_lock(data, [baseline, clarified], tmp_path / "lock.json")
    assert lock["variant"] == "baseline"  # Exact tie, baseline wins.
    proof = simulated_proof()
    runner.check_lock(lock, frozen, variant="baseline", proof=proof, languages=["ar", "en"])
    with pytest.raises(ExperimentError):
        runner.check_lock(lock, frozen, variant="clarified", proof=proof, languages=["ar", "en"])
    with pytest.raises(ExperimentError):
        runner.check_lock(lock, frozen, variant="baseline", proof=proof, languages=["en"])
    with pytest.raises((ExperimentError, FileExistsError)):
        runner.create_lock(data, [baseline], tmp_path / "another-lock.json")
    with pytest.raises(ExperimentError):
        runner.claim_phase(frozen, proof, ["ar", "en"], "development", "clarified", clarified)
    runner.claim_phase(frozen, proof, ["ar", "en"], "holdout", "baseline", tmp_path / "unrun")
    with pytest.raises(ExperimentError):
        runner.claim_phase(frozen, proof, ["ar", "en"], "holdout", "baseline", tmp_path / "unrun2")
    # No holdout examples were sent or predicted: this only tests exclusive claim files.


def test_holdout_refuses_missing_lock_before_http(tmp_path: Path) -> None:
    data = tmp_path / "dataset"
    prepare(data)
    proof = tmp_path / "SIMULATED-proof.json"
    save_new(proof, simulated_proof())
    with pytest.raises(ExperimentError, match="requires immutable"):
        runner.run_phase(
            dataset=data,
            output=tmp_path / "never-created",
            phase="holdout",
            variant="baseline",
            proof_path=proof,
            languages=["en"],
            base_url="http://127.0.0.1:7331",
            owned_target=True,
        )
    assert not (tmp_path / "never-created").exists()


@pytest.mark.parametrize(
    "field", ["source", "dataset_sha256", "config_sha256", "checkpoint_identity", "split_sha256"]
)
def test_holdout_lock_rejects_changed_frozen_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    monkeypatch.setattr(runner, "DEFAULT_RUNS", tmp_path / "cohort-registry")
    data = tmp_path / "dataset"
    frozen = prepare(data)
    baseline = tmp_path / "baseline"
    development_artifact(baseline, "baseline")
    lock = runner.create_lock(data, [baseline], tmp_path / "lock.json")
    lock[field] = "changed"
    with pytest.raises(ExperimentError):
        runner.check_lock(
            lock, frozen, variant="baseline", proof=simulated_proof(), languages=["ar", "en"]
        )


def test_partial_development_cannot_select_holdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner, "DEFAULT_RUNS", tmp_path / "cohort-registry")
    data = tmp_path / "dataset"
    prepare(data)
    directory = tmp_path / "baseline"
    development_artifact(directory, "baseline")
    manifest_path = directory / "manifest.json"
    value = json.loads(manifest_path.read_text("utf-8"))
    value["expected_ids"] = value["expected_ids"][:1]
    manifest_path.write_bytes(canonical(value))
    with pytest.raises(ExperimentError, match="cohort differs"):
        runner.create_lock(data, [directory], tmp_path / "never-lock.json")
    assert not (tmp_path / "never-lock.json").exists()
