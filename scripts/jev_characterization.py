"""Standalone Jev characterization: measured operating profile, no learning.

Runs the locked benchmark in benchmarks/jev/manifest.json against the real Jev
endpoint. No discovery provider, no macros, no policy evolution. Predictions are
never written back into the benchmark; expected labels stay human-authored. The
request budget is enforced inside the transport: the request that would exceed it
is never sent.
"""

import asyncio
import hashlib
import json
import os
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
from automation_attempts import Attempt, JevRetryTransport
from openclass_core.models import (
    ChoiceRequest,
    ChoiceResult,
    Observation,
    OntologyClass,
    OntologyVersion,
)
from openclass_core.providers import ProviderError
from openclass_provider_jev import JevDecisionProvider
from pydantic import SecretStr

MANIFEST = Path("benchmarks/jev/manifest.json")
PROTOCOL_DOC = Path("docs/research/jev-characterization.md")
JEV_URL = "https://ai-gateway.vercel.sh/typesafe/v1/systemone"
UNKNOWN_LABEL = "UNKNOWN"
FIXED_TIME = datetime(2026, 9, 24, tzinfo=UTC)
RUN_ROOT = Path("build/jev-characterization")
BUDGET_LIMIT = 250
# Protocol v2: the gateway rejects bursts with 429. Pace requests and retry
# 429/503 with backoff; only accepted (2xx) responses count against the budget.
RATE_LIMIT_STATUS = {429, 503}
BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0, 16.0)
PACE_SECONDS = 0.5


class BudgetExhausted(Exception):
    """The next live request would exceed the authorized budget; it is not sent."""


class Budget:
    """Counts accepted inferences across all runs of this characterization."""

    def __init__(self, limit: int, used: int = 0) -> None:
        self.limit = limit
        self.used = used
        self.accepted = 0
        self.rate_limited = 0

    def allow(self) -> bool:
        return self.used + self.accepted < self.limit


class BudgetedJevTransport(JevRetryTransport):
    """Allowlisted Jev transport with 429/503 backoff; accepted calls only budget."""

    def __init__(
        self,
        budget: Budget,
        record: Any,
        inner: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(record, inner)
        self.budget = budget

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) != JEV_URL:
            raise AssertionError("Only the Jev decision endpoint is permitted")
        if not self.budget.allow():
            raise BudgetExhausted
        for delay in (0.0, *BACKOFF_SECONDS):
            if delay:
                await asyncio.sleep(delay)
            response = await super().handle_async_request(request)
            if 200 <= response.status_code < 300:
                self.budget.accepted += 1
                return response
            if response.status_code not in RATE_LIMIT_STATUS:
                return response  # failed at the server; no inference, no budget use
            self.budget.rate_limited += 1
        return response


def build_transport(budget: Budget, record: Any) -> BudgetedJevTransport:
    return BudgetedJevTransport(budget, record)


def prior_accepted() -> int:
    """Accepted inferences consumed by earlier runs of this characterization."""
    total = 0
    for directory in sorted(RUN_ROOT.glob("*")):
        summary = directory / "summary.json"
        if summary.exists():
            total += int(json.loads(summary.read_text()).get("ok_cases", 0))
    return total


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def save(path: Path, value: Any) -> None:
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def load_cases(manifest_path: Path) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text())
    cases: list[dict[str, Any]] = manifest["cases"]
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)) or len(ids) != manifest["case_count"]:
        raise ValueError("manifest case ids are not unique or count mismatch")
    for entry in cases:
        names = {k["canonical_name"] for k in entry["classes"]}
        if entry["expected"] != UNKNOWN_LABEL and entry["expected"] not in names:
            raise ValueError(f"expected label missing from choice set: {entry['id']}")
    return cases


def ontology_for(entry: dict[str, Any]) -> OntologyVersion:
    classes = tuple(
        OntologyClass(
            stable_class_id=uuid5(NAMESPACE_URL, f"jev-char/{entry['id']}/{k['canonical_name']}"),
            **k,
        )
        for k in entry["classes"]
    )
    return OntologyVersion(
        id=uuid5(NAMESPACE_URL, f"jev-char/ontology/{entry['id']}"),
        classifier_id=uuid5(NAMESPACE_URL, "jev-char/classifier"),
        version_number=1,
        classes=classes,
        created_by="jev-characterization",
        created_at=FIXED_TIME,
    )


def decide(result: ChoiceResult) -> str:
    """Pre-registered rule: argmax over known classes; UNKNOWN wins ties."""
    if not result.probabilities:
        return UNKNOWN_LABEL
    top_name, top_value = max(result.probabilities.items(), key=lambda kv: kv[1])
    if result.unknown_probability >= top_value:
        return UNKNOWN_LABEL
    return top_name


