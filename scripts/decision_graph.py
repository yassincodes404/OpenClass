"""Experimental Jev-native DecisionGraph: typed nodes, macros, bounded execution.

Research harness only. Implements docs/architecture/jev-native-decision-model.md:
compile state, route a DecisionNode through Jev, execute registered macros with
deterministic preconditions/guards/postconditions, re-observe, and diagnose the
failed layer. No production persistence; discovery is structurally disableable.
"""

import hashlib
import importlib
import inspect
import json
import sys
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

sys.path.insert(0, str(Path(__file__).parent))

from automation_applicability import Frozen  # noqa: E402

MAX_CHOICES = 32
MAX_DEPTH = 8
UNKNOWN = "OPENCLASS_UNKNOWN"


class DiagnosisLayer(StrEnum):
    INFRASTRUCTURE = "INFRASTRUCTURE"
    STATE_REPRESENTATION = "STATE_REPRESENTATION"
    DECISION_SPACE = "DECISION_SPACE"
    SEMANTIC_ROUTING = "SEMANTIC_ROUTING"
    PROCEDURE = "PROCEDURE"
    PRECONDITION = "PRECONDITION"
    SAFETY_GUARD = "SAFETY_GUARD"
    POSTCONDITION = "POSTCONDITION"
    MISSING_CAPABILITY = "MISSING_CAPABILITY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class StateSnapshot(Frozen):
    schema_version: int = 1
    fields: dict[str, Any]
    raw_evidence: str = ""
    source_node: str | None = None

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.fields, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]


class Choice(Frozen):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    semantic_name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    target_node: str | None = None
    target_macro: str | None = None

    @model_validator(mode="after")
    def at_most_one_target(self) -> "Choice":
        if self.target_node is not None and self.target_macro is not None:
            raise ValueError("a choice targets at most one node or macro")
        return self


class DecisionNode(Frozen):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    question: str = Field(min_length=1, max_length=2000)
    choices: tuple[Choice, ...] = Field(min_length=1, max_length=MAX_CHOICES)
    entry: bool = False

    @model_validator(mode="after")
    def unique_choice_ids(self) -> "DecisionNode":
        if len({c.id for c in self.choices}) != len(self.choices):
            raise ValueError("choice ids must be unique within a node")
        return self


class Predicate(Frozen):
    """Deterministic state predicate; never model-evaluated."""

    field: str = Field(min_length=1, max_length=200)
    equals: bool | int | str | None


class MacroStep(Frozen):
    primitive: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    args: dict[str, Any] = Field(default_factory=dict)


class Macro(Frozen):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    semantic_purpose: str = Field(min_length=1, max_length=2000)
    preconditions: tuple[Predicate, ...] = ()
    safety_guards: tuple[Predicate, ...] = ()
    procedure: tuple[MacroStep, ...] = Field(min_length=1, max_length=32)
    postconditions: tuple[Predicate, ...] = ()


class PolicyGraphVersion(Frozen):
    id: str
    version_number: int = Field(ge=1)
    parent_version_id: str | None = None
    jev_profile_ref: str = ""
    entry_node: str
    nodes: tuple[DecisionNode, ...] = Field(min_length=1)
    macros: tuple[Macro, ...] = ()
    goal: tuple[Predicate, ...] = ()

    @model_validator(mode="after")
    def consistent(self) -> "PolicyGraphVersion":
        if len({n.id for n in self.nodes}) != len(self.nodes):
            raise ValueError("node ids must be unique")
        if len({m.id for m in self.macros}) != len(self.macros):
            raise ValueError("macro ids must be unique")
        node_ids = {n.id for n in self.nodes}
        macro_ids = {m.id for m in self.macros}
        if self.entry_node not in node_ids:
            raise ValueError("entry node must exist")
        for node in self.nodes:
            for choice in node.choices:
                if choice.target_node is not None and choice.target_node not in node_ids:
                    raise ValueError(f"choice {choice.id} targets unknown node")
                if choice.target_macro is not None and choice.target_macro not in macro_ids:
                    raise ValueError(f"choice {choice.id} targets unknown macro")
        return self


