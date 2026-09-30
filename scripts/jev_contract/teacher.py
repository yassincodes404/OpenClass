"""Teacher protocol v1.1: bounded proposals, exact layer, no activation authority."""

import json
from typing import Any, Literal

from pydantic import Field, model_validator

from .canonical import (
    Choice,
    DecisionNode,
    Frozen,
    Identifier,
    PolicyGraph,
    Predicate,
    StateFeature,
    StateSchema,
    Step,
    digest,
)
from .knowledge import Evidence, JevProfile, ProfileEvent, require_current

Layer = Literal[
    "INFRASTRUCTURE",
    "STATE_REPRESENTATION",
    "DECISION_SPACE",
    "SEMANTIC_ROUTING",
    "PROCEDURE",
    "PRECONDITION",
    "POSTCONDITION",
    "SAFETY_GUARD",
    "MISSING_CAPABILITY",
    "INSUFFICIENT_EVIDENCE",
]
Operator = Literal[
    "ADD_CHOICE",
    "GENERALIZE_CHOICE",
    "REPLACE_PROCEDURE",
    "ADD_STATE_FEATURE",
    "CHANGE_PRECONDITION",
    "CHANGE_POSTCONDITION",
    "CHANGE_SAFETY_GUARD",
    "MISSING_CAPABILITY",
    "INSUFFICIENT_EVIDENCE",
    "NO_CHANGE",
    "PROVIDER_COMPATIBILITY",
]
ALLOWED: dict[Layer, tuple[Operator, ...]] = {
    "INFRASTRUCTURE": ("NO_CHANGE", "INSUFFICIENT_EVIDENCE"),
    "STATE_REPRESENTATION": ("ADD_STATE_FEATURE",),
    "DECISION_SPACE": ("ADD_CHOICE", "MISSING_CAPABILITY"),
    "SEMANTIC_ROUTING": ("GENERALIZE_CHOICE",),
    "PROCEDURE": ("REPLACE_PROCEDURE", "MISSING_CAPABILITY"),
    "PRECONDITION": ("CHANGE_PRECONDITION",),
    "POSTCONDITION": ("CHANGE_POSTCONDITION",),
    "SAFETY_GUARD": ("CHANGE_SAFETY_GUARD", "NO_CHANGE", "MISSING_CAPABILITY"),
    "MISSING_CAPABILITY": ("MISSING_CAPABILITY",),
    "INSUFFICIENT_EVIDENCE": ("INSUFFICIENT_EVIDENCE",),
}


class Capability(Frozen):
    id: Identifier
    arguments: dict[str, Literal["string", "integer", "boolean"]]
    permitted_values: dict[str, tuple[str | int | bool, ...]] = Field(default_factory=dict)

    def validate_step(self, step: Step) -> None:
        if step.capability != self.id or set(step.arguments) != set(self.arguments):
            raise ValueError("unknown capability or argument set")
        types = {"string": str, "integer": int, "boolean": bool}
        for name, kind in self.arguments.items():
            if type(step.arguments[name]) is not types[kind]:
                raise ValueError("wrong capability argument type")
            if (
                name in self.permitted_values
                and step.arguments[name] not in self.permitted_values[name]
            ):
                raise ValueError("argument outside registered capability domain")


class Payload(Frozen):
    choice: Choice | None = None
    steps: tuple[Step, ...] | None = None
    feature: StateFeature | None = None
    predicates: tuple[Predicate, ...] | None = None


class TeacherCandidate(Frozen):
    operator: Operator
    target_id: str
    payload: Payload
    base_policy_hash: str
    semantic_description: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def payload_shape(self) -> "TeacherCandidate":
        required = {
            "ADD_CHOICE": "choice",
            "GENERALIZE_CHOICE": "choice",
            "REPLACE_PROCEDURE": "steps",
            "ADD_STATE_FEATURE": "feature",
            "CHANGE_PRECONDITION": "predicates",
            "CHANGE_POSTCONDITION": "predicates",
            "CHANGE_SAFETY_GUARD": "predicates",
        }.get(self.operator)
        present = {k for k, v in self.payload.model_dump().items() if v is not None}
        if present != ({required} if required else set()):
            raise ValueError("operator-specific payload mismatch")
        if not required and self.target_id:
            raise ValueError("non-change answers use an empty target_id")
        if required and not self.target_id:
            raise ValueError("change must identify an exact target")
        if self.payload.steps is not None and not self.payload.steps:
            raise ValueError("procedure cannot be empty")
        return self


