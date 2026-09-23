from uuid import UUID

import pytest
from openclass_core.models import (
    ChoiceResult,
    ClassificationResult,
    Observation,
    ReviewRecommendation,
    ReviewRequest,
    ReviewResult,
    SupervisorFinding,
)
from openclass_core.novelty import NoveltyPolicy, assess, signals_from
from openclass_core.providers import SupervisorProvider
from openclass_provider_mock import MockSupervisorProvider
from pydantic import ValidationError


def classification_for(ontology, *, known: bool) -> ClassificationResult:
    decision = (
        ChoiceResult(
            provider="mock",
            model="lexical-demo-v1",
            probabilities={"billing": 0.9, "technical": 0.05},
            unknown_probability=0.05,
        )
        if known
        else ChoiceResult(
            provider="mock",
            model="lexical-demo-v1",
            probabilities={"billing": 0.025, "technical": 0.025},
            unknown_probability=0.95,
        )
    )
    signals = signals_from(decision)
    selected = next(c for c in ontology.classes if c.canonical_name == "billing") if known else None
    return ClassificationResult(
        classifier_id=ontology.classifier_id,
        observation_id=UUID(int=1),
        ontology_version_id=ontology.id,
        selected_class_id=selected.stable_class_id if selected else None,
        selected_class=selected.canonical_name if selected else None,
        decision=decision,
        signals=signals,
        novelty=assess(signals, NoveltyPolicy()),
    )


# Every future supervisor adapter belongs in this factory fixture.
@pytest.fixture(params=[MockSupervisorProvider])
def supervisor(request: pytest.FixtureRequest) -> SupervisorProvider:
    return request.param()


async def test_review_contract(supervisor: SupervisorProvider, ontology) -> None:
    original = ontology.model_dump_json()
    known = classification_for(ontology, known=True)
    request = ReviewRequest(
        observation=Observation(id=UUID(int=1), content="charged twice"),
        classification=known,
        ontology=ontology,
    )
    result = await supervisor.review(request)
    assert isinstance(result, ReviewResult)
    assert result.provider and result.model
    assert 0 <= result.confidence <= 1
    assert result.rationale
    assert result.provider_metadata["simulated"] is True
    assert result.estimated_cost is not None and result.estimated_cost >= 0
    assert result == await supervisor.review(request)  # deterministic
    assert ontology.model_dump_json() == original
    with pytest.raises(ValidationError):
        result.rationale = "rewritten"


async def test_mock_reports_run_shape_without_semantic_claims(ontology) -> None:
    provider = MockSupervisorProvider()
    known = await provider.review(
        ReviewRequest(
            observation=Observation(id=UUID(int=1), content="charged twice"),
            classification=classification_for(ontology, known=True),
            ontology=ontology,
        )
    )
    assert (known.finding, known.recommendation) == (
        SupervisorFinding.NO_ISSUE,
        ReviewRecommendation.NONE,
    )
    unknown = await provider.review(
        ReviewRequest(
            observation=Observation(id=UUID(int=1), content="cancel my plan"),
            classification=classification_for(ontology, known=False),
            ontology=ontology,
        )
    )
    assert (unknown.finding, unknown.recommendation) == (
        SupervisorFinding.POSSIBLE_MISSING_CLASS,
        ReviewRecommendation.COLLECT_MORE_EVIDENCE,
    )
