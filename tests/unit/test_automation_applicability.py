"""Production applicability conformance; synthetic evidence, no discovery/model calls."""

from datetime import UTC, datetime, timedelta

import pytest
from openclass_core.automation import ApplicabilitySpec, FailureState, StateGuard
from openclass_core.automation_applicability import (
    ApplicabilityGate,
    FailureRule,
    applicable,
    check_applicability,
    compile_state,
    matches_signal,
)
from pydantic import ValidationError

APPLICABILITY_AT = datetime(2026, 10, 15, 12, tzinfo=UTC)


def spec(**updates):
    return ApplicabilitySpec(
        **dict(
            require_test_attempted=True,
            require_failed_test=True,
            require_result_inspected=True,
            raw_failure_signals=("fixture bind conflict",),
            normalization_rules=(),
            required_failure_category=None,
        )
        | updates
    )


def state(**updates):
    return FailureState(
        **dict(
            test_attempted=True,
            exit_code=1,
            output="fixture bind conflict",
            result_inspected=True,
            port=3333,
        )
        | updates
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"exit_code": 0},
        {"exit_code": None},
        {"test_attempted": False},
        {"result_inspected": False},
    ],
)
def test_failed_inspected_attempt_is_required(updates):
    assert not applicable(state(**updates), spec())


def test_literal_matching_is_escaped_and_word_bounded():
    assert matches_signal("FIXTURE  bind\nconflict", "fixture bind conflict")
    assert not matches_signal("fixture bind conflictual", "fixture bind conflict")
    assert not matches_signal("anything", ".*")
    assert matches_signal("literal .* value", ".*")


def test_normalization_is_deterministic_and_ambiguity_is_unknown():
    rule = FailureRule(category="fixture_conflict", signals=("fixture bind conflict",))
    config = spec(
        raw_failure_signals=(),
        normalization_rules=(rule,),
        required_failure_category="fixture_conflict",
    )
    assert compile_state(state(), config).failure.category == "fixture_conflict"
    assert applicable(state(), config)
    assert compile_state(state(exit_code=0), config).failure.category is None
    conflicting = spec(
        raw_failure_signals=(),
        normalization_rules=(
            rule,
            FailureRule(category="other_failure", signals=("fixture bind conflict",)),
        ),
        required_failure_category="fixture_conflict",
    )
    assert compile_state(state(), conflicting).normalization_ambiguous
    assert not applicable(state(), conflicting)


@pytest.mark.parametrize(
    "updates",
    [
        {"procedure": ("run_shell",)},
        {"raw_failure_signals": (), "required_failure_category": "missing_category"},
        {"raw_failure_signals": (), "normalization_rules": (), "required_failure_category": None},
        {
            "raw_failure_signals": (),
            "normalization_rules": (FailureRule(category="unknown", signals=("failure",)),),
            "required_failure_category": "unknown",
        },
        {"require_test_attempted": "true"},
        {"max_age_seconds": 0},
    ],
)
def test_arbitrary_procedure_unknown_category_and_malformed_spec_are_rejected(updates):
    with pytest.raises(ValidationError):
        spec(**updates)


def test_all_five_gates_are_conjunctive_and_reported_without_raw_evidence():
    config = spec(
        preconditions=(StateGuard(field="port", value=3333),),
        required_capabilities=("inspect_port",),
        safety_guards=(StateGuard(field="cwd", value="disposable"),),
    )
    outcome = check_applicability(
        state(),
        config,
        available_capabilities=frozenset({"inspect_port"}),
        cwd="disposable",
    )
    assert outcome.passed
    assert tuple(gate.gate for gate in outcome.gates) == tuple(ApplicabilityGate)
    assert "fixture bind conflict" not in outcome.model_dump_json()
    assert not check_applicability(state(), config, cwd="disposable").passed
    assert not check_applicability(
        state(),
        config,
        available_capabilities=frozenset({"inspect_port"}),
        cwd="other",
    ).passed


@pytest.mark.parametrize(
    "updates",
    [
        {"schema_id": "another_domain"},
        {"schema_version": 2},
        {"observed_at": APPLICABILITY_AT - timedelta(seconds=301)},
        {"observed_at": APPLICABILITY_AT + timedelta(seconds=60)},
    ],
)
def test_stale_future_and_wrong_schema_are_not_applicable(updates):
    # Collection may precede execution by minutes in the complete suite.
    # Freeze both sides of the freshness comparison, not only the observation.
    outcome = check_applicability(
        state(**({"observed_at": APPLICABILITY_AT} | updates)), spec(), at=APPLICABILITY_AT
    )
    assert not outcome.passed
    assert not outcome.gates[0].passed


@pytest.mark.parametrize("facts", [{}, {"port": None}, {"port": True}, {"port": "3333"}])
def test_guards_do_not_coerce_missing_null_boolean_or_string_to_integer(facts):
    assert not StateGuard(field="port", value=3333).matches(facts)
    assert not StateGuard(field="port", operator="not_equals", value=3333).matches(facts)


def test_missing_value_is_not_evidence_for_not_equals_and_false_is_present():
    assert not StateGuard(field="port", operator="not_equals", value=3333).matches({})
    assert StateGuard(field="test_attempted", operator="present").matches({"test_attempted": False})


def test_capabilities_needed_by_expansion_cannot_be_omitted_from_spec():
    outcome = check_applicability(
        state(),
        spec(),
        required_capabilities=frozenset({"run_python_tests"}),
    )
    assert not outcome.passed
    assert not outcome.gates[3].passed