class StepOutcome(Frozen):
    step: int
    primitive: str
    ok: bool
    detail: str = ""


class MacroExecution(Frozen):
    macro_id: str
    preconditions_passed: bool
    guards_passed: bool
    steps: tuple[StepOutcome, ...]
    postconditions_passed: bool | None


class Transition(Frozen):
    depth: int
    node_id: str
    selected: str
    top_known_probability: float
    unknown_probability: float
    margin: float
    state_digest: str
    macro: MacroExecution | None = None
    state_after: dict[str, Any] | None = None
    router_telemetry: dict[str, Any] | None = None


class TraceEvent(Frozen):
    kind: Literal["route", "macro", "blocked", "diagnosis", "cycle", "depth_exceeded"]
    depth: int
    detail: str


def evaluate_predicates(predicates: tuple[Predicate, ...], fields: dict[str, Any]) -> bool:
    return all(fields.get(p.field) == p.equals for p in predicates)


class GraphRunResult(Frozen):
    status: Literal["completed", "blocked", "cycle", "depth_exceeded", "failed", "diagnosed"]
    transitions: tuple[Transition, ...]
    events: tuple[TraceEvent, ...]
    diagnosis: DiagnosisLayer | None = None
    diagnosis_detail: str = ""


class RegisteredWorld:
    """In-process deterministic environment; primitives are the only effects."""

    def __init__(self, fields: dict[str, Any]) -> None:
        self.fields = dict(fields)
        self.primitive_calls: list[dict[str, Any]] = []

    def observe(self) -> StateSnapshot:
        return StateSnapshot(fields=dict(self.fields))

    def call(self, primitive: str, args: dict[str, Any]) -> tuple[bool, str]:
        method = getattr(self, f"primitive_{primitive}", None)
        if method is None or primitive.startswith("_"):
            return False, f"unregistered primitive: {primitive}"
        ok, detail = method(**args)
        self.primitive_calls.append({"primitive": primitive, "args": args, "ok": ok})
        return ok, detail


def execute_macro(macro: Macro, world: RegisteredWorld) -> MacroExecution:
    fields = world.observe().fields
    pre = evaluate_predicates(macro.preconditions, fields)
    guards = evaluate_predicates(macro.safety_guards, fields)
    steps: list[StepOutcome] = []
    post: bool | None = None
    if pre and guards:
        for number, step in enumerate(macro.procedure, 1):
            ok, detail = world.call(step.primitive, step.args)
            steps.append(StepOutcome(step=number, primitive=step.primitive, ok=ok, detail=detail))
            if not ok:
                break
        post = evaluate_predicates(macro.postconditions, world.observe().fields)
    return MacroExecution(
        macro_id=macro.id,
        preconditions_passed=pre,
        guards_passed=guards,
        steps=tuple(steps),
        postconditions_passed=post,
    )


def select_choice(result: Any) -> tuple[str, float, float, float]:
    """Pre-registered rule: argmax known; UNKNOWN wins ties. Returns name, top, unknown, margin."""
    probabilities = dict(result.probabilities)
    ordered = sorted(probabilities.values(), reverse=True)
    top = ordered[0] if ordered else 0.0
    second = ordered[1] if len(ordered) > 1 else 0.0
    name = max(probabilities, key=lambda k: probabilities[k])
    if result.unknown_probability >= probabilities[name]:
        return UNKNOWN, top, result.unknown_probability, top - second
    return name, top, result.unknown_probability, top - second


