"""Offline TypeSafe wire contracts. All credentials and responses are synthetic."""

import copy
import json
import logging
import traceback
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from openclass_core.models import ChoiceRequest, Observation
from openclass_core.providers import ProviderError
from openclass_provider_jev import UNKNOWN, JevDecisionProvider
from openclass_server.main import create_app
from openclass_server.settings import Settings
from pydantic import SecretStr

KEY = "synthetic-test-credential"


def response_body() -> dict[str, Any]:
    return {
        "model": "typesafe-ai/jev",
        "answers": {
            "classification": {
                "type": "choice",
                "choice": "billing",
                "confidence": 0.9,
                "probabilities": {"billing": 0.9, "technical": 0.05, UNKNOWN: 0.05},
            }
        },
        "usage": {"input_tokens": 318, "output_tokens": 34},
        "provider_metadata": {"gateway": {"cost": "0.00001", "untrusted": KEY}},
    }


def provider(handler, **kwargs) -> JevDecisionProvider:
    return JevDecisionProvider(
        api_key=SecretStr(KEY),
        base_url="https://ai-gateway.vercel.sh/typesafe",
        model="typesafe-ai/jev",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


async def test_known_request_mapping_and_telemetry(ontology) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://ai-gateway.vercel.sh/typesafe/v1/systemone"
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        body = json.loads(request.content)
        assert body["state"] == "charged twice"
        criteria = body["questions"]["classification"]["criteria"]
        assert set(criteria) == {"billing", "technical", UNKNOWN}
        assert criteria["billing"]["aliases"] == ["charged"]
        assert "private-metadata" not in request.content.decode()
        return httpx.Response(200, json=response_body())

    result = await provider(handle).choice(
        ChoiceRequest(
            observation=Observation(
                content="charged twice", metadata={"private-metadata": "hidden"}
            ),
            ontology=ontology,
        )
    )
    assert result.provider == "jev" and result.model == "typesafe-ai/jev"
    assert result.probabilities == {"billing": 0.9, "technical": 0.05}
    assert result.unknown_probability == 0.05
    assert result.input_tokens == 318 and result.output_tokens == 34
    assert result.estimated_cost == 0.00001 and result.latency_ms >= 0
    assert result.provider_metadata == {
        "simulated": False,
        "real_inference": True,
        "execution_mode": "api",
        "confidence": 0.9,
        "retry_count": 0,
    }
    assert KEY not in result.model_dump_json()


async def test_unknown_and_absent_usage_are_not_fabricated(ontology) -> None:
    body = response_body()
    body.pop("usage")
    body.pop("provider_metadata")
    body["answers"]["classification"].update(
        choice=UNKNOWN, probabilities={"billing": 0.02, "technical": 0.03, UNKNOWN: 0.95}
    )
    result = await provider(lambda _: httpx.Response(200, json=body)).choice(
        ChoiceRequest(observation=Observation(content="cancel"), ontology=ontology)
    )
    assert result.unknown_probability == 0.95
    assert (result.input_tokens, result.output_tokens, result.estimated_cost) == (None, None, None)
    assert all(c.canonical_name != UNKNOWN for c in ontology.classes)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_class",
        "extra_class",
        "missing_unknown",
        "negative",
        "too_large",
        "nan",
        "infinity",
        "invalid_total",
        "string_probability",
        "bool_probability",
        "missing_answers",
        "extra_answer",
        "wrong_type",
        "wrong_choice",
        "wrong_winner",
        "bad_confidence",
        "negative_tokens",
        "bad_cost",
        "null_model",
        "secret_model",
        "embedded_secret_model",
        "empty_model",
        "number_model",
        "negative_cost",
        "nan_cost",
        "bool_tokens",
    ],
)
async def test_invalid_shapes_fail_closed(ontology, mutation: str) -> None:
    body = copy.deepcopy(response_body())
    answer = body["answers"]["classification"]
    probabilities = answer["probabilities"]
    if mutation == "missing_class":
        probabilities.pop("technical")
    elif mutation == "extra_class":
        probabilities["invented"] = 0
    elif mutation == "missing_unknown":
        probabilities.pop(UNKNOWN)
    elif mutation in {
        "negative",
        "too_large",
        "nan",
        "infinity",
        "invalid_total",
        "string_probability",
        "bool_probability",
    }:
        probabilities["billing"] = {
            "negative": -0.1,
            "too_large": 1.1,
            "nan": float("nan"),
            "infinity": float("inf"),
            "invalid_total": 0.5,
            "string_probability": "0.9",
            "bool_probability": True,
        }[mutation]
    elif mutation == "missing_answers":
        body.pop("answers")
    elif mutation == "extra_answer":
        body["answers"]["other"] = answer
    elif mutation == "wrong_type":
        answer["type"] = "score"
    elif mutation == "wrong_choice":
        answer["choice"] = "invented"
    elif mutation == "wrong_winner":
        answer["choice"] = "technical"
    elif mutation == "bad_confidence":
        answer["confidence"] = 2
    elif mutation == "negative_tokens":
        body["usage"]["input_tokens"] = -1
    elif mutation == "bool_tokens":
        body["usage"]["input_tokens"] = True
    elif mutation in {"bad_cost", "negative_cost", "nan_cost"}:
        body["provider_metadata"]["gateway"]["cost"] = {
            "bad_cost": KEY,
            "negative_cost": "-1",
            "nan_cost": "NaN",
        }[mutation]
    elif mutation == "null_model":
        body["model"] = None
    elif mutation == "secret_model":
        body["model"] = KEY
    elif mutation == "embedded_secret_model":
        body["model"] = f"jev-{KEY}"
    elif mutation == "empty_model":
        body["model"] = ""
    elif mutation == "number_model":
        body["model"] = 42
    with pytest.raises(ProviderError, match="^Jev request failed$") as error:
        await provider(lambda _: httpx.Response(200, content=json.dumps(body))).choice(
            ChoiceRequest(observation=Observation(content="charged"), ontology=ontology)
        )
    assert error.value.__context__ is None
    assert KEY not in "".join(traceback.format_exception(error.value))


