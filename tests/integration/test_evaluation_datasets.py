"""Phase 12 evaluation datasets: provenance, validation, seal immutability."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from openclass_core.evaluation import (
    ExampleDraft,
    slice_coverage,
)


def _make_project(client: TestClient) -> str:
    return client.post("/api/v1/projects", json={"name": "Eval Co"}).json()["slug"]


def _make_dataset(client: TestClient, slug: str, name: str = "Gold v1") -> str:
    created = client.post(f"/api/v1/projects/{slug}/eval-datasets", json={"name": name})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _example(text: str, label: str = "BILLING", **overrides: str) -> dict:
    payload = {
        "text": text,
        "label": label,
        "source": "human",
        "annotator": "annotator@acme.test",
        "rationale": "verified from ticket history",
    }
    payload.update(overrides)
    return payload


def _make_service(client: TestClient, slug: str) -> None:
    client.post(
        f"/api/v1/projects/{slug}/decision-services",
        json={
            "name": "Router",
            "instructions": "Route the request.",
            "choices": [
                {"key": "BILLING", "label": "Billing"},
                {"key": "REFUND", "label": "Refund"},
            ],
        },
    )


def test_prediction_source_is_rejected(mock_client: TestClient):
    draft = ExampleDraft(text="hello", label="BILLING", source="prediction", annotator="someone")
    with pytest.raises(ValueError, match="predictions cannot be ground truth"):
        draft.to_example(("BILLING", "UNKNOWN"))


def test_label_must_be_existing_class_or_unknown(mock_client: TestClient):
    draft = ExampleDraft(text="hello", label="TELEPATHY", source="human", annotator="someone")
    with pytest.raises(ValueError, match="not an existing class"):
        draft.to_example(("BILLING", "UNKNOWN"))
    ok = draft.model_copy(update={"label": "UNKNOWN"})
    assert ok.to_example(("BILLING", "UNKNOWN")).label == "UNKNOWN"


def test_add_example_with_provenance_and_coverage(mock_client: TestClient):
    slug = _make_project(mock_client)
    _make_service(mock_client, slug)
    dataset = _make_dataset(mock_client, slug)
    added = client_post_example(
        mock_client, slug, dataset, _example("billing question", slice_tag="historical")
    )
    assert added.status_code == 201, added.text
    detail = mock_client.get(f"/api/v1/projects/{slug}/eval-datasets/{dataset}").json()
    assert detail["examples"][0]["annotator"] == "annotator@acme.test"
    assert detail["coverage"]["historical"] == 1


def client_post_example(client: TestClient, slug: str, dataset: str, payload: dict):
    return client.post(f"/api/v1/projects/{slug}/eval-datasets/{dataset}/examples", json=payload)


def test_api_rejects_prediction_source(mock_client: TestClient):
    slug = _make_project(mock_client)
    _make_service(mock_client, slug)
    dataset = _make_dataset(mock_client, slug)
    response = client_post_example(mock_client, slug, dataset, _example("x", source="prediction"))
    assert response.status_code == 400
    assert "predictions cannot be ground truth" in response.json()["detail"]


def test_duplicate_text_flagged(mock_client: TestClient):
    slug = _make_project(mock_client)
    _make_service(mock_client, slug)
    dataset = _make_dataset(mock_client, slug)
    assert client_post_example(mock_client, slug, dataset, _example("same text")).status_code == 201
    duplicate = client_post_example(mock_client, slug, dataset, _example("same text"))
    assert duplicate.status_code == 409


def test_seal_makes_dataset_immutable(mock_client: TestClient):
    slug = _make_project(mock_client)
    _make_service(mock_client, slug)
    dataset = _make_dataset(mock_client, slug)
    client_post_example(mock_client, slug, dataset, _example("to be frozen"))
    seal = mock_client.post(f"/api/v1/projects/{slug}/eval-datasets/{dataset}/seal")
    assert seal.status_code == 200
    blocked = client_post_example(mock_client, slug, dataset, _example("late addition"))
    assert blocked.status_code == 409
    assert "sealed" in blocked.json()["detail"]
    reseal = mock_client.post(f"/api/v1/projects/{slug}/eval-datasets/{dataset}/seal")
    assert reseal.status_code == 409


def test_slice_coverage_shape():
    coverage = slice_coverage([])
    assert set(coverage) == {"historical", "recent", "rare", "hard", "unknown", "adversarial"}


def test_cross_dataset_isolation(mock_client: TestClient):
    slug_a = _make_project(mock_client)
    slug_b = _make_project(mock_client)
    dataset_a = _make_dataset(mock_client, slug_a)
    listing_b = mock_client.get(f"/api/v1/projects/{slug_b}/eval-datasets").json()
    assert listing_b == []
    detail_b = mock_client.get(f"/api/v1/projects/{slug_b}/eval-datasets/{dataset_a}")
    assert detail_b.status_code == 404
