import pytest
from openclass_core.models import ChoiceRequest, Observation, OntologyVersion
from openclass_core.providers import DecisionProvider
from openclass_provider_mock import MockDecisionProvider


# Every future adapter belongs in a factory fixture with provider-specific setup.
@pytest.fixture(params=[MockDecisionProvider])
def provider(request: pytest.FixtureRequest) -> DecisionProvider:
    return request.param()


async def test_provider_contract(provider: DecisionProvider, ontology: OntologyVersion) -> None:
    original = ontology.model_dump_json()
    result = await provider.choice(
        ChoiceRequest(observation=Observation(content="charged twice"), ontology=ontology)
    )
    assert set(result.probabilities) == {c.canonical_name for c in ontology.classes}
    assert sum(result.probabilities.values()) + result.unknown_probability == pytest.approx(1)
    assert result.provider and result.model
    assert result.latency_ms >= 0
    assert ontology.model_dump_json() == original


async def test_unknown_and_ambiguous_are_representable(ontology: OntologyVersion) -> None:
    provider = MockDecisionProvider()
    unknown = await provider.choice(
        ChoiceRequest(observation=Observation(content="cancel my plan"), ontology=ontology)
    )
    assert unknown.unknown_probability > max(unknown.probabilities.values())
    ambiguous = await provider.choice(
        ChoiceRequest(observation=Observation(content="charged and broken"), ontology=ontology)
    )
    assert ambiguous.probabilities["billing"] == ambiguous.probabilities["technical"]


async def test_mock_does_not_match_substrings(ontology: OntologyVersion) -> None:
    result = await MockDecisionProvider().choice(
        ChoiceRequest(observation=Observation(content="uncharged"), ontology=ontology)
    )
    assert result.unknown_probability == 0.95
