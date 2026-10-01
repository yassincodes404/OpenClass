"""Decision-graph proof suite (Experiments A-C): live Jev routing in graph context.

Pre-registered budget: at most 40 accepted Jev calls for this stage. Every
experiment gets its own artifact directory and is frozen before the next starts.
Discovery providers are structurally absent: this module cannot call one.
"""

import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from automation_attempts import Attempt, JevRetryTransport
from openclass_core.models import (
    ChoiceRequest,
    ChoiceResult,
    Observation,
    OntologyClass,
    OntologyVersion,
)
from openclass_provider_jev import JevDecisionProvider
from pydantic import SecretStr

sys.path.insert(0, str(Path(__file__).parent))

import decision_graph as dg  # noqa: E402

PROOF_ROOT = Path("build/decision-graph-proof")
BUDGET = 40
JEV_URL = "https://ai-gateway.vercel.sh/typesafe/v1/systemone"
PROFILE_REF = "benchmarks/jev/jev-profile-v1.json"


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def save(path: Path, value: Any) -> None:
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False, default=str) + "\n")


class Budget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.accepted = 0
        self.rate_limited = 0

    def allow(self) -> bool:
        return self.accepted < self.limit


class BudgetedJevTransport(JevRetryTransport):
    def __init__(self, budget: Budget, record: Any) -> None:
        super().__init__(record)
        self.budget = budget

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) != JEV_URL:
            raise AssertionError("Only the Jev decision endpoint is permitted")
        if not self.budget.allow():
            raise BudgetExhausted()
        for delay in (0.0, 1.0, 2.0, 4.0, 8.0, 16.0):
            if delay:
                await asyncio.sleep(delay)
            response = await super().handle_async_request(request)
            if 200 <= response.status_code < 300:
                self.budget.accepted += 1
                return response
            if response.status_code not in {429, 503}:
                return response
            self.budget.rate_limited += 1
        return response


class BudgetExhausted(Exception):
    pass


# --- The simulated service world and registered macros --------------------


class ServiceWorld(dg.RegisteredWorld):
    """Deterministic in-process service fixture; primitives are the only effects."""

    def primitive_choose_available_test_port(
        self, preferred: int | None = None, **_: Any
    ) -> tuple[bool, str]:
        preferred = preferred or 3000
        if self.fields.pop("port_conflict", False):
            self.fields["configured_port"] = self.fields.get("free_port", preferred + 1)
            self.fields["conflict_resolved"] = True
        else:
            self.fields["configured_port"] = preferred
        return True, f"port {self.fields['configured_port']}"

    def primitive_set_environment(self, name: str | None = None, **_: Any) -> tuple[bool, str]:
        name = name or "TEST_PORT"
        self.fields["env_var"] = name
        self.fields["env_set"] = True
        return True, name

    def primitive_run_tests(self, **_: Any) -> tuple[bool, str]:
        self.fields["test_attempted"] = True
        if self.fields.get("dependency_down"):
            self.fields["last_output"] = "connect to postgres:5432: connection refused"
            self.fields["tests_passing"] = False
            return False, self.fields["last_output"]
        if self.fields.get("port_conflict"):
            self.fields["last_output"] = "OSError: [Errno 98] Address already in use"
            self.fields["tests_passing"] = False
            return False, self.fields["last_output"]
        if self.fields.get("env_var") != self.fields.get("expected_env_var", "TEST_PORT"):
            self.fields["last_output"] = (
                f"fixture reads {self.fields.get('expected_env_var')}: "
                "required environment variable is not set"
            )
            self.fields["tests_passing"] = False
            return False, self.fields["last_output"]
        self.fields["last_output"] = "Ran 2 tests: OK"
        self.fields["tests_passing"] = True
        return True, self.fields["last_output"]

    def primitive_inspect_result(self, **_: Any) -> tuple[bool, str]:
        self.fields["result_inspected"] = self.fields.get("last_output") is not None
        return self.fields["result_inspected"], str(self.fields.get("last_output"))

    def primitive_write_report(self, **_: Any) -> tuple[bool, str]:
        if not self.fields.get("tests_passing"):
            return False, "no passing test result to report"
        self.fields["report_written"] = True
        return True, "report written"

    def primitive_restart_dependency(self, **_: Any) -> tuple[bool, str]:
        if self.fields.get("dependency_down"):
            self.fields["dependency_down"] = False
            self.fields["dependency_recovered"] = True
            return True, "dependency restarted"
        return False, "no dependency to restart"


