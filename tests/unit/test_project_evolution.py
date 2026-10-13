"""Unit tests for ProjectEvolutionService: evidence synthesis, replay, and promotion."""

from uuid import UUID, uuid4

import pytest
from openclass_core.evidence import EvidenceItem, EvidenceStatus, EvidenceTriggerType
from openclass_core.project_evolution import (
    ChoiceCandidate,
    ChoiceProposal,
    ChoiceTeacher,
    ProjectEvolutionService,
    ProposalKind,
    service_hash,
)
from openclass_core.projects import (
    UNKNOWN_CHOICE,
    DecisionRun,
    DecisionService,
    DecisionServiceChoice,
    DecisionServiceNode,
    ProjectAuditEvent,
)
from openclass_core.repositories import ConflictError


class InMemoryChoiceCandidateRepository:
    def __init__(
        self,
        service: DecisionService,
        runs: list[DecisionRun],
        evidence_items: list[EvidenceItem] | None = None,
    ) -> None:
        self.service = service
        self.runs = {r.id: r for r in runs}
        self.evidence_items = {e.id: e for e in (evidence_items or [])}
        self.candidates: dict[UUID, ChoiceCandidate] = {}
        self.events: list[ProjectAuditEvent] = []

    async def get_decision_service(self, project_id: UUID, identifier: str) -> DecisionService:
        if str(self.service.id) == identifier or self.service.slug == identifier:
            return self.service
        raise ConflictError("Service not found")

    async def get_decision_run(self, project_id: UUID, run_id: UUID) -> DecisionRun:
        if run_id in self.runs:
            return self.runs[run_id]
        raise ConflictError(f"Run {run_id} not found")

    async def list_runs_for_service(
        self, project_id: UUID, service_id: UUID, limit: int = 50
    ) -> list[DecisionRun]:
        return [r for r in self.runs.values() if r.decision_service_id == service_id][:limit]

    async def save_choice_candidate(
        self, candidate: ChoiceCandidate, event: ProjectAuditEvent
    ) -> None:
        self.candidates[candidate.id] = candidate
        self.events.append(event)

    async def list_choice_candidates(self, project_id: UUID) -> list[ChoiceCandidate]:
        return list(self.candidates.values())

    async def get_choice_candidate(self, project_id: UUID, candidate_id: UUID) -> ChoiceCandidate:
        if candidate_id in self.candidates:
            return self.candidates[candidate_id]
        raise ConflictError(f"Candidate {candidate_id} not found")

    async def reject_choice_candidate(
        self, candidate: ChoiceCandidate, reason: str, event: ProjectAuditEvent
    ) -> ChoiceCandidate:
        updated = candidate.model_copy(update={"status": "rejected", "rejection_reason": reason})
        self.candidates[candidate.id] = updated
        self.events.append(event)
        return updated

    async def get_evidence_item(self, project_id: UUID, evidence_id: UUID) -> EvidenceItem:
        if evidence_id in self.evidence_items:
            return self.evidence_items[evidence_id]
        raise ConflictError(f"Evidence {evidence_id} not found")

    async def list_case_evidence(self, project_id: UUID, case_id: UUID) -> list[EvidenceItem]:
        return [e for e in self.evidence_items.values() if e.evidence_case_id == case_id]


class MockTeacher(ChoiceTeacher):
    def __init__(self, proposal: ChoiceProposal | None = None) -> None:
        self.proposal = proposal or ChoiceProposal(
            kind=ProposalKind.NEW_CHOICE,
            key="ENTERPRISE",
            label="Enterprise Tier",
            description="Enterprise accounts needing dedicated compliance.",
            rationale="Cluster of 3 runs mentions SOC2 and SSO.",
            provider="mock-teacher",
            model="mock-v1",
        )

    async def propose(
        self, service: DecisionService, runs: tuple[DecisionRun, ...]
    ) -> ChoiceProposal:
        return self.proposal