def margins(result: ChoiceResult) -> tuple[float, float]:
    ordered = sorted(result.probabilities.values(), reverse=True)
    top = ordered[0] if ordered else 0.0
    second = ordered[1] if len(ordered) > 1 else 0.0
    return top, top - second


async def run_case(
    entry: dict[str, Any],
    budget: Budget,
    key: str,
    model: str,
    sequence: int,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []

    def record(attempt: Attempt) -> None:
        attempts.append(attempt.model_dump())

    record_base = {
        "id": entry["id"],
        "suite": entry["suite"],
        "sequence": sequence,
        "expected": entry["expected"],
        **{
            k: v
            for k, v in entry.items()
            if k not in {"id", "suite", "classes", "observation", "expected"}
        },
    }
    try:
        transport = build_transport(budget, record)
        provider = JevDecisionProvider(
            api_key=SecretStr(key),
            base_url="https://ai-gateway.vercel.sh/typesafe",
            model=model,
            timeout=60,
            max_retries=0,
            transport=transport,
        )
        result = await provider.choice(
            ChoiceRequest(
                observation=Observation(content=entry["observation"]),
                ontology=ontology_for(entry),
            )
        )
    except (ProviderError, AssertionError) as exc:
        return {
            **record_base,
            "status": "infrastructure_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "provider_attempts": attempts,
        }
    top, margin = margins(result)
    selected = decide(result)
    return {
        **record_base,
        "status": "ok",
        "selected": selected,
        "correct": selected == entry["expected"],
        "top_known_probability": top,
        "margin": margin,
        "probabilities": result.probabilities,
        "unknown_probability": result.unknown_probability,
        "confidence": result.provider_metadata.get("confidence"),
        "latency_ms": result.latency_ms,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "estimated_cost": result.estimated_cost,
        "provider_attempts": attempts,
    }


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def accuracy(records: list[dict[str, Any]]) -> float | None:
    ok = [r for r in records if r["status"] == "ok"]
    return sum(1 for r in ok if r["correct"]) / len(ok) if ok else None


def by(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record.get(field))].append(record)
    return {key: accuracy(value) for key, value in sorted(groups.items())}


