"""Inactive, project-scoped Teacher proposals grounded in persisted UNKNOWN runs."""

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from .evidence import EvidenceItem, EvidenceStatus
from .models import Model
from .projects import (
    DecisionRun,
    DecisionService,
    ProjectAuditEvent,
)
from .repositories import ConflictError


class ProposalKind(StrEnum):
    NEW_CHOICE = "new_choice"
    EXISTING_CHOICE = "existing_choice"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ChoiceProposal(Model):
    kind: ProposalKind
    key: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,49}$")
    label: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    rationale: str = Field(min_length=1, max_length=2000)
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    simulated: bool = False

    @model_validator(mode="after")
    def coherent_fields(self) -> "ChoiceProposal":
        if self.kind == ProposalKind.NEW_CHOICE and not all(
            (self.key, self.label, self.description)
        ):
            raise ValueError("New choice requires key, label, and description")
        return self


class ChoiceCandidate(Model):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    decision_service_id: UUID
    base_service_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_run_ids: tuple[UUID, ...] = Field(min_length=3, max_length=20)
    proposal: ChoiceProposal
    status: str = Field(default="candidate", pattern=r"^(candidate|rejected|promoted)$")
    rejection_reason: str | None = Field(default=None, min_length=1, max_length=1000)
    promoted_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CandidateEvaluationResult(Model):
    candidate_id: UUID
    decision_service_id: UUID
    passed: bool
    accuracy_on_knowns: float = Field(ge=0, le=1)
    disambiguation_rate: float = Field(ge=0, le=1)
    regressions: tuple[str, ...] = ()
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChoiceTeacher(Protocol):
    async def propose(
        self, service: DecisionService, runs: tuple[DecisionRun, ...]
    ) -> ChoiceProposal: ...


class ChoiceCandidateRepository(Protocol):
    async def get_decision_service(self, project_id: UUID, identifier: str) -> DecisionService: ...
    async def get_decision_run(self, project_id: UUID, run_id: UUID) -> DecisionRun: ...
    async def save_choice_candidate(
        self, candidate: ChoiceCandidate, event: ProjectAuditEvent
    ) -> None: ...
    async def list_choice_candidates(self, project_id: UUID) -> list[ChoiceCandidate]: ...
    async def get_choice_candidate(
        self, project_id: UUID, candidate_id: UUID
    ) -> ChoiceCandidate: ...
    async def reject_choice_candidate(
        self, candidate: ChoiceCandidate, reason: str, event: ProjectAuditEvent
    ) -> ChoiceCandidate: ...
    async def get_evidence_item(self, project_id: UUID, evidence_id: UUID) -> EvidenceItem: ...
    async def list_case_evidence(self, project_id: UUID, case_id: UUID) -> list[EvidenceItem]: ...
    async def list_runs_for_service(
        self, project_id: UUID, service_id: UUID, limit: int = 50
    ) -> list[DecisionRun]: ...


