"""Stage 2 live: Teacher context ablation (Core / +Profile / +Skill / +Examples).

One model (google/gemini-2.5-flash), pre-registered subset of six frozen
packages, four context conditions. No condition sees another's answers. Budget:
24 successful calls, at most two byte-identical retries per call. Scoring is
deterministic against the frozen hidden evaluations.
"""

import argparse
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .canonical import digest
from .knowledge import save_new
from .live_teacher import TeacherBudget, call_teacher
from .precision import FixtureWorld, HiddenEvaluation, checks
from .runtime import execute_macro
from .teacher import ALLOWED, TeacherCandidate, TeacherRequest, apply_candidate, candidate_schema

MODEL = "google/gemini-2.5-flash"
# v2: disclose base_policy_hash uniformly (v1 binding was unsatisfiable).
AMEND_V2 = True
SUBSET = (
    "authored-procedure",
    "frozen-teacher-d2",
    "authored-space",
    "frozen-teacher-e2b",
    "authored-state",
    "frozen-teacher-d2b",
)
CONDITIONS = ("core", "profile", "skill", "examples")
CONTEXT_DIR = Path("build/jev-contract-v1/stage2-ablation-context")
DATASET = Path("benchmarks/jev-contract/v1")


def condition_packet(
    request: TeacherRequest,
    condition: str,
    skill: str,
    examples: str,
    *,
    disclose_base_hash: bool = False,
) -> dict[str, Any]:
    payload = request.model_dump(mode="json", exclude={"profile"})
    if disclose_base_hash:
        # Protocol amendment v2: the v1 candidate binding was unsatisfiable
        # because the required hash was never disclosed. Uniform for all conditions.
        payload["base_policy_hash"] = request.graph_slice.content_hash
    if condition == "core":
        pass
    elif condition == "profile":
        payload["jev_operating_manual"] = request.profile.manual()
    elif condition == "skill":
        payload["jev_operating_manual"] = request.profile.manual()
        payload["jev_skill"] = skill
    elif condition == "examples":
        payload["jev_operating_manual"] = request.profile.manual()
        payload["jev_skill"] = skill
        payload["worked_examples"] = examples
    else:
        raise ValueError(condition)
    payload["profile_hash"] = digest(request.profile.model_dump(mode="json"))
    return {
        "messages": [
            {"role": "system", "content": _system()},
            {"role": "user", "content": json.dumps(payload, sort_keys=True)},
        ],
        "temperature": 0,
        "max_tokens": 4096,
        "response_schema": candidate_schema(request),
    }


def _system() -> str:
    from .teacher import SYSTEM

    return SYSTEM


def graph_delta(base: Any, updated: Any) -> dict[str, Any]:
    changed = []
    base_nodes = {n.id: n for n in base.nodes}
    for node in updated.nodes:
        if base_nodes.get(node.id) != node:
            changed.append(f"node:{node.id}")
    if len(updated.nodes) != len(base.nodes):
        changed.append("node_count")
    base_macros = {m.id: m for m in base.macros}
    for macro in updated.macros:
        if base_macros.get(macro.id) != macro:
            changed.append(f"macro:{macro.id}")
    if len(updated.macros) != len(base.macros):
        changed.append("macro_count")
    if base.state_schema != updated.state_schema:
        changed.append(f"schema:{updated.state_schema.id}")
    return {"changed": changed}


EXPECTED_COMPONENT = {
    "ADD_CHOICE": "node:",
    "GENERALIZE_CHOICE": "node:",
    "REPLACE_PROCEDURE": "macro:",
    "CHANGE_PRECONDITION": "macro:",
    "CHANGE_POSTCONDITION": "macro:",
    "CHANGE_SAFETY_GUARD": "macro:",
    "ADD_STATE_FEATURE": "schema:",
}


