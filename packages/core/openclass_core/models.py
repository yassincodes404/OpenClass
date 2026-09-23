"""Provider-neutral domain objects. UNKNOWN is a state, never a semantic class."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")]


def now() -> datetime:
    return datetime.now(UTC)


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ClassifierType(StrEnum):
    SINGLE_CHOICE = "single_choice"


class CandidateStatus(StrEnum):
    DISCOVERED = "discovered"
    CANDIDATE = "candidate"
    COLLECTING_EVIDENCE = "collecting_evidence"
    VALIDATING = "validating"
    APPROVED = "approved"
    ACTIVE = "active"
    REJECTED = "rejected"
    MERGED = "merged"
    DEPRECATED = "deprecated"


class OntologyClass(Model):
    stable_class_id: UUID = Field(default_factory=uuid4)
    canonical_name: Name
    display_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    aliases: tuple[str, ...] = ()
    positive_examples: tuple[str, ...] = ()
    negative_examples: tuple[str, ...] = ()
    parent_stable_class_id: UUID | None = None

    @model_validator(mode="after")
    def reserved_names(self) -> "OntologyClass":
        if self.canonical_name in {"unknown", "other"}:
            raise ValueError("unknown and other are reserved classification states")
        if self.parent_stable_class_id is not None:
            raise ValueError("Genesis supports flat ontologies only")
        if any(not alias.strip() for alias in self.aliases):
            raise ValueError("aliases must be nonblank")
        return self


class OntologyVersion(Model):
    id: UUID = Field(default_factory=uuid4)
    classifier_id: UUID
    version_number: int = Field(ge=1)
    parent_version_id: UUID | None = None
    classes: tuple[OntologyClass, ...] = Field(min_length=1)
    created_by: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=now)

    @model_validator(mode="after")
    def unique_concepts(self) -> "OntologyVersion":
        ids = [c.stable_class_id for c in self.classes]
        names = [
            term.strip().casefold() for c in self.classes for term in (c.canonical_name, *c.aliases)
        ]
        if len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise ValueError("class identifiers, names, and aliases must be unique")
        return self


class Classifier(Model):
    id: UUID = Field(default_factory=uuid4)
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{0,79}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    classifier_type: ClassifierType = ClassifierType.SINGLE_CHOICE
    active_ontology_version_id: UUID
    created_at: datetime = Field(default_factory=now)


class Observation(Model):
    id: UUID = Field(default_factory=uuid4)
    content_type: Literal["text"] = "text"
    content: str = Field(min_length=1, max_length=100_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now)

    @model_validator(mode="after")
    def nonblank(self) -> "Observation":
        if not self.content.strip():
            raise ValueError("observation must contain text")
        return self


class ChoiceRequest(Model):
    observation: Observation
    ontology: OntologyVersion


class ChoiceResult(Model):
    provider: str
    model: str
    probabilities: dict[str, Probability]
    unknown_probability: Probability
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = Field(default=0, ge=0, allow_inf_nan=False)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def normalized(self) -> "ChoiceResult":
        total = sum(self.probabilities.values()) + self.unknown_probability
        if abs(total - 1.0) > 1e-6:
            raise ValueError("probabilities including UNKNOWN must sum to one")
        return self


class NoveltySignals(Model):
    unknown_probability: Probability
    top1_probability: Probability
    top2_probability: Probability
    top_margin: Probability
    entropy: Probability
    semantic_distance: Probability | None = None
    recurrence_score: Probability = 0
    provider_confidence: Probability | None = None


class NoveltyAssessment(Model):
    score: Probability
    state: Literal["known", "uncertain", "likely_novel"]
    reasons: tuple[str, ...]


class ClassificationResult(Model):
    id: UUID = Field(default_factory=uuid4)
    classifier_id: UUID
    observation_id: UUID
    ontology_version_id: UUID
    selected_class_id: UUID | None
    selected_class: str | None
    decision: ChoiceResult
    signals: NoveltySignals
    novelty: NoveltyAssessment
    created_at: datetime = Field(default_factory=now)


class UnknownEvent(Model):
    id: UUID = Field(default_factory=uuid4)
    classifier_id: UUID
    observation: Observation
    classification: ClassificationResult
    review_state: Literal["pending"] = "pending"
    cluster_id: UUID | None = None
    candidate_id: UUID | None = None


class DomainEvent(Model):
    id: UUID = Field(default_factory=uuid4)
    classifier_id: UUID
    type: str
    actor: str
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=now)