async def run_graph(
    graph: PolicyGraphVersion,
    world: RegisteredWorld,
    decide: Any,
    max_depth: int = MAX_DEPTH,
) -> GraphRunResult:
    """decide(node, snapshot) -> (selected_choice_id, top_p, unknown_p, margin).

    The run completes when the graph's goal predicates hold against a fresh
    observation after a macro; otherwise it walks until BLOCKED, a cycle, the
    depth bound, or a diagnosed failure.
    """
    if graph.goal and evaluate_predicates(graph.goal, world.observe().fields):
        return GraphRunResult(
            status="completed", transitions=(), events=(), diagnosis=None, diagnosis_detail=""
        )
    transitions: list[Transition] = []
    events: list[TraceEvent] = []
    visited: dict[str, str] = {}
    node_id = graph.entry_node
    nodes = {n.id: n for n in graph.nodes}
    macros = {m.id: m for m in graph.macros}
    status: Any = "completed"
    diagnosis: DiagnosisLayer | None = None
    detail = ""
    for depth in range(1, max_depth + 1):
        node = nodes[node_id]
        snapshot = world.observe()
        digest = snapshot.digest()
        if node_id in visited and visited[node_id] == digest:
            events.append(TraceEvent(kind="cycle", depth=depth, detail=node_id))
            status, diagnosis = "cycle", DiagnosisLayer.INSUFFICIENT_EVIDENCE
            break
        visited[node_id] = digest
        decision = decide(node, snapshot)
        if inspect.isawaitable(decision):
            decision = await decision
        if len(decision) == 5:
            selected, top, unknown_p, margin, telemetry = decision
        else:
            selected, top, unknown_p, margin = decision
            telemetry = None
        if selected == UNKNOWN:
            events.append(TraceEvent(kind="blocked", depth=depth, detail=node_id))
            transitions.append(
                Transition(
                    depth=depth,
                    node_id=node_id,
                    selected=selected,
                    top_known_probability=top,
                    unknown_probability=unknown_p,
                    margin=margin,
                    state_digest=digest,
                    router_telemetry=telemetry,
                )
            )
            status, diagnosis = "blocked", DiagnosisLayer.DECISION_SPACE
            detail = f"node {node_id}: router selected UNKNOWN"
            break
        choice = next(c for c in node.choices if c.id == selected)
        transition = Transition(
            depth=depth,
            node_id=node_id,
            selected=selected,
            top_known_probability=top,
            unknown_probability=unknown_p,
            margin=margin,
            state_digest=digest,
            router_telemetry=telemetry,
        )
        if choice.target_macro is not None:
            execution = execute_macro(macros[choice.target_macro], world)
            transitions.append(transition.model_copy(update={"macro": execution}))
            events.append(TraceEvent(kind="macro", depth=depth, detail=execution.model_dump_json()))
            if not execution.preconditions_passed:
                status, diagnosis = "diagnosed", DiagnosisLayer.PRECONDITION
                detail = f"{execution.macro_id}: preconditions failed"
                break
            if not execution.guards_passed:
                status, diagnosis = "diagnosed", DiagnosisLayer.SAFETY_GUARD
                detail = f"{execution.macro_id}: safety guards refused execution"
                break
            if any(not s.ok for s in execution.steps):
                status, diagnosis = "diagnosed", DiagnosisLayer.PROCEDURE
                detail = f"{execution.macro_id}: step failure"
                break
            if execution.postconditions_passed is not True:
                status, diagnosis = "diagnosed", DiagnosisLayer.POSTCONDITION
                detail = f"{execution.macro_id}: postconditions did not hold"
                break
            after = world.observe()
            transitions[-1] = transitions[-1].model_copy(update={"state_after": after.fields})
            if graph.goal and evaluate_predicates(graph.goal, after.fields):
                status = "completed"
                break
            node_id = graph.entry_node
            continue
        transitions.append(transition)
        events.append(TraceEvent(kind="route", depth=depth, detail=selected))
        node_id = str(choice.target_node)
    else:
        events.append(TraceEvent(kind="depth_exceeded", depth=max_depth, detail=node_id))
        status = "depth_exceeded"
    return GraphRunResult(
        status=status,
        transitions=tuple(transitions),
        events=tuple(events),
        diagnosis=diagnosis,
        diagnosis_detail=detail,
    )


# --- Teacher candidate envelope (docs/architecture/teacher-protocol.md) -----