def score_response(
    request: TeacherRequest, hidden: HiddenEvaluation, response: dict[str, Any]
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "infrastructure_status": response["infrastructure_status"],
        "schema_valid": False,
        "diagnosis_respected": False,
        "operator_correct": False,
        "target_correct": False,
        "payload_correct": False,
        "arguments_correct": None,
        "registered_capabilities_only": None,
        "jevprofile_respected": None,
        "minimal_change": None,
        "no_unrelated_changes": None,
        "missing_capability_correct": False,
        "insufficient_evidence_correct": False,
        "evaluation_passed": False,
        "regression": None,
        "status": "infrastructure_failure",
    }
    if response["infrastructure_status"] != "ok":
        return report
    try:
        candidate = TeacherCandidate.model_validate_json(response["content"] or "")
    except (ValueError, ValidationError):
        report["status"] = "schema_invalid"
        return report
    report["schema_valid"] = True
    allowed = {*ALLOWED[request.failed_layer], "INSUFFICIENT_EVIDENCE", "PROVIDER_COMPATIBILITY"}
    report["diagnosis_respected"] = candidate.operator in allowed
    report["operator_correct"] = candidate.operator == hidden.operator
    report["target_correct"] = candidate.target_id == hidden.target_id
    report["payload_correct"] = checks(
        candidate.payload.model_dump(mode="json"), hidden.payload_checks
    )
    report["missing_capability_correct"] = (
        hidden.operator == candidate.operator == "MISSING_CAPABILITY"
    )
    report["insufficient_evidence_correct"] = (
        hidden.operator == candidate.operator == ("INSUFFICIENT_EVIDENCE")
    )
    catalog = {c.id: c for c in request.capabilities}
    steps = candidate.payload.steps or ()
    if steps:
        ok = True
        for step in steps:
            capability = catalog.get(step.capability)
            if capability is None:
                ok = False
                break
            try:
                capability.validate_step(step)
            except ValueError:
                ok = False
                break
        report["registered_capabilities_only"] = ok
        report["arguments_correct"] = ok
    else:
        report["registered_capabilities_only"] = True
        report["arguments_correct"] = None
    try:
        graph = apply_candidate(request, candidate)
    except ValueError:
        report["status"] = "application_rejected"
        return report
    report["jevprofile_respected"] = True  # apply_candidate compiles every node
    delta = graph_delta(request.graph_slice, graph)
    prefix = EXPECTED_COMPONENT.get(candidate.operator)
    if prefix is None:
        report["minimal_change"] = not delta["changed"]
        report["no_unrelated_changes"] = candidate.base_policy_hash == (
            request.graph_slice.content_hash
        )
    else:
        report["minimal_change"] = all(part.startswith(prefix) for part in delta["changed"])
        report["no_unrelated_changes"] = (
            candidate.base_policy_hash == request.graph_slice.content_hash
            and len(delta["changed"]) == 1
        )
    value = graph.model_dump(mode="json")
    fixtures_pass = True
    for fixture in hidden.macro_fixtures:
        macro = next((m for m in graph.macros if m.id == fixture.macro_id), None)
        passed = (
            macro is not None
            and execute_macro(macro, FixtureWorld(fixture), request.capabilities) is None
        )
        fixtures_pass &= passed == fixture.expected_pass
    report["regression"] = not checks(value, hidden.regressions)
    report["evaluation_passed"] = (
        report["operator_correct"]
        and report["target_correct"]
        and report["payload_correct"]
        and checks(value, hidden.graph_checks)
        and fixtures_pass
        and not report["regression"]
    )
    report["status"] = "evaluated"
    return report


METRIC_KEYS = (
    "schema_valid",
    "diagnosis_respected",
    "operator_correct",
    "target_correct",
    "payload_correct",
    "arguments_correct",
    "registered_capabilities_only",
    "jevprofile_respected",
    "minimal_change",
    "no_unrelated_changes",
    "missing_capability_correct",
    "insufficient_evidence_correct",
    "evaluation_passed",
)


