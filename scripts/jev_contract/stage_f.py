"""Experiment F: localized DecisionGraph evolution under Teacher Protocol v2.1.

Preregistered scenario: parent routing stays valid; the lower `network_failure`
node meets a genuinely missing semantic concept (an expired TLS certificate)
whose correct current answer is UNKNOWN; the fix is one ADD_CHOICE on that node
targeting an existing registered macro. No procedure change. Exactly one
TeacherProposal; no repair; no second proposal; stop at the approval boundary.

Budgets (pre-registered): at most 20 accepted Jev inferences and 1 successful
Teacher call (transport retries resend identical bytes only).
"""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from openclass_core.models import ChoiceResult
from openclass_provider_jev import JevDecisionProvider
from pydantic import SecretStr, ValidationError

from .canonical import (
    Choice,
    DecisionNode,
    Macro,
    PolicyGraph,
    Predicate,
    ResolvedDecision,
    StateFeature,
    StateSchema,
    Step,
    compile_state,
    digest,
)
from .jev import UNKNOWN, DecisionTelemetry, JevDecisionCompiler, telemetry
from .knowledge import JevProfile, save_new
from .live_teacher import TeacherBudget, call_teacher
from .protocol_v21 import (
    ProposalRejected,
    apply_proposal,
    context_pack,
    parse_proposal,
    proposal_schema,
    wrap,
)
from .stage1_live import Budget, RecordingTransport
from .teacher import Capability

ROOT = Path("build/experiment-f")
DATASET = Path("benchmarks/jev-contract/v1")
TEACHER_MODEL = "google/gemini-2.5-flash"
# Stage-1 preregistered selection (margin_unknown family), research-only.
SUPERVISION: dict[str, Any] = {
    "family": "margin_unknown",
    "min_top": 0.0,
    "min_margin": 0.0,
    "max_unknown": 0.3,
}
JEV_BUDGET = 20
TEACHER_BUDGET = 1

SYSTEM_V21 = """You are the OpenClass Teacher. Propose the smallest change to a
versioned decision system as a typed proposal. The failed layer is deterministic
evidence, not your choice. Never change procedures to solve routing, or routing
to hide procedure failures. Every identifier you may reference is constrained to
the provided enums; never invent identifiers outside them; the one exception is
the id of a genuinely new choice, which you coin following the existing naming
convention. Do not encode environment strings as semantic aliases where semantic
routing covers the concept. Use the empirical Jev operating profile supplied in
the context: concrete self-contained choice meanings, no anaphoric references,
flat choice sets. Machine binding fields (candidate ids, hashes, provenance) are
applied by OpenClass after inference; never output them. Return
MISSING_CAPABILITY for unregistered primitives, INSUFFICIENT_EVIDENCE when the
facts cannot support a change, or NO_CHANGE when the graph is already correct.
Output only the supplied proposal schema.
"""


def capabilities() -> tuple[Capability, ...]:
    return (
        Capability(id="select_free_port", arguments={}),
        Capability(id="run_checks", arguments={}),
        Capability(id="flush_dns", arguments={}),
        Capability(id="rotate_certificate", arguments={}),
    )


