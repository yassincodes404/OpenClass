"""Phase 7 provider protocol: test endpoint, usage rollups, safe failures."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from openclass_core.models import (
    ChoiceRequest,
    ChoiceResult,
    OntologyClass,
    OntologyVersion,
)
from openclass_core.providers import ProviderError
from openclass_server.main import create_app
from openclass_server.settings import Settings


def _make_project(client: TestClient) -> str:
    return client.post("/api/v1/projects", json={"name": "Proto Co"}).json()["slug"]


def _make_service(client: TestClient, slug: str) -> str:
    body = {
        "name": "Router",
        "instructions": "Route the message.",
        "choices": [{"key": "BILLING", "label": "Billing"}],
    }
    return client.post(f"/api/v1/projects/{slug}/decision-services", json=body).json()["id"]


def test_provider_test_endpoint_dry_run(mock_client: TestClient):
    response = mock_client.post("/api/v1/providers/test", json={"provider": "mock"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["simulated"] is True
    assert "latency_ms" in payload
    assert set(payload["normalized_preview"]) == {
        "selected",
        "top_probability",
        "unknown_probability",
    }
    # Nothing persisted: no runs exist.
    slug = _make_project(mock_client)
    assert mock_client.get(f"/api/v1/projects/{slug}/runs").json() == []


def test_provider_test_unsupported_provider_is_safe(mock_client: TestClient):
    response = mock_client.post("/api/v1/providers/test", json={"provider": "quantum"})
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "error" in response.json()


def test_usage_rollup_counts_runs_and_unknowns(mock_client: TestClient):
    slug = _make_project(mock_client)
    service = _make_service(mock_client, slug)
    for index in range(3):
        run = mock_client.post(
            f"/api/v1/projects/{slug}/decision-services/{service}/runs",
            json={"content": f"billing question number {index}"},
        )
        assert run.status_code == 201
    usage = mock_client.get(f"/api/v1/projects/{slug}/providers/usage").json()
    assert len(usage) == 1
    row = usage[0]
    assert row["provider"] == "mock"
    assert row["calls"] == 3
    assert row["errors"] == 0
    assert row["avg_latency_ms"] >= 0


class ExplodingProvider:
    async def choice(self, request: ChoiceRequest) -> ChoiceResult:
        raise ProviderError("upstream returned garbage", kind="bad_response")


class MalformedProvider:
    async def choice(self, request: ChoiceRequest) -> ChoiceResult:
        ontology = request.ontology
        billing = ontology.classes[0]
        return ChoiceResult(
            provider="malformed",
            model="broken-v1",
            probabilities={billing.canonical_name: 0.4},
            unknown_probability=0.4,  # sums to 0.8 → normalization rejected
        )


@pytest.mark.parametrize("provider", [ExplodingProvider(), MalformedProvider()])
def test_provider_failures_are_safe_and_persist_no_runs(tmp_path, monkeypatch, provider):
    from alembic import command
    from alembic.config import Config

    url = f"sqlite+aiosqlite:///{tmp_path / 'proto.db'}"
    monkeypatch.setenv("OPENCLASS_DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    settings = Settings(database_url=url, decision_provider="mock")
    app = create_app(settings, provider=provider)
    with TestClient(app, raise_server_exceptions=False) as client:
        slug = client.post("/api/v1/projects", json={"name": "Fail Co"}).json()["slug"]
        service = client.post(
            f"/api/v1/projects/{slug}/decision-services",
            json={
                "name": "R",
                "instructions": "Route it.",
                "choices": [{"key": "BILLING", "label": "Billing"}],
            },
        ).json()["id"]
        response = client.post(
            f"/api/v1/projects/{slug}/decision-services/{service}/runs",
            json={"content": "billing help"},
        )
        assert response.status_code == 502
        assert "provider" in response.json()["detail"].lower()
        # No run persisted.
        assert client.get(f"/api/v1/projects/{slug}/runs").json() == []


def test_provider_catalog_lists_registry(mock_client: TestClient):
    catalog = mock_client.get("/api/v1/providers").json()
    names = [entry["name"] for entry in catalog]
    assert mock_client.get("/api/v1/providers/status").status_code == 200
    assert isinstance(names, list) and len(names) >= 3


class RateLimitedProvider:
    provider_name = "glm"
    model = "glm-5.1"

    async def choice(self, request: ChoiceRequest) -> ChoiceResult:
        raise ProviderError("upstream rate limited with secret sk-123", kind="rate_limit")


def test_provider_rate_limit_returns_429_and_records_provider_telemetry(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    url = f"sqlite+aiosqlite:///{tmp_path / 'ratelimit.db'}"
    monkeypatch.setenv("OPENCLASS_DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    settings = Settings(database_url=url, decision_provider="mock")
    app = create_app(settings, provider=RateLimitedProvider())
    with TestClient(app, raise_server_exceptions=False) as client:
        slug = client.post("/api/v1/projects", json={"name": "Rate Co"}).json()["slug"]
        service = client.post(
            f"/api/v1/projects/{slug}/decision-services",
            json={
                "name": "R",
                "instructions": "Route it.",
                "choices": [{"key": "BILLING", "label": "Billing"}],
            },
        ).json()["id"]
        response = client.post(
            f"/api/v1/projects/{slug}/decision-services/{service}/runs",
            json={"content": "billing help"},
            headers={"X-Correlation-ID": "corr-test-429"},
        )
        assert response.status_code == 429
        assert response.headers.get("X-Correlation-ID") == "corr-test-429"
        body = response.json()
        assert body["kind"] == "rate_limit"
        assert "sk-123" not in response.text
        assert client.get(f"/api/v1/projects/{slug}/runs").json() == []
        usage = client.get(f"/api/v1/projects/{slug}/providers/usage").json()
        assert len(usage) == 1
        assert usage[0]["provider"] == "glm"
        assert usage[0]["model"] == "glm-5.1"
        assert usage[0]["errors"] == 1
        assert usage[0]["calls"] == 0


def _ontology_fixture() -> Any:
    return OntologyVersion(
        classifier_id=__import__("uuid").uuid4(),
        version_number=1,
        classes=(OntologyClass(canonical_name="billing", display_name="Billing"),),
        created_by="t",
    )


@pytest.mark.parametrize("name", ["jev", "laya"])
def test_real_adapters_keep_two_model_success_and_failure_usage_separate(database_url, name):
    """Synthetic wire responses prove attribution only, not model quality."""
    import json

    import httpx
    from openclass_provider_jev import JevDecisionProvider
    from openclass_provider_laya import LayaDecisionProvider
    from pydantic import SecretStr

    key = "synthetic-attribution-credential"
    slug = service = ""
    expected = {}
    for suffix in ("a", "b"):
        configured = f"typesafe-ai/jev-alias-{suffix}" if name == "jev" else f"laya-alias-{suffix}"
        actual = f"typesafe-ai/jev-actual-{suffix}" if name == "jev" else f"laya-actual-{suffix}"
        calls = 0

        def handle(request, actual_model=actual):
            nonlocal calls
            calls += 1
            if calls == 2:
                return httpx.Response(500, text=key)
            criteria = json.loads(request.content)["questions"]["classification"]["criteria"]
            return httpx.Response(
                200,
                json={
                    "model": actual_model,
                    "answers": {
                        "classification": {
                            "type": "choice",
                            "choice": "billing",
                            "confidence": 0.95,
                            "probabilities": {
                                item: 0.95 if item == "billing" else 0.05 for item in criteria
                            },
                        }
                    },
                    "usage": {"input_tokens": 10, "output_tokens": 2},
                },
            )

        adapter = (
            JevDecisionProvider(
                api_key=SecretStr(key),
                base_url="https://api.typesafe.ai",
                model=configured,
                transport=httpx.MockTransport(handle),
            )
            if name == "jev"
            else LayaDecisionProvider(model=configured, transport=httpx.MockTransport(handle))
        )
        settings = Settings(database_url=database_url, decision_provider="mock")
        with TestClient(create_app(settings, provider=adapter)) as client:
            if not slug:
                slug = _make_project(client)
                service = _make_service(client, slug)
            path = f"/api/v1/projects/{slug}/decision-services/{service}/runs"
            success = client.post(path, json={"content": f"billing {suffix}"})
            assert success.status_code == 201, success.text
            assert success.json()[0]["model"] == actual
            failure = client.post(
                path,
                json={"content": "billing failure"},
                headers={"X-Correlation-ID": f"attribution-{suffix}"},
            )
            assert failure.status_code == 502, failure.text
            assert failure.headers["X-Correlation-ID"] == f"attribution-{suffix}"
            expected[actual] = (1, 0)
            expected[configured] = (0, 1)
            usage = client.get(f"/api/v1/projects/{slug}/providers/usage").json()
            assert {row["model"]: (row["calls"], row["errors"]) for row in usage} == expected
            assert {row["provider"] for row in usage} == {name}
            assert len(client.get(f"/api/v1/projects/{slug}/runs").json()) == len(expected) // 2
            audits = client.get(f"/api/v1/projects/{slug}/audit").json()
            failures = [
                entry for entry in audits if entry["event_type"] == "decision.provider_failed"
            ]
            assert {entry["payload"]["model"] for entry in failures} == {
                model for model, counts in expected.items() if counts == (0, 1)
            }
            assert key not in json.dumps(usage) + json.dumps(audits) + failure.text