def summarize(conditions: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for condition, cases in conditions.items():
        rows = [r for r in cases.values() if r["infrastructure_status"] == "ok"]
        metrics: dict[str, Any] = {
            "semantic_responses": len(rows),
            "infrastructure_failures": len(cases) - len(rows),
        }
        for key in METRIC_KEYS:
            values = [r[key] for r in rows if r[key] is not None]
            metrics[key] = sum(values) / len(values) if values else None
            metrics[key + "_denominator"] = len(values)
        regression_denominator = sum(r["regression"] is not None for r in rows)
        metrics["regression"] = (
            sum(bool(r["regression"]) for r in rows if r["regression"] is not None)
            / regression_denominator
            if regression_denominator
            else None
        )
        out[condition] = metrics
    return out


def run(root: Path, key: str) -> int:
    root.mkdir(parents=True)
    skill = (CONTEXT_DIR / "jev-skill.md").read_text()
    examples = (CONTEXT_DIR / "examples.md").read_text()
    requests = {
        r.id: r
        for r in (
            TeacherRequest.model_validate(x)
            for x in json.loads((DATASET / "teacher-packages.json").read_text())
        )
    }
    hidden = {
        k: HiddenEvaluation.model_validate(v)
        for k, v in json.loads((DATASET / "teacher-hidden.json").read_text()).items()
    }
    packets = {
        (condition, rid): condition_packet(
            requests[rid], condition, skill, examples, disclose_base_hash=AMEND_V2
        )
        for condition in CONDITIONS
        for rid in SUBSET
    }
    frozen_hashes = json.loads((DATASET / "protocol.json").read_text())["packet_hashes"]
    from .precision import packet as frozen_packet

    for rid in SUBSET:
        if digest(frozen_packet(requests[rid])) != frozen_hashes[rid]:
            raise ValueError(f"frozen packet drift: {rid}")
        if not AMEND_V2:
            if packets[("profile", rid)] != frozen_packet(requests[rid]):
                raise ValueError(f"condition 'profile' must equal the frozen packet: {rid}")
        else:
            expected = json.loads(json.dumps(frozen_packet(requests[rid])))
            user = json.loads(expected["messages"][1]["content"])
            user["base_policy_hash"] = requests[rid].graph_slice.content_hash
            expected["messages"][1]["content"] = json.dumps(user, sort_keys=True)
            if packets[("profile", rid)] != expected:
                raise ValueError(
                    f"v2 profile condition must equal frozen packet + amendment: {rid}"
                )
    save_new(
        root / "protocol.json",
        {
            "stage": 2,
            "experiment": "teacher-context-ablation",
            "model": MODEL,
            "temperature": 0,
            "conditions": {
                "core": "system + typed request without jev_operating_manual",
                "profile": "the frozen packet (Core + operating manual)",
                "skill": "profile + authored Jev Skill document",
                "examples": "skill + worked examples from frozen D/E evidence",
            },
            "subset": list(SUBSET),
            "subset_rationale": (
                "six packages spanning four diagnosed layers, mixing authored and "
                "historical live-failure packages where Teacher precision failed"
            ),
            "budget_successful_calls": 24,
            "max_identical_retries_per_call": 2,
            "context_artifact_hashes": {
                name: hashlib.sha256((CONTEXT_DIR / name).read_bytes()).hexdigest()
                for name in ("jev-skill.md", "examples.md")
            },
            "condition_packet_hashes": {
                f"{condition}/{rid}": digest(packets[(condition, rid)])
                for condition in CONDITIONS
                for rid in SUBSET
            },
            "cross_condition_isolation": "no condition sees another condition's answers",
            "protocol_amendment_v2": (
                "user content discloses base_policy_hash (graph content hash) for every "
                "condition; the v1 binding was unsatisfiable — see stage2 v1 README"
            )
            if AMEND_V2
            else None,
            "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
    )
    budget = TeacherBudget(24)
    results: dict[str, dict[str, dict[str, Any]]] = {c: {} for c in CONDITIONS}
    order = list(CONDITIONS)
    for index, rid in enumerate(SUBSET):
        rotation = order[index % len(order) :] + order[: index % len(order)]
        for condition in rotation:
            attempts: list[dict[str, Any]] = []
            record = asyncio.run(
                call_teacher(MODEL, packets[(condition, rid)], key, budget, attempts)
            )
            record["attempts"] = attempts
            scored = score_response(requests[rid], hidden[rid], record)
            scored["latency_ms"] = record["latency_ms"]
            scored["input_tokens"] = record["input_tokens"]
            scored["output_tokens"] = record["output_tokens"]
            scored["reported_cost"] = record["reported_cost"]
            case_value: Any = {
                "response": {k: v for k, v in record.items() if k != "attempts"},
                "attempts": attempts,
                "score": scored,
            }
            save_new(root / f"case-{condition}-{rid}.json", case_value)
            results[condition][rid] = scored
            time.sleep(0.8)
    summary = summarize(results)
    report_value: Any = {"summary": summary, "conditions": results}
    save_new(root / "ablation-report.json", report_value)
    print(json.dumps({"successful": budget.successful, "retries": budget.retries}, indent=2))
    print(json.dumps(summary, indent=2, default=str)[:2000])
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    run(args.root, os.environ["AI_GATEWAY_API_KEY"])


if __name__ == "__main__":
    main()
