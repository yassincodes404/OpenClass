"""Trusted configured profiles, never provider names or wire metadata, grant trust."""

import pytest
from openclass_core.supervision import (
    InferenceProvenance,
    OperatingProfile,
    RuntimeSupervisionPolicy,
    evaluate_supervision,
)


def calibrated(**updates):
    return OperatingProfile(
        calibration_status="calibrated",
        validation_artifact_hash="synthetic-fixture-not-empirical",
        measured_max_choices=3,
        **updates,
    )


def evaluate(profile, **updates):
    args = dict(
        policy=RuntimeSupervisionPolicy(),
        provenance=InferenceProvenance(execution_mode="api", simulated=False),
        profile=profile,
        selected_choice="BILLING",
        top_probability=0.8,
        margin=0.6,
        unknown_probability=0.1,
        risk_level="ordinary",
        choice_count=3,
    )
    args.update(updates)
    return evaluate_supervision(**args)[0]


def test_unknown_missing_uncalibrated_and_high_risk_are_conservative():
    assert evaluate(None) == "REVIEW"
    assert evaluate(OperatingProfile()) == "REVIEW"
    assert evaluate(calibrated(), risk_level="high") == "REVIEW"
    assert evaluate(calibrated(), selected_choice="UNKNOWN") == "UNKNOWN"
    assert evaluate(calibrated(), unknown_probability=0.21) == "REVIEW"


def test_inclusive_limits_and_measurement_distinct_from_declaration():
    assert evaluate(calibrated(), margin=0.25, unknown_probability=0.2) == "TRUSTED"
    assert evaluate(calibrated(), margin=0.249) == "REVIEW"
    assert evaluate(calibrated(), choice_count=4) == "REVIEW"
    assert evaluate(OperatingProfile(declared_max_choices=255)) == "REVIEW"
    assert evaluate(calibrated(declared_max_choices=2)) == "REVIEW"


@pytest.mark.parametrize("temperature", [0, -1, float("nan")])
def test_invalid_temperature_rejected(temperature):
    with pytest.raises(ValueError):
        OperatingProfile(temperature=temperature)


def test_nonunit_temperature_cannot_imply_validated_scaling():
    assert evaluate(calibrated(temperature=2)) == "REVIEW"


def test_inference_provenance_must_match_profile_and_cannot_be_missing():
    assert evaluate(calibrated(), provenance=None) == "REVIEW"
    fallback = InferenceProvenance(execution_mode="deterministic_test_fallback", simulated=True)
    assert evaluate(calibrated(), provenance=fallback) == "REVIEW"
    simulated_profile = OperatingProfile(
        calibration_status="simulated",
        allow_simulated_continuation=True,
    )
    assert evaluate(simulated_profile) == "REVIEW"  # actual inference is not a mock
    assert evaluate(simulated_profile, provenance=fallback) == "TRUSTED"
    with pytest.raises(ValueError):
        InferenceProvenance(execution_mode="deterministic_test_fallback", simulated=False)