class AggregateFeedback(Frozen):
    protocol_id: str
    evaluated: int = Field(ge=0, le=10000)
    passed: int = Field(ge=0, le=10000)
    regressions: int = Field(ge=0, le=10000)

    @model_validator(mode="after")
    def counts(self) -> "AggregateFeedback":
        if max(self.passed, self.regressions) > self.evaluated:
            raise ValueError("invalid aggregate counts")
        return self


class TeacherRequest(Frozen):
    id: str
    failed_layer: Layer
    deterministic_evidence: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[Evidence, ...] = ()
    graph_slice: PolicyGraph
    state_schema: StateSchema
    profile: JevProfile
    candidate_history: tuple[TeacherCandidate, ...] = ()
    capabilities: tuple[Capability, ...]
    permitted_operators: tuple[Operator, ...]
    feedback_protocol: str | None = None
    feedback: AggregateFeedback | None = None

    @model_validator(mode="after")
    def scope(self) -> "TeacherRequest":
        if self.state_schema != self.graph_slice.state_schema:
            raise ValueError("Teacher schema must match graph")
        allowed = {*ALLOWED[self.failed_layer], "INSUFFICIENT_EVIDENCE", "PROVIDER_COMPATIBILITY"}
        if not self.permitted_operators or not set(self.permitted_operators) <= allowed:
            raise ValueError("operator outside diagnosed layer")
        if self.feedback and self.feedback.protocol_id != self.feedback_protocol:
            raise ValueError("aggregate feedback was not predeclared")
        if len({c.id for c in self.capabilities}) != len(self.capabilities):
            raise ValueError("duplicate capability")
        return self


SYSTEM = """You are the OpenClass Teacher, an engineer proposing the smallest change to a
versioned decision system. Output only the supplied typed candidate schema. Never activate
candidates or claim approval. The failed layer is deterministic evidence, not your choice.
Never change procedures to solve routing, or routing to hide procedure failures. A layer
change requires new deterministic evidence and a new request. Never delegate deterministic
safety to Jev. Do not encode exact environment strings as semantic aliases where semantic
routing handles the concept; literal distinctions require specific evidence. Procedure
arguments may use literal registered values grounded in failing-step evidence. Prefer
concrete, self-contained choices and explicit resolved state; avoid unnecessary hierarchy.
Use the supplied empirical profile, whose recommendations are bounded inferences. If the
policy cannot fit the measured profile, return PROVIDER_COMPATIBILITY. Never infer hidden
evaluation cases. Feedback, if present, is only predeclared bounded aggregate counts.
Use only the registered capability catalog with exact argument names/types/domains.
Return MISSING_CAPABILITY for nonexistent primitives, or INSUFFICIENT_EVIDENCE when facts
cannot support a change. UNKNOWN alone never proves that a new choice is necessary.
Non-change answers use an empty target_id and all-null payload fields.
No shell, code, paths, credentials, hidden labels, or activation authority are supplied.
"""


def messages(
    request: TeacherRequest, events: tuple[ProfileEvent, ...] = ()
) -> list[dict[str, str]]:
    require_current(request.profile, events)
    payload = request.model_dump(mode="json", exclude={"profile"})
    payload["jev_operating_manual"] = request.profile.manual()
    payload["profile_hash"] = digest(request.profile.model_dump(mode="json"))
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps(payload, sort_keys=True)},
    ]


