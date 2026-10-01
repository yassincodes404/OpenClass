from typing import Any, Literal
from uuid import UUID

from openclass_core.models import Model, Observation, OntologyClass, OntologyVersion
from openclass_core.project_evolution import ChoiceCandidate
from openclass_core.projects import DecisionService
from pydantic import Field, model_validator


class CreateClassifier(Model):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{0,79}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    classes: tuple[OntologyClass, ...] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def valid_ontology(self) -> "CreateClassifier":
        from uuid import uuid4

        OntologyVersion(
            classifier_id=uuid4(), version_number=1, classes=self.classes, created_by="local"
        )
        return self


class ClassifyRequest(Model):
    observation: str = Field(min_length=1, max_length=100_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_observation(self) -> "ClassifyRequest":
        Observation(content=self.observation, metadata=self.metadata)
        return self


class CreateReview(Model):
    trigger: Literal["manual"] = "manual"


class DiscoverRequest(Model):
    unknown_ids: tuple[str, ...] = Field(min_length=1, max_length=50)


class RejectCandidateRequest(Model):
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def nonblank_reason(self) -> "RejectCandidateRequest":
        reason = self.reason.strip()
        if not reason:
            raise ValueError("Rejection reason is required")
        object.__setattr__(self, "reason", reason)
        return self


class ProposeProjectChoiceRequest(Model):
    run_ids: tuple[str, ...] = Field(min_length=3, max_length=20)


class CreateProject(Model):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def strip_fields(self) -> "CreateProject":
        if not self.name.strip():
            raise ValueError("project name is required")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "description", self.description.strip())
        return self


class UpdateProject(Model):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: Literal["active", "archived"] | None = None

    @model_validator(mode="after")
    def has_changes(self) -> "UpdateProject":
        if self.name is None and self.description is None and self.status is None:
            raise ValueError("update must change at least one field")
        return self


class ProjectSummaryResponse(Model):
    events: int
    decision_runs: int
    unknowns: int
    pending_evidence: int
    active_policy: str | None
    pending_candidates: int
    audit_events: int


class RawEventCreate(Model):
    content: str = Field(min_length=1)
    source_type: Literal["text", "json", "csv", "webhook"] = "text"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_content(self) -> "RawEventCreate":
        if not self.content.strip():
            raise ValueError("event content cannot be blank")
        object.__setattr__(self, "content", self.content.strip())
        return self


class RawEventBatchCreate(Model):
    items: list[dict[str, Any]] = Field(min_length=1, max_length=1000)
    source_type: Literal["text", "json", "csv", "webhook"] = "text"


class RawEventResponse(Model):
    id: str
    project_id: str
    source_type: str
    content: str
    metadata: dict[str, Any]
    created_at: str


class DecisionChoiceCreate(Model):
    key: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def clean_choice(self) -> "DecisionChoiceCreate":
        key = self.key.strip().upper()
        if not key:
            raise ValueError("choice key cannot be blank")
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "label", self.label.strip() or key)
        object.__setattr__(self, "description", self.description.strip())
        return self


class DecisionServiceCreate(Model):
    name: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=4000)
    choices: list[DecisionChoiceCreate] = Field(min_length=1)
    description: str = Field(default="", max_length=2000)
    provider_override: str | None = None

    @model_validator(mode="after")
    def clean_fields(self) -> "DecisionServiceCreate":
        if not self.name.strip():
            raise ValueError("service name is required")
        if not self.instructions.strip():
            raise ValueError("instructions are required")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "instructions", self.instructions.strip())
        object.__setattr__(self, "description", self.description.strip())
        return self


class DecisionServiceUpdateSchema(Model):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=4000)
    status: Literal["active", "draft", "archived"] | None = None
    provider_override: str | None = None

    @model_validator(mode="after")
    def has_changes(self) -> "DecisionServiceUpdateSchema":
        if (
            self.name is None
            and self.description is None
            and self.instructions is None
            and self.status is None
            and self.provider_override is None
        ):
            raise ValueError("update must change at least one field")
        return self


class ExecuteDecisionRunRequest(Model):
    raw_event_ids: list[str] = Field(min_length=1, max_length=100)


class DecisionServiceResponse(Model):
    id: str
    project_id: str
    slug: str
    name: str
    description: str
    instructions: str
    nodes: list[dict[str, Any]]
    status: str
    provider_override: str | None
    created_at: str
    updated_at: str


class DecisionRunResponse(Model):
    id: str
    project_id: str
    raw_event_id: str
    decision_service_id: str
    decision_node_id: str
    provider: str
    model: str
    execution_mode: str
    real_inference: bool
    selected_choice: str
    probabilities: dict[str, float]
    top_probability: float
    second_probability: float | None
    margin: float
    unknown_probability: float
    supervision_outcome: str
    supervision_reason: str
    latency_ms: float
    input_snapshot: dict[str, Any]
    instructions_snapshot: str
    choices_snapshot: list[dict[str, Any]]
    provider_metadata: dict[str, Any]
    created_at: str


class TriageEvidenceRequest(Model):
    diagnosis: str = Field(min_length=1, max_length=50)
    rationale: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def strip_rationale(self) -> "TriageEvidenceRequest":
        if not self.rationale.strip():
            raise ValueError("Rationale cannot be blank")
        return self


class TransitionEvidenceRequest(Model):
    target_status: str = Field(min_length=1, max_length=30)
    rationale: str | None = Field(default=None, max_length=2000)


class CreateEvidenceCaseRequest(Model):
    title: str = Field(min_length=1, max_length=200)
    decision_service_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def strip_title(self) -> "CreateEvidenceCaseRequest":
        if not self.title.strip():
            raise ValueError("Case title cannot be blank")
        return self


class SubmitRunFeedbackRequest(Model):
    action: str = Field(min_length=1, max_length=30)
    corrected_choice: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def check_correction(self) -> "SubmitRunFeedbackRequest":
        if self.action == "correct" and not self.corrected_choice:
            raise ValueError("corrected_choice is required for action correct")
        return self


class ProposeFromEvidenceRequest(Model):
    service_id: str | None = None
    evidence_ids: list[UUID] | None = None
    evidence_case_id: UUID | None = None

    @model_validator(mode="after")
    def validate_proposal_source(self) -> "ProposeFromEvidenceRequest":
        if not self.evidence_ids and not self.evidence_case_id:
            raise ValueError("Either evidence_ids or evidence_case_id must be provided")
        if self.evidence_ids and not self.service_id:
            raise ValueError("service_id is required when evidence_ids is provided")
        return self


class PromoteCandidateRequest(Model):
    note: str | None = Field(default=None, max_length=2000)


class PromoteCandidateResponse(Model):
    candidate: ChoiceCandidate
    decision_service: DecisionService
