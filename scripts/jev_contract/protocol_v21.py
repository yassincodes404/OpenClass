"""Teacher Protocol v2.2: semantic proposals only; OpenClass owns binding and scope.

The Teacher emits a TeacherProposal (operator, target selection, payload,
description, rationale, confidence). Every machine-identity field — candidate
id, base policy id/hash, provider, profile hash, context and schema hashes,
timestamps — is attached afterwards by OpenClass in a CandidateEnvelope and is
never generated or copied by the model. Symbolic identifiers whose valid
universe is known at request time are constrained to strict enums so invalid
tokens are structurally impossible rather than merely discouraged.

v2.2: state-feature scope (`required`) is no longer Teacher authority. The
proposal names the registered source a fact comes from; OpenClass derives
scope deterministically from that source's availability contract.
"""

import json
import uuid
from datetime import UTC, datetime
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
    Step,
    digest,
)
from .knowledge import JevProfile, require_current
from .teacher import Capability, Operator

PROTOCOL_VERSION = "teacher-protocol-v2.2"


class StateSource(Frozen):
    """Registered observation-source contract owned by OpenClass, not the model."""

    id: Identifier
    availability: Literal["always", "conditional"]
    observes: str = Field(min_length=1, max_length=500)


class FeatureProposal(Frozen):
    """Semantic state-feature proposal. Scope is derived from the named source."""

    id: Identifier
    kind: Literal["string", "integer", "boolean"]
    sensor_field: str = Field(min_length=1, max_length=200)
    source: Identifier


class TeacherProposal(Frozen):
    """Semantic content only. No hashes, ids of candidates, or provenance."""

    operator: Operator
    target_id: str = ""
    choice: Choice | None = None
    steps: tuple[Step, ...] | None = None
    feature: FeatureProposal | None = None
    predicates: tuple[Predicate, ...] | None = None
    semantic_description: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def shape(self) -> "TeacherProposal":
        required = {
            "ADD_CHOICE": "choice",
            "GENERALIZE_CHOICE": "choice",
            "REPLACE_PROCEDURE": "steps",
            "ADD_STATE_FEATURE": "feature",
            "CHANGE_PRECONDITION": "predicates",
            "CHANGE_POSTCONDITION": "predicates",
            "CHANGE_SAFETY_GUARD": "predicates",
        }.get(self.operator)
        present = {
            key
            for key, value in {
                "choice": self.choice,
                "steps": self.steps,
                "feature": self.feature,
                "predicates": self.predicates,
            }.items()
            if value is not None
        }
        if present != ({required} if required else set()):
            raise ValueError("operator-specific payload mismatch")
        if not required and self.target_id:
            raise ValueError("non-change answers use an empty target_id")
        if required and not self.target_id:
            raise ValueError("change must identify an exact target")
        if self.steps is not None and not self.steps:
            raise ValueError("procedure cannot be empty")
        return self


class CandidateEnvelope(Frozen):
    """Deterministic OpenClass-owned provenance around an exact proposal."""

    candidate_id: str
    base_policy_id: str
    base_policy_hash: str
    teacher_provider: str
    teacher_model: str
    protocol_version: str
    jevprofile_id: str
    jevprofile_hash: str
    context_pack_hash: str
    schema_hash: str
    created_at: datetime
    proposal: TeacherProposal

    @model_validator(mode="after")
    def binding(self) -> "CandidateEnvelope":
        if self.protocol_version != PROTOCOL_VERSION:
            raise ValueError("envelope protocol mismatch")
        if self.proposal.model_dump(mode="json").get("base_policy_hash") is not None:
            raise ValueError("proposals never carry binding fields")
        return self