def recovery_macro(env_name: str = "TEST_PORT") -> dg.Macro:
    return dg.Macro(
        id="recover_from_port_conflict",
        semantic_purpose=(
            "Recover when tests fail because their required network port is already "
            "occupied: select a free port, reconfigure the fixture, rerun tests, "
            "verify and report."
        ),
        preconditions=(dg.Predicate(field="port_conflict", equals=True),),
        procedure=(
            dg.MacroStep(primitive="choose_available_test_port", args={"preferred": 3000}),
            dg.MacroStep(primitive="set_environment", args={"name": env_name}),
            dg.MacroStep(primitive="run_tests"),
            dg.MacroStep(primitive="inspect_result"),
            dg.MacroStep(primitive="write_report"),
        ),
        postconditions=(
            dg.Predicate(field="tests_passing", equals=True),
            dg.Predicate(field="report_written", equals=True),
        ),
    )


def commander_node(extra_choices: tuple[dg.Choice, ...] = ()) -> dg.DecisionNode:
    return dg.DecisionNode(
        id="incident_commander",
        question=(
            "Which registered action should execute next to get the project's tests "
            "passing and reported?"
        ),
        choices=(
            dg.Choice(
                id="execute_recovery",
                semantic_name="execute port-conflict recovery",
                description=(
                    "Run the registered recovery macro when tests fail because their "
                    "required network port is already occupied."
                ),
                target_macro="recover_from_port_conflict",
            ),
            dg.Choice(
                id="check_result",
                semantic_name="inspect the latest test result",
                description="Look at the recorded test output before acting further.",
                target_node="result_reader",
            ),
            *extra_choices,
        ),
        entry=True,
    )


def reader_node() -> dg.DecisionNode:
    return dg.DecisionNode(
        id="result_reader",
        question="The latest test result has been inspected. What should happen now?",
        choices=(
            dg.Choice(
                id="resume_command",
                semantic_name="return to the incident commander",
                description="Continue the recovery workflow with the result inspected.",
                target_node="incident_commander",
            ),
        ),
    )


def base_graph(
    extra_choices: tuple[dg.Choice, ...] = (), env_name: str = "TEST_PORT"
) -> dg.PolicyGraphVersion:
    return dg.PolicyGraphVersion(
        id="decision-graph-proof",
        version_number=1,
        jev_profile_ref=PROFILE_REF,
        entry_node="incident_commander",
        nodes=(commander_node(extra_choices), reader_node()),
        macros=(recovery_macro(env_name),),
        goal=(
            dg.Predicate(field="tests_passing", equals=True),
            dg.Predicate(field="report_written", equals=True),
        ),
    )


# --- Live Jev decision adapter --------------------------------------------