@pytest.mark.parametrize("reported", [None, "typesafe-ai/jev-resolved"])
async def test_model_attribution_preserves_reported_identity_or_uses_configured(
    ontology, reported
) -> None:
    body = response_body()
    if reported is None:
        body.pop("model")
    else:
        body["model"] = reported
    adapter = provider(lambda _: httpx.Response(200, json=body))
    result = await adapter.choice(
        ChoiceRequest(observation=Observation(content="charged"), ontology=ontology)
    )
    assert result.model == (reported or "typesafe-ai/jev")
    assert adapter.model == "typesafe-ai/jev"
    with pytest.raises(AttributeError):
        adapter.model = "typesafe-ai/jev-other"


def test_configured_identity_cannot_expose_provider_credential() -> None:
    with pytest.raises(ValueError, match="^Invalid Jev configuration$"):
        JevDecisionProvider(
            api_key=SecretStr(KEY),
            base_url="https://api.typesafe.ai",
            model=f"jev-{KEY}",
        )


@pytest.mark.parametrize(
    "content",
    [b"not-json", b"[]", b'{"model":"a","model":"b"}', b"x" * 1_000_001],
    ids=["not_json", "array", "duplicate_key", "oversized_1mb"],
)
async def test_malformed_json_is_safe(ontology, content: bytes) -> None:
    with pytest.raises(ProviderError):
        await provider(lambda _: httpx.Response(200, content=content)).choice(
            ChoiceRequest(observation=Observation(content="charged"), ontology=ontology)
        )


@pytest.mark.parametrize("status", [301, 401, 403, 422, 429, 500, 502, 529])
async def test_http_failures_are_safe_and_bounded(ontology, status: int, caplog) -> None:
    calls = 0

    def handle(request):
        nonlocal calls
        calls += 1
        return httpx.Response(status, text=KEY, headers={"location": "https://untrusted.example"})

    with caplog.at_level(logging.DEBUG), pytest.raises(ProviderError) as error:
        await provider(handle, max_retries=1).choice(
            ChoiceRequest(observation=Observation(content="charged"), ontology=ontology)
        )
    assert calls == (2 if status == 429 or status >= 500 else 1)
    assert KEY not in caplog.text + "".join(traceback.format_exception(error.value))


async def test_timeout_is_safe(ontology) -> None:
    def handle(request):
        raise httpx.ReadTimeout(KEY, request=request)

    with pytest.raises(ProviderError) as error:
        await provider(handle).choice(
            ChoiceRequest(observation=Observation(content="charged"), ontology=ontology)
        )
    assert error.value.__context__ is None


def test_real_adapter_through_api_persists_and_records_safe_failure(
    database_url, classifier_body
) -> None:
    calls = 0

    def handle(request):
        nonlocal calls
        calls += 1
        if calls == 2:
            return httpx.Response(401, text=KEY)
        body = response_body()
        body["answers"]["classification"]["probabilities"]["sales"] = 0
        return httpx.Response(200, json=body)

    with TestClient(create_app(Settings(database_url=database_url), provider(handle))) as client:
        client.post("/api/v1/classifiers", json=classifier_body).raise_for_status()
        base = "/api/v1/classifiers/support-intent"
        run = client.post(f"{base}/classify", json={"observation": "charged twice"})
        assert run.status_code == 200
        assert run.json()["decision"]["provider"] == "jev"
        stored = client.get(f"{base}/runs/{run.json()['id']}").json()
        assert stored["result"] == run.json()
        failure = client.post(f"{base}/classify", json={"observation": "charged twice"})
        assert failure.status_code == 502
        assert failure.json() == {"detail": "Decision provider failed"}
        assert len(client.get(f"{base}/runs").json()) == 1
        events = client.get(f"{base}/events").json()
        assert events[-1]["event"]["type"] == "provider.error"
        assert KEY not in json.dumps(events) + json.dumps(stored)
