"""Contract test suite for LayaDecisionProvider."""

import json
from typing import Any

import httpx
import pytest
from openclass_core.models import ChoiceRequest, Observation, OntologyClass, OntologyVersion
from openclass_core.providers import ProviderError
from openclass_provider_laya import UNKNOWN, LayaDecisionProvider
from openclass_provider_laya.profile import LayaProfile
from openclass_provider_laya.status import LayaStatus, check_jev_status, check_laya_endpoint


@pytest.fixture
def ontology() -> OntologyVersion:
    return OntologyVersion(
        classifier_id="00000000-0000-0000-0000-000000000001",
        version_number=1,
        created_by="test-fixture",
        classes=(
            OntologyClass(
                canonical_name="billing",
                display_name="Billing",
                description="Invoices, payments, and refunds.",
                aliases=("charged", "invoice"),
            ),
            OntologyClass(
                canonical_name="technical",
                display_name="Technical",
                description="Bugs, outages, and system errors.",
                aliases=("bug", "error", "crash"),
            ),
        ),
    )


def synthetic_laya_response(choice: str = "billing", confidence: float = 0.9) -> dict[str, Any]:
    unknown_p = 0.05
    known_p = 0.9 if choice == "billing" else 0.05
    other_p = 0.05 if choice == "billing" else 0.9
    return {
        "model": "laya-router",
        "answers": {
            "classification": {
                "type": "choice",
                "choice": choice,
                "confidence": confidence,
                "probabilities": {
                    "billing": known_p,
                    "technical": other_p,
                    UNKNOWN: unknown_p,
                },
            }
        },
        "provider_metadata": {"router_route": "en_core", "local": True},
    }


def create_mock_provider(handler: Any) -> LayaDecisionProvider:
    return LayaDecisionProvider(
        base_url="http://127.0.0.1:8000",
        model="laya-router",
        transport=httpx.MockTransport(handler),
    )


async def test_laya_known_choice_request_mapping(ontology: OntologyVersion) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://127.0.0.1:8000/v1/systemone"
        body = json.loads(request.content)
        assert body["state"] == "I was charged twice on my invoice"
        criteria = body["questions"]["classification"]["criteria"]
        assert set(criteria) == {"billing", "technical", UNKNOWN}
        assert criteria["billing"]["name"] == "Billing"
        return httpx.Response(200, json=synthetic_laya_response(choice="billing", confidence=0.92))

    provider = create_mock_provider(handle)
    result = await provider.choice(
        ChoiceRequest(
            observation=Observation(content="I was charged twice on my invoice"),
            ontology=ontology,
        )
    )

    assert result.provider == "laya"
    assert result.model == "laya-router"
    assert result.probabilities["billing"] > result.probabilities["technical"]
    assert result.unknown_probability == 0.05
    assert result.provider_metadata["local"] is True
    assert result.latency_ms >= 0


async def test_laya_explicit_unknown_selection(ontology: OntologyVersion) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        resp = {
            "model": "laya-router",
            "answers": {
                "classification": {
                    "type": "choice",
                    "choice": UNKNOWN,
                    "confidence": 0.95,
                    "probabilities": {
                        "billing": 0.025,
                        "technical": 0.025,
                        UNKNOWN: 0.95,
                    },
                }
            },
        }
        return httpx.Response(200, json=resp)

    provider = create_mock_provider(handle)
    result = await provider.choice(
        ChoiceRequest(
            observation=Observation(content="unrelated topic about weather"),
            ontology=ontology,
        )
    )

    assert result.unknown_probability == 0.95
    assert result.probabilities["billing"] == 0.025
    assert result.probabilities["technical"] == 0.025


async def test_laya_distribution_normalization(ontology: OntologyVersion) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        # Sum != 1.0 (unnormalized raw model output)
        resp = {
            "model": "laya-router",
            "answers": {
                "classification": {
                    "type": "choice",
                    "choice": "billing",
                    "confidence": 0.8,
                    "probabilities": {
                        "billing": 0.8,
                        "technical": 0.4,
                        UNKNOWN: 0.8,
                    },
                }
            },
        }
        return httpx.Response(200, json=resp)

    provider = create_mock_provider(handle)
    result = await provider.choice(
        ChoiceRequest(
            observation=Observation(content="charged twice"),
            ontology=ontology,
        )
    )

    total = sum(result.probabilities.values()) + result.unknown_probability
    assert pytest.approx(total, abs=1e-3) == 1.0


async def test_laya_malformed_request_bounds(ontology: OntologyVersion) -> None:
    # Test invalid constructor bounds
    with pytest.raises(ValueError, match="Invalid Laya request bounds"):
        LayaDecisionProvider(timeout=-5)

    # Test class count limit
    huge_ontology = OntologyVersion(
        classifier_id="00000000-0000-0000-0000-000000000001",
        version_number=1,
        created_by="test-fixture",
        classes=tuple(
            OntologyClass(canonical_name=f"c_{i}", display_name=f"C {i}") for i in range(255)
        ),
    )
    provider = LayaDecisionProvider()
    with pytest.raises(ProviderError, match="Laya supports at most 254 known classes"):
        await provider.choice(
            ChoiceRequest(
                observation=Observation(content="valid text"),
                ontology=huge_ontology,
            )
        )


async def test_laya_provider_http_error(ontology: OntologyVersion) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"Internal server error")

    provider = create_mock_provider(handle)
    with pytest.raises(ProviderError, match="Laya server error HTTP 500"):
        await provider.choice(
            ChoiceRequest(
                observation=Observation(content="test error"),
                ontology=ontology,
            )
        )


def test_laya_profile_is_distinct_from_jev() -> None:
    profile = LayaProfile()
    assert profile.provider == "laya"
    assert profile.declared.local is True
    assert profile.declared.choice is True
    assert profile.measured_by_openclass.max_choice_count_tested is None
    assert profile.measured_by_openclass.calibration_status == "uncalibrated"


def test_jev_status_detection() -> None:
    assert check_jev_status("some-api-key") == "configured"
    assert check_jev_status("") == "not_configured"
    assert check_jev_status(None) == "not_configured"


async def test_laya_endpoint_status_detection() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ready"})

    transport = httpx.MockTransport(handle)
    status = await check_laya_endpoint(transport=transport)
    assert status == LayaStatus.READY


async def test_installed_laya_is_not_daemon_readiness() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ConnectError("unavailable", request=request)

    status = await check_laya_endpoint(transport=httpx.MockTransport(handle))
    assert status == LayaStatus.UNAVAILABLE
    assert len(requests) == 1


async def test_laya_fallback_engine_works_without_external_service(
    ontology: OntologyVersion,
) -> None:
    # Uses local fallback engine directly
    provider = LayaDecisionProvider(
        base_url="http://invalid-nonexistent-url:9999", prefer_local_process=False
    )
    result = await provider.choice(
        ChoiceRequest(
            observation=Observation(content="I have an error and a bug in the code"),
            ontology=ontology,
        )
    )
    assert result.provider == "laya"
    assert result.probabilities["technical"] > result.probabilities["billing"]
    assert result.unknown_probability < 0.5
    assert result.provider_metadata["local"] is True
    assert result.provider_metadata["simulated"] is True
    assert result.provider_metadata["real_inference"] is False
