import json
from uuid import uuid4

import httpx
import pytest
from openclass_core.candidates import ClusterDiscoveryRequest
from openclass_core.models import ChoiceRequest, Observation, OntologyClass, OntologyVersion
from openclass_core.providers import ProviderError
from openclass_provider_glm.gateway import (
    GatewayClusterDiscovery,
    GatewayDecisionProvider,
    GatewayEmbedder,
)
from pydantic import SecretStr


def configuration(handler):
    return dict(
        api_key=SecretStr("contract-secret"),
        base_url="https://gateway.example/v1",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )


async def test_compiled_state_budget_and_credentials_are_not_sent():
    from openclass_core.state_compiler import StateCompilationError

    def forbidden(_):
        pytest.fail("Invalid state must not reach a transport")

    for metadata, error in [
        ({"state_facts": {"declared": "contract-secret"}}, ProviderError),
        (
            {"state_facts": {"declared": "界"}, "state_budgets": {"max_estimated_tokens": 10}},
            StateCompilationError,
        ),
    ]:
        request = choice_request().model_copy(
            update={
                "observation": Observation(content="charged", metadata=metadata),
            }
        )
        with pytest.raises(error):
            await GatewayDecisionProvider(**configuration(forbidden)).choice(request)


def choice_request(content="actual observation"):
    return ChoiceRequest(
        observation=Observation(content=content),
        ontology=OntologyVersion(
            classifier_id=uuid4(),
            version_number=1,
            created_by="test",
            classes=(OntologyClass(canonical_name="bug", display_name="Bug"),),
        ),
    )


def structured_response(value):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": json.dumps(value)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.001},
        },
    )


async def test_real_choice_retains_usage_and_unknown():
    def handler(request):
        payload = json.loads(request.content)
        assert "metadata" not in payload["messages"][1]["content"]
        assert request.headers["authorization"] == "Bearer contract-secret"
        return structured_response({"probabilities": {"bug": 0.1, "UNKNOWN": 0.9}})

    result = await GatewayDecisionProvider(**configuration(handler)).choice(choice_request())
    assert result.unknown_probability == 0.9
    assert result.provider_metadata["real_inference"] is True
    assert result.provider_metadata["simulated"] is False
    assert result.input_tokens == 10 and result.estimated_cost == 0.001


@pytest.mark.parametrize(
    "scores",
    [
        {"bug": 1.0},
        {"bug": 1.0, "UNKNOWN": 0.1},
        {"bug": True, "UNKNOWN": 0},
        {"bug": 0.5, "UNKNOWN": 0.5, "invented": 0},
    ],
)
async def test_choice_rejects_malformed_distributions(scores):
    provider = GatewayDecisionProvider(
        **configuration(lambda _: structured_response({"probabilities": scores}))
    )
    with pytest.raises(ProviderError):
        await provider.choice(choice_request())


async def test_secrets_and_upstream_errors_are_not_exposed():
    provider = GatewayDecisionProvider(
        **configuration(lambda _: httpx.Response(403, text="contract-secret"))
    )
    with pytest.raises(ProviderError) as error:
        await provider.choice(choice_request())
    assert "contract-secret" not in str(error.value)
    with pytest.raises(ProviderError):
        await provider.choice(choice_request("contract-secret"))


async def test_embeddings_reorder_batch_and_validate_dimensions():
    vector = [0.1] * 1536
    embedder = GatewayEmbedder(
        **configuration(
            lambda _: httpx.Response(
                200,
                json={
                    "data": [{"index": 1, "embedding": vector}, {"index": 0, "embedding": vector}],
                },
            )
        )
    )
    assert len(await embedder.embed(["one", "two"])) == 2
    assert await embedder.embed([]) == []


@pytest.mark.parametrize(
    "data",
    [
        [{"index": 0, "embedding": [0.1]}],
        [{"index": 1, "embedding": [0.1] * 1536}],
        [{"index": 0, "embedding": [0.0] * 1536}],
        [{"index": 0, "embedding": [True] * 1536}],
    ],
)
async def test_embeddings_reject_missing_or_invalid_vectors(data):
    embedder = GatewayEmbedder(**configuration(lambda _: httpx.Response(200, json={"data": data})))
    with pytest.raises(ProviderError):
        await embedder.embed(["one"])


async def test_cluster_discovery_cannot_bypass_minimum_evidence():
    provider = GatewayClusterDiscovery(
        **configuration(
            lambda _: structured_response(
                {
                    "type": "NEW_CLASS",
                    "canonical_name": "build_ci",
                    "definition": "Build failures",
                    "confidence": 0.9,
                    "reason": "Model suggestion",
                }
            )
        )
    )
    with pytest.raises(ProviderError):
        await provider.discover(
            ClusterDiscoveryRequest(
                cluster_id=uuid4(),
                member_texts=("one actual issue",),
                existing_classes=("bug",),
            )
        )


async def test_cluster_discovery_retains_inactive_proposal_without_ontology_access():
    provider = GatewayClusterDiscovery(
        **configuration(
            lambda _: structured_response(
                {
                    "type": "NEW_CLASS",
                    "canonical_name": "build_ci",
                    "definition": "Build failures",
                    "confidence": 0.9,
                    "reason": "Related evidence",
                    "aliases": ["ci_failure"],
                }
            )
        )
    )
    result = await provider.discover(
        ClusterDiscoveryRequest(
            cluster_id=uuid4(),
            member_texts=("one", "two", "three"),
            existing_classes=("bug",),
        )
    )
    assert result.canonical_name == "build_ci"
    assert result.aliases == ("ci_failure",)


def test_model_overrides_and_unsupported_providers_fail_closed():
    from openclass_server.provider_config import resolve_decision_provider
    from openclass_server.settings import Settings

    settings = Settings(discovery_api_key=SecretStr("contract-secret"))
    result = resolve_decision_provider(settings, "openai-compatible:google/gemini-2.5-flash")
    assert result.model == "google/gemini-2.5-flash"  # type: ignore[attr-defined]
    with pytest.raises(ValueError):
        resolve_decision_provider(settings, "unknown-provider")
    with pytest.raises(ValueError):
        resolve_decision_provider(settings, "openai-compatible:unregistered-model")
