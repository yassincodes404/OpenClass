"""Unit tests for project-scoped Evidence domain rules, eligibility, and human triage."""

from uuid import uuid4

import pytest
from openclass_core.evidence import (
    DiagnosisCategory,
    EvidenceStatus,
    EvidenceTriggerType,
    FeedbackAction,
    evaluate_eligibility,
    validate_status_transition,
)
from openclass_core.projects import DecisionRun, ProjectService
from openclass_core.repositories import ConflictError

from tests.unit.test_projects import InMemoryProjects, SlowClock


@pytest.fixture
def service() -> ProjectService:
    return ProjectService(InMemoryProjects(), clock=SlowClock())


def test_eligibility_policy_semantic_unknown() -> None:
    res = evaluate_eligibility(
        selected_choice="UNKNOWN",
        supervision_outcome="TRUSTED",
        supervision_reason="Semantic unknown selected",
    )
    assert res.eligible is True
    assert res.trigger_type == EvidenceTriggerType.SEMANTIC_UNKNOWN


def test_eligibility_policy_research_calibration_review_not_eligible() -> None:
    res = evaluate_eligibility(
        selected_choice="FEATURE_REQUEST",
        supervision_outcome="REVIEW",
        supervision_reason=(
            "Laya provider operates under research calibration (conservative supervision)"
        ),
    )
    assert res.eligible is False
    assert "research-calibration" in res.reason.lower()


def test_eligibility_policy_calibrated_low_trust_eligible() -> None:
    res = evaluate_eligibility(
        selected_choice="FEATURE_REQUEST",
        supervision_outcome="REVIEW",
        supervision_reason="Margin below safety threshold 0.20",
    )
    assert res.eligible is True
    assert res.trigger_type == EvidenceTriggerType.LOW_TRUST


def test_eligibility_policy_trusted_decision_not_eligible() -> None:
    res = evaluate_eligibility(
        selected_choice="FEATURE_REQUEST",
        supervision_outcome="TRUSTED",
        supervision_reason="High confidence decision",
    )
    assert res.eligible is False


def test_status_transitions_valid() -> None:
    validate_status_transition(EvidenceStatus.PENDING, EvidenceStatus.TRIAGED)
    validate_status_transition(EvidenceStatus.PENDING, EvidenceStatus.RESOLVED)
    validate_status_transition(EvidenceStatus.PENDING, EvidenceStatus.DISMISSED)
    validate_status_transition(EvidenceStatus.TRIAGED, EvidenceStatus.READY_FOR_EVOLUTION)
    validate_status_transition(EvidenceStatus.TRIAGED, EvidenceStatus.RESOLVED)
    validate_status_transition(EvidenceStatus.TRIAGED, EvidenceStatus.DISMISSED)


def test_status_transitions_invalid() -> None:
    with pytest.raises(ConflictError):
        validate_status_transition(EvidenceStatus.RESOLVED, EvidenceStatus.PENDING)
    with pytest.raises(ConflictError):
        validate_status_transition(EvidenceStatus.DISMISSED, EvidenceStatus.TRIAGED)
    with pytest.raises(ConflictError):
        validate_status_transition(EvidenceStatus.READY_FOR_EVOLUTION, EvidenceStatus.PENDING)
    with pytest.raises(ConflictError):
        validate_status_transition(EvidenceStatus.PENDING, EvidenceStatus.READY_FOR_EVOLUTION)


async def test_record_unknown_run_creates_evidence_automatically(service: ProjectService) -> None:
    project = await service.create("Support System")
    ds = await service.create_decision_service(
        identifier=str(project.id),
        name="Routing",
        instructions="Route support issues",
        choices=[{"key": "TECH", "label": "Tech"}],
    )
    run = DecisionRun(
        raw_event_id=uuid4(),
        project_id=project.id,
        decision_service_id=ds.id,
        decision_node_id=ds.nodes[0].id,
        provider="laya",
        model="laya-router",
        execution_mode="in_process",
        real_inference=True,
        selected_choice="UNKNOWN",
        probabilities={"TECH": 0.2, "UNKNOWN": 0.8},
        top_probability=0.8,
        second_probability=0.2,
        margin=0.6,
        unknown_probability=0.8,
        supervision_outcome="UNKNOWN",
        supervision_reason="Unknown choice chosen",
        latency_ms=12.5,
        input_snapshot={"content": "New unsupported question"},
        instructions_snapshot="Route support issues",
        choices_snapshot=[{"key": "TECH"}, {"key": "UNKNOWN"}],
    )
    evidence = await service.record_decision_run(run)
    assert evidence is not None
    assert evidence.trigger_type == EvidenceTriggerType.SEMANTIC_UNKNOWN
    assert evidence.status == EvidenceStatus.PENDING
    assert evidence.decision_run_id == run.id

    # Verify listing evidence
    items = await service.list_evidence(str(project.id))
    assert len(items) == 1
    assert items[0].id == evidence.id


