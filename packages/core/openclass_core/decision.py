"""Decision-plane domain model, reconciled from the validated research program.

Provider-neutral: decision providers compile requests from these types and
return distributions; nothing here imports a provider, the server, or an SDK.
The canonical semantics are deliberate: UNKNOWN is a permanent state, choice
sets are concrete and self-contained, graphs are immutable versions linked by
parent hash, and state compilation never classifies text.
"""

import hashlib
import json
import math
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from .models import Model


def content_digest(value: Any) -> str:
    """Deterministic sha256 over canonical JSON; the basis for all identity."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class SourceAvailability(StrEnum):
    """How often an observation source reports. Drives feature scope derivation."""

    ALWAYS = "always"
    CONDITIONAL = "conditional"


class StateSource(Model):
    """Registered observation-source contract. Scope is derived from this, never
    decided by a model."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    availability: SourceAvailability
    observes: str = Field(min_length=1, max_length=500)


class StateFeature(Model):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    kind: Literal["string", "integer", "boolean"]
    sensor_field: str = Field(min_length=1, max_length=200)
    required: bool = True
    nullable: bool = False
    source: Literal["metadata", "prior_decision"] = "metadata"


class StateSchema(Model):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    version: int = Field(ge=1)
    features: tuple[StateFeature, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_features(self) -> "StateSchema":
        if len({f.id for f in self.features}) != len(self.features):
            raise ValueError("duplicate state feature")
        return self


class ResolvedDecision(Model):
    """A prior decision, restated concretely. Routers never rely on anaphora."""

    node_id: str
    choice_id: str
    meaning: str = Field(min_length=1)


class StateSnapshot(Model):
    schema_id: str
    schema_version: int = Field(ge=1)
    facts: dict[str, Any]
    raw_evidence: tuple[str, ...] = ()
    resolved_decisions: tuple[ResolvedDecision, ...] = ()

    @property
    def id(self) -> str:
        return content_digest(self.model_dump(mode="json"))


def compile_state(
    schema: StateSchema,
    sensor_facts: dict[str, Any],
    raw_evidence: tuple[str, ...] = (),
    resolved: tuple[ResolvedDecision, ...] = (),
) -> StateSnapshot:
    """Copy schema-declared sensor facts into a snapshot.

    Never classifies text, never coerces types, never invents values. Required
    features that are missing fail loudly: a representation gap is a
    representational problem, not silent absence.
    """
    types: dict[str, type] = {"string": str, "integer": int, "boolean": bool}
    facts: dict[str, Any] = {}
    for feature in schema.features:
        if feature.sensor_field not in sensor_facts:
            if feature.required:
                raise ValueError(f"missing sensor fact: {feature.id}")
            continue
        value = sensor_facts[feature.sensor_field]
        if not (value is None and feature.nullable) and type(value) is not types[feature.kind]:
            raise ValueError(f"wrong sensor type: {feature.id}")
        facts[feature.id] = value
    return StateSnapshot(
        schema_id=schema.id,
        schema_version=schema.version,
        facts=facts,
        raw_evidence=raw_evidence,
        resolved_decisions=resolved,
    )


class Choice(Model):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    meaning: str = Field(min_length=1, max_length=2000)
    target_kind: Literal["node", "macro", "terminal"]
    target_id: str | None = None

    @model_validator(mode="after")
    def target(self) -> "Choice":
        if (self.target_kind == "terminal") != (self.target_id is None):
            raise ValueError("only terminal choices omit target_id")
        if self.id == "unknown":
            raise ValueError("UNKNOWN is permanent and cannot be a domain choice")
        return self


class DecisionNode(Model):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    question: str = Field(min_length=1, max_length=2000)
    choices: tuple[Choice, ...] = Field(min_length=1, max_length=32)
    risk: Literal["ordinary", "high"] = "ordinary"
    decomposition_reason: str | None = None

    @model_validator(mode="after")
    def unique_choices(self) -> "DecisionNode":
        if len({c.id for c in self.choices}) != len(self.choices):
            raise ValueError("duplicate choice id")
        if any(c.target_kind == "node" for c in self.choices) and not self.decomposition_reason:
            raise ValueError("hierarchy requires a real domain decomposition reason")
        return self


class Predicate(Model):
    field: str = Field(min_length=1, max_length=200)
    equals: str | int | bool | None


class Step(Model):
    capability: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    arguments: dict[str, str | int | bool]


class Capability(Model):
    """A registered primitive. Proposals may only compose these; anything else
    is MISSING_CAPABILITY."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    arguments: dict[str, Literal["string", "integer", "boolean"]]
    permitted_values: dict[str, tuple[str | int | bool, ...]] = Field(default_factory=dict)

    def validate_step(self, step: Step) -> None:
        if step.capability != self.id or set(step.arguments) != set(self.arguments):
            raise ValueError("unknown capability or argument set")
        types: dict[str, type] = {"string": str, "integer": int, "boolean": bool}
        for name, kind in self.arguments.items():
            if type(step.arguments[name]) is not types[kind]:
                raise ValueError("wrong capability argument type")
            if (
                name in self.permitted_values
                and step.arguments[name] not in self.permitted_values[name]
            ):
                raise ValueError("argument outside registered capability domain")


class Macro(Model):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    purpose: str = Field(min_length=1, max_length=2000)
    steps: tuple[Step, ...] = Field(min_length=1, max_length=32)
    preconditions: tuple[Predicate, ...] = ()
    safety_guards: tuple[Predicate, ...] = ()
    postconditions: tuple[Predicate, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def steps_use_known_shapes(self) -> "Macro":
        if any(not s.capability for s in self.steps):
            raise ValueError("capability ids must be nonempty")
        return self


class PolicyGraph(Model):
    """Immutable decision-graph version. Evolution creates a new version with a
    parent hash; nothing is edited in place."""

    id: str
    version: int = Field(ge=1)
    parent_hash: str | None = None
    state_schema: StateSchema
    entry_node: str
    nodes: tuple[DecisionNode, ...] = Field(min_length=1)
    macros: tuple[Macro, ...] = ()
    goal: tuple[Predicate, ...] = ()

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
        return content_digest(self.model_dump(mode="json"))


def evaluate_predicates(predicates: tuple[Predicate, ...], facts: dict[str, Any]) -> bool:
    for p in predicates:
        if p.field not in facts:
            return False
        actual = facts[p.field]
        if isinstance(actual, bool) != isinstance(p.equals, bool):
            return False
        if actual != p.equals:
            return False
    return True


class DecisionOutcome(Model):
    """Provider-neutral result of one compiled decision. Semantic fields are
    present only for successful inferences; infrastructure failure carries none."""

    selected_choice: str | None
    distribution: dict[str, float] | None = None
    selected_probability: float | None = None
    top_probability: float | None = None
    second_probability: float | None = None
    margin: float | None = None
    unknown_probability: float | None = None
    infrastructure_status: Literal["ok", "transport", "http", "invalid_response"] = "ok"
    simulated: bool = False
    latency_ms: float = Field(default=0, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def separation(self) -> "DecisionOutcome":
        semantic = (
            self.selected_choice,
            self.distribution,
            self.top_probability,
            self.second_probability,
            self.margin,
            self.unknown_probability,
        )
        if self.infrastructure_status != "ok":
            if any(v is not None for v in semantic):
                raise ValueError("infrastructure failure is not a semantic observation")
            return self
        distribution = self.distribution
        if any(v is None for v in semantic) or distribution is None:
            raise ValueError("successful decision requires full semantic telemetry")
        if UNKNOWN not in distribution:
            raise ValueError("distribution must include UNKNOWN")
        if any(not math.isfinite(v) or not 0 <= v <= 1 for v in distribution.values()):
            raise ValueError("invalid probability")
        if abs(sum(distribution.values()) - 1) > 1e-6:
            raise ValueError("distribution must be normalized")
        expected_selected = max(distribution, key=lambda k: (distribution[k], k == UNKNOWN, k))
        if self.selected_choice != expected_selected:
            raise ValueError("selected choice disagrees with the deterministic selection rule")
        ordered = sorted(distribution.values(), reverse=True)
        expected = (
            distribution[self.selected_choice],
            ordered[0],
            ordered[1],
            ordered[0] - ordered[1],
            distribution[UNKNOWN],
        )
        actual = (
            self.selected_probability,
            self.top_probability,
            self.second_probability,
            self.margin,
            self.unknown_probability,
        )
        if any(
            v is None or not math.isfinite(v) or abs(v - e) > 1e-8
            for v, e in zip(actual, expected, strict=True)
        ):
            raise ValueError("derived probability telemetry mismatch")
        return self


UNKNOWN = "UNKNOWN"


def select_choice(distribution: dict[str, float]) -> str:
    """Pre-registered rule: argmax over known choices; UNKNOWN wins ties."""
    return max(distribution, key=lambda k: (distribution[k], k == UNKNOWN, k))


class SupervisionPolicy(Model):
    """Research-calibrated escalation rule. Never production thresholds without
    held-out evidence and human review; infrastructure and UNKNOWN always
    escalate, and high-risk nodes are never auto-continued."""

    id: str
    min_margin: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    max_unknown: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    calibration: Literal["research", "production"] = "research"
    validation_artifact_hash: str | None = None

    def decide(
        self, outcome: DecisionOutcome, node: DecisionNode
    ) -> Literal["continue", "escalate"]:
        if outcome.infrastructure_status != "ok" or outcome.selected_choice == UNKNOWN:
            return "escalate"
        if node.risk == "high":
            return "escalate"
        if self.calibration != "production" or self.validation_artifact_hash is None:
            return "escalate"
        assert outcome.margin is not None and outcome.unknown_probability is not None
        if self.min_margin is None or self.max_unknown is None:
            return "escalate"
        return (
            "continue"
            if outcome.margin >= self.min_margin and outcome.unknown_probability <= self.max_unknown
            else "escalate"
        )
