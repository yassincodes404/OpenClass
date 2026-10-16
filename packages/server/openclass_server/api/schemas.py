from typing import Any, Literal
from uuid import UUID

from openclass_core.models import Model, Observation, OntologyClass, OntologyVersion
from openclass_core.project_evolution import ChoiceCandidate
from openclass_core.projects import DecisionService
from openclass_core.state_compiler import RuntimeDecisionConfig
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
    workspace_id: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def has_changes(self) -> "UpdateProject":
        if (
            self.name is None
            and self.description is None
            and self.status is None
            and self.workspace_id is None
        ):
            raise ValueError("update must change at least one field")
        return self


class ClaimProjectRequest(Model):
    workspace_id: str | None = Field(default=None, min_length=1, max_length=120)
    actor: str = Field(default="operator", min_length=1, max_length=80)


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
    aliases: list[str] = Field(default_factory=list)
    target_node_id: UUID | None = None
    target_node_name: str | None = None

    @model_validator(mode="after")
    def clean_choice(self) -> "DecisionChoiceCreate":
        key = self.key.strip().upper()
        if not key:
            raise ValueError("choice key cannot be blank")
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "label", self.label.strip() or key)
        object.__setattr__(self, "description", self.description.strip())
        object.__setattr__(self, "aliases", [a.strip() for a in self.aliases if a.strip()])
        return self


DecisionChoiceSpec = DecisionChoiceCreate


class DecisionServiceNodeCreate(Model):
    id: UUID | None = None
    name: str = Field(min_length=1, max_length=100)
    instructions: str = Field(min_length=1, max_length=2000)
    choices: list[DecisionChoiceCreate] = Field(min_length=1, max_length=50)
    risk_level: Literal["ordinary", "high"] = "ordinary"
    min_margin: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    max_unknown_probability: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    pause_on_review: bool = False


class DecisionServiceTransitionCreate(Model):
    from_node_key: str = Field(min_length=1, max_length=200)
    choice_key: str = Field(min_length=1, max_length=120)
    to_node_key: str = Field(min_length=1, max_length=200)
    require_approval: bool = False


class DecisionServiceCreate(Model):
    name: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=4000)
    choices: list[DecisionChoiceCreate] = Field(default_factory=list)
    nodes: list[DecisionServiceNodeCreate] | None = None
    transitions: list[DecisionServiceTransitionCreate] = Field(default_factory=list)
    description: str = Field(default="", max_length=2000)
    runtime_config: RuntimeDecisionConfig = Field(default_factory=RuntimeDecisionConfig)
    provider_override: str | None = None

    @model_validator(mode="after")
    def clean_fields(self) -> "DecisionServiceCreate":
        if not self.name.strip():
            raise ValueError("service name is required")
        if not self.instructions.strip():
            raise ValueError("instructions are required")
        if not self.choices and not self.nodes:
            raise ValueError("choices or nodes are required")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "instructions", self.instructions.strip())
        object.__setattr__(self, "description", self.description.strip())
        return self


class DecisionServiceUpdateSchema(Model):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=4000)
    status: Literal["active", "draft", "archived"] | None = None
    runtime_config: RuntimeDecisionConfig | None = None
    provider_override: str | None = None
    nodes: list[DecisionServiceNodeCreate] | None = None
    transitions: list[DecisionServiceTransitionCreate] | None = None

    @model_validator(mode="after")
    def has_changes(self) -> "DecisionServiceUpdateSchema":
        if (
            self.name is None
            and self.description is None
            and self.instructions is None
            and self.status is None
            and self.provider_override is None
            and self.nodes is None
            and self.transitions is None
            and self.runtime_config is None
        ):
            raise ValueError("update must change at least one field")
        return self


class ExecuteDecisionRunRequest(Model):
    raw_event_ids: list[str] = Field(default_factory=list, max_length=100)
    # Alternative input: raw text is ingested as an observation first.
    content: str | None = Field(default=None, min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def has_input(self) -> "ExecuteDecisionRunRequest":
        if not self.raw_event_ids and not self.content:
            raise ValueError("raw_event_ids or content is required")
        return self


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
    version_number: int = 1
    active_version_id: str | None = None
    created_at: str
    updated_at: str


class DecisionRunResponse(Model):
    id: str
    project_id: str
    raw_event_id: str
    decision_service_id: str
    decision_node_id: str
    decision_service_version_id: str | None = None
    service_hash: str | None = None
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
    target_status: str | None = Field(default=None, min_length=1, max_length=30)
    status: str | None = Field(default=None, min_length=1, max_length=30)
    rationale: str | None = Field(default=None, max_length=2000)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def normalize_transition_fields(self) -> "TransitionEvidenceRequest":
        resolved_status = self.target_status or self.status
        if not resolved_status or not resolved_status.strip():
            raise ValueError("target_status is required")
        resolved_rationale = self.rationale if self.rationale is not None else self.note
        object.__setattr__(self, "target_status", resolved_status.strip())
        object.__setattr__(self, "rationale", resolved_rationale)
        return self


class CreateEvidenceCaseRequest(Model):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    decision_service_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def strip_title(self) -> "CreateEvidenceCaseRequest":
        if not self.title.strip():
            raise ValueError("Case title cannot be blank")
        return self


class AddEvidenceToCaseRequest(Model):
    evidence_id: UUID | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_ids(self) -> "AddEvidenceToCaseRequest":
        if self.evidence_id is None and not self.evidence_ids:
            raise ValueError("evidence_id or evidence_ids is required")
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