def wrap(
    proposal: TeacherProposal,
    graph: PolicyGraph,
    profile: JevProfile,
    teacher_model: str,
    context_pack_hash: str,
    schema_hash: str,
    teacher_provider: str = "openai-compatible-gateway",
) -> CandidateEnvelope:
    return CandidateEnvelope(
        candidate_id=str(uuid.uuid4()),
        base_policy_id=graph.id,
        base_policy_hash=graph.content_hash,
        teacher_provider=teacher_provider,
        teacher_model=teacher_model,
        protocol_version=PROTOCOL_VERSION,
        jevprofile_id=profile.id,
        jevprofile_hash=digest(profile.model_dump(mode="json")),
        context_pack_hash=context_pack_hash,
        schema_hash=schema_hash,
        created_at=datetime.now(UTC),
        proposal=proposal,
    )


def context_pack(
    failed_layer: str,
    deterministic_evidence: tuple[str, ...],
    graph: PolicyGraph,
    capabilities: tuple[Capability, ...],
    permitted_operators: tuple[Operator, ...],
    profile: JevProfile,
    events: tuple[Any, ...] = (),
) -> dict[str, Any]:
    """Compact v2.1 context: Core contract facts + profile; no skill, no examples."""
    require_current(profile, events)
    return {
        "failed_layer": failed_layer,
        "deterministic_evidence": list(deterministic_evidence),
        "graph": graph.model_dump(mode="json"),
        "capabilities": [c.model_dump(mode="json") for c in capabilities],
        "permitted_operators": list(permitted_operators),
        "jev_operating_manual": profile.manual(),
    }


def valid_targets(operator: str, graph: PolicyGraph) -> tuple[str, ...]:
    if operator in {"ADD_CHOICE", "GENERALIZE_CHOICE"}:
        return tuple(n.id for n in graph.nodes)
    if operator == "ADD_STATE_FEATURE":
        return (graph.state_schema.id,)
    if operator in {
        "REPLACE_PROCEDURE",
        "CHANGE_PRECONDITION",
        "CHANGE_POSTCONDITION",
        "CHANGE_SAFETY_GUARD",
    }:
        return tuple(m.id for m in graph.macros)
    return ("",)


