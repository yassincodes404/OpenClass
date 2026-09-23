import math
from uuid import uuid4

import pytest
from openclass_core.models import ChoiceResult, Observation, OntologyClass, OntologyVersion
from openclass_core.novelty import NoveltyPolicy, assess, signals_from
from pydantic import ValidationError


def decision(known: dict[str, float], unknown: float) -> ChoiceResult:
    return ChoiceResult(
        provider="test", model="test", probabilities=known, unknown_probability=unknown
    )


@pytest.mark.parametrize(
    "probabilities,unknown",
    [
        ({"a": 0.9}, 0.9),
        ({"a": -0.1}, 1.1),
        ({"a": math.nan}, 0),
        ({"a": math.inf}, 0),
    ],
)
def test_invalid_distributions_rejected(probabilities: dict, unknown: float) -> None:
    with pytest.raises(ValidationError):
        decision(probabilities, unknown)


@pytest.mark.parametrize("name", ["unknown", "other", "Bad Name"])
def test_reserved_and_invalid_names(name: str) -> None:
    with pytest.raises(ValidationError):
        OntologyClass(canonical_name=name, display_name=name)


def test_aliases_unique_across_classes() -> None:
    classes = (
        OntologyClass(canonical_name="a", display_name="A", aliases=(" Shared ",)),
        OntologyClass(canonical_name="b", display_name="B", aliases=("shared",)),
    )
    with pytest.raises(ValidationError, match="unique"):
        OntologyVersion(classifier_id=uuid4(), version_number=1, classes=classes, created_by="test")


def test_ontology_is_deeply_immutable(ontology: OntologyVersion) -> None:
    with pytest.raises(ValidationError):
        ontology.classes[0].canonical_name = "rewritten"
    with pytest.raises(ValidationError):
        ontology.classes = ()


def test_blank_observation_rejected() -> None:
    with pytest.raises(ValidationError):
        Observation(content=" \n  ")


@pytest.mark.parametrize(
    "known,unknown,state,reason",
    [
        ({"a": 0.9, "b": 0.05}, 0.05, "known", "known_class_supported"),
        ({"a": 0.1, "b": 0.1}, 0.8, "likely_novel", "strong_unknown_probability"),
        ({"a": 0.49, "b": 0.46}, 0.05, "uncertain", "low_top_class_margin"),
        ({"a": 0.4, "b": 0.2}, 0.4, "uncertain", "elevated_unknown_probability"),
        ({"a": 0.3, "b": 0.29}, 0.41, "uncertain", "unknown_is_top_choice"),
    ],
)
def test_novelty_reasons(known: dict, unknown: float, state: str, reason: str) -> None:
    assessment = assess(signals_from(decision(known, unknown)), NoveltyPolicy())
    assert assessment.state == state
    assert reason in assessment.reasons


def test_policy_and_semantic_distance() -> None:
    signals = signals_from(decision({"a": 0.6}, 0.4)).model_copy(update={"semantic_distance": 0.9})
    assert assess(signals, NoveltyPolicy()).state == "likely_novel"
    assert assess(signals, NoveltyPolicy(semantic_distance_threshold=0.95)).state == "uncertain"
    with pytest.raises(ValidationError):
        NoveltyPolicy(weak_unknown_threshold=0.8, strong_unknown_threshold=0.7)


def test_entropy_is_normalized_and_single_class_works() -> None:
    assert signals_from(decision({"a": 0.5}, 0.5)).entropy == pytest.approx(1)
    assert signals_from(decision({"a": 1}, 0)).entropy == 0


def test_weak_threshold_without_embeddings_still_abstains() -> None:
    assessment = assess(signals_from(decision({"a": 0.6}, 0.4)), NoveltyPolicy())
    assert assessment.state == "uncertain"