CANDIDATE_TYPES = (
    "ADD_CHOICE",
    "GENERALIZE_CHOICE",
    "SPLIT_CHOICE",
    "MERGE_CHOICES",
    "ADD_DECISION_NODE",
    "RESTRUCTURE_NODE",
    "ADD_MACRO",
    "ADD_MACRO_BRANCH",
    "DEPRECATE_MACRO",
    "ADD_STATE_FEATURE",
    "ADD_NORMALIZER",
    "CHANGE_PRECONDITION",
    "CHANGE_POSTCONDITION",
    "MISSING_CAPABILITY",
    "NO_CHANGE",
    "INSUFFICIENT_EVIDENCE",
)


class TeacherCandidate(Frozen):
    """Typed evolution envelope; sections must match the declared operator."""

    candidate_type: Literal[
        "ADD_CHOICE",
        "GENERALIZE_CHOICE",
        "SPLIT_CHOICE",
        "MERGE_CHOICES",
        "ADD_DECISION_NODE",
        "RESTRUCTURE_NODE",
        "ADD_MACRO",
        "ADD_MACRO_BRANCH",
        "DEPRECATE_MACRO",
        "ADD_STATE_FEATURE",
        "ADD_NORMALIZER",
        "CHANGE_PRECONDITION",
        "CHANGE_POSTCONDITION",
        "MISSING_CAPABILITY",
        "NO_CHANGE",
        "INSUFFICIENT_EVIDENCE",
    ]
    target_id: str = ""
    macro: Macro | None = None
    choice: Choice | None = None
    semantic_description: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    base_policy_id: str

    @model_validator(mode="after")
    def sections_match_operator(self) -> "TeacherCandidate":
        if self.candidate_type == "ADD_MACRO":
            if self.macro is None or self.choice is not None:
                raise ValueError("ADD_MACRO requires a macro section and no choice")
        elif self.candidate_type == "ADD_CHOICE":
            if self.choice is None or self.macro is not None:
                raise ValueError("ADD_CHOICE requires a choice section and no macro")
        elif self.candidate_type in {
            "NO_CHANGE",
            "INSUFFICIENT_EVIDENCE",
            "MISSING_CAPABILITY",
        }:
            if self.macro is not None or self.choice is not None:
                raise ValueError(f"{self.candidate_type} carries no change sections")
        return self


def load_module(name: str) -> Any:
    return importlib.import_module(name)


def build_candidate_schema() -> dict[str, Any]:
    """Fully typed strict schema; pydantic emits nested definitions the gateway honours.

    Strict mode rejects open-ended objects, so MacroStep's free-form args are
    narrowed to the registered primitive argument names (nullable when unused).
    """
    schema = TeacherCandidate.model_json_schema()
    for definition in schema.get("$defs", {}).values():
        if definition.get("title") == "MacroStep":
            definition["properties"]["args"] = {
                "type": "object",
                "properties": {
                    "preferred": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                    "name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
                "required": ["preferred", "name"],
                "additionalProperties": False,
            }
    return schema


def apply_add_choice(graph: PolicyGraphVersion, candidate: TeacherCandidate) -> PolicyGraphVersion:
    """Deterministically apply an ADD_CHOICE candidate to a new graph version."""
    assert candidate.choice is not None
    choice = candidate.choice
    nodes = []
    changed = False
    for node in graph.nodes:
        if node.id == candidate.target_id:
            changed = True
            if any(c.id == choice.id for c in node.choices):
                raise ValueError("choice id already present")
            if len(node.choices) >= MAX_CHOICES:
                raise ValueError("node at maximum choice count")
            nodes.append(node.model_copy(update={"choices": (*node.choices, choice)}))
        else:
            nodes.append(node)
    if not changed:
        raise ValueError(f"target node not found: {candidate.target_id}")
    return PolicyGraphVersion(
        id=graph.id,
        version_number=graph.version_number + 1,
        parent_version_id=graph.id,
        jev_profile_ref=graph.jev_profile_ref,
        entry_node=graph.entry_node,
        nodes=tuple(nodes),
        macros=graph.macros,
    )