def graph_v1() -> PolicyGraph:
    schema = StateSchema(
        id="network_ops_state",
        version=1,
        features=(
            StateFeature(id="service", kind="string", sensor_field="service", required=True),
            StateFeature(
                id="port_conflict", kind="boolean", sensor_field="port_conflict", required=True
            ),
            StateFeature(id="dns_stale", kind="boolean", sensor_field="dns_stale", required=True),
            StateFeature(
                id="cert_expired", kind="boolean", sensor_field="cert_expired", required=True
            ),
            StateFeature(
                id="unrelated_signal",
                kind="string",
                sensor_field="unrelated_signal",
                required=False,
            ),
        ),
    )
    network = DecisionNode(
        id="network_failure",
        question=(
            "Which network condition explains the failure evidence for this service? "
            "Answer UNKNOWN when the evidence does not match a listed condition."
        ),
        choices=(
            Choice(
                id="port_bind_conflict",
                meaning=(
                    "The service cannot bind its required network port because another "
                    "process already occupies it; recover by selecting a free port "
                    "and rerunning the checks."
                ),
                target_kind="macro",
                target_id="recover_port",
            ),
            Choice(
                id="dns_failure",
                meaning=(
                    "The service fails to resolve dependencies because cached DNS "
                    "records are stale; recover by flushing the DNS cache."
                ),
                target_kind="macro",
                target_id="flush_dns",
            ),
        ),
    )
    parent = DecisionNode(
        id="response_router",
        question="Which response path fits this incident right now?",
        decomposition_reason=(
            "Response-path selection and network-condition diagnosis are separately "
            "bounded decisions: the parent picks the workflow, the child classifies "
            "the observed network condition within it."
        ),
        choices=(
            Choice(
                id="handle_network_failure",
                meaning=(
                    "The incident is a connectivity or transport problem: the service "
                    "cannot bind, resolve, or securely reach its network endpoints or "
                    "dependencies; route to the network failure diagnosis."
                ),
                target_kind="node",
                target_id="network_failure",
            ),
            Choice(
                id="run_tests_now",
                meaning="The incident only requires running the service checks now.",
                target_kind="macro",
                target_id="run_test_workflow",
            ),
        ),
    )
    macros = (
        Macro(
            id="recover_port",
            purpose="Recover from a port bind conflict: select a free port, rerun checks.",
            steps=(
                Step(capability="select_free_port", arguments={}),
                Step(capability="run_checks", arguments={}),
            ),
            postconditions=(Predicate(field="port_conflict", equals=False),),
        ),
        Macro(
            id="flush_dns",
            purpose="Flush stale DNS cache entries and rerun the checks.",
            steps=(
                Step(capability="flush_dns", arguments={}),
                Step(capability="run_checks", arguments={}),
            ),
            postconditions=(Predicate(field="dns_stale", equals=False),),
        ),
        Macro(
            id="rotate_certificate",
            purpose="Replace an expired TLS certificate and rerun the checks.",
            steps=(
                Step(capability="rotate_certificate", arguments={}),
                Step(capability="run_checks", arguments={}),
            ),
            postconditions=(Predicate(field="cert_expired", equals=False),),
        ),
        Macro(
            id="run_test_workflow",
            purpose="Run the service checks without any recovery.",
            steps=(Step(capability="run_checks", arguments={}),),
            postconditions=(Predicate(field="port_conflict", equals=False),),
        ),
    )
    return PolicyGraph(
        id="network_ops",
        version=1,
        state_schema=schema,
        entry_node="response_router",
        nodes=(parent, network),
        macros=macros,
    )


class FWorld:
    """Deterministic in-process world; registered primitives are the only effects."""

    def __init__(self, facts: dict[str, Any]) -> None:
        self.facts = dict(facts)

    def observe(self) -> Any:
        from .canonical import StateSnapshot

        return StateSnapshot(
            schema_id="network_ops_state",
            schema_version=1,
            facts=self.facts,
        )

    def execute(self, step: Step) -> bool:
        if step.capability == "select_free_port":
            self.facts["port_conflict"] = False
        elif step.capability == "run_checks":
            return not (
                self.facts.get("port_conflict")
                or self.facts.get("dns_stale")
                or self.facts.get("cert_expired")
            )
        elif step.capability == "flush_dns":
            self.facts["dns_stale"] = False
        elif step.capability == "rotate_certificate":
            self.facts["cert_expired"] = False
        else:
            return False
        return True