class Decider:
    def __init__(self, key: str, budget: Budget, attempts: list[dict[str, Any]]) -> None:
        self.key = key
        self.budget = budget
        self.attempts = attempts
        self.calls = 0

    def _record(self, attempt: Attempt) -> None:
        self.attempts.append(attempt.model_dump())

    def ontology(self, node: dg.DecisionNode) -> OntologyVersion:
        classes = tuple(
            OntologyClass(
                stable_class_id=uuid.uuid5(uuid.NAMESPACE_URL, f"proof/{node.id}/{c.id}"),
                canonical_name=c.id,
                display_name=c.semantic_name,
                description=c.description,
            )
            for c in node.choices
        )
        return OntologyVersion(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"proof/{node.id}"),
            classifier_id=uuid.uuid5(uuid.NAMESPACE_URL, "proof/classifier"),
            version_number=1,
            classes=classes,
            created_by="decision-graph-proof",
        )

    def observation(self, node: dg.DecisionNode, snapshot: dg.StateSnapshot) -> str:
        return json.dumps(
            {
                "question": node.question,
                "state": snapshot.fields,
                "raw_evidence": snapshot.raw_evidence,
            },
            indent=2,
        )

    async def decide(self, node: dg.DecisionNode, snapshot: dg.StateSnapshot) -> tuple[Any, ...]:
        self.calls += 1
        attempts: list[dict[str, Any]] = []
        transport = BudgetedJevTransport(self.budget, self._record)
        provider = JevDecisionProvider(
            api_key=SecretStr(self.key),
            base_url="https://ai-gateway.vercel.sh/typesafe",
            model="typesafe-ai/jev",
            timeout=60,
            max_retries=0,
            transport=transport,
        )
        result: ChoiceResult | None = None
        error = ""
        try:
            result = await provider.choice(
                ChoiceRequest(
                    observation=Observation(content=self.observation(node, snapshot)),
                    ontology=self.ontology(node),
                )
            )
        except Exception as exc:  # noqa: BLE001 - recorded as infrastructure evidence
            error = f"{type(exc).__name__}: {exc}"
        self.attempts.extend(attempts)
        if result is None:
            return dg.UNKNOWN, 0.0, 1.0, 0.0, {"status": "infrastructure_failed", "error": error}
        selected, top, unknown_p, margin = dg.select_choice(result)
        return (
            selected,
            top,
            unknown_p,
            margin,
            {
                "status": "ok",
                "probabilities": result.probabilities,
                "confidence": result.provider_metadata.get("confidence"),
                "latency_ms": result.latency_ms,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            },
        )


def build_decider(key: str, budget: Budget, attempts: list[dict[str, Any]]) -> tuple[Any, Decider]:
    decider = Decider(key, budget, attempts)

    async def decide(node: dg.DecisionNode, snapshot: dg.StateSnapshot) -> tuple[Any, ...]:
        return await decider.decide(node, snapshot)

    return decide, decider


def run_live(
    graph: dg.PolicyGraphVersion, world: dg.RegisteredWorld, decide: Any
) -> dg.GraphRunResult:
    return asyncio.run(dg.run_graph(graph, world, decide))


# --- Experiments -----------------------------------------------------------


def experiment_c(key: str, budget: Budget) -> dict[str, Any]:
    """Known macro, discovery disabled, three port-conflict scenarios."""
    attempts: list[dict[str, Any]] = []
    decide, decider = build_decider(key, budget, attempts)
    runs = []
    for scenario, conflict_port in (("standard", 3000), ("alternate", 8000), ("high", 5432)):
        world = ServiceWorld(
            {
                "service": f"fixture-{scenario}",
                "preferred_port": conflict_port,
                "port_conflict": True,
                "free_port": conflict_port + 1,
                "expected_env_var": "TEST_PORT",
                "tests_passing": False,
            }
        )
        started = time.perf_counter()
        outcome = run_live(base_graph(), world, decide)
        runs.append(
            {
                "scenario": scenario,
                "occupied_port": conflict_port,
                "status": outcome.status,
                "diagnosis": outcome.diagnosis,
                "selections": [
                    {"node": t.node_id, "selected": t.selected, "margin": t.margin}
                    for t in outcome.transitions
                ],
                "configured_port": world.fields.get("configured_port"),
                "tests_passing": world.fields.get("tests_passing"),
                "report_written": world.fields.get("report_written"),
                "discovery_calls": 0,
                "jev_calls": decider.calls,
                "elapsed_ms": (time.perf_counter() - started) * 1000,
                "events": [e.model_dump(mode="json") for e in outcome.events],
            }
        )
    passed = sum(1 for r in runs if r["status"] == "completed")
    return {
        "experiment": "C_known_macro_recovery",
        "expectation": (
            "Jev routes to the registered recovery macro in all three scenarios; the "
            "macro completes with verified postconditions; zero discovery calls."
        ),
        "runs": runs,
        "passed": passed == len(runs),
        "provider_attempts": attempts,
    }


