"""Evolution-plane domain model: failure evidence, Teacher proposals, candidate
envelopes, and the approval boundary.

Boundary rule proven by the research program: the Teacher owns meaning; the
envelope and every machine-level field (ids, hashes, versions, scope) is
attached by OpenClass after inference and is never generated or copied by a
model.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from .decision import (
    Capability,
    Choice,
    Predicate,
    SourceAvailability,
    StateFeature,
    StateSource,
    Step,
    content_digest,
)
from .models import Model


class FailureLayer(StrEnum):
    """The knowledge layer a deterministic diagnosis attributes a failure to."""

    INFRASTRUCTURE = "infrastructure"
    STATE_REPRESENTATION = "state_representation"
    DECISION_SPACE = "decision_space"
    SEMANTIC_ROUTING = "semantic_routing"
    PROCEDURE = "procedure"
    PRECONDITION = "precondition"
    SAFETY_GUARD = "safety_guard"
    POSTCONDITION = "postcondition"
    MISSING_CAPABILITY = "missing_capability"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


LAYER_OPERATORS: dict[FailureLayer, tuple[str, ...]] = {
    FailureLayer.INFRASTRUCTURE: ("no_change", "insufficient_evidence"),
    FailureLayer.STATE_REPRESENTATION: ("add_state_feature",),
    FailureLayer.DECISION_SPACE: ("add_choice", "missing_capability"),
    FailureLayer.SEMANTIC_ROUTING: ("generalize_choice",),
    FailureLayer.PROCEDURE: ("replace_procedure", "missing_capability"),
    FailureLayer.PRECONDITION: ("change_precondition",),
    FailureLayer.POSTCONDITION: ("change_postcondition",),
    FailureLayer.SAFETY_GUARD: ("change_safety_guard", "no_change", "missing_capability"),
    FailureLayer.MISSING_CAPABILITY: ("missing_capability",),
    FailureLayer.INSUFFICIENT_EVIDENCE: ("insufficient_evidence",),
}


class FailureDiagnosis(Model):
    """Deterministic attribution, produced before any Teacher inference."""

    layer: FailureLayer
    node_id: str | None = None
    macro_id: str | None = None
    rule: str = Field(min_length=1)
    deterministic_evidence: tuple[str, ...] = Field(min_length=1)
    unrepresented_sensor_facts: dict[str, Any] = Field(default_factory=dict)


class Evidence(Model):
    """Hash-addressed reference to recorded observation artifacts."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,79}$")
    description: str = Field(min_length=1, max_length=2000)
    source_path: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)


