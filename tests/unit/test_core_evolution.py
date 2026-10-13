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


def test_apply_candidate_produces_versioned_policy_graph_and_enforces_guards() -> None:
    from openclass_core.decision import (
        Capability,
        Choice,
        DecisionNode,
        Macro,
        PolicyGraph,
        Predicate,
        StateFeature,
        StateSchema,
        Step,
    )
    from openclass_core.evolution import apply_candidate

    schema = StateSchema(
        id="ops_state",
        version=1,
        features=(StateFeature(id="service_up", kind="boolean", sensor_field="service_up"),),
    )
    macro = Macro(
        id="restart_service",
        purpose="Restart unhealthy service.",
        steps=(Step(capability="systemctl", arguments={"action": "restart"}),),
        safety_guards=(Predicate(field="service_up", equals=False),),
        postconditions=(Predicate(field="service_up", equals=True),),
    )
    node = DecisionNode(
        id="root",
        question="Select operational action.",
        choices=(
            Choice(
                id="restart",
                meaning="Restart the service when it is down.",
                target_kind="macro",
                target_id="restart_service",
            ),
        ),
    )
    graph = PolicyGraph(
        id="ops_graph",
        version=1,
        state_schema=schema,
        entry_node="root",
        nodes=(node,),
        macros=(macro,),
    )

    # 1. ADD_STATE_FEATURE increments schema & graph version and links parent_hash
    feat_env = envelope(
        state_feature_proposal_proposal(),
        base_policy_hash=graph.content_hash,
    )
    updated_feat = apply_candidate(
        graph,
        feat_env,
        layer=FailureLayer.STATE_REPRESENTATION,
        state_sources=SOURCES,
    )
    assert updated_feat.version == 2
    assert updated_feat.parent_hash == graph.content_hash
    assert updated_feat.state_schema.version == 2
    assert len(updated_feat.state_schema.features) == 2

    # 2. ADD_CHOICE adds choice to target node
    add_choice_prop = TeacherProposal(
        operator="add_choice",
        target_id="root",
        choice=Choice(
            id="escalate_oncall",
            meaning="Escalate to human on-call engineer.",
            target_kind="terminal",
        ),
        semantic_description="Add escalation terminal choice.",
        rationale="Some incidents require manual escalation.",
        confidence=0.92,
    )
    choice_env = envelope(add_choice_prop, base_policy_hash=graph.content_hash)
    updated_choice = apply_candidate(
        graph,
        choice_env,
        layer=FailureLayer.DECISION_SPACE,
    )
    assert [c.id for c in updated_choice.nodes[0].choices] == ["restart", "escalate_oncall"]

    # 3. REPLACE_PROCEDURE validates capability steps
    cap = Capability(
        id="systemctl",
        arguments={"action": "string"},
        permitted_values={"action": ("restart", "reload")},
    )
    proc_prop = TeacherProposal(
        operator="replace_procedure",
        target_id="restart_service",
        steps=(Step(capability="systemctl", arguments={"action": "reload"}),),
        semantic_description="Reload before restart.",
        rationale="Reload is less disruptive.",
        confidence=0.85,
    )
    proc_env = envelope(proc_prop, base_policy_hash=graph.content_hash)
    updated_proc = apply_candidate(
        graph,
        proc_env,
        layer=FailureLayer.PROCEDURE,
        capabilities=(cap,),
    )
    assert updated_proc.macros[0].steps[0].arguments["action"] == "reload"

    # 4. Removing an existing safety guard is rejected
    bad_guard_prop = TeacherProposal(
        operator="change_safety_guard",
        target_id="restart_service",
        predicates=(),
        semantic_description="Drop safety guard.",
        rationale="Unsafe removal.",
        confidence=0.5,
    )
    bad_guard_env = envelope(bad_guard_prop, base_policy_hash=graph.content_hash)
    with pytest.raises(ValueError, match="remove existing safety guards"):
        apply_candidate(graph, bad_guard_env, layer=FailureLayer.SAFETY_GUARD)

    # 5. Stale base_policy_hash is rejected
    with pytest.raises(ValueError, match="stale candidate base"):
        apply_candidate(graph, envelope(add_choice_prop, base_policy_hash="0" * 64))

