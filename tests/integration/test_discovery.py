from copy import deepcopy

import pytest
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


def test_discovery_resolves_requested_ids_beyond_first_200(
    mock_client: TestClient, classifier_body: dict, database_url: str
) -> None:
    import asyncio
    from uuid import UUID, uuid4

    import sqlalchemy as sa
    from openclass_core.models import UnknownEvent
    from openclass_server.persistence.tables import ObservationRow, RunRow, UnknownRow
    from sqlalchemy.ext.asyncio import create_async_engine

    mock_client.post("/api/v1/classifiers", json=classifier_body).raise_for_status()
    base = f"/api/v1/classifiers/{classifier_body['slug']}"
    for text in ("tablet one", "tablet two", "tablet three"):
        mock_client.post(f"{base}/classify", json={"observation": text}).raise_for_status()
    requested = mock_client.get(f"{base}/unknowns").json()
    selected_ids = [item["id"] for item in requested]
    template = UnknownEvent.model_validate(requested[0])

    async def seed_newer_unknowns():
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as connection:
                observations, runs, unknowns = [], [], []
                for index in range(201):
                    observation = template.observation.model_copy(update={"id": uuid4()})
                    result = template.classification.model_copy(
                        update={"id": uuid4(), "observation_id": observation.id}
                    )
                    # Legacy pagination orders by ID, not timestamp. Ensure all
                    # newer fixtures precede the requested historical IDs.
                    unknown = template.model_copy(
                        update={
                            "id": UUID(int=index + 1),
                            "observation": observation,
                            "classification": result,
                        }
                    )
                    observations.append(
                        {"id": str(observation.id), "payload": observation.model_dump(mode="json")}
                    )
                    runs.append(
                        {
                            "id": str(result.id),
                            "observation_id": str(observation.id),
                            "classifier_id": str(result.classifier_id),
                            "ontology_version_id": str(result.ontology_version_id),
                            "payload": result.model_dump(mode="json"),
                        }
                    )
                    unknowns.append(
                        {
                            "id": str(unknown.id),
                            "classifier_id": str(unknown.classifier_id),
                            "run_id": str(result.id),
                            "payload": unknown.model_dump(mode="json"),
                        }
                    )
                await connection.execute(sa.insert(ObservationRow), observations)
                await connection.execute(sa.insert(RunRow), runs)
                await connection.execute(sa.insert(UnknownRow), unknowns)
        finally:
            await engine.dispose()

    asyncio.run(seed_newer_unknowns())
    assert not set(selected_ids) & {
        item["id"] for item in mock_client.get(f"{base}/unknowns").json()
    }
    response = mock_client.post(f"{base}/discoveries", json={"unknown_ids": selected_ids})
    assert response.status_code == 201, response.text
    assert response.json()["evidence_ids"] == selected_ids
    assert response.json()["status"] == "candidate"


@pytest.mark.parametrize("invalid", ["missing", "known", "other_classifier"])
def test_discovery_evidence_lookup_fails_closed(
    mock_client: TestClient, classifier_body: dict, invalid: str
) -> None:
    from uuid import uuid4

    mock_client.post("/api/v1/classifiers", json=classifier_body).raise_for_status()
    base = f"/api/v1/classifiers/{classifier_body['slug']}"
    for text in ("tablet one", "tablet two", "tablet three"):
        mock_client.post(f"{base}/classify", json={"observation": text}).raise_for_status()
    ids = [item["id"] for item in mock_client.get(f"{base}/unknowns").json()]
    if invalid == "missing":
        replacement = str(uuid4())
    elif invalid == "known":
        known = mock_client.post(f"{base}/classify", json={"observation": "charged"}).json()
        assert known["selected_class"] == "billing"
        replacement = known["id"]
    else:
        other = {**classifier_body, "slug": "other-classifier"}
        mock_client.post("/api/v1/classifiers", json=other).raise_for_status()
        mock_client.post(
            "/api/v1/classifiers/other-classifier/classify", json={"observation": "tablet"}
        ).raise_for_status()
        replacement = mock_client.get("/api/v1/classifiers/other-classifier/unknowns").json()[0][
            "id"
        ]
    response = mock_client.post(
        f"{base}/discoveries", json={"unknown_ids": [*ids[:2], replacement]}
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Unknown evidence is not available for this classifier"
    assert mock_client.get(f"{base}/candidates").json() == []
