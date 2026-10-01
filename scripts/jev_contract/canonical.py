"""Provider-neutral, versioned policy and factual state boundaries."""

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


def digest(value: JsonValue) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


class StateFeature(Frozen):
    id: Identifier
    kind: Literal["string", "integer", "boolean"]
    sensor_field: str
    required: bool = True


class StateSchema(Frozen):
    id: Identifier
    version: int = Field(ge=1)
    features: tuple[StateFeature, ...]

    @model_validator(mode="after")
    def unique(self) -> "StateSchema":
        if len({f.id for f in self.features}) != len(self.features):
            raise ValueError("duplicate state feature")
        return self


class ResolvedDecision(Frozen):
    node_id: Identifier
    choice_id: Identifier
    meaning: str = Field(min_length=1)


class StateSnapshot(Frozen):
    schema_id: Identifier
    schema_version: int = Field(ge=1)
    facts: dict[str, JsonValue]
    raw_evidence: tuple[str, ...] = ()
    resolved_decisions: tuple[ResolvedDecision, ...] = ()

    @property
    def id(self) -> str:
        return digest(self.model_dump(mode="json"))


def compile_state(
    state_schema: StateSchema,
    sensor_facts: dict[str, JsonValue],
    raw_evidence: tuple[str, ...] = (),
    resolved: tuple[ResolvedDecision, ...] = (),
) -> StateSnapshot:
    """Copy sensor facts; never classify text or silently coerce absent facts."""
    facts: dict[str, JsonValue] = {}
    types = {"string": str, "integer": int, "boolean": bool}
    for feature in state_schema.features:
        if feature.sensor_field not in sensor_facts:
            if feature.required:
                raise ValueError(f"missing sensor fact: {feature.id}")
            continue
        value = sensor_facts[feature.sensor_field]
        if type(value) is not types[feature.kind]:
            raise ValueError(f"wrong sensor type: {feature.id}")
        facts[feature.id] = value
    return StateSnapshot(
        schema_id=state_schema.id,
        schema_version=state_schema.version,
        facts=facts,
        raw_evidence=raw_evidence,
        resolved_decisions=resolved,
    )


class Choice(Frozen):
    id: Identifier
    meaning: str = Field(min_length=1, max_length=2000)
    target_kind: Literal["node", "macro", "terminal"]
    target_id: Identifier | None

    @model_validator(mode="after")
    def target(self) -> "Choice":
        if (self.target_kind == "terminal") != (self.target_id is None):
            raise ValueError("only terminal choices omit target_id")
        if self.id == "unknown":
            raise ValueError("UNKNOWN is permanent and cannot be a domain choice")
        return self


class DecisionNode(Frozen):
    id: Identifier
    question: str = Field(min_length=1, max_length=2000)
    choices: tuple[Choice, ...] = Field(min_length=1)
    risk: Literal["ordinary", "high"] = "ordinary"
    decomposition_reason: str | None = None

    @model_validator(mode="after")
    def unique(self) -> "DecisionNode":
        if len({c.id for c in self.choices}) != len(self.choices):
            raise ValueError("duplicate choice id")
        return self


class Predicate(Frozen):
    field: Identifier
    equals: str | int | bool | None


class Step(Frozen):
    capability: Identifier
    arguments: dict[str, str | int | bool]


class Macro(Frozen):
    id: Identifier
    purpose: str
    steps: tuple[Step, ...] = Field(min_length=1)
    preconditions: tuple[Predicate, ...] = ()
    safety_guards: tuple[Predicate, ...] = ()
    postconditions: tuple[Predicate, ...] = Field(min_length=1)


class PolicyGraph(Frozen):
    id: Identifier
    version: int = Field(ge=1)
    parent_hash: str | None = None
    state_schema: StateSchema
    entry_node: Identifier
    nodes: tuple[DecisionNode, ...] = Field(min_length=1)
    macros: tuple[Macro, ...] = ()

    @model_validator(mode="after")
    def references(self) -> "PolicyGraph":
        nodes, macros = {n.id for n in self.nodes}, {m.id for m in self.macros}
        if len(nodes) != len(self.nodes) or len(macros) != len(self.macros):
            raise ValueError("duplicate node or macro")
        if self.entry_node not in nodes:
            raise ValueError("missing entry node")
        for node in self.nodes:
            for choice in node.choices:
                if choice.target_kind == "node" and choice.target_id not in nodes:
                    raise ValueError("missing target node")
                if choice.target_kind == "macro" and choice.target_id not in macros:
                    raise ValueError("missing target macro")
        return self

    @property
    def content_hash(self) -> str:
        return digest(self.model_dump(mode="json"))
