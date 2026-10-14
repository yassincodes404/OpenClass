"""Tests for the reconciled decision-plane core domain model."""

import pytest
from openclass_core.decision import (
    UNKNOWN,
    Capability,
    Choice,
    DecisionNode,
    DecisionOutcome,
    Macro,
    PolicyGraph,
    Predicate,
    SourceAvailability,
    StateSchema,
    StateSource,
    Step,
    SupervisionPolicy,
    compile_state,
    evaluate_predicates,
    select_choice,
)
from pydantic import ValidationError


def schema(**feature_overrides) -> StateSchema:
    features = [
        {"id": "service", "kind": "string", "sensor_field": "service", "required": True},
        {
            "id": "port_conflict",
            "kind": "boolean",
            "sensor_field": "port_conflict",
            "required": True,
        },
    ]
    features = [{**f, **feature_overrides} for f in features]
    return StateSchema(id="ops_state", version=1, features=features)  # type: ignore[arg-type]


def node() -> DecisionNode:
    return DecisionNode(
        id="route",
        question="Which recovery fits?",
        choices=(
            Choice(
                id="dns_failure",
                meaning="Stale DNS records; flush the resolver cache.",
                target_kind="terminal",
                target_id=None,
            ),
        ),
    )


def outcome(**updates) -> DecisionOutcome:
    distribution = {"dns_failure": 0.9, UNKNOWN: 0.1}
    data = {
        "selected_choice": "dns_failure",
        "distribution": distribution,
        "selected_probability": 0.9,
        "top_probability": 0.9,
        "second_probability": 0.1,
        "margin": 0.8,
        "unknown_probability": 0.1,
        "infrastructure_status": "ok",
    }
    return DecisionOutcome.model_validate(data | updates)


def test_compile_copies_declared_facts_and_fails_loudly_on_missing_required() -> None:
    snap = compile_state(schema(), {"service": "checkout", "port_conflict": True}, ("e",))
    assert snap.facts == {"service": "checkout", "port_conflict": True}
    with pytest.raises(ValueError, match="missing sensor fact"):
        compile_state(schema(), {"service": "checkout"}, ())


def test_compile_rejects_wrong_sensor_types() -> None:
    with pytest.raises(ValueError, match="wrong sensor type"):
        compile_state(schema(), {"service": 3, "port_conflict": True}, ())


def test_select_rule_unknown_wins_ties() -> None:
    assert select_choice({"a": 0.6, "b": 0.3, UNKNOWN: 0.1}) == "a"
    assert select_choice({"a": 0.5, UNKNOWN: 0.5}) == UNKNOWN


def test_outcome_separates_infrastructure_from_semantics() -> None:
    failed = outcome(
        infrastructure_status="http",
        selected_choice=None,
        distribution=None,
        selected_probability=None,
        top_probability=None,
        second_probability=None,
        margin=None,
        unknown_probability=None,
    )
    assert failed.infrastructure_status == "http"
    with pytest.raises(ValidationError, match="full semantic telemetry"):
        outcome(selected_choice=None)
    with pytest.raises(ValidationError, match="normalized"):
        outcome(distribution={"dns_failure": 0.5, UNKNOWN: 0.2})


def test_supervision_escalates_infrastructure_unknown_and_unreviewed() -> None:
    policy = SupervisionPolicy(
        id="s",
        min_margin=0.2,
        max_unknown=0.3,
        calibration="production",
        validation_artifact_hash="a" * 64,
    )
    assert policy.decide(outcome(), node()) == "continue"
    assert (
        policy.decide(
            outcome(
                selected_choice=UNKNOWN,
                distribution={"dns_failure": 0.3, UNKNOWN: 0.7},
                selected_probability=0.7,
                top_probability=0.7,
                second_probability=0.3,
                margin=0.4,
                unknown_probability=0.7,
            ),
            node(),
        )
        == "escalate"
    )
    assert (
        policy.decide(
            outcome(
                infrastructure_status="transport",
                selected_choice=None,
                distribution=None,
                selected_probability=None,
                top_probability=None,
                second_probability=None,
                margin=None,
                unknown_probability=None,
            ),
            node(),
        )
        == "escalate"
    )
    research_only = SupervisionPolicy(id="s", min_margin=0.0, max_unknown=0.3)
    assert research_only.decide(outcome(), node()) == "escalate"