def experiment_b(key: str, budget: Budget) -> dict[str, Any]:
    """Semantic port-failure classification across wordings, in graph context."""
    attempts: list[dict[str, Any]] = []
    decide, decider = build_decider(key, budget, attempts)
    cases = [
        ("errno98", "OSError: [Errno 98] Address already in use", "port_bind_conflict"),
        ("bare", "ERROR: listen tcp :3000: bind: address in use", "port_bind_conflict"),
        (
            "allocated",
            "docker: port is already allocated on port 3000",
            "port_bind_conflict",
        ),
        ("errno_style", "socket.bind failed with errno 98 while binding", "port_bind_conflict"),
        ("refused", "connect to payments:8443: connection refused", "connection_failure"),
        ("denied", "open /etc/app/secrets.env: permission denied", "permission_failure"),
        ("yaml", "yaml parse error on line 12: mapping values not allowed", "config_failure"),
        ("control", "cron: rotate-logs timer fired with no matching handler", "UNKNOWN"),
    ]
    node = dg.DecisionNode(
        id="failure_classifier",
        question="Which failure category does the observed evidence belong to?",
        choices=(
            dg.Choice(
                id="port_bind_conflict",
                semantic_name="port bind conflict",
                description=(
                    "A network port the service must bind is already occupied "
                    "(address/port in use, EADDRINUSE, errno 98)."
                ),
                target_node="incident_commander",
            ),
            dg.Choice(
                id="connection_failure",
                semantic_name="connection failure",
                description="An outbound connection was refused or timed out.",
                target_node="incident_commander",
            ),
            dg.Choice(
                id="permission_failure",
                semantic_name="permission failure",
                description="The operating system denied a file or resource access.",
                target_node="incident_commander",
            ),
            dg.Choice(
                id="config_failure",
                semantic_name="configuration failure",
                description="A configuration file failed to parse or validate.",
                target_node="incident_commander",
            ),
        ),
        entry=True,
    )
    graph = dg.PolicyGraphVersion(
        id="classifier-graph",
        version_number=1,
        jev_profile_ref=PROFILE_REF,
        entry_node="failure_classifier",
        nodes=(node, commander_node(), reader_node()),
        macros=(recovery_macro(),),
        goal=(dg.Predicate(field="inspected_only", equals=True),),
    )
    results = []
    for cid, evidence, expected in cases:
        world = ServiceWorld({"inspected_only": False, "evidence": evidence})
        outcome = asyncio.run(dg.run_graph(graph, world, decide, max_depth=1))
        selected = outcome.transitions[0].selected if outcome.transitions else dg.UNKNOWN
        expected_label = dg.UNKNOWN if expected == "UNKNOWN" else expected
        results.append(
            {
                "case": cid,
                "evidence": evidence,
                "expected": expected_label,
                "selected": selected,
                "correct": selected == expected_label,
                "run_status": outcome.status,
            }
        )
    correct = sum(1 for r in results if r["correct"])
    return {
        "experiment": "B_semantic_failure_classification",
        "expectation": (
            "All four bind-conflict wordings classify as port_bind_conflict without "
            "literal aliases; in-set negatives classify to their own category; the "
            "out-of-set control yields UNKNOWN."
        ),
        "results": results,
        "accuracy": correct / len(results),
        "passed": correct == len(results),
        "provider_attempts": attempts,
    }


