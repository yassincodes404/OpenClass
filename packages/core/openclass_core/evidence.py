"""Project-scoped evidence domain: the bridge between OPERATE and EVOLVE.

Evidence is observed material supporting or contradicting a possible
knowledge change.  It exists before the Teacher — Mission 5 will consume
evidence and diagnosis to create Teacher proposals and candidates.

This module is separate from ``evolution.py`` which defines the
graph/automation-plane models (FailureLayer, TeacherProposal, etc.).
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from .models import Model


def _now() -> datetime:
    return datetime.now(UTC)


# ── Enums ────────────────────────────────────────────────────────────


class EvidenceTriggerType(StrEnum):
    """Why a DecisionRun became evolution evidence."""

    SEMANTIC_UNKNOWN = "semantic_unknown"
    LOW_TRUST = "low_trust"
    HUMAN_CORRECTION = "human_correction"
    HUMAN_MARKED_MISSING_CONCEPT = "human_marked_missing_concept"
    SUPERVISOR_FINDING = "supervisor_finding"
    POSTCONDITION_FAILURE = "postcondition_failure"
    REPEATED_PATTERN = "repeated_pattern"
    STATE_GAP = "state_gap"
    ANALYTICAL_GAP = "analytical_gap"


class EvidenceStatus(StrEnum):
    """Small explicit lifecycle for evidence items and cases."""

    PENDING = "pending"
    TRIAGED = "triaged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    READY_FOR_EVOLUTION = "ready_for_evolution"


class DiagnosisCategory(StrEnum):
    """Product-facing failure diagnosis taxonomy from the Master Spec.

    Separate from ``FailureLayer`` in evolution.py which serves the
    graph/automation plane with node-level granularity.
    """

    DECISION_SPACE = "decision_space"
    PROCEDURE = "procedure"
    STATE_REPRESENTATION = "state_representation"
    PRECONDITION = "precondition"
    MISSING_CAPABILITY = "missing_capability"
    PROVIDER_FAILURE = "provider_failure"
    OUT_OF_DOMAIN = "out_of_domain"
    AMBIGUOUS_OR_INSUFFICIENT = "ambiguous_or_insufficient"
    ANALYTICAL_GAP = "analytical_gap"


class FeedbackAction(StrEnum):
    """Human feedback actions on a DecisionRun."""

    CONFIRM = "confirm"
    CORRECT = "correct"
    MISSING_CONCEPT = "missing_concept"
    AMBIGUOUS = "ambiguous"
    OUT_OF_DOMAIN = "out_of_domain"
    NOTE = "note"


# ── Valid status transitions ─────────────────────────────────────────

VALID_TRANSITIONS: dict[EvidenceStatus, frozenset[EvidenceStatus]] = {
    EvidenceStatus.PENDING: frozenset(
        {
            EvidenceStatus.TRIAGED,
            EvidenceStatus.RESOLVED,
            EvidenceStatus.DISMISSED,
        }
    ),
    EvidenceStatus.TRIAGED: frozenset(
        {
            EvidenceStatus.RESOLVED,
            EvidenceStatus.DISMISSED,
            EvidenceStatus.READY_FOR_EVOLUTION,
        }
    ),
    EvidenceStatus.RESOLVED: frozenset(),
    EvidenceStatus.DISMISSED: frozenset(),
    EvidenceStatus.READY_FOR_EVOLUTION: frozenset(),
}


class DiagnosisResult(Model):
    """Structured failure diagnosis produced by human or supervisory AI."""

    diagnosis: DiagnosisCategory
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)
    recommended_action: str | None = Field(default=None, max_length=1000)
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    simulated: bool = False


class DiagnosisProvider(Protocol):
    """Advisory diagnosis provider (e.g. Gemini LLM via Vercel AI Gateway)."""

    async def diagnose(self, context: dict[str, Any]) -> DiagnosisResult: ...


class EvolutionEligibility(Model):
    """Deterministic result of the evidence eligibility policy."""

    eligible: bool
    trigger_type: EvidenceTriggerType | None = None
    reason: str = Field(min_length=1)


class EvidenceItem(Model):
    """Canonical project-scoped evidence record.

    Links back to authoritative objects (DecisionRun, RawEvent) rather
    than duplicating all data, but preserves enough immutable context
    that the evidence remains interpretable historically.
    """

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID

    # Source references
    raw_event_id: UUID | None = None
    decision_run_id: UUID | None = None
    decision_service_id: UUID | None = None
    decision_node_id: UUID | None = None
    evidence_case_id: UUID | None = None

    # Classification
    trigger_type: EvidenceTriggerType
    status: EvidenceStatus = EvidenceStatus.PENDING
    diagnosis: DiagnosisCategory | None = None
    diagnosis_rationale: str | None = Field(default=None, max_length=2000)

    # Decision context snapshot
    selected_choice: str | None = None
    probabilities_snapshot: dict[str, float] = Field(default_factory=dict)
    unknown_probability: float = 0.0
    margin: float = 0.0
    supervision_outcome: str | None = None
    supervision_reason: str | None = None

    # Provider provenance
    provider: str | None = None
    model: str | None = None
    execution_mode: str | None = None

    # Origin
    source: Literal["automatic", "human", "supervisor"] = "automatic"
    human_note: str | None = Field(default=None, max_length=4000)
    corrected_choice: str | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=_now)
    resolved_at: datetime | None = None


class EvidenceCase(Model):
    """Evidence grouping: related observations that may share a root
    cause or point to the same knowledge gap."""

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    decision_service_id: UUID | None = None
    decision_node_id: UUID | None = None
    status: EvidenceStatus = EvidenceStatus.PENDING
    diagnosis: DiagnosisCategory | None = None
    diagnosis_rationale: str | None = Field(default=None, max_length=2000)
    title: str = Field(min_length=1, max_length=200)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class RunFeedback(Model):
    """Human feedback on a DecisionRun.

    Feedback is append-only: each action creates a new record.
    Multiple feedback entries may exist for the same run.
    """

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    decision_run_id: UUID
    action: FeedbackAction
    corrected_choice: str | None = None
    note: str | None = Field(default=None, max_length=4000)
    actor: str = Field(min_length=1, max_length=80)
    created_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def validate_correction(self) -> "RunFeedback":
        if self.action == FeedbackAction.CORRECT and not self.corrected_choice:
            raise ValueError("corrected_choice is required for CORRECT")
        return self


class EvolutionSummary(Model):
    """Project evolution overview counters."""

    pending_evidence: int = Field(default=0, ge=0)
    triaged_evidence: int = Field(default=0, ge=0)
    ready_for_evolution: int = Field(default=0, ge=0)
    resolved_evidence: int = Field(default=0, ge=0)
    dismissed_evidence: int = Field(default=0, ge=0)
    total_evidence: int = Field(default=0, ge=0)
    open_cases: int = Field(default=0, ge=0)


# ── Evidence eligibility policy ─────────────────────────────────────

_RESEARCH_CALIBRATION = "research calibration"


def evaluate_eligibility(
    selected_choice: str,
    supervision_outcome: str,
    supervision_reason: str,
) -> EvolutionEligibility:
    """Deterministic policy: should a DecisionRun generate evidence?

    Hard invariants:
    - UNKNOWN → always eligible (SEMANTIC_UNKNOWN)
    - Research-calibration REVIEW alone → NOT eligible
    - Provider failure → never reaches here (no run persisted)
    - Calibrated REVIEW (non-research) → eligible (LOW_TRUST)
    """
    if selected_choice == "UNKNOWN":
        return EvolutionEligibility(
            eligible=True,
            trigger_type=EvidenceTriggerType.SEMANTIC_UNKNOWN,
            reason=("Provider selected semantic UNKNOWN outcome"),
        )

    reason_lower = supervision_reason.lower()
    if supervision_outcome == "REVIEW" and _RESEARCH_CALIBRATION in reason_lower:
        return EvolutionEligibility(
            eligible=False,
            reason=("Research-calibration REVIEW alone is not evolution evidence"),
        )

    if supervision_outcome == "REVIEW":
        return EvolutionEligibility(
            eligible=True,
            trigger_type=EvidenceTriggerType.LOW_TRUST,
            reason=("Low-trust decision warrants evolution review"),
        )

    return EvolutionEligibility(
        eligible=False,
        reason="Decision is trusted; no evolution needed",
    )


def validate_status_transition(
    current: EvidenceStatus,
    target: EvidenceStatus,
) -> None:
    """Raise ConflictError on invalid status transition."""
    from .repositories import ConflictError

    allowed = VALID_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise ConflictError(f"Cannot transition from {current} to {target}")


def evidence_from_run(
    run: "DecisionRun",
) -> EvidenceItem | None:
    """Create an EvidenceItem from a DecisionRun if eligible.

    Returns None if the run is not eligible for evolution.
    """
    # Avoid circular import — DecisionRun is in projects.py
    eligibility = evaluate_eligibility(
        selected_choice=run.selected_choice,
        supervision_outcome=run.supervision_outcome,
        supervision_reason=run.supervision_reason,
    )
    if not eligibility.eligible:
        return None
    assert eligibility.trigger_type is not None
    return EvidenceItem(
        project_id=run.project_id,
        raw_event_id=run.raw_event_id,
        decision_run_id=run.id,
        decision_service_id=run.decision_service_id,
        decision_node_id=run.decision_node_id,
        trigger_type=eligibility.trigger_type,
        selected_choice=run.selected_choice,
        probabilities_snapshot=dict(run.probabilities),
        unknown_probability=run.unknown_probability,
        margin=run.margin,
        supervision_outcome=run.supervision_outcome,
        supervision_reason=run.supervision_reason,
        provider=run.provider,
        model=run.model,
        execution_mode=run.execution_mode,
        source="automatic",
    )


if TYPE_CHECKING:
    from .projects import DecisionRun