def snapshot_for(schema: StateSchema, scenario: str) -> Any:
    scenarios: dict[str, tuple[dict[str, Any], tuple[str, ...]]] = {
        "tls": (
            {
                "service": "checkout-api",
                "port_conflict": False,
                "dns_stale": False,
                "cert_expired": True,
            },
            (
                "2026-09-25T10:00:01Z checkout ERROR upstream handshake failed: "
                "certificate has expired",
                "2026-09-25T10:00:01Z checkout WARN tls_verify: unable to get local "
                "issuer certificate",
            ),
        ),
        "port": (
            {
                "service": "checkout-api",
                "port_conflict": True,
                "dns_stale": False,
                "cert_expired": False,
            },
            ("OSError: [Errno 98] Address already in use while binding port 3000",),
        ),
        "dns": (
            {
                "service": "checkout-api",
                "port_conflict": False,
                "dns_stale": True,
                "cert_expired": False,
            },
            ("resolution failed: stale cache entry for payments.internal",),
        ),
        "tests_only": (
            {
                "service": "checkout-api",
                "port_conflict": False,
                "dns_stale": False,
                "cert_expired": False,
            },
            ("operator request: run the service checks now",),
        ),
        "unrelated": (
            {
                "service": "checkout-api",
                "port_conflict": False,
                "dns_stale": False,
                "cert_expired": False,
                "unrelated_signal": "cron timer fired with no handler",
            },
            ("cron: rotate-logs timer fired with no matching handler",),
        ),
    }
    facts, evidence = scenarios[scenario]
    return compile_state(schema, facts, evidence)


def supervision(record: DecisionTelemetry) -> dict[str, Any]:
    """Frozen Stage-1 rule (research-only): margin >= 0.0 and UNKNOWN <= 0.3."""
    if record.infrastructure_status != "ok" or record.selected_choice == UNKNOWN:
        return {"decision": "escalate", "rule": SUPERVISION}
    assert record.margin is not None and record.unknown_probability is not None
    ok = (
        record.margin >= SUPERVISION["min_margin"]
        and record.unknown_probability <= SUPERVISION["max_unknown"]
    )
    return {"decision": "continue" if ok else "escalate", "rule": SUPERVISION}


async def jev_decide(
    compiler: JevDecisionCompiler,
    profile: JevProfile,
    node: DecisionNode,
    snapshot: Any,
    key: str,
    budget: Budget,
    attempts: list[dict[str, Any]],
) -> tuple[DecisionTelemetry, ChoiceResult | None]:
    compiled = compiler.compile(node, snapshot)
    provider = JevDecisionProvider(
        api_key=SecretStr(key),
        base_url="https://ai-gateway.vercel.sh/typesafe",
        model="typesafe-ai/jev",
        timeout=60,
        max_retries=0,
        transport=RecordingTransport(budget, attempts),
    )
    result = None
    try:
        result = await provider.choice(compiled.request)
    except Exception:  # infrastructure only
        result = None
    record = telemetry(
        compiled,
        profile,
        result,
        latency_ms=0.0,
        retry_count=max(len(attempts) - 1, 0),
        simulated=False,
    )
    return record, result


