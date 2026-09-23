"""Supervisor review models: bounded advisory output, never authority."""

from uuid import uuid4

import pytest
from openclass_core.models import (
    ReviewRecommendation,
    ReviewResult,
    SupervisorFinding,
    SupervisorReview,
)
from pydantic import ValidationError


def review_result(**overrides: object) -> ReviewResult:
    fields: dict[str, object] = {
        "provider": "stub",
        "model": "stub",
        "finding": SupervisorFinding.NO_ISSUE,
        "confidence": 0.5,
        "recommendation": ReviewRecommendation.NONE,
        "rationale": "advisory only",
    }
    return ReviewResult(**{**fields, **overrides})  # type: ignore[arg-type]


@pytest.mark.parametrize("confidence", [-0.01, 1.01, float("nan")])
def test_confidence_is_a_bounded_probability(confidence: float) -> None:
    with pytest.raises(ValidationError):
        review_result(confidence=confidence)


@pytest.mark.parametrize(
    "field,value",
    [
        ("rationale", ""),
        ("rationale", "x" * 4001),
        ("suspected_class", "x" * 201),
        ("proposed_class", ""),
        ("proposed_instruction", "y" * 4001),
    ],
)
def test_free_text_fields_are_bounded(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        review_result(**{field: value})


def test_findings_and_recommendations_are_closed_enums() -> None:
    with pytest.raises(ValidationError):
        review_result(finding="definitely_wrong")
    with pytest.raises(ValidationError):
        review_result(recommendation="promote_class")


def test_reviews_default_to_manual_trigger_only() -> None:
    review = SupervisorReview(
        classifier_id=uuid4(),
        classification_run_id=uuid4(),
        ontology_version_id=uuid4(),
        result=review_result(),
    )
    assert review.trigger == "manual"
    with pytest.raises(ValidationError):
        SupervisorReview(
            classifier_id=uuid4(),
            classification_run_id=uuid4(),
            ontology_version_id=uuid4(),
            result=review_result(),
            trigger="scheduled",
        )


def test_usage_telemetry_rejects_negative_values() -> None:
    with pytest.raises(ValidationError):
        review_result(latency_ms=-1)
    with pytest.raises(ValidationError):
        review_result(input_tokens=-5)
    with pytest.raises(ValidationError):
        review_result(estimated_cost=-0.01)


def test_review_output_is_immutable() -> None:
    result = review_result()
    with pytest.raises(ValidationError):
        result.rationale = "rewritten"
