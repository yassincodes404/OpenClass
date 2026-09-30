"""Synthetic tests of Proof #2B semantics; no model or live-artifact dependency."""

import importlib
import json

import httpx
import pytest
from pydantic import ValidationError


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    return (
        importlib.import_module("automation_applicability"),
        importlib.import_module("automation_proof2b"),
    )


def spec(m, **updates):
    data = dict(
        require_test_attempted=True,
        require_failed_test=True,
        require_result_inspected=True,
        raw_failure_signals=("fixture bind conflict",),
        normalization_rules=(),
        required_failure_category=None,
    )
    return m.ApplicabilitySpec(**(data | updates))


def state(m, **updates):
    data = dict(
        test_attempted=True,
        exit_code=1,
        output="fixture bind conflict",
        result_inspected=True,
        port=3333,
    )
    return m.FailureState(**(data | updates))


@pytest.mark.parametrize(
    "updates",
    [{"exit_code": 0}, {"exit_code": None}, {"test_attempted": False}, {"result_inspected": False}],
)
def test_failed_inspected_attempt_is_required(modules, updates):
    m, _ = modules
    assert not m.applicable(state(m, **updates), spec(m))


def test_literal_matching_is_escaped_and_word_bounded(modules):
    m, _ = modules
    assert m.matches_signal("FIXTURE  bind\nconflict", "fixture bind conflict")
    assert not m.matches_signal("fixture bind conflictual", "fixture bind conflict")
    assert not m.matches_signal("anything", ".*")
    assert m.matches_signal("literal .* value", ".*")


def test_normalization_is_deterministic_and_ambiguity_is_unknown(modules):
    m, _ = modules
    rule = m.FailureRule(category="fixture_conflict", signals=("fixture bind conflict",))
    config = spec(
        m,
        raw_failure_signals=(),
        normalization_rules=(rule,),
        required_failure_category="fixture_conflict",
    )
    assert m.compile_state(state(m), config).failure.category == "fixture_conflict"
    assert m.applicable(state(m), config)
    assert m.compile_state(state(m, exit_code=0), config).failure.category is None
    conflicting = config.model_copy(
        update={
            "normalization_rules": (
                rule,
                m.FailureRule(category="other_failure", signals=("fixture bind conflict",)),
            )
        }
    )
    assert m.compile_state(state(m), conflicting).normalization_ambiguous
    assert not m.applicable(state(m), conflicting)


def test_arbitrary_procedure_or_unknown_category_is_rejected(modules):
    m, _ = modules
    with pytest.raises(ValidationError):
        m.ApplicabilityProposal.model_validate_json(
            json.dumps(
                {
                    "proposal_type": "NO_CHANGE",
                    "semantic_description": "simulated",
                    "applicability_spec": None,
                    "rationale": "simulated",
                    "confidence": 0.5,
                    "procedure": ["run_shell"],
                }
            )
        )
    with pytest.raises(ValidationError):
        spec(m, raw_failure_signals=(), required_failure_category="missing_category")


def test_no_change_is_not_promoted_or_repaired(modules):
    m, harness = modules
    proposal = m.ApplicabilityProposal(
        proposal_type="NO_CHANGE",
        semantic_description="simulated",
        applicability_spec=None,
        rationale="simulated",
        confidence=0.6,
    )
    result = harness.evaluate(proposal, [])
    assert result["status"] == "not_evaluated"
    assert not result["promotion_allowed"]


def test_eval_failure_and_regressions_are_explicit(modules):
    m, harness = modules
    proposal = m.ApplicabilityProposal(
        proposal_type="GENERALIZE_TRIGGER",
        semantic_description="simulated",
        applicability_spec=spec(m),
        rationale="simulated",
        confidence=0.5,
    )
    case = {
        "id": "miss",
        "state": state(m, output="Address already in use").model_dump(),
        "expected": True,
    }
    result = harness.evaluate(proposal, [case])
    assert result["status"] == "failed"
    assert result["regressions"] == ["miss"]
    assert not result["promotion_allowed"]


def test_eval_cases_are_not_in_the_provider_request(modules):
    _, harness = modules
    request = harness.payload_for({"observations": [{"output": "Address in use"}]}, "fixture")
    encoded = json.dumps(request)
    for hidden in (
        "EADDRINUSE",
        "Connection refused",
        "Permission denied",
        "File not found",
        "expected",
        "evaluation-fixtures",
    ):
        assert hidden not in encoded


@pytest.mark.asyncio
async def test_invalid_response_retry_is_identical_and_bounded(modules, monkeypatch, tmp_path):
    _, harness = modules
    requests = []

    def handle(request):
        requests.append(request.content)
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{"}}]}
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        harness.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    with pytest.raises(ValueError):
        await harness.discover(harness.payload_for({}, "fixture"), "fixture-key", tmp_path)
    assert len(requests) == 2 and requests[0] == requests[1]
    assert (tmp_path / "attempt-1.json").exists()
    assert (tmp_path / "attempt-2.json").exists()
    assert not (tmp_path / "provider-proposal.json").exists()


def test_task_success_and_applicability_failure_remain_separate(modules):
    _, harness = modules
    outcome = harness.interpret(
        {
            "run": 3,
            "postconditions_verified": True,
            "trace": [{"selected_action": "done"}],
            "macro_selected_by_jev": True,
            "macro_selected_at_observed_inspected_conflict": False,
            "discovery_calls": 0,
        }
    )
    assert outcome.task_outcome == "success"
    assert outcome.procedure_outcome == "success"
    assert outcome.applicability_gate == "failed"
    assert outcome.generalization_checkpoint == "failed"
