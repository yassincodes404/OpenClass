"""Genesis loop through public HTTP; full discovery/promotion is a later gate."""

from fastapi.testclient import TestClient
from openclass_server.main import create_app
from openclass_server.settings import Settings


def test_known_unknown_history_survives_restart(database_url: str, classifier_body: dict) -> None:
    settings = Settings(database_url=database_url)
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/v1/classifiers", json=classifier_body)
        assert created.status_code == 201
        classifier = created.json()
        base = f"/api/v1/classifiers/{classifier['id']}"
        ontology = client.get(f"{base}/ontology").json()
        known = client.post(f"{base}/classify", json={"observation": "I was charged twice"}).json()
        assert known["selected_class"] == "billing"
        assert known["novelty"]["state"] == "known"
        for observation in ("Cancel my plan", "Stop renewing my subscription", "End my membership"):
            result = client.post(f"{base}/classify", json={"observation": observation}).json()
            assert result["selected_class"] is None
            assert result["novelty"]["state"] == "likely_novel"
            assert result["ontology_version_id"] == ontology["id"]
    with TestClient(create_app(settings)) as client:
        unknowns = client.get(f"{base}/unknowns").json()
        assert len(unknowns) == 3
        assert {row["observation"]["content"] for row in unknowns} == {
            "Cancel my plan",
            "Stop renewing my subscription",
            "End my membership",
        }
        assert client.get(f"{base}/ontology").json() == ontology
        assert client.get(f"{base}/ontology/versions").json() == [ontology]
        first = client.get(f"{base}/events?limit=2").json()
        rest = client.get(f"{base}/events?after={first[-1]['sequence']}").json()
        assert len(first) + len(rest) == 8  # v1 + known + 3*(classification + unknown)
        assert first[-1]["sequence"] < rest[0]["sequence"]