def test_high_risk_nodes_always_escalate() -> None:
    policy = SupervisionPolicy(
        id="s",
        min_margin=0.0,
        max_unknown=1.0,
        calibration="production",
        validation_artifact_hash="a" * 64,
    )
    risky = DecisionNode(
        id="rsk",
        question="?",
        risk="high",
        choices=(
            Choice(id="abc", meaning="simulated choice.", target_kind="terminal", target_id=None),
        ),
    )
    assert policy.decide(outcome(), risky) == "escalate"


def test_policy_graph_reference_and_hash_discipline() -> None:
    macro = Macro(
        id="recover",
        purpose="simulated recovery",
        steps=(Step(capability="flush_dns", arguments={}),),
        postconditions=(Predicate(field="port_conflict", equals=False),),
    )
    graph = PolicyGraph(
        id="g",
        version=1,
        state_schema=schema(),
        entry_node="route",
        nodes=(node(),),
        macros=(macro,),
    )
    with pytest.raises(ValidationError, match="missing target macro"):
        PolicyGraph(
            id="g",
            version=1,
            state_schema=schema(),
            entry_node="route",
            nodes=(
                DecisionNode(
                    id="route",
                    question="?",
                    choices=(
                        Choice(
                            id="xyz",
                            meaning="simulated.",
                            target_kind="macro",
                            target_id="missing",
                        ),
                    ),
                ),
            ),
        )
    assert graph.content_hash != ""


def test_hierarchy_requires_decomposition_reason() -> None:
    with pytest.raises(ValidationError, match="decomposition reason"):
        DecisionNode(
            id="parent",
            question="?",
            choices=(
                Choice(id="child", meaning="simulated.", target_kind="node", target_id="child"),
            ),
        )


def test_capability_argument_validation() -> None:
    cap = Capability(
        id="flush_dns", arguments={"confirm": "boolean"}, permitted_values={"confirm": (True,)}
    )
    cap.validate_step(Step(capability="flush_dns", arguments={"confirm": True}))
    with pytest.raises(ValueError, match="argument set"):
        cap.validate_step(Step(capability="flush_dns", arguments={}))
    with pytest.raises(ValueError, match="outside registered"):
        cap.validate_step(Step(capability="flush_dns", arguments={"confirm": False}))


def test_source_availability_enum_drives_scope_elsewhere() -> None:
    assert (
        SourceAvailability.ALWAYS.value == "always"
        and SourceAvailability.CONDITIONAL.value == "conditional"
    )
    source = StateSource(
        id="resolver_probe",
        availability=SourceAvailability.CONDITIONAL,
        observes="resolver incidents",
    )
    assert source.availability is SourceAvailability.CONDITIONAL


def test_predicate_evaluation_is_exact() -> None:
    assert evaluate_predicates((Predicate(field="a", equals=True),), {"a": True})
    assert not evaluate_predicates((Predicate(field="a", equals=True),), {"a": "true"})
    assert not evaluate_predicates((Predicate(field="a", equals=True),), {})
    # Missing field must never match None, and bool must never match int (True != 1, False != 0)
    assert not evaluate_predicates((Predicate(field="a", equals=None),), {})
    assert evaluate_predicates((Predicate(field="a", equals=None),), {"a": None})
    assert not evaluate_predicates((Predicate(field="a", equals=1),), {"a": True})
    assert not evaluate_predicates((Predicate(field="a", equals=True),), {"a": 1})
    assert not evaluate_predicates((Predicate(field="a", equals=0),), {"a": False})