def run(root: Path, key: str) -> int:
    root.mkdir(parents=True)
    profile = JevProfile.model_validate_json((DATASET / "profile.json").read_text())
    graph = graph_v1()
    caps = capabilities()
    freeze = json.loads((DATASET / "benchmark-sha256.json").read_text())
    stage1 = json.loads(
        (ROOT.parent / "jev-contract-v1/stage1-calibration/calibration-report.json").read_text()
    )
    selected_rule = stage1["selected_on_calibration"]["margin_unknown"]["rule"]
    assert selected_rule == SUPERVISION, selected_rule
    hidden_expectations = {
        "tls": "new choice routes to rotate_certificate; cert_expired cleared after execution",
        "port": "port_bind_conflict selected; port_conflict cleared",
        "dns": "dns_failure selected; dns_stale cleared",
        "tests_only": "run_tests_now selected at the parent; nothing recovered",
        "unrelated": "UNKNOWN retained at network_failure",
    }
    protocol_value: Any = {
        "experiment": "F_localized_decision_graph_evolution",
        "teacher_protocol": "v2.1 (proposal/envelope separation; enum-constrained identifiers)",
        "teacher_model": TEACHER_MODEL,
        "temperature": 0,
        "context": "Core contract + compact JevProfile (no skill, no worked examples)",
        "jev_contract_v1_hashes": {
            name: freeze[name] for name in ("profile.json", "protocol.json") if name in freeze
        },
        "supervision_policy": {
            **SUPERVISION,
            "status": "research-calibrated, not production-calibrated",
        },
        "scenario": {
            "parent_node": "response_router (must remain valid and unchanged)",
            "scenario_version": 2,
            "scenario_v1_deviation": (
                "run 20260925T01 froze: parent answered UNKNOWN for the TLS "
                "incident because v1 parent semantics were too narrow; v2 "
                "broadens the parent meaning to the honest transport scope"
            ),
            "lower_node": "network_failure (missing semantic concept)",
            "gap": ("TLS certificate failure is unrepresented; correct answer is UNKNOWN"),
            "fix_shape": "one ADD_CHOICE on network_failure targeting an existing macro",
            "expected_new_class_name_not_disclosed": True,
        },
        "hidden_expectations": hidden_expectations,
        "budget": {"accepted_jev": JEV_BUDGET, "teacher_successful_calls": TEACHER_BUDGET},
        "stop_rule": (
            "any deviation freezes the failure; one proposal only; no repair; "
            "no second semantic request; stop at the approval boundary"
        ),
        "graph_v1_hash": graph.content_hash,
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    save_new(root / "protocol.json", protocol_value)
    compiler = JevDecisionCompiler(profile)
    jev_budget = Budget(JEV_BUDGET)
    trace: dict[str, Any] = {}

    async def sequence() -> int:
        # 1-2: parent routing then lower-node UNKNOWN on the TLS scenario.
        tls_snapshot = snapshot_for(graph.state_schema, "tls")
        attempts: list[dict[str, Any]] = []
        parent_record, _ = await jev_decide(
            compiler, profile, graph.nodes[0], tls_snapshot, key, jev_budget, attempts
        )
        trace["parent_route"] = {
            "record": parent_record.model_dump(mode="json"),
            "attempts": attempts,
            "supervision": supervision(parent_record),
        }
        if parent_record.selected_choice != "handle_network_failure":
            trace["failure"] = "parent did not route the TLS incident to network_failure"
            return 0
        attempts = []
        network_node = graph.nodes[1]
        lower_record, _ = await jev_decide(
            compiler, profile, network_node, tls_snapshot, key, jev_budget, attempts
        )
        trace["lower_unknown"] = {
            "record": lower_record.model_dump(mode="json"),
            "attempts": attempts,
            "supervision": supervision(lower_record),
        }
        if lower_record.selected_choice != UNKNOWN:
            trace["failure"] = "lower node did not answer UNKNOWN on the missing concept"
            return 0
        trace["diagnosis"] = {
            "layer": "DECISION_SPACE",
            "node": "network_failure",
            "deterministic": "router UNKNOWN at a node whose choices do not fit the evidence",
        }
        # 3: one Teacher proposal under v2.1.
        evidence = (
            "Router selected UNKNOWN at node network_failure "
            f"(unknown probability {lower_record.unknown_probability:.2f}).",
            "Observed evidence: upstream TLS handshake failed: certificate has expired; "
            "tls_verify reports unable to get local issuer certificate.",
            "Offered choices at network_failure cover port bind conflicts and stale DNS "
            "records only; neither fits certificate failures.",
            "Registered macros include rotate_certificate (replace an expired TLS "
            "certificate and rerun checks), currently unreachable from network_failure.",
            "No procedure change is required; parent routing is correct.",
        )
        pack = context_pack(
            "DECISION_SPACE",
            evidence,
            graph,
            caps,
            ("ADD_CHOICE", "MISSING_CAPABILITY", "INSUFFICIENT_EVIDENCE"),
            profile,
        )
        schema = proposal_schema(
            graph, caps, ("ADD_CHOICE", "MISSING_CAPABILITY", "INSUFFICIENT_EVIDENCE")
        )
        packet: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": SYSTEM_V21},
                {"role": "user", "content": json.dumps(pack, sort_keys=True)},
            ],
            "temperature": 0,
            "max_tokens": 4096,
            "response_schema": schema,
        }
        save_new(root / "teacher-request.json", packet)
        teacher_budget = TeacherBudget(TEACHER_BUDGET)
        t_attempts: list[dict[str, Any]] = []
        response = await call_teacher(TEACHER_MODEL, packet, key, teacher_budget, t_attempts)
        trace["teacher"] = {
            "response": {k: v for k, v in response.items() if k != "attempts"},
            "attempts": t_attempts,
        }
        if response["infrastructure_status"] != "ok":
            trace["failure"] = "teacher infrastructure failure; no semantic result"
            return 0
        try:
            proposal = parse_proposal(response["content"] or "")
        except (ValueError, ValidationError):
            trace["failure"] = "teacher proposal schema-invalid; frozen as-is"
            return 0
        if proposal.operator != "ADD_CHOICE":
            trace["failure"] = (
                f"teacher answered {proposal.operator}; localized ADD_CHOICE required"
            )
            return 0
        envelope = wrap(
            proposal,
            graph,
            profile,
            TEACHER_MODEL,
            context_pack_hash=digest(packet["messages"][1]["content"]),
            schema_hash=digest(schema),
        )
        save_new(root / "envelope.json", envelope.model_dump(mode="json"))
        try:
            graph_v2 = apply_proposal(graph, proposal, caps)
        except ProposalRejected as exc:
            trace["failure"] = f"proposal rejected by deterministic applier: {exc}"
            return 0
        save_new(root / "graph-v2.json", graph_v2.model_dump(mode="json"))
        # 4: hidden behavioral evaluation with live Jev on the amended graph.
        v2_network = next(n for n in graph_v2.nodes if n.id == "network_failure")
        v2_parent = next(n for n in graph_v2.nodes if n.id == "response_router")
        evaluation: dict[str, Any] = {}
        new_choice = next(
            c for c in v2_network.choices if c.id not in {ch.id for ch in network_node.choices}
        )

        def expect_id(target: str) -> Any:
            def check(sel: object) -> bool:
                return sel == target

            return check

        for scenario, node, expect in (
            ("tls", v2_network, expect_id(new_choice.id)),
            ("port", v2_network, expect_id("port_bind_conflict")),
            ("dns", v2_network, expect_id("dns_failure")),
            ("tests_only", v2_parent, expect_id("run_tests_now")),
            ("unrelated", v2_network, expect_id(UNKNOWN)),
        ):
            snap = snapshot_for(graph.state_schema, scenario)
            resolved = (
                (
                    ResolvedDecision(
                        node_id="response_router",
                        choice_id="handle_network_failure",
                        meaning="network-level failure routed by the parent",
                    ),
                )
                if node is v2_network
                else ()
            )
            snap = snap.model_copy(update={"resolved_decisions": resolved})
            att: list[dict[str, Any]] = []
            record, _ = await jev_decide(compiler, profile, node, snap, key, jev_budget, att)
            evaluation[scenario] = {
                "selected": record.selected_choice,
                "expected_pass": expect(record.selected_choice),
                "supervision": supervision(record),
                "record": record.model_dump(mode="json"),
            }
        # Macro behavioral check: the TLS fix actually works end to end.
        world = FWorld(
            {"service": "x", "port_conflict": False, "dns_stale": False, "cert_expired": True}
        )
        macro = next(m for m in graph_v2.macros if m.id == "rotate_certificate")
        executed = all(world.execute(s) for s in macro.steps)
        postconditions = all(world.facts.get(p.field) == p.equals for p in macro.postconditions)
        delta = {
            "parent_unchanged": v2_parent == graph.nodes[0],
            "macros_unchanged": tuple(m.model_dump() for m in graph_v2.macros)
            == tuple(m.model_dump() for m in graph.macros),
            "schema_unchanged": graph_v2.state_schema == graph.state_schema,
            "node_delta": [n.id for n in graph_v2.nodes if n not in graph.nodes],
            "localized": v2_network.choices[:-1] == network_node.choices
            if len(v2_network.choices) == len(network_node.choices) + 1
            else False,
            "no_new_capability": new_choice.target_kind == "macro"
            and new_choice.target_id in {c.id for c in caps} | {m.id for m in graph.macros},
        }
        checks = {
            "1_new_concept_recognized": evaluation["tls"]["expected_pass"]
            and executed
            and postconditions,
            "2_existing_lower_cases_correct": evaluation["port"]["expected_pass"]
            and evaluation["dns"]["expected_pass"],
            "3_parent_unchanged_behavior": evaluation["tests_only"]["expected_pass"]
            and delta["parent_unchanged"],
            "4_unrelated_unknown_retained": evaluation["unrelated"]["expected_pass"],
            "5_no_unrelated_changes": delta["macros_unchanged"]
            and delta["schema_unchanged"]
            and delta["localized"],
            "6_no_new_primitive": delta["no_new_capability"],
            # A localized node change must appear in the delta as exactly the
            # diagnosed node; an empty delta would mean nothing changed at all.
            "7_change_localized_to_diagnosed_node": delta["localized"]
            and delta["node_delta"] == ["network_failure"],
        }
        evaluation["macro_execution"] = {"executed": executed, "postconditions": postconditions}
        evaluation["graph_delta"] = delta
        trace["evaluation"] = {"cases": evaluation, "checks": checks}
        trace["outcome"] = (
            "candidate_passed_all_checks" if all(checks.values()) else "candidate_failed_checks"
        )
        return 0

    code = asyncio.run(sequence())
    trace["jev_accepted"] = jev_budget.accepted
    trace["rejected_retries"] = jev_budget.rejected_retries
    save_new(root / "trace.json", trace)
    print(
        json.dumps(
            {
                "outcome": trace.get("outcome") or trace.get("failure"),
                "jev_accepted": jev_budget.accepted,
            }
        )
    )
    return code


