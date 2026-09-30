"""Stage 1 live: run the frozen calibration dataset through real Jev.

Pre-registered budget: at most 120 accepted Jev inferences; at most 3 transport
attempts per logical case; rate-limit retries are recorded but never semantic
observations. The dataset, labels, profile and rule grid are frozen inputs; this
module only acquires telemetry and reports through calibration.evaluate.
"""

import argparse
import asyncio
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Literal

import httpx
from openclass_core.models import ChoiceResult
from openclass_provider_jev import JevDecisionProvider
from pydantic import SecretStr

from .calibration import CalibrationDataset, Rule, evaluate, grid, load_dataset, score
from .jev import UNKNOWN, CompiledDecision, DecisionTelemetry, JevDecisionCompiler, telemetry
from .knowledge import JevProfile, save_new

JEV_URL = "https://ai-gateway.vercel.sh/typesafe/v1/systemone"
BUDGET_ACCEPTED = 120
MAX_ATTEMPTS_PER_CASE = 3
PACE_SECONDS = 0.6
BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0, 16.0)


class Budget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.accepted = 0
        self.rejected_retries = 0


class BudgetExhausted(Exception):
    pass


class RecordingTransport(httpx.AsyncBaseTransport):
    """Paced, allowlisted Jev transport: attempts bounded per case, never semantic."""

    def __init__(self, budget: Budget, attempts: list[dict[str, Any]]) -> None:
        self.budget = budget
        self.attempts = attempts
        self.inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) != JEV_URL:
            raise AssertionError("only the Jev decision endpoint is permitted")
        if self.budget.accepted >= self.budget.limit:
            raise BudgetExhausted
        response: httpx.Response | None = None
        for number in range(1, MAX_ATTEMPTS_PER_CASE + 1):
            started = time.perf_counter()
            try:
                response = await self.inner.handle_async_request(request)
                await response.aread()
            except httpx.TransportError:
                self.attempts.append(
                    {
                        "attempt": number,
                        "status": "transport_failed",
                        "latency_ms": (time.perf_counter() - started) * 1000,
                    }
                )
                response = None
            else:
                record = {
                    "attempt": number,
                    "status": "http" if response.status_code != 200 else "accepted",
                    "http_status": response.status_code,
                    "latency_ms": (time.perf_counter() - started) * 1000,
                }
                self.attempts.append(record)
                if 200 <= response.status_code < 300:
                    self.budget.accepted += 1
                    return response
                if response.status_code not in {429, 503}:
                    return response
                self.budget.rejected_retries += 1
                response = None
            if number < MAX_ATTEMPTS_PER_CASE:
                await asyncio.sleep(BACKOFF_SECONDS[min(number - 1, len(BACKOFF_SECONDS) - 1)])
        assert response is not None or self.attempts
        if response is None:
            raise httpx.TransportError("case attempts exhausted")
        return response

    async def aclose(self) -> None:
        await self.inner.aclose()


async def call_jev(
    compiled: CompiledDecision, key: str, budget: Budget, attempts: list[dict[str, Any]]
) -> tuple[ChoiceResult | None, str]:
    provider = JevDecisionProvider(
        api_key=SecretStr(key),
        base_url="https://ai-gateway.vercel.sh/typesafe",
        model="typesafe-ai/jev",
        timeout=60,
        max_retries=0,
        transport=RecordingTransport(budget, attempts),
    )
    started = time.perf_counter()
    try:
        result = await provider.choice(compiled.request)
    except Exception as exc:  # recorded as infrastructure; never a semantic value
        return None, f"{type(exc).__name__}"
    return result, f"{(time.perf_counter() - started) * 1000:.1f}ms"


def raw_decision_stats(
    dataset: CalibrationDataset, results: dict[str, DecisionTelemetry]
) -> dict[str, Any]:
    ok = [c for c in dataset.cases if results[c.id].infrastructure_status == "ok"]
    labels = dataset.labels
    selected_unknown = [c for c in ok if results[c.id].selected_choice == UNKNOWN]
    expected_unknown = [c for c in ok if labels[c.id] == UNKNOWN]
    false_known = [
        c for c in ok if labels[c.id] == UNKNOWN and results[c.id].selected_choice != UNKNOWN
    ]
    false_unknown = [
        c for c in ok if labels[c.id] != UNKNOWN and results[c.id].selected_choice == UNKNOWN
    ]
    correct = [c for c in ok if results[c.id].selected_choice == labels[c.id]]
    tp = len([c for c in expected_unknown if results[c.id].selected_choice == UNKNOWN])
    precision = tp / len(selected_unknown) if selected_unknown else None
    recall = tp / len(expected_unknown) if expected_unknown else None
    per_stratum = {}
    for stratum in sorted({c.stratum for c in dataset.cases}):
        members = [c for c in ok if c.stratum == stratum]
        per_stratum[stratum] = {
            "cases": len(members),
            "accuracy": sum(results[c.id].selected_choice == labels[c.id] for c in members)
            / len(members)
            if members
            else None,
            "selected_unknown": sum(results[c.id].selected_choice == UNKNOWN for c in members),
            "expected_unknown": sum(labels[c.id] == UNKNOWN for c in members),
        }
    return {
        "semantic_responses": len(ok),
        "overall_accuracy": len(correct) / len(ok) if ok else None,
        "unknown_precision": precision,
        "unknown_recall": recall,
        "false_known": len(false_known),
        "false_known_ids": [c.id for c in false_known],
        "false_unknown": len(false_unknown),
        "false_unknown_ids": [c.id for c in false_unknown],
        "per_stratum": per_stratum,
    }


