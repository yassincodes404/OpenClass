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

from tests.conftest import database_url  # noqa: F401


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


def _ontology_fixture() -> Any:
    return OntologyVersion(
        classifier_id=__import__("uuid").uuid4(),
        version_number=1,
        classes=(OntologyClass(canonical_name="billing", display_name="Billing"),),
        created_by="t",
    )