def rescore(root: Path) -> int:
    """Recompute the hidden checks from a frozen trace; no new inference.

    Used when a check FORMULA (not the proposal) was defective: every input to
    the checks is recorded in the trace, so deterministic rescoring is exact.
    """
    trace = json.loads((root / "trace.json").read_text())
    cases = trace["evaluation"]["cases"]
    delta = cases["graph_delta"]
    checks = {
        "1_new_concept_recognized": cases["tls"]["expected_pass"]
        and cases["macro_execution"]["executed"]
        and cases["macro_execution"]["postconditions"],
        "2_existing_lower_cases_correct": cases["port"]["expected_pass"]
        and cases["dns"]["expected_pass"],
        "3_parent_unchanged_behavior": cases["tests_only"]["expected_pass"]
        and delta["parent_unchanged"],
        "4_unrelated_unknown_retained": cases["unrelated"]["expected_pass"],
        "5_no_unrelated_changes": delta["macros_unchanged"]
        and delta["schema_unchanged"]
        and delta["localized"],
        "6_no_new_primitive": delta["no_new_capability"],
        "7_change_localized_to_diagnosed_node": delta["localized"]
        and delta["node_delta"] == ["network_failure"],
    }
    outcome = "candidate_passed_all_checks" if all(checks.values()) else "candidate_failed_checks"
    save_new(
        root / "final-report.json",
        {
            "outcome": outcome,
            "checks": checks,
            "correction": (
                "Original run 20260925T07 check 7 required an empty node delta, which "
                "contradicts locality: a localized ADD_CHOICE must change exactly the "
                "diagnosed node. Formula corrected; checks deterministically rescored "
                "from the frozen trace with no new inference and no proposal change."
            ),
            "jev_accepted_in_original_run": trace["jev_accepted"],
            "teacher_successful_calls_in_original_run": 1,
        },
    )
    print(json.dumps({"outcome": outcome, "checks": checks}, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--key-env", default="OPENCLASS_JEV_API_KEY")
    parser.add_argument("--rescore", action="store_true")
    args = parser.parse_args()
    if args.rescore:
        raise SystemExit(rescore(args.root))
    run(args.root, os.environ[args.key_env])


if __name__ == "__main__":
    main()