def summarize(records: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in records if r["status"] == "ok"]
    expected_unknown = [r for r in ok if r["expected"] == UNKNOWN_LABEL]
    expected_known = [r for r in ok if r["expected"] != UNKNOWN_LABEL]
    tp = sum(1 for r in expected_unknown if r["selected"] == UNKNOWN_LABEL)
    fp = sum(1 for r in expected_known if r["selected"] == UNKNOWN_LABEL)
    fn = len(expected_unknown) - tp
    correct_margins = [r["margin"] for r in ok if r["correct"]]
    wrong_margins = [r["margin"] for r in ok if not r["correct"]]
    paraphrase_pairs: dict[int, list[dict[str, Any]]] = defaultdict(list)
    order_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    repeat_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    depth_chains: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    hierarchy: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    reobservation: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for record in ok:
        suite = record["suite"]
        if suite == "F_paraphrase":
            paraphrase_pairs[record["pair"]].append(record)
        elif suite == "G_order_sensitivity":
            order_groups[record["group"]].append(record)
        elif suite == "I_repeatability":
            repeat_groups[record["group"]].append(record)
        elif suite == "K_decision_depth":
            scenario = record.get("scenario")
            if scenario is not None:
                depth_chains[str(scenario)][record["depth"]] = record
        elif suite == "J_flat_vs_hierarchical":
            scenario = record.get("scenario")
            if scenario is not None:
                hierarchy[str(scenario)][record["stage"]] = record
        elif suite == "N_reobservation":
            scenario = record.get("scenario")
            if scenario is not None:
                reobservation[str(scenario)][record["step"]] = record
    paraphrase_disagreement = [
        pair
        for pair, members in paraphrase_pairs.items()
        if len({m["selected"] for m in members}) > 1
    ]
    order_stable = [
        group
        for group, members in order_groups.items()
        if len({m["selected"] for m in members}) == 1
    ]
    repeat_stats = []
    for group, members in sorted(repeat_groups.items()):
        selections = [m["selected"] for m in members if m["selected"] != UNKNOWN_LABEL]
        probs = [
            m["probabilities"][s]
            for m, s in zip(members, selections, strict=False)
            if s in m["probabilities"]
        ]
        repeat_stats.append(
            {
                "group": group,
                "distinct_selections": len({m["selected"] for m in members}),
                "selected_probability_spread": round(max(probs) - min(probs), 6) if probs else None,
            }
        )
    hierarchy_stage1 = [
        members["hierarchy_level1"]
        for members in hierarchy.values()
        if "hierarchy_level1" in members
    ]
    hierarchy_stage2 = [
        members["hierarchy_level2"]
        for members in hierarchy.values()
        if "hierarchy_level2" in members
    ]
    hierarchy_paths = [
        members
        for members in hierarchy.values()
        if "hierarchy_level1" in members and "hierarchy_level2" in members
    ]
    depth_paths = {}
    for depth in (1, 2, 3, 4):
        paths = [
            chain
            for chain in depth_chains.values()
            if all(stage in chain for stage in range(1, depth + 1))
        ]
        if paths:
            depth_paths[f"depth_{depth}"] = sum(
                1
                for chain in paths
                if all(chain[stage]["correct"] for stage in range(1, depth + 1))
            ) / len(paths)
    both_steps = [members for members in reobservation.values() if len(members) == 2]
    l_positive = [r for r in ok if r["suite"] == "L_changed_wording" and r.get("kind") == "pos"]
    l_negative = [r for r in ok if r["suite"] == "L_changed_wording" and r.get("kind") == "neg"]
    l_control = [r for r in ok if r["suite"] == "L_changed_wording" and r.get("kind") == "control"]
    return {
        "planned_cases": len(cases),
        "ok_cases": len(ok),
        "infrastructure_failures": len(records) - len(ok),
        "overall_accuracy": accuracy(records),
        "unknown_precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "unknown_recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "false_known_rate": round(fn / len(expected_unknown), 4) if expected_unknown else None,
        "false_unknown_rate": round(fp / len(expected_known), 4) if expected_known else None,
        "latency_p50_ms": percentile([r["latency_ms"] for r in ok], 0.50),
        "latency_p95_ms": percentile([r["latency_ms"] for r in ok], 0.95),
        "total_input_tokens": sum(r["input_tokens"] or 0 for r in ok),
        "total_output_tokens": sum(r["output_tokens"] or 0 for r in ok),
        "total_reported_cost": sum(r["estimated_cost"] or 0 for r in ok),
        "margin_when_correct_mean": (
            round(sum(correct_margins) / len(correct_margins), 4) if correct_margins else None
        ),
        "margin_when_wrong_mean": (
            round(sum(wrong_margins) / len(wrong_margins), 4) if wrong_margins else None
        ),
        "suite_accuracy": {
            suite: accuracy([r for r in records if r["suite"] == suite])
            for suite in sorted({r["suite"] for r in records})
        },
        "B_accuracy_by_size": by(
            [r for r in records if r["suite"] == "B_choice_space_size"], "size"
        ),
        "C_accuracy_by_similarity": by(
            [r for r in records if r["suite"] == "C_choice_similarity"], "similarity"
        ),
        "D_accuracy_by_style": by(
            [r for r in records if r["suite"] == "D_choice_representation"], "style"
        ),
        "E_accuracy_by_style": by(
            [r for r in records if r["suite"] == "E_input_representation"], "style"
        ),
        "F_paraphrase_disagreement_rate": round(
            len(paraphrase_disagreement) / len(paraphrase_pairs), 4
        )
        if paraphrase_pairs
        else None,
        "G_order_stable_rate": round(len(order_stable) / len(order_groups), 4)
        if order_groups
        else None,
        "G_accuracy_by_order": by(
            [r for r in records if r["suite"] == "G_order_sensitivity"], "order"
        ),
        "H_selections_by_grade": {
            grade: {
                "accuracy": accuracy([r for r in ok if r.get("grade") == grade]),
                "selected": {
                    label: [r["selected"] for r in ok if r.get("grade") == grade].count(label)
                    for label in sorted({r["selected"] for r in ok if r.get("grade") == grade})
                },
            }
            for grade in sorted({str(r.get("grade")) for r in ok if r.get("grade")})
        },
        "I_repeat_groups": repeat_stats,
        "J_flat_accuracy": accuracy([r for r in ok if r.get("stage") == "flat"]),
        "J_hierarchy_stage1_accuracy": accuracy(hierarchy_stage1),
        "J_hierarchy_stage2_accuracy": accuracy(hierarchy_stage2),
        "J_hierarchy_path_accuracy": (
            sum(
                1
                for members in hierarchy_paths
                if members["hierarchy_level1"]["correct"] and members["hierarchy_level2"]["correct"]
            )
            / len(hierarchy_paths)
        )
        if hierarchy_paths
        else None,
        "K_path_success_by_depth": depth_paths,
        "L_positive_wording_accuracy": accuracy(l_positive),
        "L_in_set_negative_accuracy": accuracy(l_negative),
        "L_out_of_set_control": (
            {
                "expected": UNKNOWN_LABEL,
                "selected": [r["selected"] for r in l_control],
            }
            if l_control
            else None
        ),
        "M_accuracy_by_noise": by(
            [r for r in records if r["suite"] == "M_distractor_evidence"], "noise"
        ),
        "N_step_accuracy": by([r for r in ok if r["suite"] == "N_reobservation"], "step"),
        "N_both_steps_correct_rate": (
            sum(1 for members in both_steps if all(m["correct"] for m in members.values()))
            / len(both_steps)
        )
        if both_steps
        else None,
    }


