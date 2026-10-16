"""Dependency-free metrics; failures are not semantic UNKNOWN predictions."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from .dataset import LABELS, ExperimentError


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def quantile(values: list[float], probability: float) -> float | None:
    """Linear interpolation at (n-1)*p, the inclusive/type-7 quantile."""
    if not 0 <= probability <= 1 or any(not math.isfinite(v) or v < 0 for v in values):
        raise ExperimentError("invalid quantile input")
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matrix = {actual: dict.fromkeys(LABELS, 0) for actual in LABELS}
    successful = [r for r in rows if r.get("error") is None]
    trusted = [r for r in successful if r.get("trusted") is True]
    for row in successful:
        if row.get("expected") not in LABELS or row.get("predicted") not in LABELS:
            raise ExperimentError("invalid metric label")
        matrix[row["expected"]][row["predicted"]] += 1
    correct = sum(matrix[label][label] for label in LABELS)
    f1: list[float] = []
    for label in LABELS:
        tp = matrix[label][label]
        actual = sum(matrix[label].values())
        predicted = sum(matrix[a][label] for a in LABELS)
        f1.append(2 * tp / (actual + predicted) if actual + predicted else 0.0)
    unknown_tp = matrix["UNKNOWN"]["UNKNOWN"]
    latencies = [
        float(r["api_elapsed_ms"])
        for r in rows
        if r.get("warm") is True and r.get("api_elapsed_ms") is not None
    ]
    return {
        "count": len(rows),
        "successful": len(successful),
        "failures": len(rows) - len(successful),
        "accuracy": ratio(correct, len(successful)),
        "accuracy_all_attempts": ratio(correct, len(rows)),
        "macro_f1": sum(f1) / len(LABELS) if successful else None,
        "macro_f1_policy": "fixed four-label macro; unsupported labels contribute zero",
        "confusion_matrix": matrix,
        "unknown_precision": ratio(unknown_tp, sum(matrix[a]["UNKNOWN"] for a in LABELS)),
        "unknown_recall": ratio(unknown_tp, sum(matrix["UNKNOWN"].values())),
        "semantic_coverage": ratio(
            sum(r["predicted"] != "UNKNOWN" for r in successful), len(successful)
        ),
        "trusted_count": len(trusted),
        "trusted_sample_coverage": ratio(len(trusted), len(rows)),
        "errors_among_trusted": (
            sum(r["expected"] != r["predicted"] for r in trusted) if trusted else None
        ),
        "trusted_error_rate": ratio(
            sum(r["expected"] != r["predicted"] for r in trusted), len(trusted)
        ),
        "api_warm_latency_ms": {
            "count": len(latencies),
            "p50": quantile(latencies, 0.5),
            "p95": quantile(latencies, 0.95),
            "quantile": "type-7 linear (n-1)*p",
            "includes_failed_attempts": True,
        },
        "errors": dict(Counter(r["error"] for r in rows if r.get("error") is not None)),
        "failure_analysis": [
            {k: r.get(k) for k in ("id", "category", "expected", "predicted", "error")}
            for r in rows
            if r.get("error") is not None or r["expected"] != r["predicted"]
        ],
    }


def grouped(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = sorted({(r["language"], r["checkpoint"], r["split"]) for r in rows})
    return {
        "/".join(key): summarize(
            [r for r in rows if (r["language"], r["checkpoint"], r["split"]) == key]
        )
        for key in keys
    }
