import json

import httpx
import pytest
from openclass_core.models import (
    Classifier,
    DiscoveryRequest,
    OntologyClass,
    OntologyVersion,
    UnknownEvent,
)
from openclass_core.providers import ProviderError
from openclass_provider_glm import GLMDiscoveryProvider
from pydantic import SecretStr


def request() -> DiscoveryRequest:
    classifier = Classifier(
        id="00000000-0000-0000-0000-000000000001",
        slug="device-type",
        name="Device",
        active_ontology_version_id="00000000-0000-0000-0000-000000000002",
    )
    ontology = OntologyVersion(
        id=classifier.active_ontology_version_id,
        classifier_id=classifier.id,
        version_number=1,
        created_by="test",
        classes=(
            OntologyClass(canonical_name="phone", display_name="Phone"),
            OntologyClass(canonical_name="laptop", display_name="Laptop"),
        ),
    )
    from openclass_core.models import (
        ChoiceResult,
        ClassificationResult,
        NoveltyAssessment,
        NoveltySignals,
        Observation,
    )

    observation = Observation(content="iPad Pro")
    result = ClassificationResult(
        classifier_id=classifier.id,
        observation_id=observation.id,
        ontology_version_id=ontology.id,
        selected_class_id=None,
        selected_class=None,
        decision=ChoiceResult(
            provider="jev",
            model="jev",
            probabilities={"phone": 0.05, "laptop": 0.05},
            unknown_probability=0.9,
        ),
        signals=NoveltySignals(
            unknown_probability=0.9,
            top1_probability=0.05,
            top2_probability=0.05,
            top_margin=0,
            entropy=0.3,
        ),
        novelty=NoveltyAssessment(score=0.9, state="likely_novel", reasons=("test",)),
    )
    return DiscoveryRequest(
        classifier=classifier,
        ontology=ontology,
        unknowns=(
            UnknownEvent(
                classifier_id=classifier.id, observation=observation, classification=result
            ),
        ),
    )


@pytest.mark.asyncio
async def test_glm_structured_result_is_validated() -> None:
    body = {
        "model": "glm-5.3-flash",
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "proposal_type": "new_class",
                            "canonical_name": "tablet",
                            "display_name": "Tablet",
                            "description": "Touchscreen computer",
                            "confidence": 0.94,
                            "rationale": "Consistent tablet evidence.",
                        }
                    )
                }
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 30},
    }
    provider = GLMDiscoveryProvider(
        api_key=SecretStr("synthetic"),
        base_url="https://glm5.test",
        model="glm-5.3-flash",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
    )
    result = await provider.discover(request())
    assert result.canonical_name == "tablet" and result.input_tokens == 100


@pytest.mark.asyncio
async def test_glm_malformed_output_fails_safely() -> None:
    provider = GLMDiscoveryProvider(
        api_key=SecretStr("synthetic"),
        base_url="https://glm5.test",
        model="glm-5.3-flash",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})
        ),
    )
    with pytest.raises(ProviderError):
        await provider.discover(request())