def service_hash(service: DecisionService) -> str:
    snapshot = json.dumps(service.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(snapshot.encode()).hexdigest()


class ProjectEvolutionService:
    def __init__(self, repository: ChoiceCandidateRepository, teacher: ChoiceTeacher) -> None:
        self.repository = repository
        self.teacher = teacher

    async def propose(
        self, project_id: UUID, service_identifier: str, run_ids: tuple[UUID, ...], actor: str
    ) -> ChoiceCandidate:
        if len(run_ids) < 3 or len(run_ids) > 20 or len(set(run_ids)) != len(run_ids):
            raise ConflictError("Select 3–20 distinct UNKNOWN runs")
        service = await self.repository.get_decision_service(project_id, service_identifier)
        if service.status != "active":
            raise ConflictError("Only an active decision service can receive proposals")
        runs = tuple(
            [await self.repository.get_decision_run(project_id, run_id) for run_id in run_ids]
        )
        if any(
            run.decision_service_id != service.id or run.selected_choice != "UNKNOWN"
            for run in runs
        ):
            raise ConflictError("Proposal evidence must be UNKNOWN runs of this service")
        proposal = await self.teacher.propose(service, runs)
        if proposal.kind == ProposalKind.NEW_CHOICE:
            assert proposal.key is not None and proposal.label is not None
            existing = service.nodes[0].choices
            if any(
                proposal.key == choice.key or proposal.label.casefold() == choice.label.casefold()
                for choice in existing
            ):
                raise ConflictError("Proposal duplicates an existing choice")
        candidate = ChoiceCandidate(
            project_id=project_id,
            decision_service_id=service.id,
            base_service_hash=service_hash(service),
            evidence_run_ids=run_ids,
            proposal=proposal,
        )
        await self.repository.save_choice_candidate(
            candidate,
            ProjectAuditEvent(
                project_id=project_id,
                event_type="choice_candidate.created",
                actor=actor,
                payload={"candidate_id": str(candidate.id), "service_id": str(service.id)},
            ),
        )
        return candidate

    async def propose_from_evidence(
        self,
        project_id: UUID,
        service_identifier: str,
        evidence_ids: tuple[UUID, ...],
        actor: str,
    ) -> ChoiceCandidate:
        if (
            len(evidence_ids) < 3
            or len(evidence_ids) > 20
            or len(set(evidence_ids)) != len(evidence_ids)
        ):
            raise ConflictError("Select 3–20 distinct evidence items")
        service = await self.repository.get_decision_service(project_id, service_identifier)
        if service.status != "active":
            raise ConflictError("Only an active decision service can receive proposals")

        evidence_items: list[EvidenceItem] = []
        for eid in evidence_ids:
            ev = await self.repository.get_evidence_item(project_id, eid)
            if ev.status != EvidenceStatus.READY_FOR_EVOLUTION:
                raise ConflictError(
                    f"Evidence {eid} must be in ready_for_evolution status before synthesis"
                )
            if ev.decision_service_id is not None and ev.decision_service_id != service.id:
                raise ConflictError("All evidence items must belong to the target decision service")
            if ev.decision_run_id is None:
                raise ConflictError(f"Evidence {eid} must have an associated decision run")
            evidence_items.append(ev)

        run_ids = tuple(
            ev.decision_run_id for ev in evidence_items if ev.decision_run_id is not None
        )
        return await self.propose(project_id, service_identifier, run_ids, actor)

    async def propose_from_case(
        self,
        project_id: UUID,
        case_id: UUID,
        actor: str,
    ) -> ChoiceCandidate:
        items = await self.repository.list_case_evidence(project_id, case_id)
        ready_items = [
            i for i in items if i.status == EvidenceStatus.READY_FOR_EVOLUTION and i.decision_run_id
        ]
        if len(ready_items) < 3:
            raise ConflictError(
                f"Case must have at least 3 ready_for_evolution items (found {len(ready_items)})"
            )
        service_id = ready_items[0].decision_service_id
        if service_id is None:
            raise ConflictError("Evidence items in case must have a valid decision_service_id")
        selected_ids = tuple(item.id for item in ready_items[:20])
        return await self.propose_from_evidence(project_id, str(service_id), selected_ids, actor)

    async def evaluate(self, project_id: UUID, candidate_id: UUID) -> CandidateEvaluationResult:
        await self.repository.get_choice_candidate(project_id, candidate_id)
        raise ConflictError("Verified replay evaluation is not implemented")

    async def promote(
        self,
        project_id: UUID,
        candidate_id: UUID,
        actor: str,
    ) -> tuple[ChoiceCandidate, DecisionService]:
        candidate = await self.repository.get_choice_candidate(project_id, candidate_id)
        if candidate.status != "candidate":
            raise ConflictError(
                f"Candidate {candidate_id} is in status '{candidate.status}', cannot promote"
            )
        if candidate.proposal.kind != ProposalKind.NEW_CHOICE:
            raise ConflictError("Only NEW_CHOICE candidates can be promoted")
        assert candidate.proposal.key is not None and candidate.proposal.label is not None

        service = await self.repository.get_decision_service(
            project_id, str(candidate.decision_service_id)
        )
        if service.status != "active":
            raise ConflictError("Target decision service is not active")
        if service_hash(service) != candidate.base_service_hash:
            raise ConflictError("Decision service was modified after candidate was generated")

        existing_choices = list(service.nodes[0].choices)
        if any(c.key == candidate.proposal.key for c in existing_choices):
            raise ConflictError(
                f"Choice {candidate.proposal.key} already exists in decision service"
            )

        # Evidence counts and historical predictions cannot serve as ground truth.
        # No durable verified evaluation/approval/version chain exists for this path yet.
        raise ConflictError("Verified replay evaluation is required before activation")

    async def reject(
        self, project_id: UUID, candidate_id: UUID, reason: str, actor: str
    ) -> ChoiceCandidate:
        candidate = await self.repository.get_choice_candidate(project_id, candidate_id)
        if candidate.status != "candidate":
            raise ConflictError("Only pending candidates can be rejected")
        reason = reason.strip()
        if not 1 <= len(reason) <= 1000:
            raise ValueError("Rejection reason must contain 1–1000 characters")
        event = ProjectAuditEvent(
            project_id=project_id,
            event_type="choice_candidate.rejected",
            actor=actor,
            payload={"candidate_id": str(candidate_id), "reason": reason},
        )
        return await self.repository.reject_choice_candidate(candidate, reason, event)