def experiment_a(key: str, budget: Budget) -> dict[str, Any]:
    """Flat 16-way vs 4-to-4 hierarchical routing in graph context."""
    attempts: list[dict[str, Any]] = []
    decide, decider = build_decider(key, budget, attempts)
    groups = {
        "compute_actions": (
            ("restart_service", "Start a wedged service process again."),
            ("reboot_host", "Boot the entire machine again."),
            ("scale_deployment", "Change replica counts to match load."),
            ("recycle_pod", "Replace a Kubernetes pod with a fresh instance."),
        ),
        "network_actions": (
            ("rotate_certificate", "Issue and install a fresh TLS certificate."),
            ("open_firewall", "Allow traffic through a firewall rule."),
            ("restart_load_balancer", "Restart the load balancer process."),
            ("flush_dns", "Clear cached DNS entries."),
        ),
        "data_actions": (
            ("clear_cache", "Invalidate stale cached data."),
            ("run_migration", "Apply pending schema migrations."),
            ("backup_database", "Create a consistent database backup."),
            ("purge_queue", "Delete poisoned messages from a queue."),
        ),
        "access_actions": (
            ("rotate_credentials", "Replace exposed secrets."),
            ("revoke_sessions", "Invalidate all active user sessions."),
            ("unlock_account", "Remove a login lock from one account."),
            ("reset_permissions", "Restore a role's intended permission set."),
        ),
    }
    scenarios = [
        (
            "a1",
            "compute_actions",
            "recycle_pod",
            "The checkout pod is crash-looping since the last deploy; replace the pod.",
        ),
        (
            "a2",
            "compute_actions",
            "reboot_host",
            "The worker host kernel is out of memory; boot the machine again.",
        ),
        (
            "a3",
            "compute_actions",
            "scale_deployment",
            "CPU is pinned at 100% under ten-fold traffic; add replicas.",
        ),
        (
            "a4",
            "compute_actions",
            "restart_service",
            "The api service is wedged with no heartbeat; start the process again.",
        ),
        (
            "a5",
            "network_actions",
            "rotate_certificate",
            "The gateway certificate expires in two hours; replace it.",
        ),
        (
            "a6",
            "network_actions",
            "restart_load_balancer",
            "The load balancer returns 502 everywhere; restart its process.",
        ),
        (
            "a7",
            "network_actions",
            "flush_dns",
            "Staging still resolves to the decommissioned balancer; clear DNS cache.",
        ),
        (
            "a8",
            "network_actions",
            "open_firewall",
            "New replicas cannot reach the database; the firewall drops the subnet.",
        ),
    ]

    def leaf_choices(group: str) -> tuple[dg.Choice, ...]:
        return tuple(
            dg.Choice(id=name, semantic_name=name.replace("_", " "), description=desc)
            for name, desc in groups[group]
        )

    flat_node = dg.DecisionNode(
        id="ops_router_flat",
        question="Which registered operation does this incident need?",
        choices=tuple(
            dg.Choice(id=n, semantic_name=n.replace("_", " "), description=d)
            for members in groups.values()
            for n, d in members
        ),
        entry=True,
    )
    flat_graph = dg.PolicyGraphVersion(
        id="flat",
        version_number=1,
        jev_profile_ref=PROFILE_REF,
        entry_node="ops_router_flat",
        nodes=(flat_node,),
    )
    group_node = dg.DecisionNode(
        id="ops_group",
        question="Which operation domain does this incident belong to?",
        choices=tuple(
            dg.Choice(
                id=g,
                semantic_name=g.replace("_", " "),
                description=f"Operations for {g.replace('_', ' ')}.",
            )
            for g in groups
        ),
        entry=True,
    )

    flat_results = []
    hier_results = []
    for sid, group, leaf, evidence in scenarios:
        world = ServiceWorld({"ops_target": leaf, "evidence": evidence})
        outcome = asyncio.run(dg.run_graph(flat_graph, world, decide, max_depth=1))
        selected = outcome.transitions[0].selected if outcome.transitions else dg.UNKNOWN
        flat_results.append(
            {
                "scenario": sid,
                "expected": leaf,
                "selected": selected,
                "correct": selected == leaf,
                "shape": "flat16",
            }
        )
        stage1_graph = dg.PolicyGraphVersion(
            id="hier1",
            version_number=1,
            jev_profile_ref=PROFILE_REF,
            entry_node="ops_group",
            nodes=(group_node,),
        )
        outcome1 = asyncio.run(dg.run_graph(stage1_graph, world, decide, max_depth=1))
        picked_group = outcome1.transitions[0].selected if outcome1.transitions else dg.UNKNOWN
        leaf_ok = False
        if picked_group == group:
            leaf_node = dg.DecisionNode(
                id=f"leaves_{group}",
                question="Which registered operation does this incident need?",
                choices=leaf_choices(group),
                entry=True,
            )
            leaf_graph = dg.PolicyGraphVersion(
                id=f"hier2-{group}",
                version_number=1,
                jev_profile_ref=PROFILE_REF,
                entry_node=f"leaves_{group}",
                nodes=(leaf_node,),
            )
            outcome2 = asyncio.run(dg.run_graph(leaf_graph, world, decide, max_depth=1))
            picked_leaf = outcome2.transitions[0].selected if outcome2.transitions else dg.UNKNOWN
            leaf_ok = picked_leaf == leaf
        hier_results.append(
            {
                "scenario": sid,
                "group": picked_group,
                "group_correct": picked_group == group,
                "leaf": leaf,
                "path_correct": leaf_ok,
                "shape": "hierarchy4x4",
            }
        )
    flat_acc = sum(1 for r in flat_results if r["correct"]) / len(flat_results)
    hier_acc = sum(1 for r in hier_results if r["path_correct"]) / len(hier_results)
    return {
        "experiment": "A_flat_vs_hierarchical",
        "expectation": (
            "Compare 16-way flat routing against a 4-to-4 hierarchy on identical "
            "scenarios; the characterization predicted flat >= hierarchical."
        ),
        "flat_results": flat_results,
        "hierarchy_results": hier_results,
        "flat_accuracy": flat_acc,
        "hierarchy_path_accuracy": hier_acc,
        "passed": flat_acc >= hier_acc,
        "provider_attempts": attempts,
    }