def make_service(project_id: UUID) -> DecisionService:
    choice_a = DecisionServiceChoice(key="STANDARD", label="Standard", description="Standard tier")
    node = DecisionServiceNode(
        name="Root",
        instructions="Classify tier",
        choices=(choice_a, UNKNOWN_CHOICE),
    )
    return DecisionService(
        project_id=project_id,
        slug="tier-classifier",
        name="Tier Classifier",
        instructions="Classify into standard or unknown",
        nodes=(node,),
    )


def make_run(project_id: UUID, service_id: UUID, choice: str = "UNKNOWN") -> DecisionRun:
    return DecisionRun(
        project_id=project_id,
        raw_event_id=uuid4(),
        decision_service_id=service_id,
        decision_node_id=uuid4(),
        provider="mock",
        model="mock-model",
        execution_mode="in_process",
        real_inference=False,
        selected_choice=choice,
        probabilities={choice: 1.0},
        top_probability=1.0,
        margin=1.0,
        unknown_probability=1.0 if choice == "UNKNOWN" else 0.0,
        supervision_outcome="UNKNOWN" if choice == "UNKNOWN" else "TRUSTED",
        supervision_reason="Uncertain" if choice == "UNKNOWN" else "High confidence",
        latency_ms=10.0,
        input_snapshot={"text": "Request enterprise SSO"},
        instructions_snapshot="Classify tier",
        choices_snapshot=[{"key": "STANDARD", "label": "Standard", "description": ""}],
    )


def make_evidence(
    project_id: UUID,
    service_id: UUID,
    run_id: UUID,
    status: EvidenceStatus = EvidenceStatus.READY_FOR_EVOLUTION,
    case_id: UUID | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        project_id=project_id,
        decision_service_id=service_id,
        decision_run_id=run_id,
        evidence_case_id=case_id,
        trigger_type=EvidenceTriggerType.SEMANTIC_UNKNOWN,
        status=status,
        selected_choice="UNKNOWN",
        supervision_outcome="UNKNOWN",
        source="automatic",
    )


@pytest.mark.asyncio
async def test_propose_from_evidence_flow() -> None:
    project_id = uuid4()
    service = make_service(project_id)
    runs = [make_run(project_id, service.id) for _ in range(3)]
    ev_items = [make_evidence(project_id, service.id, r.id) for r in runs]

    repo = InMemoryChoiceCandidateRepository(service, runs, ev_items)
    teacher = MockTeacher()
    evolution = ProjectEvolutionService(repo, teacher)

    candidate = await evolution.propose_from_evidence(
        project_id,
        str(service.id),
        tuple(e.id for e in ev_items),
        actor="tester",
    )

    assert candidate.status == "candidate"
    assert candidate.proposal.key == "ENTERPRISE"
    assert candidate.base_service_hash == service_hash(service)
    assert len(repo.events) == 1
    assert repo.events[0].event_type == "choice_candidate.created"
    with pytest.raises(ValueError, match="Rejection reason"):
        await evolution.reject(project_id, candidate.id, "x" * 1001, actor="tester")
    assert len(repo.events) == 1
    rejected = await evolution.reject(
        project_id, candidate.id, "  Unsupported proposal  ", actor="tester"
    )
    assert rejected.status == "rejected"
    assert rejected.rejection_reason == "Unsupported proposal"
    assert repo.events[-1].event_type == "choice_candidate.rejected"


@pytest.mark.asyncio
async def test_propose_from_evidence_rejects_non_ready_evidence() -> None:
    project_id = uuid4()
    service = make_service(project_id)
    runs = [make_run(project_id, service.id) for _ in range(3)]
    ev_items = [
        make_evidence(project_id, service.id, runs[0].id, status=EvidenceStatus.PENDING),
        make_evidence(project_id, service.id, runs[1].id),
        make_evidence(project_id, service.id, runs[2].id),
    ]

    repo = InMemoryChoiceCandidateRepository(service, runs, ev_items)
    teacher = MockTeacher()
    evolution = ProjectEvolutionService(repo, teacher)

    with pytest.raises(ConflictError, match="ready_for_evolution"):
        await evolution.propose_from_evidence(
            project_id,
            str(service.id),
            tuple(e.id for e in ev_items),
            actor="tester",
        )


