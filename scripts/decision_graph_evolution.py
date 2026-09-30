"""Decision-graph evolution proofs (Experiments D-G) with a typed Teacher.

Each experiment: run the graph, diagnose the failed layer deterministically, give
the teacher ONLY that layer's evidence, apply its valid typed candidates to a new
graph version, and re-evaluate on the drifted world plus the regression suite.
One teacher request per candidate; a valid-but-failing candidate is retained and
the experiment stops. No repair loop, no activation without approval records.

Pre-registered budget: <=60 accepted Jev calls and <=10 discovery calls total.
"""

import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from automation_attempts import Attempt
from openclass_core.providers import ProviderError
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent))

import decision_graph as dg  # noqa: E402
from decision_graph_proof import (  # noqa: E402
    Budget,
    ServiceWorld,
    base_graph,
    build_decider,
)

ROOT = Path("build/decision-graph-evolution")
JEV_BUDGET = 60
DISCOVERY_BUDGET = 10


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def save(path: Path, value: Any) -> None:
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False, default=str) + "\n")


def apply_candidate(
    graph: dg.PolicyGraphVersion, candidate: dg.TeacherCandidate
) -> dg.PolicyGraphVersion:
    if candidate.candidate_type == "ADD_CHOICE":
        return dg.apply_add_choice(graph, candidate)
    if candidate.candidate_type == "ADD_MACRO":
        assert candidate.macro is not None
        macro = candidate.macro
        if any(m.id == macro.id for m in graph.macros):
            raise ValueError("macro id already present")
        return dg.PolicyGraphVersion(
            id=graph.id,
            version_number=graph.version_number + 1,
            parent_version_id=graph.id,
            jev_profile_ref=graph.jev_profile_ref,
            entry_node=graph.entry_node,
            nodes=graph.nodes,
            macros=(*graph.macros, macro),
            goal=graph.goal,
        )
    raise ValueError(f"no deterministic applier for {candidate.candidate_type}")


def regression_suite(graph: dg.PolicyGraphVersion, decide: Any) -> list[dict[str, Any]]:
    cases = []
    for scenario, conflict_port in (("regression_standard", 3000), ("regression_alt", 8000)):
        world = ServiceWorld(
            {
                "service": scenario,
                "port_conflict": True,
                "free_port": conflict_port + 1,
                "expected_env_var": "TEST_PORT",
            }
        )
        outcome = asyncio.run(dg.run_graph(graph, world, decide))
        cases.append(
            {
                "case": scenario,
                "status": outcome.status,
                "passed": outcome.status == "completed"
                and world.fields.get("report_written") is True,
            }
        )
    return cases


async def run_outcome(
    world: ServiceWorld, graph: dg.PolicyGraphVersion, decide: Any
) -> dg.GraphRunResult:
    return await dg.run_graph(graph, world, decide)


# --- Teacher adapter (Gemini via gateway; schema from decision_graph) -------


