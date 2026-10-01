"""Tests for the reconciled evolution-plane core domain model."""

from datetime import UTC, datetime

import pytest
from openclass_core.decision import (
    SourceAvailability,
    StateSource,
)
from openclass_core.evolution import (
    LAYER_OPERATORS,
    Candidate,
    CandidateEnvelope,
    CandidateStatus,
    EvaluationSummary,
    FailureLayer,
    FeatureProposal,
    TeacherProposal,
    derive_state_feature,
)
from pydantic import ValidationError

PROPOSAL_ID = "32905f97-a668-4f4e-aae7-d688b03b0d6c"


def feature_proposal(**updates) -> FeatureProposal:
    data = dict(
        id="resolver_generation_stale",
        kind="boolean",
        sensor_field="resolver_generation_stale",
        source="resolver_probe",
    )
    return FeatureProposal(**(data | updates))


def state_feature_proposal_proposal(**updates) -> TeacherProposal:
    data = dict(
        operator="add_state_feature",
        target_id="ops_state",
        feature=feature_proposal(**updates.pop("feature_updates", {})),
        semantic_description="Represent resolver generation staleness.",
        rationale="Raw evidence contains the fact; the compiler drops it.",
        confidence=0.9,
    )
    return TeacherProposal(**(data | updates))


SOURCES = (
    StateSource(
        id="service_monitor", availability=SourceAvailability.ALWAYS, observes="core facts"
    ),
    StateSource(
        id="resolver_probe",
        availability=SourceAvailability.CONDITIONAL,
        observes="resolver incidents",
    ),
)


def envelope(proposal, **updates) -> CandidateEnvelope:
    data = dict(
        candidate_id=PROPOSAL_ID,
        base_policy_id="network_ops",
        base_policy_hash="a" * 64,
        teacher_provider="gateway",
        teacher_model="google/gemini-2.5-flash",
        protocol_version="teacher-protocol-v2.2",
        profile_id="jev-profile",
        profile_hash="b" * 64,
        context_pack_hash="c" * 64,
        schema_hash="d" * 64,
        created_at=datetime(2026, 9, 25, tzinfo=UTC),
        proposal=proposal,
    )
    return CandidateEnvelope.model_validate(data | updates)


def test_layer_operator_registry_is_closed_and_diagnosis_compatible() -> None:
    for _layer, operators in LAYER_OPERATORS.items():
        assert operators
    assert LAYER_OPERATORS[FailureLayer.DECISION_SPACE] == ("add_choice", "missing_capability")
    assert LAYER_OPERATORS[FailureLayer.PROCEDURE] == ("replace_procedure", "missing_capability")


def test_proposal_payload_must_match_operator() -> None:
    correct = state_feature_proposal_proposal()
    assert correct.feature is not None and correct.target_id == "ops_state"
    with pytest.raises(ValidationError, match="payload mismatch"):
        TeacherProposal(
            operator="add_state_feature",
            target_id="ops_state",
            semantic_description="simulated",
            rationale="simulated",
            confidence=0.5,
        )
    with pytest.raises(ValidationError, match="exact target"):
        state_feature_proposal_proposal(target_id="")
    with pytest.raises(ValidationError, match="empty target_id"):
        TeacherProposal(
            operator="no_change",
            target_id="route",
            semantic_description="simulated",
            rationale="simulated",
            confidence=0.5,
        )


def test_non_change_answers_carry_no_sections() -> None:
    proposal = TeacherProposal(
        operator="missing_capability",
        semantic_description="No registered primitive covers this.",
        rationale="Evidence requires an unregistered capability.",
        confidence=0.8,
    )
    assert proposal.permitted_for(FailureLayer.MISSING_CAPABILITY)
    assert not proposal.permitted_for(FailureLayer.STATE_REPRESENTATION)


def test_scope_is_derived_from_source_not_proposal() -> None:
    proposal = feature_proposal()
    assert not hasattr(proposal, "required") or "required" not in proposal.model_dump()
    derived = derive_state_feature(proposal, SOURCES)
    assert derived.required is False  # conditional source
    always = feature_proposal(source="service_monitor")
    assert derive_state_feature(always, SOURCES).required is True
    with pytest.raises(ValueError, match="unknown state source"):
        derive_state_feature(feature_proposal(source="mystery_probe"), SOURCES)


def test_envelope_owns_identity_and_binding() -> None:
    proposal = state_feature_proposal_proposal()
    env = envelope(proposal)
    assert str(env.candidate_id) == PROPOSAL_ID
    assert env.base_policy_hash == "a" * 64
    assert env.protocol_version == "teacher-protocol-v2.2"
    assert env.proposal.confidence == 0.9
    # Core records protocol provenance as-is; version enforcement lives in the
    # adapter/runtime layer that knows which protocol versions it speaks.
    old_protocol = envelope(proposal, protocol_version="teacher-protocol-v2.1")
    assert old_protocol.protocol_version == "teacher-protocol-v2.1"


def test_candidate_status_transitions_are_validated() -> None:
    from openclass_core.evolution import Approval

    env = envelope(state_feature_proposal_proposal())
    with pytest.raises(ValidationError, match="requires recorded approval"):
        Candidate(candidate_id=env.candidate_id, envelope=env, status=CandidateStatus.APPROVED)
    approval = Approval(
        candidate_id=env.candidate_id,
        approved_at=datetime(2026, 9, 25, tzinfo=UTC),
        approver="human",
        scope="experimental activation only",
        statement="Approved unchanged.",
    )
    candidate = Candidate(
        candidate_id=env.candidate_id,
        envelope=env,
        status=CandidateStatus.ACTIVATED,
        approval=approval,
    )
    assert candidate.approval is not None


def test_evaluation_summary_retention_bounds() -> None:
    with pytest.raises(ValidationError):
        EvaluationSummary(passed=True, checks={"a": True}, knowledge_retention_rate=1.5)
    summary = EvaluationSummary(passed=True, checks={"a": True}, knowledge_retention_rate=1.0)
    assert summary.regressions == ()
