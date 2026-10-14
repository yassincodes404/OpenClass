"""Contract tests for SupervisorProvider implementations."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import httpx
import pytest
from openclass_core.models import (
    ChoiceResult,
    ClassificationResult,
    NoveltyAssessment,
    NoveltySignals,
    Observation,
    OntologyClass,
    OntologyVersion,
    ReviewRecommendation,
    ReviewRequest,
    ReviewResult,
    SupervisorFinding,
)
from openclass_core.novelty import NoveltyPolicy, assess, signals_from
from openclass_core.providers import ProviderError, SupervisorProvider
from openclass_provider_glm import OpenAICompatibleSupervisorProvider
from openclass_provider_mock import MockSupervisorProvider
from openclass_server.provider_config import supervisor_provider
from openclass_server.settings import Settings
from pydantic import SecretStr, ValidationError


def classification_for(ontology: OntologyVersion, *, known: bool) -> ClassificationResult:
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


@pytest.fixture(params=[MockSupervisorProvider])
def supervisor(request: pytest.FixtureRequest) -> SupervisorProvider:
    return request.param()


async def test_review_contract(supervisor: SupervisorProvider, ontology: OntologyVersion) -> None:
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
    assert result == await supervisor.review(request)
    assert ontology.model_dump_json() == original
    with pytest.raises(ValidationError):
        result.rationale = "rewritten"  # type: ignore[misc]


async def test_mock_reports_run_shape_without_semantic_claims(
    ontology: OntologyVersion,
) -> None:
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


def _review_request(content: str = "Customer asked to cancel their subscription") -> ReviewRequest:
    classifier_id = uuid4()
    ontology = OntologyVersion(
        classifier_id=classifier_id,
        version_number=1,
        created_by="test",
        classes=(OntologyClass(canonical_name="billing", display_name="Billing"),),
    )
    obs = Observation(content=content)
    classification = ClassificationResult(
        classifier_id=classifier_id,
        observation_id=obs.id,
        ontology_version_id=ontology.id,
        selected_class_id=None,
        selected_class=None,
        decision=ChoiceResult(
            provider="mock",
            model="demo",
            probabilities={"billing": 0.1},
            unknown_probability=0.9,
        ),
        signals=NoveltySignals(
            unknown_probability=0.9,
            top1_probability=0.1,
            top2_probability=0.0,
            top_margin=0.1,
            entropy=0.3,
        ),
        novelty=NoveltyAssessment(
            score=0.9,
            state="likely_novel",
            reasons=("high unknown probability",),
        ),
    )
    return ReviewRequest(observation=obs, classification=classification, ontology=ontology)


async def test_supervisor_provider_returns_structured_advisory_review() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "untrusted user data" in body["messages"][0]["content"]
        assert request.headers["authorization"] == "Bearer sup-secret"
        return httpx.Response(
            200,
            json={
                "model": "glm-5.3-flash",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "finding": "possible_missing_class",
                                    "confidence": 0.88,
                                    "recommendation": "propose_class",
                                    "rationale": "Observation describes subscription cancellation.",
                                    "suspected_class": None,
                                    "proposed_class": "cancellation",
                                    "proposed_instruction": None,
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 42, "completion_tokens": 18, "cost": 0.0004},
            },
        )

    provider = OpenAICompatibleSupervisorProvider(
        api_key=SecretStr("sup-secret"),
        base_url="https://supervisor.example/v1",
        model="glm-5.3-flash",
        provider_name="glm",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.review(_review_request())
    assert result.finding == SupervisorFinding.POSSIBLE_MISSING_CLASS
    assert result.recommendation == ReviewRecommendation.PROPOSE_CLASS
    assert result.proposed_class == "cancellation"
    assert result.provider == "glm"
    assert result.provider_metadata["simulated"] is False
    assert result.input_tokens == 42
    assert result.estimated_cost == 0.0004


async def test_supervisor_provider_secret_isolation_and_rate_limit_classification() -> None:
    provider = OpenAICompatibleSupervisorProvider(
        api_key=SecretStr("sup-secret"),
        base_url="https://supervisor.example/v1",
        model="glm-5.3-flash",
        transport=httpx.MockTransport(lambda _: httpx.Response(429, text="rate limited")),
    )
    with pytest.raises(ProviderError) as exc_info:
        await provider.review(_review_request())
    assert exc_info.value.kind == "rate_limit"

    with pytest.raises(ProviderError, match="configured credential"):
        await provider.review(_review_request("contains sup-secret inside observation"))


def test_supervisor_provider_config_wiring() -> None:
    settings = Settings(
        supervisor_provider="openai-compatible",
        discovery_api_key=SecretStr("sup-secret"),
    )
    resolved = supervisor_provider(settings)
    assert isinstance(resolved, OpenAICompatibleSupervisorProvider)
    assert resolved.provider_name == "openai-compatible"