async def _execute_cases(
    cases: list[dict[str, Any]], budget: Budget, key: str
) -> tuple[list[tuple[int, dict[str, Any]]], str]:
    executed: list[tuple[int, dict[str, Any]]] = []
    status = "completed"
    for sequence, entry in enumerate(cases, 1):
        if sequence > 1:
            await asyncio.sleep(PACE_SECONDS)
        try:
            record = await run_case(entry, budget, key, "typesafe-ai/jev", sequence)
        except BudgetExhausted:
            status = "budget_exhausted"
            break
        executed.append((sequence, record))
    return executed, status


def execute(
    root: Path,
    manifest_path: Path,
    key: str,
    budget_limit: int | None = None,
    used: int = 0,
) -> int:
    cases = load_cases(manifest_path)
    manifest_bytes = manifest_path.read_bytes()
    budget = Budget(budget_limit if budget_limit is not None else BUDGET_LIMIT, used=used)
    save(
        root / "protocol.json",
        {
            "benchmark": "jev-characterization-baseline",
            "protocol_version": 2,
            "model": "typesafe-ai/jev",
            "base_url": "https://ai-gateway.vercel.sh/typesafe",
            "decision_rule": "argmax over known probabilities; UNKNOWN wins ties",
            "request_budget": budget.limit,
            "budget_counts": (
                "accepted (2xx) provider responses across all runs of this "
                "characterization; 429/503-rejected requests are retried with "
                "backoff and do not consume the budget"
            ),
            "budget_used_before_this_run": used,
            "rate_limit_backoff_seconds": list(BACKOFF_SECONDS),
            "pace_seconds": PACE_SECONDS,
            "manifest_sha256": sha(manifest_bytes),
            "protocol_doc_sha256": sha(PROTOCOL_DOC.read_bytes()),
            "implementation_sha256": {
                name: sha(Path(__file__).with_name(name).read_bytes())
                for name in ("jev_characterization.py", "automation_attempts.py")
            },
            "labels_source": "human-authored manifest only",
            "tuning_during_run": False,
        },
    )
    evaluation_set = [
        {
            "id": entry["id"],
            "suite": entry["suite"],
            "expected": entry["expected"],
            **{
                k: v
                for k, v in entry.items()
                if k not in {"id", "suite", "classes", "observation", "expected"}
            },
        }
        for entry in cases
    ]
    save(root / "evaluation-set.json", evaluation_set)
    save(
        root / "evaluation-set.sha256",
        {"sha256": sha((root / "evaluation-set.json").read_bytes())},
    )
    started = time.perf_counter()
    executed, status = asyncio.run(_execute_cases(cases, budget, key))
    for sequence, record in executed:
        save(root / f"case-{sequence:03d}.json", record)
    records = [record for _, record in executed]
    summary = summarize(records, cases)
    save(root / "summary.json", summary)
    if not any(r["status"] == "ok" for r in records) and status == "completed":
        status = "infrastructure_failed"
    report = {
        "experiment": "Jev characterization baseline",
        "root": str(root),
        "status": status,
        "cases_executed": len(records),
        "accepted_inferences": budget.accepted,
        "rate_limited_requests": budget.rate_limited,
        "budget_used_including_this_run": used + budget.accepted,
        "request_budget": budget.limit,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
        "summary": str(root / "summary.json"),
    }
    save(root / "report.json", report)
    print(
        json.dumps(
            {
                "status": status,
                "cases": len(records),
                "accepted": budget.accepted,
                "rate_limited": budget.rate_limited,
            }
        )
    )
    return {"completed": 0, "infrastructure_failed": 2}.get(status, 3)


def freeze(root: Path, key: str) -> None:
    leaked = [
        str(path.relative_to(root))
        for path in sorted(root.rglob("*"))
        if path.is_file() and key and key in path.read_text(errors="ignore")
    ]
    save(
        root / "integrity.json",
        {
            "secret_material_absent": not leaked,
            "budget_within_250": json.loads((root / "report.json").read_text())["request_budget"]
            <= 250,
            "labels_from_manifest_only": True,
        },
    )
    manifest = {
        str(path.relative_to(root)): sha(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name not in {"sha256.json"}
    }
    save(root / "sha256.json", manifest)
    if leaked:
        raise ValueError("secret material found in artifacts")


def main() -> int:
    key = os.environ["OPENCLASS_JEV_API_KEY"]
    root = RUN_ROOT / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root.mkdir(parents=True)
    exit_code: int = execute(root, MANIFEST, key, used=prior_accepted())
    freeze(root, key)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
