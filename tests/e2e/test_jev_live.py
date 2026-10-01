"""One explicitly enabled remote call through the real API/service/repository stack."""

import os

import pytest
from fastapi.testclient import TestClient
from openclass_server.main import create_app
from openclass_server.settings import Settings


@pytest.mark.live
@pytest.mark.skipif(os.getenv("OPENCLASS_RUN_LIVE_TESTS") != "1", reason="Live inference is opt-in")
def test_jev_live_stack(database_url, classifier_body) -> None:
    settings = Settings(database_url=database_url, decision_provider="jev", provider_max_retries=0)
    with TestClient(create_app(settings)) as client:
        client.post("/api/v1/classifiers", json=classifier_body).raise_for_status()
        base = "/api/v1/classifiers/support-intent"
        response = client.post(f"{base}/classify", json={"observation": "I was charged twice"})
        assert response.status_code == 200, (
            "Live provider failed; inspect sanitized provider.error event"
        )
        result = response.json()
        assert result["decision"]["provider"] == "jev"
        assert result["decision"]["provider_metadata"]["simulated"] is False
        assert client.get(f"{base}/runs/{result['id']}").json()["result"] == result
        assert len(client.get(f"{base}/ontology/versions").json()) == 1
        unknowns = client.get(f"{base}/unknowns").json()
        assert len(unknowns) == (1 if result["selected_class"] is None else 0)
        events = client.get(f"{base}/events").json()
        assert any(e["event"]["type"] == "classification.completed" for e in events)