def proposal_schema(
    graph: PolicyGraph,
    capabilities: tuple[Capability, ...],
    permitted_operators: tuple[Operator, ...],
    sources: tuple[StateSource, ...] = (),
) -> dict[str, Any]:
    """Strict schema with request-specific enums for every known universe."""
    node_ids = [n.id for n in graph.nodes]
    macro_ids = [m.id for m in graph.macros]
    choice_ids = sorted({c.id for n in graph.nodes for c in n.choices})
    state_fields = [f.id for f in graph.state_schema.features]

    operators_by_target: dict[str, list[str]] = {}
    for operator in permitted_operators:
        operators_by_target.setdefault(operator, [])
    choice_targets = ["terminal"]
    if macro_ids:
        choice_targets.append("macro")
    if len(node_ids) > 1:
        choice_targets.append("node")

    def enum(values: list[str]) -> dict[str, Any]:
        return {"type": "string", "enum": values}

    step_shapes = []
    for capability in capabilities:
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
                    "capability": enum([capability.id]),
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

    new_choice = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {
                "type": "string",
                "pattern": "^[a-z][a-z0-9_]{2,40}$",
            },
            "meaning": {"type": "string", "minLength": 8, "maxLength": 500},
            "target_kind": enum(choice_targets),
            "target_id": {
                "anyOf": [
                    *([{"type": "string", "enum": macro_ids}] if "macro" in choice_targets else []),
                    *([{"type": "string", "enum": node_ids}] if "node" in choice_targets else []),
                    {"type": "null"},
                ]
            },
        },
        "required": ["id", "meaning", "target_kind", "target_id"],
    }
    generalize_choice = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": enum(choice_ids),
            "meaning": {"type": "string", "minLength": 8, "maxLength": 500},
            "target_kind": enum(choice_targets),
            "target_id": {
                "anyOf": [
                    *([{"type": "string", "enum": macro_ids}] if "macro" in choice_targets else []),
                    *([{"type": "string", "enum": node_ids}] if "node" in choice_targets else []),
                    {"type": "null"},
                ]
            },
        },
        "required": ["id", "meaning", "target_kind", "target_id"],
    }
    predicate = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "field": enum(state_fields) if state_fields else {"type": "string"},
            "equals": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "integer"},
                    {"type": "boolean"},
                    {"type": "null"},
                ]
            },
        },
        "required": ["field", "equals"],
    }
    feature = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{2,40}$"},
            "kind": enum(["string", "integer", "boolean"]),
            "sensor_field": {"type": "string", "minLength": 1},
            "source": enum([s.id for s in sources]),
        },
        "required": ["id", "kind", "sensor_field", "source"],
    }

    payload_properties: dict[str, Any] = {}
    if "ADD_CHOICE" in permitted_operators or "GENERALIZE_CHOICE" in permitted_operators:
        payload_properties["choice"] = (
            new_choice if "ADD_CHOICE" in permitted_operators else generalize_choice
        )
    if "REPLACE_PROCEDURE" in permitted_operators and step_shapes:
        payload_properties["steps"] = {"type": "array", "items": {"anyOf": step_shapes}}
    if "ADD_STATE_FEATURE" in permitted_operators and sources:
        payload_properties["feature"] = feature
    if {"CHANGE_PRECONDITION", "CHANGE_POSTCONDITION", "CHANGE_SAFETY_GUARD"} & set(
        permitted_operators
    ):
        payload_properties["predicates"] = {"type": "array", "items": predicate}
    payload: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": payload_properties,
        "required": list(payload_properties),
    }
    # Bare JSON schema: the wire layer wraps it as response_format.json_schema
    # (name/strict). Nesting the envelope here makes gateways drop enforcement.
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "operator": enum(list(permitted_operators)),
            # Providers reject empty enum values, so the non-change target is
            # expressed as null and normalized to "" deterministically on parse.
            "target_id": {
                "anyOf": [
                    *(
                        [
                            {
                                "type": "string",
                                "enum": sorted(
                                    {
                                        t
                                        for op in permitted_operators
                                        for t in valid_targets(op, graph)
                                        if t
                                    }
                                ),
                            }
                        ]
                        if any(t for op in permitted_operators for t in valid_targets(op, graph))
                        else []
                    ),
                    {"type": "null"},
                ]
            },
            "payload": payload,
            "semantic_description": {"type": "string", "minLength": 1, "maxLength": 2000},
            "rationale": {"type": "string", "minLength": 1, "maxLength": 4000},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": [
            "operator",
            "target_id",
            "payload",
            "semantic_description",
            "rationale",
            "confidence",
        ],
    }


class ProposalRejected(ValueError):
    """The proposal does not fit the graph; evaluation never runs."""


def parse_proposal(content: str) -> TeacherProposal:
    """Parse the wire proposal with deterministic normalization.

    The wire nests operator payload fields under `payload`; the model is flat.
    Null/empty sentinels normalize to absence. Normalization can only remove
    sentinels or unwrap the wire envelope, never invent or drop real content.
    """
    data = json.loads(content)
    if isinstance(data, dict):
        if data.get("target_id") is None:
            data["target_id"] = ""
        payload = data.pop("payload", None)
        if isinstance(payload, dict):
            for key, value in payload.items():
                data[key] = None if value in ({}, [], "") else value
    return TeacherProposal.model_validate(data)


def derive_feature(feature: FeatureProposal, sources: tuple[StateSource, ...]) -> StateFeature:
    """Deterministic scope: required only when the named source reports always."""
    match = next((s for s in sources if s.id == feature.source), None)
    if match is None:
        raise ProposalRejected(f"unknown state source: {feature.source}")
    return StateFeature(
        id=feature.id,
        kind=feature.kind,
        sensor_field=feature.sensor_field,
        required=match.availability == "always",
    )