def policy_frame(curve: list[dict[str, Any]], split: str) -> dict[str, Any]:
    """Map the pre-registered rule grid to the A-F supervision policy families."""
    by_family: dict[str, list[dict[str, Any]]] = {}
    for row in curve:
        rule = row["rule"]
        if rule["family"] == "probability_only":
            by_family.setdefault("B_top_probability", []).append(row)
        elif rule["max_unknown"] >= 1.0:
            by_family.setdefault("C_margin_only", []).append(row)
        elif rule["min_margin"] <= 0.0:
            by_family.setdefault("D_unknown_only", []).append(row)
        else:
            by_family.setdefault("E_margin_and_unknown", []).append(row)
    argmax_row = next(
        r
        for r in curve
        if r["rule"]["family"] == "probability_only" and r["rule"]["min_top"] == 0.0
    )
    summary: dict[str, Any] = {
        "A_argmax_only": {
            "rule": argmax_row["rule"],
            "trusted_decision_error_rate": argmax_row["selective_error_rate"],
            "escalation_rate": 1 - argmax_row["coverage"]
            if argmax_row["coverage"] is not None
            else None,
            **{
                k: argmax_row[k]
                for k in ("coverage", "correct_known_coverage", "false_known", "selective_errors")
            },
        },
    }
    for name in ("B_top_probability", "C_margin_only", "D_unknown_only", "E_margin_and_unknown"):
        rows = sorted(
            by_family.get(name, []),
            key=lambda r: (
                r["false_known"],
                r["selective_errors"],
                -r["continued"],
                json.dumps(r["rule"], sort_keys=True),
            ),
        )
        summary[name] = {
            "best_on_split_by_predeclared_objective": rows[0] if rows else None,
            "coverage_error_points": [
                {
                    "rule": r["rule"],
                    "coverage": r["coverage"],
                    "trusted_decision_error_rate": r["selective_error_rate"],
                    "false_known": r["false_known"],
                    "wilson_95": r["error_interval_95_wilson"],
                }
                for r in sorted(by_family.get(name, []), key=lambda r: -(r["coverage"] or 0))
            ],
        }
    summary["split"] = split
    return summary


def stratum_rule_sensitivity(
    dataset: CalibrationDataset, results: dict[str, DecisionTelemetry], rules: tuple[Rule, ...]
) -> list[dict[str, Any]]:
    """Do strata need different thresholds? Per-stratum continuation/error for key rules."""
    rows = []
    for rule in rules:
        per = {}
        for stratum in sorted({c.stratum for c in dataset.cases}):
            members = tuple(c for c in dataset.cases if c.stratum == stratum)
            row = score(rule, members, dataset.labels, results)
            per[stratum] = {
                "coverage": row["coverage"],
                "selective_error_rate": row["selective_error_rate"],
                "false_known": row["false_known"],
            }
        rows.append({"rule": rule.model_dump(), "per_stratum": per})
    return rows


async def acquire(
    dataset: CalibrationDataset, profile: JevProfile, key: str, budget: Budget
) -> tuple[dict[str, DecisionTelemetry], dict[str, Any]]:
    compiler = JevDecisionCompiler(profile)
    results: dict[str, DecisionTelemetry] = {}
    attempts_log: dict[str, list[dict[str, Any]]] = {}
    for index, case in enumerate(dataset.cases, 1):
        if index > 1:
            await asyncio.sleep(PACE_SECONDS)
        compiled = compiler.compile(case.node, case.snapshot)
        attempts: list[dict[str, Any]] = []
        result, _note = await call_jev(compiled, key, budget, attempts)
        attempts_log[case.id] = attempts
        failure: Literal["transport", "http"] = "transport"
        for attempt in reversed(attempts):
            if attempt.get("status") == "http":
                failure = "http"
                break
            if attempt.get("status") == "transport_failed":
                break
        record = telemetry(
            compiled,
            profile,
            result,
            latency_ms=0.0,
            retry_count=max(len(attempts) - 1, 0),
            simulated=False,
            failure=failure,
        )
        if attempts:
            record = record.model_copy(
                update={"latency_ms": sum(a["latency_ms"] for a in attempts if "latency_ms" in a)}
            )
        results[case.id] = record
    return results, attempts_log