class FeatureProposal(Model):
    """Semantic state-feature proposal. Scope is derived by OpenClass from the
    named source's availability contract — the proposal never carries it."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    kind: Literal["string", "integer", "boolean"]
    sensor_field: str = Field(min_length=1, max_length=200)
    source: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")


class EvolutionOperator(StrEnum):
    ADD_CHOICE = "add_choice"
    GENERALIZE_CHOICE = "generalize_choice"
    REPLACE_PROCEDURE = "replace_procedure"
    ADD_STATE_FEATURE = "add_state_feature"
    CHANGE_PRECONDITION = "change_precondition"
    CHANGE_POSTCONDITION = "change_postcondition"
    CHANGE_SAFETY_GUARD = "change_safety_guard"
    MISSING_CAPABILITY = "missing_capability"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NO_CHANGE = "no_change"


CHANGE_SECTIONS = {
    EvolutionOperator.ADD_CHOICE: "choice",
    EvolutionOperator.GENERALIZE_CHOICE: "choice",
    EvolutionOperator.REPLACE_PROCEDURE: "steps",
    EvolutionOperator.ADD_STATE_FEATURE: "feature",
    EvolutionOperator.CHANGE_PRECONDITION: "predicates",
    EvolutionOperator.CHANGE_POSTCONDITION: "predicates",
    EvolutionOperator.CHANGE_SAFETY_GUARD: "predicates",
}


class TeacherProposal(Model):
    """Semantic proposal content only. Identity, hashes, versions and scope are
    attached by OpenClass in the CandidateEnvelope and never emitted by a model."""

    operator: EvolutionOperator
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
        sections = {
            "choice": self.choice,
            "steps": self.steps,
            "feature": self.feature,
            "predicates": self.predicates,
        }
        required = CHANGE_SECTIONS.get(self.operator)
        present = {k for k, v in sections.items() if v is not None}
        if present != ({required} if required else set()):
            raise ValueError("operator-specific payload mismatch")
        if not required and self.target_id:
            raise ValueError("non-change answers use an empty target_id")
        if required and not self.target_id:
            raise ValueError("change must identify an exact target")
        if self.steps is not None and not self.steps:
            raise ValueError("procedure cannot be empty")
        return self

    def permitted_for(self, layer: FailureLayer) -> bool:
        return self.operator in LAYER_OPERATORS[layer]


class CandidateEnvelope(Model):
    """OpenClass-owned provenance around an exact proposal. Attached after
    inference; nothing here is generated by a model."""

    candidate_id: UUID = Field(default_factory=uuid4)
    base_policy_id: str
    base_policy_hash: str = Field(min_length=64, max_length=64)
    teacher_provider: str
    teacher_model: str
    protocol_version: str
    profile_id: str
    profile_hash: str
    context_pack_hash: str
    schema_hash: str
    created_at: datetime
    proposal: TeacherProposal


class CandidateStatus(StrEnum):
    PROPOSED = "proposed"
    EVALUATED = "evaluated"
    APPROVED = "approved"
    ACTIVATED = "activated"
    REJECTED = "rejected"


class Approval(Model):
    """Explicit, scoped, per-version human approval. Never inferred."""

    candidate_id: UUID
    approved_at: datetime
    approver: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    statement: str = Field(min_length=1)


class EvaluationSummary(Model):
    """Deterministic evaluation outcome over hidden, human-authored cases."""

    passed: bool
    checks: dict[str, bool]
    knowledge_retention_rate: float = Field(ge=0, le=1)
    regressions: tuple[str, ...] = ()


class Candidate(Model):
    """A proposed graph version: proposal + envelope + evaluation + approval.
    Inactive by construction; activation is a separate recorded human decision."""

    candidate_id: UUID
    envelope: CandidateEnvelope
    status: CandidateStatus = CandidateStatus.PROPOSED
    evaluation: EvaluationSummary | None = None
    approval: Approval | None = None
    resulting_version: int | None = None
    resulting_hash: str | None = None

    @model_validator(mode="after")
    def consistency(self) -> "Candidate":
        if self.envelope.candidate_id != self.candidate_id:
            raise ValueError("envelope and candidate disagree")
        if self.status == CandidateStatus.EVALUATED and self.evaluation is None:
            raise ValueError("evaluated candidate requires an evaluation summary")
        if self.approval is not None and self.approval.candidate_id != self.candidate_id:
            raise ValueError("approval binds a different candidate")
        if self.status in {CandidateStatus.APPROVED, CandidateStatus.ACTIVATED} and (
            self.approval is None
        ):
            raise ValueError(f"{self.status} requires recorded approval")
        if self.status == CandidateStatus.REJECTED and (
            self.evaluation is not None and self.evaluation.passed
        ):
            raise ValueError("a passed candidate is not rejected without cause")
        return self


def validate_capability_step(capability: Capability, step: Step) -> None:
    capability.validate_step(step)


def derive_state_feature(
    proposal: FeatureProposal, sources: tuple[StateSource, ...]
) -> StateFeature:
    """Deterministic scope: required only when the named source reports always."""
    source = next((s for s in sources if s.id == proposal.source), None)
    if source is None:
        raise ValueError(f"unknown state source: {proposal.source}")
    return StateFeature(
        id=proposal.id,
        kind=proposal.kind,
        sensor_field=proposal.sensor_field,
        required=source.availability == SourceAvailability.ALWAYS,
    )


def candidate_content_hash(envelope: CandidateEnvelope) -> str:
    return content_digest(envelope.model_dump(mode="json"))