async def test_human_correction_creates_evidence(service: ProjectService) -> None:
    project = await service.create("Intent Analysis")
    ds = await service.create_decision_service(
        identifier=str(project.id),
        name="Customer Intent",
        instructions="Classify user intention",
        choices=[{"key": "BILLING", "label": "Billing"}],
    )
    run = DecisionRun(
        raw_event_id=uuid4(),
        project_id=project.id,
        decision_service_id=ds.id,
        decision_node_id=ds.nodes[0].id,
        provider="laya",
        model="laya-router",
        execution_mode="in_process",
        real_inference=True,
        selected_choice="BILLING",
        probabilities={"BILLING": 0.95, "UNKNOWN": 0.05},
        top_probability=0.95,
        second_probability=0.05,
        margin=0.9,
        unknown_probability=0.05,
        supervision_outcome="TRUSTED",
        supervision_reason="Trusted",
        latency_ms=10.0,
        input_snapshot={"content": "We need SSO integration"},
        instructions_snapshot="Classify user intention",
        choices_snapshot=[{"key": "BILLING"}, {"key": "UNKNOWN"}],
    )
    # Persist run (not eligible initially because choice=BILLING and TRUSTED)
    item = await service.record_decision_run(run)
    assert item is None

    # Operator corrects the decision
    feedback = await service.submit_run_feedback(
        str(project.id),
        run.id,
        FeedbackAction.CORRECT,
        corrected_choice="ENTERPRISE_FEATURE",
        note="Customer asked for SSO which is an enterprise feature",
    )
    assert feedback.action == FeedbackAction.CORRECT

    # Evidence should now exist
    evidence_list = await service.list_evidence(str(project.id))
    assert len(evidence_list) == 1
    ev = evidence_list[0]
    assert ev.trigger_type == EvidenceTriggerType.HUMAN_CORRECTION
    assert ev.source == "human"
    assert ev.corrected_choice == "ENTERPRISE_FEATURE"


async def test_evidence_triage_and_lifecycle(service: ProjectService) -> None:
    project = await service.create("Triage Test")
    ds = await service.create_decision_service(
        identifier=str(project.id),
        name="Categorizer",
        instructions="Sort items",
        choices=[{"key": "A", "label": "A"}],
    )
    run = DecisionRun(
        raw_event_id=uuid4(),
        project_id=project.id,
        decision_service_id=ds.id,
        decision_node_id=ds.nodes[0].id,
        provider="laya",
        model="laya-router",
        execution_mode="in_process",
        real_inference=True,
        selected_choice="UNKNOWN",
        probabilities={"A": 0.1, "UNKNOWN": 0.9},
        top_probability=0.9,
        second_probability=0.1,
        margin=0.8,
        unknown_probability=0.9,
        supervision_outcome="UNKNOWN",
        supervision_reason="Unknown",
        latency_ms=10.0,
        input_snapshot={"content": "Mystery item"},
        instructions_snapshot="Sort items",
        choices_snapshot=[{"key": "A"}, {"key": "UNKNOWN"}],
    )
    ev = await service.record_decision_run(run)
    assert ev is not None

    # Triage evidence
    triaged = await service.triage_evidence(
        str(project.id),
        ev.id,
        diagnosis=DiagnosisCategory.DECISION_SPACE,
        rationale="Item represents a completely new product category",
    )
    assert triaged.status == EvidenceStatus.TRIAGED
    assert triaged.diagnosis == DiagnosisCategory.DECISION_SPACE

    # Transition to READY_FOR_EVOLUTION
    ready = await service.transition_evidence(
        str(project.id),
        ev.id,
        target_status=EvidenceStatus.READY_FOR_EVOLUTION,
    )
    assert ready.status == EvidenceStatus.READY_FOR_EVOLUTION

    # Check evolution summary
    summary = await service.evolution_summary(str(project.id))
    assert summary.ready_for_evolution == 1
    assert summary.total_evidence == 1


async def test_evidence_case_creation_and_grouping(service: ProjectService) -> None:
    project = await service.create("Cases Test")
    ds = await service.create_decision_service(
        identifier=str(project.id),
        name="Classifier",
        instructions="Classify",
        choices=[{"key": "KNOWN", "label": "Known"}],
    )
    # Create two unknown runs
    runs = []
    ev_ids = []
    for i in range(2):
        r = DecisionRun(
            raw_event_id=uuid4(),
            project_id=project.id,
            decision_service_id=ds.id,
            decision_node_id=ds.nodes[0].id,
            provider="laya",
            model="laya-router",
            execution_mode="in_process",
            real_inference=True,
            selected_choice="UNKNOWN",
            probabilities={"KNOWN": 0.1, "UNKNOWN": 0.9},
            top_probability=0.9,
            second_probability=0.1,
            margin=0.8,
            unknown_probability=0.9,
            supervision_outcome="UNKNOWN",
            supervision_reason="Unknown",
            latency_ms=10.0,
            input_snapshot={"content": f"Unknown {i}"},
            instructions_snapshot="Classify",
            choices_snapshot=[{"key": "KNOWN"}, {"key": "UNKNOWN"}],
        )
        ev = await service.record_decision_run(r)
        assert ev is not None
        runs.append(r)
        ev_ids.append(ev.id)

    # Create case
    case = await service.create_evidence_case(
        str(project.id),
        title="Repeated Multi-user Requests",
        decision_service_id=ds.id,
        evidence_ids=ev_ids,
    )
    assert case.title == "Repeated Multi-user Requests"

    # Verify evidence items linked to case
    ev0 = await service.get_evidence(str(project.id), ev_ids[0])
    assert ev0.evidence_case_id == case.id