def freeze(directory: Path, key: str) -> None:
    leaked = [
        str(p.relative_to(directory))
        for p in sorted(directory.rglob("*"))
        if p.is_file() and key and key in p.read_text(errors="ignore")
    ]
    save(
        directory / "integrity.json",
        {
            "secret_material_absent": not leaked,
            "discovery_capability_present": False,
            "budget_limit": BUDGET,
        },
    )
    manifest = {
        str(p.relative_to(directory)): sha(p.read_bytes())
        for p in sorted(directory.rglob("*"))
        if p.is_file() and p.name != "sha256.json"
    }
    save(directory / "sha256.json", manifest)
    if leaked:
        raise ValueError("secret material found in artifacts")


def main() -> int:
    key = os.environ["OPENCLASS_JEV_API_KEY"]
    root = PROOF_ROOT / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root.mkdir(parents=True)
    budget = Budget(BUDGET)
    experiments = []
    for runner in (experiment_c, experiment_b, experiment_a):
        if not budget.allow():
            directory = root / f"skipped_{runner.__name__}"
            directory.mkdir()
            save(
                directory / "result.json",
                {"status": "budget_exhausted", "experiment": runner.__name__},
            )
            freeze(directory, key)
            continue
        result = runner(key, budget)
        experiments.append(result)
        directory = root / result["experiment"]
        directory.mkdir()
        save(directory / "result.json", result)
        freeze(directory, key)
        print(
            json.dumps(
                {
                    "experiment": result["experiment"],
                    "passed": result["passed"],
                    "accepted": budget.accepted,
                }
            )
        )
    save(
        root / "report.json",
        {
            "stage": "A-C routing proofs",
            "status": "completed" if budget.accepted <= BUDGET else "budget_exceeded",
            "accepted_inferences": budget.accepted,
            "rate_limited_requests": budget.rate_limited,
            "budget_limit": BUDGET,
            "experiments": [e["experiment"] for e in experiments],
            "all_passed": all(e["passed"] for e in experiments),
        },
    )
    freeze(root, key)
    return 0 if all(e["passed"] for e in experiments) else 1


if __name__ == "__main__":
    raise SystemExit(main())
