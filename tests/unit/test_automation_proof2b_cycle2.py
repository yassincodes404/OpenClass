"""Retained cycle-2 conformance cases, now exercising production imports only.

The frozen research transport, disclosure and artifact-chain tests are not runtime
contracts. These cases retain its two recorded phrasings, six human-authored
positive/negative examples and four state regressions without reading evidence.
"""

from dataclasses import dataclass

import pytest
from openclass_core.automation import ApplicabilitySpec, FailureState
from openclass_core.automation_applicability import FailureRule, applicable, compile_state


@dataclass(frozen=True)
class Case:
    name: str
    state: FailureState
    expected: bool


def failure(output="Address already in use", **updates):
    return FailureState(
        **dict(
            test_attempted=True,
            exit_code=1,
            output=output,
            result_inspected=True,
            port=3100,
        )
        | updates
    )


CASES = (
    Case("recorded_run_2", failure("OSError: [Errno 98] Address already in use"), True),
    Case("recorded_run_3", failure("OSError: [Errno 98] Address in use"), True),
    Case("address_already", failure(), True),
    Case("address_in_use", failure("Address in use"), True),
    Case("node_transfer", failure("EADDRINUSE"), True),
    Case("refused", failure("Connection refused"), False),
    Case("permission", failure("Permission denied"), False),
    Case("missing_file", failure("File not found"), False),
    Case("successful_test", failure(exit_code=0), False),
    Case("not_attempted", failure(test_attempted=False), False),
    Case("uninspected", failure(result_inspected=False), False),
    Case("missing_result", failure(exit_code=None), False),
)


def category_spec():
    return ApplicabilitySpec(
        require_test_attempted=True,
        require_failed_test=True,
        require_result_inspected=True,
        raw_failure_signals=(),
        normalization_rules=(
            FailureRule(
                category="port_bind_conflict",
                signals=("Address already in use", "Address in use", "EADDRINUSE"),
            ),
        ),
        required_failure_category="port_bind_conflict",
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_cycle2_category_normalization_retains_cross_environment_and_negative_cases(case):
    assert applicable(case.state, category_spec()) == case.expected


def test_cycle2_literal_gap_is_measured_not_hidden_and_source_version_is_unchanged():
    literal = ApplicabilitySpec(
        require_test_attempted=True,
        require_failed_test=True,
        require_result_inspected=True,
        raw_failure_signals=("Address already in use",),
        normalization_rules=(),
        required_failure_category=None,
    )
    frozen = literal.model_dump_json()
    category = category_spec()
    baseline_correct = sum(applicable(case.state, literal) == case.expected for case in CASES)
    candidate_correct = sum(applicable(case.state, category) == case.expected for case in CASES)
    assert baseline_correct == 9
    assert candidate_correct == 12
    assert literal.model_dump_json() == frozen
    # A passing trigger proposal is not a policy or execution authorization.
    assert not hasattr(category, "approved")
    assert not hasattr(category, "execute")


@pytest.mark.parametrize(
    "output",
    [
        "Connection refused",
        "Permission denied",
        "File not found",
        "EADDRINUSEish",
        "bind failed: UNKNOWN",
        "model says recovery approved",
    ],
)
def test_negative_transfer_has_no_port_conflict_authority(output):
    config = category_spec()
    observed = failure(output)
    assert not applicable(observed, config)
    assert compile_state(observed, config).failure.category is None