@pytest.mark.asyncio
async def test_evaluation_cannot_use_predictions_as_ground_truth() -> None:
    project_id = uuid4()
    service = make_service(project_id)
    unknown_runs = [make_run(project_id, service.id) for _ in range(3)]
    known_runs = [make_run(project_id, service.id, choice="STANDARD") for _ in range(2)]
    runs = unknown_runs + known_runs
    ev_items = [make_evidence(project_id, service.id, r.id) for r in unknown_runs]

    repo = InMemoryChoiceCandidateRepository(service, runs, ev_items)
    teacher = MockTeacher()
    evolution = ProjectEvolutionService(repo, teacher)

    candidate = await evolution.propose_from_evidence(
        project_id,
        str(service.id),
        tuple(e.id for e in ev_items),
        actor="tester",
    )

    with pytest.raises(ConflictError, match="Verified replay evaluation"):
        await evolution.evaluate(project_id, candidate.id)
    assert repo.service == service
    assert len(repo.events) == 1


@pytest.mark.asyncio
async def test_activation_requires_verified_replay_even_with_human_actor() -> None:
    project_id = uuid4()
    service = make_service(project_id)
    runs = [make_run(project_id, service.id) for _ in range(3)]
    ev_items = [make_evidence(project_id, service.id, r.id) for r in runs]

    repo = InMemoryChoiceCandidateRepository(service, runs, ev_items)
    teacher = MockTeacher()
    evolution = ProjectEvolutionService(repo, teacher)

    candidate = await evolution.propose_from_evidence(
        project_id,
        str(service.id),
        tuple(e.id for e in ev_items),
        actor="tester",
    )

    with pytest.raises(ConflictError, match="Verified replay evaluation"):
        await evolution.promote(project_id, candidate.id, actor="lead-architect")
    assert repo.service == service
    assert repo.candidates[candidate.id] == candidate
    assert all(
        ev.status == EvidenceStatus.READY_FOR_EVOLUTION for ev in repo.evidence_items.values()
    )
    assert [e.event_type for e in repo.events] == ["choice_candidate.created"]


@pytest.mark.asyncio
async def test_cannot_promote_modified_service() -> None:
    project_id = uuid4()
    service = make_service(project_id)
    runs = [make_run(project_id, service.id) for _ in range(3)]
    ev_items = [make_evidence(project_id, service.id, r.id) for r in runs]

    repo = InMemoryChoiceCandidateRepository(service, runs, ev_items)
    teacher = MockTeacher()
    evolution = ProjectEvolutionService(repo, teacher)

    candidate = await evolution.propose_from_evidence(
        project_id,
        str(service.id),
        tuple(e.id for e in ev_items),
        actor="tester",
    )

    # Simulate service modified concurrently
    modified_node = DecisionServiceNode(
        name="Root",
        instructions="Modified instructions",
        choices=service.nodes[0].choices,
    )
    repo.service = service.model_copy(update={"nodes": (modified_node,)})

    with pytest.raises(ConflictError, match="modified after candidate was generated"):
        await evolution.promote(project_id, candidate.id, actor="tester")


@pytest.mark.asyncio
async def test_propose_from_evidence_accepts_low_trust_and_human_correction_runs() -> None:
    project_id = uuid4()
    service = make_service(project_id)
    runs = [make_run(project_id, service.id, choice="STANDARD") for _ in range(3)]
    ev_items = [
        EvidenceItem(
            project_id=project_id,
            decision_service_id=service.id,
            decision_run_id=r.id,
            trigger_type=EvidenceTriggerType.LOW_TRUST,
            status=EvidenceStatus.READY_FOR_EVOLUTION,
            selected_choice="STANDARD",
            supervision_outcome="REVIEW",
            source="automatic",
        )
        for r in runs
    ]

    repo = InMemoryChoiceCandidateRepository(service, runs, ev_items)
    teacher = MockTeacher()
    evolution = ProjectEvolutionService(repo, teacher)

    candidate = await evolution.propose_from_evidence(
        project_id,
        str(service.id),
        tuple(e.id for e in ev_items),
        actor="tester",
    )
    assert candidate.status == "candidate"
    assert candidate.proposal.key == "ENTERPRISE"