def candidate_schema(request: TeacherRequest) -> dict[str, object]:
    """Close procedure argument objects against the actual registered catalog."""
    schema: dict[str, Any] = TeacherCandidate.model_json_schema()
    step_shapes = []
    for capability in request.capabilities:
        arguments = {
            name: {
                "type": kind,
                **(
                    {"enum": list(capability.permitted_values[name])}
                    if name in capability.permitted_values
                    else {}
                ),
            }
            for name, kind in capability.arguments.items()
        }
        step_shapes.append(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "capability": {"type": "string", "enum": [capability.id]},
                    "arguments": {
                        "type": "object",
                        "properties": arguments,
                        "required": list(arguments),
                        "additionalProperties": False,
                    },
                },
                "required": ["capability", "arguments"],
            }
        )
    if step_shapes:
        schema["$defs"]["Step"] = {"anyOf": step_shapes}
    else:
        schema["$defs"]["Step"] = {"not": {}}

    def close(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                value["required"] = list(value.get("properties", {}))
                value["additionalProperties"] = False
            value.pop("default", None)
            for child in value.values():
                close(child)
        elif isinstance(value, list):
            for child in value:
                close(child)

    close(schema)
    return schema


def apply_candidate(request: TeacherRequest, candidate: TeacherCandidate) -> PolicyGraph:
    """Create an inactive evaluation copy; there is intentionally no activation operation."""
    graph = request.graph_slice
    if candidate.base_policy_hash != graph.content_hash:
        raise ValueError("stale candidate base")
    if candidate.operator not in request.permitted_operators:
        raise ValueError("candidate changes the wrong diagnosed layer")
    nodes, macros = list(graph.nodes), list(graph.macros)
    schema = graph.state_schema
    payload = candidate.payload
    if candidate.operator in {
        "NO_CHANGE",
        "MISSING_CAPABILITY",
        "INSUFFICIENT_EVIDENCE",
        "PROVIDER_COMPATIBILITY",
    }:
        return graph
    if candidate.operator in {"ADD_CHOICE", "GENERALIZE_CHOICE"}:
        index = next((i for i, n in enumerate(nodes) if n.id == candidate.target_id), None)
        if index is None or payload.choice is None:
            raise ValueError("missing target node")
        node = nodes[index]
        choices = list(node.choices)
        existing = next((i for i, c in enumerate(choices) if c.id == payload.choice.id), None)
        if candidate.operator == "ADD_CHOICE":
            if existing is not None:
                raise ValueError("choice already exists")
            choices.append(payload.choice)
        else:
            if existing is None:
                raise ValueError("missing choice to generalize")
            old = choices[existing]
            if (old.target_id, old.target_kind) != (
                payload.choice.target_id,
                payload.choice.target_kind,
            ):
                raise ValueError("semantic repair cannot change a working procedure target")
            choices[existing] = payload.choice
        nodes[index] = DecisionNode.model_validate({**node.model_dump(), "choices": choices})
    elif candidate.operator == "ADD_STATE_FEATURE":
        if candidate.target_id != schema.id or payload.feature is None:
            raise ValueError("missing target schema")
        schema = StateSchema(
            id=schema.id, version=schema.version + 1, features=(*schema.features, payload.feature)
        )
    else:
        index = next((i for i, m in enumerate(macros) if m.id == candidate.target_id), None)
        if index is None:
            raise ValueError("missing target macro")
        macro = macros[index]
        field = {
            "REPLACE_PROCEDURE": "steps",
            "CHANGE_PRECONDITION": "preconditions",
            "CHANGE_POSTCONDITION": "postconditions",
            "CHANGE_SAFETY_GUARD": "safety_guards",
        }[candidate.operator]
        value = payload.steps if field == "steps" else payload.predicates
        if field == "steps":
            catalog = {c.id: c for c in request.capabilities}
            for step in payload.steps or ():
                if step.capability not in catalog:
                    raise ValueError("MISSING_CAPABILITY")
                catalog[step.capability].validate_step(step)
        if field == "safety_guards" and not all(p in (value or ()) for p in macro.safety_guards):
            raise ValueError("Teacher may not remove existing safety guards")
        macros[index] = type(macro).model_validate({**macro.model_dump(), field: value})
    updated = PolicyGraph(
        id=graph.id,
        version=graph.version + 1,
        parent_hash=graph.content_hash,
        state_schema=schema,
        entry_node=graph.entry_node,
        nodes=tuple(nodes),
        macros=tuple(macros),
    )
    from .canonical import StateSnapshot
    from .jev import JevDecisionCompiler

    compiler = JevDecisionCompiler(request.profile)
    for node in updated.nodes:
        compiler.compile(
            node, StateSnapshot(schema_id=schema.id, schema_version=schema.version, facts={})
        )
    return updated