async def ask_teacher(
    key: str,
    evidence: dict[str, Any],
    budget: Budget,
    attempts: list[dict[str, Any]],
    root: Path,
) -> dg.TeacherCandidate:
    system = (
        "You are the OpenClass Teacher. Your role is to improve versioned decision "
        "knowledge used by a bounded semantic decision provider called Jev. "
        "Jev is not a general planner, shell generator, safety authority, or source "
        "of ground truth. Jev chooses among a bounded set of semantic alternatives "
        "supplied by OpenClass. Measured characterization: Jev classifies robustly "
        "up to at least 32 concrete choices; it is degraded by abstract group "
        "descriptions, by anaphoric references to earlier decisions, and at the "
        "borderline between a plausible class and UNKNOWN. "
        "OpenClass executes only registered capabilities and independently verifies "
        "outcomes. A supplied failure diagnosis names the layer that failed. Do not "
        "change a working procedure to repair a routing problem. Do not change "
        "routing to hide an execution failure. "
        "Prefer the smallest reusable change supported by the evidence. Do not add "
        "literal aliases merely to memorize observations when the evidence supports "
        "a stable semantic concept; do not generalize beyond the evidence merely "
        "because abstraction seems elegant. "
        "Preserve known-good behavior. A candidate that gains coverage by regressing "
        "verified previous behavior will normally fail evaluation. "
        "Never invent executable shell, Python, paths, environment variables, "
        "credentials, or primitive names. You may only compose the registered "
        "primitives listed in the evidence. If the required operation is unavailable, "
        "return MISSING_CAPABILITY. "
        "Never assume model output is ground truth. Never activate your own "
        "proposal. Never claim human approval. Hidden evaluation cases are "
        "unavailable to you. If the evidence is insufficient, return "
        "INSUFFICIENT_EVIDENCE. Output only the supplied typed candidate schema."
    )
    payload = {
        "model": os.getenv("OPENCLASS_DISCOVERY_MODEL", "google/gemini-2.5-flash"),
        "temperature": 0,
        "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(evidence)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "teacher_candidate",
                "strict": True,
                "schema": dg.build_candidate_schema(),
            },
        },
    }
    save(root / "teacher-request.json", payload)
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
        response = await client.post(
            "https://ai-gateway.vercel.sh/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        )
        response.raise_for_status()
    body = response.json()
    attempts.append(
        Attempt(
            operation="teacher",
            attempt=1,
            status="response_received",
            latency_ms=(time.perf_counter() - started) * 1000,
            input_tokens=body.get("usage", {}).get("prompt_tokens"),
            output_tokens=body.get("usage", {}).get("completion_tokens"),
        ).model_dump()
    )
    budget.accepted += 1
    content = body["choices"][0]["message"]["content"].strip()
    if content.startswith("```json") and content.endswith("```"):
        content = content[7:-3].strip()
    save(root / "teacher-response.json", json.loads(content))
    return dg.TeacherCandidate.model_validate_json(content)


# --- Experiments -----------------------------------------------------------


async def stage_world(
    key: str,
    budget: Budget,
    graph: dg.PolicyGraphVersion,
    world: ServiceWorld,
    attempts: list[dict[str, Any]],
) -> dg.GraphRunResult:
    decide, _decider = build_decider(key, budget, attempts)
    return await dg.run_graph(graph, world, decide)


def experiment_d(
    key: str,
    discovery_key: str,
    jev_budget: Budget,
    disc_budget: Budget,
    root: Path,
) -> dict[str, Any]:
    """Environment drift: the macro's env step no longer matches the fixture."""
    attempts: list[dict[str, Any]] = []
    world = ServiceWorld(
        {
            "service": "drifted-fixture",
            "port_conflict": True,
            "free_port": 3001,
            "expected_env_var": "SERVICE_TEST_PORT",
        }
    )
    graph_v1 = base_graph()
    outcome_v1 = asyncio.run(stage_world(key, jev_budget, graph_v1, world, attempts))
    v1_record = {
        "status": outcome_v1.status,
        "diagnosis": outcome_v1.diagnosis,
        "detail": outcome_v1.diagnosis_detail,
        "steps": [s.model_dump() for t in outcome_v1.transitions if t.macro for s in t.macro.steps],
    }
    if outcome_v1.status != "diagnosed" or outcome_v1.diagnosis != dg.DiagnosisLayer.PROCEDURE:
        return {
            "experiment": "D_environment_drift",
            "passed": False,
            "v1": v1_record,
            "reason": "expected PROCEDURE diagnosis on the drifted world",
            "provider_attempts": attempts,
        }
    evidence = {
        "diagnosis": outcome_v1.diagnosis,
        "question": (
            "The recovery macro was selected correctly and its earlier steps ran, but "
            "a procedure step failed after an environment change. Diagnose and propose "
            "the smallest reusable change."
        ),
        "registered_primitives": [
            "choose_available_test_port",
            "set_environment",
            "run_tests",
            "inspect_result",
            "write_report",
        ],
        "allowed_operators": list(dg.CANDIDATE_TYPES),
        "applicable_operators_for_this_diagnosis": [
            "ADD_MACRO",
            "ADD_CHOICE",
            "NO_CHANGE",
            "INSUFFICIENT_EVIDENCE",
            "MISSING_CAPABILITY",
        ],
        "section_contract": {
            "ADD_MACRO": {
                "macro": {
                    "id": "snake_case identifier",
                    "semantic_purpose": "what the macro achieves",
                    "preconditions": [{"field": "state field", "equals": "required value"}],
                    "procedure": [{"primitive": "registered primitive", "args": {}}],
                    "postconditions": [{"field": "state field", "equals": "required value"}],
                }
            },
            "ADD_CHOICE": {
                "choice": {
                    "id": "snake_case identifier",
                    "semantic_name": "name the router sees",
                    "description": "one-line semantics",
                    "target_macro": "id of a registered macro",
                }
            },
        },
        "macro_v1": json.loads(graph_v1.macros[0].model_dump_json()),
        "state_at_failure": world.fields,
        "raw_evidence": [
            s.detail for t in outcome_v1.transitions if t.macro for s in t.macro.steps
        ],
        "base_policy_id": graph_v1.id,
    }
    if not disc_budget.allow():
        return {
            "experiment": "D_environment_drift",
            "passed": False,
            "reason": "discovery budget exhausted",
        }
    (root / "teacher-d").mkdir(parents=True, exist_ok=True)
    candidate = asyncio.run(
        ask_teacher(discovery_key, evidence, disc_budget, attempts, root / "teacher-d")
    )
    try:
        graph_v2 = apply_candidate(graph_v1, candidate)
    except (ValueError, ValidationError) as exc:
        save(root / "teacher-d" / "apply-error.json", {"error": str(exc)})
        return {
            "experiment": "D_environment_drift",
            "passed": False,
            "v1": v1_record,
            "candidate": candidate.model_dump(),
            "reason": f"candidate not applicable: {exc}",
            "provider_attempts": attempts,
        }
    world_v2 = ServiceWorld(
        {
            "service": "drifted-fixture",
            "port_conflict": True,
            "free_port": 3001,
            "expected_env_var": "SERVICE_TEST_PORT",
        }
    )
    outcome_v2 = asyncio.run(stage_world(key, jev_budget, graph_v2, world_v2, attempts))
    regressions = regression_suite(graph_v2, build_decider(key, jev_budget, attempts)[0])
    passed = outcome_v2.status == "completed" and all(r["passed"] for r in regressions)
    return {
        "experiment": "D_environment_drift",
        "passed": passed,
        "v1": v1_record,
        "candidate": candidate.model_dump(),
        "graph_v2_version": graph_v2.version_number,
        "v2": {
            "status": outcome_v2.status,
            "diagnosis": outcome_v2.diagnosis,
            "report_written": world_v2.fields.get("report_written"),
        },
        "regressions": regressions,
        "provider_attempts": attempts,
    }


def experiment_e(
    key: str,
    discovery_key: str,
    jev_budget: Budget,
    disc_budget: Budget,
    root: Path,
) -> dict[str, Any]:
    """Decision-space expansion: a failure class the graph cannot represent."""
    attempts: list[dict[str, Any]] = []
    world = ServiceWorld(
        {
            "service": "queue-service",
            "port_conflict": False,
            "expected_env_var": "TEST_PORT",
            "dependency": "postgres",
            "last_output": "connect to postgres:5432: connection refused",
        }
    )
    graph_v1 = base_graph()
    outcome_v1 = asyncio.run(stage_world(key, jev_budget, graph_v1, world, attempts))
    v1_record = {
        "status": outcome_v1.status,
        "diagnosis": outcome_v1.diagnosis,
        "detail": outcome_v1.diagnosis_detail,
        "selections": [{"node": t.node_id, "selected": t.selected} for t in outcome_v1.transitions],
    }
    if outcome_v1.status != "blocked" or outcome_v1.diagnosis != dg.DiagnosisLayer.DECISION_SPACE:
        return {
            "experiment": "E_decision_space_expansion",
            "passed": False,
            "v1": v1_record,
            "reason": "expected DECISION_SPACE block on the unrepresentable failure",
            "provider_attempts": attempts,
        }
    evidence = {
        "diagnosis": "DECISION_SPACE",
        "question": (
            "The router found no offered choice that fits the observed dependency "
            "failure. Propose the missing capability structure: first register the "
            "macro, then add the routing choice. Two candidates."
        ),
        "registered_primitives": [
            "choose_available_test_port",
            "set_environment",
            "run_tests",
            "inspect_result",
            "write_report",
        ],
        "current_choices": [
            {"id": c.id, "description": c.description} for c in graph_v1.nodes[0].choices
        ],
        "state": world.fields,
        "allowed_operators": list(dg.CANDIDATE_TYPES),
        "graph_context": {
            "entry_node_id": graph_v1.entry_node,
            "node_ids": [n.id for n in graph_v1.nodes],
        },
        "id_convention": (
            "Macro and choice ids are unique across the graph; new candidates must "
            "introduce new ids. ADD_CHOICE requires target_id to be the receiving "
            "node's id."
        ),
        "section_contract": {
            "ADD_MACRO": {
                "macro": {
                    "id": "snake_case identifier",
                    "semantic_purpose": "what the macro achieves",
                    "preconditions": [{"field": "state field", "equals": "required value"}],
                    "procedure": [{"primitive": "registered primitive", "args": {}}],
                    "postconditions": [{"field": "state field", "equals": "required value"}],
                }
            },
            "ADD_CHOICE": {
                "choice": {
                    "id": "snake_case identifier",
                    "semantic_name": "name the router sees",
                    "description": "one-line semantics",
                    "target_macro": "id of a registered macro",
                }
            },
        },
        "base_policy_id": graph_v1.id,
    }
    if not disc_budget.allow():
        return {
            "experiment": "E_decision_space_expansion",
            "passed": False,
            "reason": "discovery budget exhausted",
        }
    (root / "teacher-e1").mkdir(parents=True, exist_ok=True)
    macro_candidate = asyncio.run(
        ask_teacher(discovery_key, evidence, disc_budget, attempts, root / "teacher-e1")
    )
    try:
        graph_v2 = apply_candidate(graph_v1, macro_candidate)
    except (ValueError, ValidationError) as exc:
        return {
            "experiment": "E_decision_space_expansion",
            "passed": False,
            "v1": v1_record,
            "candidate": macro_candidate.model_dump(),
            "reason": f"macro candidate not applicable: {exc}",
        }
    evidence2 = {
        **evidence,
        "question": (
            "Add the routing choice for the newly registered recovery macro on node "
            "'incident_commander'. Set target_id to the node id."
        ),
        "registered_macros": [m.id for m in graph_v2.macros],
    }
    if not disc_budget.allow():
        return {
            "experiment": "E_decision_space_expansion",
            "passed": False,
            "reason": "discovery budget exhausted",
        }
    (root / "teacher-e2").mkdir(parents=True, exist_ok=True)
    choice_candidate = asyncio.run(
        ask_teacher(discovery_key, evidence2, disc_budget, attempts, root / "teacher-e2")
    )
    try:
        graph_v3 = apply_candidate(graph_v2, choice_candidate)
    except (ValueError, ValidationError) as exc:
        return {
            "experiment": "E_decision_space_expansion",
            "passed": False,
            "v1": v1_record,
            "candidate": choice_candidate.model_dump(),
            "reason": f"choice candidate not applicable: {exc}",
        }
    outcome_v3 = asyncio.run(stage_world(key, jev_budget, graph_v3, world, attempts))
    regressions = regression_suite(graph_v3, build_decider(key, jev_budget, attempts)[0])
    passed = outcome_v3.status == "completed" and all(r["passed"] for r in regressions)
    return {
        "experiment": "E_decision_space_expansion",
        "passed": passed,
        "v1": v1_record,
        "macro_candidate": macro_candidate.model_dump(),
        "choice_candidate": choice_candidate.model_dump(),
        "graph_versions": [
            graph_v1.version_number,
            graph_v2.version_number,
            graph_v3.version_number,
        ],
        "v3": {"status": outcome_v3.status, "diagnosis": outcome_v3.diagnosis},
        "regressions": regressions,
        "provider_attempts": attempts,
    }


def experiment_d2(
    key: str,
    discovery_key: str,
    jev_budget: Budget,
    disc_budget: Budget,
    root: Path,
) -> dict[str, Any]:
    """Second, failure-informed drift round: the D1 verdict is aggregate evidence."""
    attempts: list[dict[str, Any]] = []
    world = ServiceWorld(
        {
            "service": "drifted-fixture",
            "port_conflict": True,
            "free_port": 3001,
            "expected_env_var": "SERVICE_TEST_PORT",
        }
    )
    graph_v1 = base_graph()
    outcome_v1 = asyncio.run(stage_world(key, jev_budget, graph_v1, world, attempts))
    if outcome_v1.status != "diagnosed" or outcome_v1.diagnosis != dg.DiagnosisLayer.PROCEDURE:
        return {
            "experiment": "D2_environment_drift_informed",
            "passed": False,
            "reason": "expected PROCEDURE diagnosis",
            "provider_attempts": attempts,
        }
    evidence = {
        "diagnosis": "PROCEDURE",
        "question": (
            "The recovery macro was routed correctly but a procedure step failed after "
            "an environment change. A prior valid ADD_MACRO candidate was applied and "
            "deterministically REJECTED: the drifted scenario still failed its "
            "postconditions because the new macro did not adapt the failing step's "
            "arguments. Aggregate verdict only; individual cases are not disclosed. "
            "Ground every procedure argument in the failing step's evidence below."
        ),
        "registered_primitives": [
            "choose_available_test_port",
            "set_environment",
            "run_tests",
            "inspect_result",
            "write_report",
        ],
        "primitive_signatures": {
            "choose_available_test_port": {"preferred": "int"},
            "set_environment": {"name": "string"},
            "run_tests": {},
            "inspect_result": {},
            "write_report": {},
        },
        "failing_step_evidence": [
            "fixture reads SERVICE_TEST_PORT: required environment variable is not set"
        ],
        "macro_v1": json.loads(graph_v1.macros[0].model_dump_json()),
        "state_at_failure": world.fields,
        "allowed_operators": list(dg.CANDIDATE_TYPES),
        "id_convention": (
            "Macro ids are unique across the graph and versions are append-only; "
            "a new macro version must use a new unique id."
        ),
        "empty_args_note": (
            "Empty procedure arguments fall back to built-in defaults; the prior "
            "candidate was rejected because its arguments did not adapt to the "
            "failing step's evidence. Set every argument explicitly."
        ),
        "base_policy_id": graph_v1.id,
    }
    (root / "teacher-d2").mkdir(parents=True, exist_ok=True)
    if not disc_budget.allow():
        return {
            "experiment": "D2_environment_drift_informed",
            "passed": False,
            "reason": "discovery budget exhausted",
        }
    candidate = asyncio.run(
        ask_teacher(discovery_key, evidence, disc_budget, attempts, root / "teacher-d2")
    )
    if candidate.candidate_type != "ADD_MACRO" or candidate.macro is None:
        return {
            "experiment": "D2_environment_drift_informed",
            "passed": False,
            "v1_diagnosis": outcome_v1.diagnosis,
            "candidate": candidate.model_dump(),
            "reason": "teacher did not propose an applicable ADD_MACRO",
        }
    try:
        graph_v2 = apply_candidate(graph_v1, candidate)
    except (ValueError, ValidationError) as exc:
        return {
            "experiment": "D2_environment_drift_informed",
            "passed": False,
            "candidate": candidate.model_dump(),
            "reason": f"not applicable: {exc}",
        }
    evidence2 = {
        **evidence,
        "question": (
            "Register the routing choice for the newly registered macro on node "
            "'incident_commander'. Set target_id to the node id."
        ),
        "registered_macros": [m.id for m in graph_v2.macros],
        "graph_context": {
            "entry_node_id": graph_v2.entry_node,
            "node_ids": [n.id for n in graph_v2.nodes],
        },
    }
    (root / "teacher-d2b").mkdir(parents=True, exist_ok=True)
    if not disc_budget.allow():
        return {
            "experiment": "D2_environment_drift_informed",
            "passed": False,
            "reason": "discovery budget exhausted",
        }
    choice_candidate = asyncio.run(
        ask_teacher(discovery_key, evidence2, disc_budget, attempts, root / "teacher-d2b")
    )
    if choice_candidate.candidate_type != "ADD_CHOICE" or choice_candidate.choice is None:
        return {
            "experiment": "D2_environment_drift_informed",
            "passed": False,
            "macro_candidate": candidate.model_dump(),
            "candidate": choice_candidate.model_dump(),
            "reason": "teacher did not propose ADD_CHOICE",
        }
    try:
        graph_v3 = apply_candidate(graph_v2, choice_candidate)
    except (ValueError, ValidationError) as exc:
        return {
            "experiment": "D2_environment_drift_informed",
            "passed": False,
            "macro_candidate": candidate.model_dump(),
            "candidate": choice_candidate.model_dump(),
            "reason": f"choice not applicable: {exc}",
        }
    world_v2 = ServiceWorld(
        {
            "service": "drifted-fixture",
            "port_conflict": True,
            "free_port": 3001,
            "expected_env_var": "SERVICE_TEST_PORT",
        }
    )
    outcome_v3 = asyncio.run(stage_world(key, jev_budget, graph_v3, world_v2, attempts))
    regressions = regression_suite(graph_v3, build_decider(key, jev_budget, attempts)[0])
    passed = outcome_v3.status == "completed" and all(r["passed"] for r in regressions)
    return {
        "experiment": "D2_environment_drift_informed",
        "passed": passed,
        "macro_candidate": candidate.model_dump(),
        "choice_candidate": choice_candidate.model_dump(),
        "graph_versions": [
            graph_v1.version_number,
            graph_v2.version_number,
            graph_v3.version_number,
        ],
        "v3": {
            "status": outcome_v3.status,
            "diagnosis": outcome_v3.diagnosis,
            "report_written": world_v2.fields.get("report_written"),
        },
        "regressions": regressions,
        "provider_attempts": attempts,
    }


def experiment_e2(
    key: str,
    discovery_key: str,
    jev_budget: Budget,
    disc_budget: Budget,
    root: Path,
) -> dict[str, Any]:
    """Expansion round after MISSING_CAPABILITY: humans register the primitive."""
    attempts: list[dict[str, Any]] = []
    world = ServiceWorld(
        {
            "service": "queue-service",
            "port_conflict": False,
            "expected_env_var": "TEST_PORT",
            "dependency_down": True,
        }
    )
    graph_v1 = base_graph()
    outcome_v1 = asyncio.run(stage_world(key, jev_budget, graph_v1, world, attempts))
    if outcome_v1.status != "blocked" or outcome_v1.diagnosis != dg.DiagnosisLayer.DECISION_SPACE:
        return {
            "experiment": "E2_expansion_after_capability_registration",
            "passed": False,
            "reason": "expected DECISION_SPACE block",
            "provider_attempts": attempts,
        }
    evidence = {
        "diagnosis": "DECISION_SPACE",
        "question": (
            "The router found no offered choice that fits the observed dependency "
            "failure. In response to the earlier MISSING_CAPABILITY result, a new "
            "primitive restart_dependency has been registered by humans. Propose the "
            "missing capability structure: first register the macro, then add the "
            "routing choice. Two candidates."
        ),
        "registered_primitives": [
            "choose_available_test_port",
            "set_environment",
            "run_tests",
            "inspect_result",
            "write_report",
            "restart_dependency",
        ],
        "primitive_signatures": {
            "choose_available_test_port": {"preferred": "int"},
            "set_environment": {"name": "string"},
            "run_tests": {},
            "inspect_result": {},
            "write_report": {},
            "restart_dependency": {},
        },
        "current_choices": [
            {"id": c.id, "description": c.description} for c in graph_v1.nodes[0].choices
        ],
        "state": world.fields,
        "allowed_operators": list(dg.CANDIDATE_TYPES),
        "base_policy_id": graph_v1.id,
    }
    (root / "teacher-e2a").mkdir(parents=True, exist_ok=True)
    if not disc_budget.allow():
        return {
            "experiment": "E2_expansion_after_capability_registration",
            "passed": False,
            "reason": "discovery budget exhausted",
        }
    macro_candidate = asyncio.run(
        ask_teacher(discovery_key, evidence, disc_budget, attempts, root / "teacher-e2a")
    )
    if macro_candidate.candidate_type != "ADD_MACRO" or macro_candidate.macro is None:
        return {
            "experiment": "E2_expansion_after_capability_registration",
            "passed": False,
            "v1_diagnosis": outcome_v1.diagnosis,
            "candidate": macro_candidate.model_dump(),
            "reason": "teacher did not propose ADD_MACRO",
        }
    try:
        graph_v2 = apply_candidate(graph_v1, macro_candidate)
    except (ValueError, ValidationError) as exc:
        return {
            "experiment": "E2_expansion_after_capability_registration",
            "passed": False,
            "candidate": macro_candidate.model_dump(),
            "reason": f"macro not applicable: {exc}",
        }
    evidence2 = {
        **evidence,
        "question": (
            "Add the routing choice for the newly registered recovery macro on node "
            "'incident_commander'. Set target_id to the node id."
        ),
        "registered_macros": [m.id for m in graph_v2.macros],
    }
    (root / "teacher-e2b").mkdir(parents=True, exist_ok=True)
    if not disc_budget.allow():
        return {
            "experiment": "E2_expansion_after_capability_registration",
            "passed": False,
            "reason": "discovery budget exhausted",
        }
    choice_candidate = asyncio.run(
        ask_teacher(discovery_key, evidence2, disc_budget, attempts, root / "teacher-e2b")
    )
    if choice_candidate.candidate_type != "ADD_CHOICE" or choice_candidate.choice is None:
        return {
            "experiment": "E2_expansion_after_capability_registration",
            "passed": False,
            "candidate": choice_candidate.model_dump(),
            "reason": "teacher did not propose ADD_CHOICE",
        }
    try:
        graph_v3 = apply_candidate(graph_v2, choice_candidate)
    except (ValueError, ValidationError) as exc:
        return {
            "experiment": "E2_expansion_after_capability_registration",
            "passed": False,
            "candidate": choice_candidate.model_dump(),
            "reason": f"choice not applicable: {exc}",
        }
    outcome_v3 = asyncio.run(stage_world(key, jev_budget, graph_v3, world, attempts))
    regressions = regression_suite(graph_v3, build_decider(key, jev_budget, attempts)[0])
    passed = outcome_v3.status == "completed" and all(r["passed"] for r in regressions)
    return {
        "experiment": "E2_expansion_after_capability_registration",
        "passed": passed,
        "v1": {"status": outcome_v1.status, "diagnosis": outcome_v1.diagnosis},
        "macro_candidate": macro_candidate.model_dump(),
        "choice_candidate": choice_candidate.model_dump(),
        "graph_versions": [
            graph_v1.version_number,
            graph_v2.version_number,
            graph_v3.version_number,
        ],
        "v3": {"status": outcome_v3.status, "diagnosis": outcome_v3.diagnosis},
        "regressions": regressions,
        "provider_attempts": attempts,
    }


def main() -> int:
    key = os.environ["OPENCLASS_JEV_API_KEY"]
    discovery_key = os.environ.get("AI_GATEWAY_API_KEY", key)
    run_root = ROOT / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root.mkdir(parents=True)
    jev_budget = Budget(JEV_BUDGET)
    disc_budget = Budget(DISCOVERY_BUDGET)
    experiments = []
    for runner in (experiment_d2, experiment_e2):
        try:
            result = runner(key, discovery_key, jev_budget, disc_budget, run_root)
        except (
            ValueError,
            ValidationError,
            httpx.HTTPError,
            ProviderError,
            KeyError,
            TypeError,
        ) as exc:
            result = {
                "experiment": runner.__name__,
                "passed": False,
                "reason": f"{type(exc).__name__}: {exc}",
            }
        experiments.append(result)
        directory = run_root / result["experiment"]
        directory.mkdir()
        save(directory / "result.json", result)
        print(
            json.dumps(
                {
                    "experiment": result["experiment"],
                    "passed": result["passed"],
                    "jev_accepted": jev_budget.accepted,
                    "discovery_accepted": disc_budget.accepted,
                }
            )
        )
    save(
        run_root / "report.json",
        {
            "stage": "D2/E2 evolution proofs (failure-informed round 2)",
            "jev_accepted": jev_budget.accepted,
            "discovery_accepted": disc_budget.accepted,
            "jev_budget": JEV_BUDGET,
            "discovery_budget": DISCOVERY_BUDGET,
            "all_passed": all(e["passed"] for e in experiments),
            "experiments": [e["experiment"] for e in experiments],
        },
    )
    return 0 if all(e["passed"] for e in experiments) else 1


if __name__ == "__main__":
    raise SystemExit(main())
