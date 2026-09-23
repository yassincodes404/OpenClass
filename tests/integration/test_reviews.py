"""Supervisor reviews over HTTP: advisory, isolated, safe on provider failure."""

from uuid import uuid4

from fastapi.testclient import TestClient
from openclass_core.models import ReviewRequest, ReviewResult
from openclass_core.providers import ProviderError, SupervisorProvider
from openclass_server.main import create_app
from openclass_server.settings import EXPECTED_SCHEMA_REVISION, Settings


def test_review_lifecycle_persists_advisory_findings(
    client: TestClient, classifier_body: dict
) -> None:
    assert client.get("/health/ready").json()["schema"] == EXPECTED_SCHEMA_REVISION
    created = client.post("/api/v1/classifiers", json=classifier_body)
    assert created.status_code == 201
    base = f"/api/v1/classifiers/{created.json()['id']}"
    known = client.post(f"{base}/classify", json={"observation": "I was charged twice"}).json()
    unknown = client.post(f"{base}/classify", json={"observation": "Cancel my plan"}).json()

    runs = client.get(f"{base}/runs").json()
    assert len(runs) == 2
    assert {record["result"]["id"] for record in runs} == {known["id"], unknown["id"]}
    assert {record["observation"]["content"] for record in runs} == {
        "I was charged twice",
        "Cancel my plan",
    }
    single = client.get(f"{base}/runs/{unknown['id']}").json()
    assert single["result"]["selected_class"] is None
    assert single["observation"]["id"] == single["result"]["observation_id"]
    assert client.get(f"{base}/runs/{uuid4()}").status_code == 404

    known_review = client.post(f"{base}/runs/{known['id']}/reviews")
    assert known_review.status_code == 201
    assert known_review.json()["result"]["finding"] == "no_issue"
    assert known_review.json()["classification_run_id"] == known["id"]
    assert known_review.json()["trigger"] == "manual"
    unknown_review = client.post(f"{base}/runs/{unknown['id']}/reviews").json()
    assert unknown_review["result"]["finding"] == "possible_missing_class"
    assert unknown_review["result"]["recommendation"] == "collect_more_evidence"

    reviews = client.get(f"{base}/reviews").json()
    assert {review["classification_run_id"] for review in reviews} == {known["id"], unknown["id"]}

    events = [row["event"] for row in client.get(f"{base}/events?limit=50").json()]
    review_events = [event for event in events if event["type"] == "supervisor.review_completed"]
    assert {event["payload"]["run_id"] for event in review_events} == {known["id"], unknown["id"]}
    assert all(
        set(event["payload"]) == {"review_id", "run_id", "finding"} for event in review_events
    )

    # Reviews are advisory: the reviewed run and the ontology remain untouched.
    assert client.get(f"{base}/runs/{known['id']}").json()["result"]["selected_class"] == "billing"
    assert len(client.get(f"{base}/ontology/versions").json()) == 1


def test_same_run_can_be_reviewed_multiple_times(client: TestClient, classifier_body: dict) -> None:
    created = client.post("/api/v1/classifiers", json=classifier_body)
    base = f"/api/v1/classifiers/{created.json()['id']}"
    run = client.post(f"{base}/classify", json={"observation": "charged twice"}).json()
    first = client.post(f"{base}/runs/{run['id']}/reviews")
    second = client.post(f"{base}/runs/{run['id']}/reviews")
    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["id"] != second.json()["id"]
    assert len(client.get(f"{base}/reviews").json()) == 2


def test_reviews_are_scoped_to_their_classifier(client: TestClient, classifier_body: dict) -> None:
    created = client.post("/api/v1/classifiers", json=classifier_body)
    base = f"/api/v1/classifiers/{created.json()['id']}"
    run = client.post(f"{base}/classify", json={"observation": "charged twice"}).json()
    other = {**classifier_body, "slug": "other-intent", "name": "Other"}
    second = client.post("/api/v1/classifiers", json=other)
    other_base = f"/api/v1/classifiers/{second.json()['id']}"
    assert client.post(f"{other_base}/runs/{run['id']}/reviews").status_code == 404
    assert client.get(f"{other_base}/runs/{run['id']}").status_code == 404
    assert client.get(f"{other_base}/reviews").json() == []
    assert client.get(f"{other_base}/runs").json() == []


class LeakingSupervisor:
    async def review(self, request: ReviewRequest) -> ReviewResult:
        raise ProviderError("upstream refused with key sk-live-abcdef")


def test_supervisor_failures_are_safe_and_persist_nothing(
    database_url: str, classifier_body: dict
) -> None:
    app = create_app(Settings(database_url=database_url), supervisor_provider=LeakingSupervisor())
    with TestClient(app) as client:
        created = client.post("/api/v1/classifiers", json=classifier_body)
        base = f"/api/v1/classifiers/{created.json()['id']}"
        run = client.post(f"{base}/classify", json={"observation": "charged twice"}).json()
        response = client.post(f"{base}/runs/{run['id']}/reviews")
        assert response.status_code == 502
        assert response.json() == {"detail": "Supervisor provider failed"}
        assert "sk-live" not in response.text
        assert client.get(f"{base}/reviews").json() == []
        events = client.get(f"{base}/events").json()
        assert all(row["event"]["type"] != "supervisor.review_completed" for row in events)


def test_openapi_documents_reviews_without_unguarded_actions(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "SupervisorReview" in schema["components"]["schemas"]
    assert "ClassificationRecord" in schema["components"]["schemas"]
    assert not any(
        keyword in path for path in schema["paths"] for keyword in ("promote", "apply", "auto")
    )


def test_supervisor_provider_type_is_satisfiable_by_stubs() -> None:
    # The port is structural; test doubles and future adapters implement review().
    from openclass_provider_mock import MockSupervisorProvider

    provider: SupervisorProvider = MockSupervisorProvider()
    assert hasattr(provider, "review")