def run(root: Path, key: str, dataset_root: Path) -> int:
    dataset = load_dataset(dataset_root)
    profile = JevProfile.model_validate_json((dataset_root / "profile.json").read_text())
    root.mkdir(parents=True)
    freeze_manifest = json.loads((dataset_root / "benchmark-sha256.json").read_text())
    inputs_ok = all(
        hashlib.sha256((dataset_root / name).read_bytes()).hexdigest() == expected
        for name, expected in freeze_manifest.items()
        if name
        in {"calibration-cases.json", "calibration-labels.json", "profile.json", "protocol.json"}
    )
    if not inputs_ok:
        raise ValueError("frozen calibration inputs changed")
    save_new(
        root / "protocol.json",
        {
            "stage": 1,
            "experiment": "jev-supervision-calibration-live",
            "authorized_budget_accepted": BUDGET_ACCEPTED,
            "max_attempts_per_case": MAX_ATTEMPTS_PER_CASE,
            "pace_seconds": PACE_SECONDS,
            "retry_policy": "429/503 exponential backoff; retries are never semantic observations",
            "inputs_verified_against_freeze": True,
            "profile_hash": hashlib.sha256(
                (dataset_root / "profile.json").read_bytes()
            ).hexdigest(),
            "policy_families": {
                "A": "argmax only (accept every known-class selection)",
                "B": "top-probability threshold (probability_only family)",
                "C": "margin threshold (max_unknown unconstrained)",
                "D": "UNKNOWN-probability threshold (min_margin unconstrained)",
                "E": "margin + UNKNOWN combined",
                "F": "calibrated rule selected only on the calibration split",
            },
            "primary_metric": (
                "trusted_decision_error_rate = selective_error_rate among continued decisions"
            ),
            "implementation_sha256": {
                name: hashlib.sha256(Path(__file__).parent.joinpath(name).read_bytes()).hexdigest()
                for name in ("stage1_live.py", "calibration.py", "jev.py")
            },
            "node_scope_note": (
                "Dataset contains one decision node; cross-node calibration necessity "
                "cannot be assessed here and is reported as a limitation."
            ),
        },
    )
    budget = Budget(BUDGET_ACCEPTED)
    results, attempts_log = asyncio.run(acquire(dataset, profile, key, budget))
    save_new(root / "attempts.json", attempts_log)
    save_new(
        root / "results.json",
        {k: v.model_dump(mode="json") for k, v in results.items()},
    )
    report = evaluate(dataset, results)
    save_new(root / "calibration-report.json", report)
    train = tuple(c for c in dataset.cases if c.split == "calibration")
    holdout = tuple(c for c in dataset.cases if c.split == "validation")
    analysis = {
        "raw_decisions": raw_decision_stats(dataset, results),
        "budget": {
            "accepted": budget.accepted,
            "limit": budget.limit,
            "rejected_retries": budget.rejected_retries,
            "attempt_histogram": dict(Counter(len(v) for v in attempts_log.values())),
        },
        "policies_calibration_split": policy_frame(
            [score(r, train, dataset.labels, results) for r in grid()], "calibration"
        ),
        "policies_validation_split_descriptive": policy_frame(
            [score(r, holdout, dataset.labels, results) for r in grid()], "validation"
        ),
        "selected_F_on_validation": report["held_out_validation"],
        "stratum_threshold_sensitivity": stratum_rule_sensitivity(
            dataset,
            results,
            tuple(
                rule
                for rule in grid()
                if rule
                in {Rule(family="probability_only", min_top=0.5, min_margin=0, max_unknown=1)}
                or (
                    rule.family == "margin_unknown"
                    and rule.min_margin in {0.2, 0.3, 0.4}
                    and rule.max_unknown in {0.2, 0.3}
                )
            ),
        ),
        "claims barred": [
            "no probability calibration claim",
            "no universal threshold claim from one node",
            "held-out results cannot authorize execution",
        ],
    }
    save_new(root / "analysis.json", analysis)
    print(
        json.dumps(
            {
                "accepted": budget.accepted,
                "semantic": analysis["raw_decisions"]["semantic_responses"],
                "overall_accuracy": analysis["raw_decisions"]["overall_accuracy"],
                "false_known": analysis["raw_decisions"]["false_known"],
                "false_unknown": analysis["raw_decisions"]["false_unknown"],
                "root": str(root),
            }
        )
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--key-env", default="OPENCLASS_JEV_API_KEY")
    parser.add_argument("--dataset", type=Path, default=Path("benchmarks/jev-contract/v1"))
    args = parser.parse_args()
    import os

    run(args.root, os.environ[args.key_env], args.dataset)


if __name__ == "__main__":
    main()
