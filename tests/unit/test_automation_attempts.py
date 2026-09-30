"""Retry limits, unchanged requests, safe telemetry, and no semantic retries."""

import importlib
import json

import httpx
import pytest


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    return (
        importlib.import_module("automation_attempts"),
        importlib.import_module("automation_proof2_stage_a"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failures", [2, 3])
async def test_jev_transport_attempts_are_bounded_and_recorded(modules, failures):
    attempts, _ = modules
    records = []
    requests = []

    async def handle(request):
        requests.append(request.content)
        if len(requests) <= failures:
            raise httpx.ConnectError("upstream secret must not enter telemetry")
        return httpx.Response(200, json={"usage": {"input_tokens": 7}})

    transport = attempts.JevRetryTransport(records.append, httpx.MockTransport(handle))
    async with httpx.AsyncClient(transport=transport) as client:
        if failures == 3:
            with pytest.raises(httpx.TransportError):
                await client.post("https://example.invalid", json={"state": "unchanged"})
        else:
            assert (
                await client.post("https://example.invalid", json={"state": "unchanged"})
            ).status_code == 200
    assert len(records) == len(requests) == 3
    assert len(set(requests)) == 1
    assert "secret" not in json.dumps([r.model_dump() for r in records])


@pytest.mark.asyncio
async def test_jev_does_not_retry_a_received_invalid_response(modules):
    attempts, _ = modules
    records = []
    transport = attempts.JevRetryTransport(
        records.append,
        httpx.MockTransport(lambda request: httpx.Response(200, json={"invalid": "response"})),
    )
    async with httpx.AsyncClient(transport=transport) as client:
        await client.post("https://example.invalid", json={})
    assert len(records) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("valid_second", [True, False])
async def test_discovery_retries_same_request_once(modules, monkeypatch, valid_second):
    _, harness = modules
    records = []
    requests = []
    valid = {
        "proposal_type": "insufficient_evidence",
        "canonical_name": None,
        "description": None,
        "trigger": "",
        "steps": [],
        "success_condition": "",
        "confidence": 0.4,
        "rationale": "insufficient",
    }

    def handle(request):
        requests.append(request.content)
        content = json.dumps(valid) if valid_second and len(requests) == 2 else "{"
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": content}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        harness.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handle), **kw),
    )
    if valid_second:
        result = await harness.discover_macro(
            "fixture-key", "https://example.invalid", "fixture-model", {}, records.append
        )
        assert result["proposal_type"] == "insufficient_evidence"
    else:
        with pytest.raises(ValueError):
            await harness.discover_macro(
                "fixture-key", "https://example.invalid", "fixture-model", {}, records.append
            )
    assert len(requests) == len(records) == 2
    assert requests[0] == requests[1]
    assert all(r.input_tokens == 3 for r in records)
    assert all(r.reported_cost is None for r in records)
