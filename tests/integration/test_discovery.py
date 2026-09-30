from copy import deepcopy

from fastapi.testclient import TestClient


def test_unknown_discovery_candidate_rejection_is_audited_without_activation(
    mock_client: TestClient, classifier_body: dict
) -> None:
    body = deepcopy(classifier_body)
    body["slug"] = "device-type"
    body["classes"] = [
        {"canonical_name": "phone", "display_name": "Phone"},
        {"canonical_name": "laptop", "display_name": "Laptop"},
    ]
    created = mock_client.post("/api/v1/classifiers", json=body)
    assert created.status_code == 201
    base = "/api/v1/classifiers/device-type"
    before = mock_client.get(f"{base}/ontology").json()
    for text in ("iPad Pro", "Samsung Galaxy Tab", "Lenovo Tab P12", "Pixel Tablet"):
        mock_client.post(f"{base}/classify", json={"observation": text}).json()
    unknowns = mock_client.get(f"{base}/unknowns").json()
    assert len(unknowns) == 4
    candidate_response = mock_client.post(
        f"{base}/discoveries", json={"unknown_ids": [u["id"] for u in unknowns[:3]]}
    )
    assert candidate_response.status_code == 201
    candidate = candidate_response.json()
    assert candidate["canonical_name"] == "tablet"
    assert candidate["status"] == "candidate"
    assert mock_client.get(f"{base}/ontology").json() == before
    evaluated = mock_client.post(f"{base}/candidates/{candidate['id']}/evaluate")
    assert evaluated.status_code == 409
    assert "Verified replay" in evaluated.json()["detail"]
    assert mock_client.post(f"{base}/candidates/{candidate['id']}/approve").status_code == 409
    rejected = mock_client.post(
        f"{base}/candidates/{candidate['id']}/reject",
        json={"reason": "  Evidence may describe multiple device types.  "},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "Evidence may describe multiple device types."
    assert (
        mock_client.post(
            f"{base}/candidates/{candidate['id']}/reject", json={"reason": "again"}
        ).status_code
        == 409
    )
    assert mock_client.post(f"{base}/candidates/{candidate['id']}/approve").status_code == 409
    assert mock_client.get(f"{base}/ontology").json() == before
    versions = mock_client.get(f"{base}/ontology/versions").json()
    assert versions == [before]
    assert mock_client.get(f"{base}/candidates").json()[0]["status"] == "rejected"
    events = mock_client.get(f"{base}/events").json()
    assert any(row["event"]["type"] == "candidate.rejected" for row in events)


def test_candidate_rejection_requires_reason_and_classifier_scope(
    mock_client: TestClient, classifier_body: dict
) -> None:
    body = deepcopy(classifier_body)
    body["slug"] = "scoped-devices"
    mock_client.post("/api/v1/classifiers", json=body)
    base = "/api/v1/classifiers/scoped-devices"
    for content in ("tablet one", "tablet two", "tablet three"):
        mock_client.post(f"{base}/classify", json={"observation": content})
    unknowns = mock_client.get(f"{base}/unknowns").json()
    candidate = mock_client.post(
        f"{base}/discoveries", json={"unknown_ids": [item["id"] for item in unknowns]}
    ).json()
    path = f"{base}/candidates/{candidate['id']}/reject"
    assert mock_client.post(path, json={"reason": "  "}).status_code == 422
    assert mock_client.post(path, json={"reason": "x" * 1001}).status_code == 422
    assert (
        mock_client.post(
            f"/api/v1/classifiers/other/candidates/{candidate['id']}/reject",
            json={"reason": "wrong scope"},
        ).status_code
        == 404
    )
    assert mock_client.get(f"{base}/candidates").json()[0]["status"] == "candidate"


def test_discovery_requires_three_distinct_unknowns(
    client: TestClient, classifier_body: dict
) -> None:
    created = client.post("/api/v1/classifiers", json=classifier_body).json()
    base = f"/api/v1/classifiers/{created['slug']}"
    client.post(f"{base}/classify", json={"observation": "tablet"})
    unknown = client.get(f"{base}/unknowns").json()[0]["id"]
    response = client.post(f"{base}/discoveries", json={"unknown_ids": [unknown, unknown, unknown]})
    assert response.status_code == 409