def apply_proposal(
    graph: PolicyGraph,
    proposal: TeacherProposal,
    capabilities: tuple[Capability, ...] = (),
    sources: tuple[StateSource, ...] = (),
) -> PolicyGraph:
    """Deterministic application to an INACTIVE next version; no activation path."""
    if proposal.target_id and proposal.target_id not in valid_targets(proposal.operator, graph):
        raise ProposalRejected("target outside the request's valid universe")
    nodes, macros = list(graph.nodes), list(graph.macros)
    schema = graph.state_schema
    if proposal.operator in {
        "NO_CHANGE",
        "MISSING_CAPABILITY",
        "INSUFFICIENT_EVIDENCE",
        "PROVIDER_COMPATIBILITY",
    }:
        return graph
    if proposal.operator in {"ADD_CHOICE", "GENERALIZE_CHOICE"}:
        assert proposal.choice is not None
        index = next((i for i, n in enumerate(nodes) if n.id == proposal.target_id), None)
        if index is None:
            raise ProposalRejected("missing target node")
        node = nodes[index]
        choices = list(node.choices)
        existing = next((i for i, c in enumerate(choices) if c.id == proposal.choice.id), None)
        if proposal.operator == "ADD_CHOICE":
            if existing is not None:
                raise ProposalRejected("choice id already exists")
            if proposal.choice.target_kind == "macro" and proposal.choice.target_id not in {
                m.id for m in macros
            }:
                raise ProposalRejected("choice targets an unknown macro")
            if proposal.choice.target_kind == "node" and proposal.choice.target_id not in {
                n.id for n in nodes
            }:
                raise ProposalRejected("choice targets an unknown node")
            choices.append(proposal.choice)
        else:
            if existing is None:
                raise ProposalRejected("missing choice to generalize")
            old = choices[existing]
            if (old.target_id, old.target_kind) != (
                proposal.choice.target_id,
                proposal.choice.target_kind,
            ):
                raise ProposalRejected("generalization cannot change the working target")
            choices[existing] = proposal.choice
        nodes[index] = DecisionNode.model_validate({**node.model_dump(), "choices": choices})
    elif proposal.operator == "ADD_STATE_FEATURE":
        assert proposal.feature is not None
        if proposal.target_id != schema.id:
            raise ProposalRejected("missing target schema")
        derived = derive_feature(proposal.feature, sources)
        schema = type(schema).model_validate(
            {
                **schema.model_dump(),
                "version": schema.version + 1,
                "features": (*schema.features, derived),
            }
        )
    else:
        assert proposal.target_id in {m.id for m in macros}
        index = next(i for i, m in enumerate(macros) if m.id == proposal.target_id)
        macro = macros[index]
        field = {
            "REPLACE_PROCEDURE": "steps",
            "CHANGE_PRECONDITION": "preconditions",
            "CHANGE_POSTCONDITION": "postconditions",
            "CHANGE_SAFETY_GUARD": "safety_guards",
        }[proposal.operator]
        value: tuple[Step, ...] | tuple[Predicate, ...] | None
        if field == "steps":
            assert proposal.steps is not None
            catalog = {c.id: c for c in capabilities}
            for step in proposal.steps:
                capability = catalog.get(step.capability)
                if capability is None:
                    raise ProposalRejected("MISSING_CAPABILITY")
                capability.validate_step(step)
            value = proposal.steps
        else:
            assert proposal.predicates is not None
            if field == "safety_guards" and not all(
                p in proposal.predicates for p in macro.safety_guards
            ):
                raise ProposalRejected("existing safety guards may not be removed")
            value = proposal.predicates
        macros[index] = type(macro).model_validate({**macro.model_dump(), field: value})
    return PolicyGraph(
        id=graph.id,
        version=graph.version + 1,
        parent_hash=graph.content_hash,
        state_schema=schema,
        entry_node=graph.entry_node,
        nodes=tuple(nodes),
        macros=tuple(macros),
    )
