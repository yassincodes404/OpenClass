"""Offline tests for the stage 1 live runner's analysis layer; no network."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.jev_contract.calibration import Rule, grid, load_dataset, score
from scripts.jev_contract.jev import UNKNOWN, DecisionTelemetry
from scripts.jev_contract.stage1_live import (
    policy_frame,
    raw_decision_stats,
    stratum_rule_sensitivity,
)


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(Path("benchmarks/jev-contract/v1"))


def synthetic_telemetry(dataset, chooser):
    """Synthetic but schema-valid telemetry: chooser(case) -> (top, unknown, pick)."""
    results = {}
    for case in dataset.cases:
        top, unknown, pick = chooser(case)
        other = min(0.95, max(0.0, top - 0.1))
        rest = max(0.0, 1 - top - unknown - other)
        distribution = {"runner_up": other}
        if pick == UNKNOWN:
            distribution[UNKNOWN] = top + unknown
        else:
            distribution[pick] = top
            distribution[UNKNOWN] = unknown
        if rest > 0:
            distribution["rest"] = rest
        distribution = {k: v for k, v in distribution.items() if v > 0}
        scale = sum(distribution.values())
        distribution = {k: v / scale for k, v in distribution.items()}
        ordered = sorted(distribution.values(), reverse=True)
        snapshot_json = json.loads(case.snapshot.model_dump_json())
        results[case.id] = DecisionTelemetry.model_validate(
            {
                "event": "decision.completed",
                "profile_id": "p",
                "profile_version": 1,
                "profile_hash": "h",
                "provider": "jev",
                "model": "typesafe-ai/jev",
                "node_id": case.node.id,
                "decision_spec_id": "d",
                "state_snapshot_id": case.snapshot.id,
                "state_snapshot": snapshot_json,
                "choice_set_hash": "c",
                "selected_choice": pick,
                "distribution": distribution,
                "selected_probability": distribution[pick],
                "top_probability": ordered[0],
                "second_probability": ordered[1],
                "margin": ordered[0] - ordered[1],
                "unknown_probability": distribution[UNKNOWN],
                "latency_ms": 10.0,
                "retry_count": 0,
                "infrastructure_status": "ok",
                "simulated": False,
            }
        )
    return results


def test_raw_stats_count_false_known_and_false_unknown(dataset):
    labels = dataset.labels

    def chooser(case):
        label = labels[case.id]
        if case.stratum == "dangerous_false_known":
            return 0.8, 0.1, next(c.id for c in case.node.choices)
        if label == UNKNOWN:
            return 0.2, 0.7, UNKNOWN
        return 0.9, 0.05, label

    results = synthetic_telemetry(dataset, chooser)
    stats = raw_decision_stats(dataset, results)
    assert stats["semantic_responses"] == len(dataset.cases)
    assert stats["false_known"] >= 1
    assert stats["false_known"] == len(stats["false_known_ids"])
    errors = sum(results[c.id].selected_choice != labels[c.id] for c in dataset.cases)
    assert stats["overall_accuracy"] == pytest.approx(1 - errors / len(dataset.cases))
    assert stats["false_known"] + stats["false_unknown"] <= errors


def test_policy_frame_covers_all_families_and_argmax(dataset):
    def chooser(case):
        return 0.7, 0.2, UNKNOWN

    results = synthetic_telemetry(dataset, chooser)
    curve = [score(r, tuple(dataset.cases), dataset.labels, results) for r in grid()]
    frame = policy_frame(curve, "calibration")
    assert set(frame) == {
        "A_argmax_only",
        "B_top_probability",
        "C_margin_only",
        "D_unknown_only",
        "E_margin_and_unknown",
        "split",
    }
    # No known-class selection exists, so no decision is continued: rate is undefined.
    assert frame["A_argmax_only"]["trusted_decision_error_rate"] is None
    for name in ("B_top_probability", "C_margin_only", "D_unknown_only", "E_margin_and_unknown"):
        assert frame[name]["coverage_error_points"], name


def test_stratum_sensitivity_runs(dataset):
    def chooser(case):
        return 0.9, 0.05, UNKNOWN

    results = synthetic_telemetry(dataset, chooser)
    rules = (Rule(family="probability_only", min_top=0.5, min_margin=0, max_unknown=1),)
    rows = stratum_rule_sensitivity(dataset, results, rules)
    assert len(rows) == 1
    assert set(rows[0]["per_stratum"]) == {
        "clear_known",
        "near_known",
        "genuine_unknown",
        "ambiguous_overlap",
        "dangerous_false_known",
        "close_top_two",
    }
