"""Reviews survive restarts; confident mistakes are flagged without rewriting history."""

from fastapi.testclient import TestClient
from openclass_core.models import (
    ChoiceRequest,
    ChoiceResult,
    ReviewRecommendation,
    ReviewRequest,
    ReviewResult,
    SupervisorFinding,
)
from openclass_server.main import create_app
from openclass_server.settings import Settings


def test_reviews_survive_restart(database_url: str, classifier_body: dict) -> None:
    settings = Settings(database_url=database_url)
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/v1/classifiers", json=classifier_body)
        assert created.status_code == 201
        base = f"/api/v1/classifiers/{created.json()['id']}"
        known = client.post(f"{base}/classify", json={"observation": "I was charged twice"}).json()
        unknown = client.post(f"{base}/classify", json={"observation": "Cancel my plan"}).json()
        known_review = client.post(f"{base}/runs/{known['id']}/reviews").json()
        unknown_review = client.post(f"{base}/runs/{unknown['id']}/reviews").json()
    with TestClient(create_app(settings)) as client:
        reviews = client.get(f"{base}/reviews").json()
        assert {review["id"] for review in reviews} == {known_review["id"], unknown_review["id"]}
        by_run = {review["classification_run_id"]: review for review in reviews}
        assert by_run[known["id"]]["result"]["finding"] == "no_issue"
        assert by_run[unknown["id"]]["result"]["finding"] == "possible_missing_class"
        # Restarting did not touch the reviewed history or the ontology.
        assert client.get(f"{base}/runs/{known['id']}").json()["result"]["selected_class"] == (
            "billing"
        )
        assert len(client.get(f"{base}/ontology/versions").json()) == 1
        assert len(client.get(f"{base}/unknowns").json()) == 1


class ConfidentMistakeProvider:
    """Stub decision layer: confidently wrong on a known-looking input."""

    async def choice(self, request: ChoiceRequest) -> ChoiceResult:
        return ChoiceResult(
            provider="stub",
            model="confident-mistake",
            probabilities={"phone": 0.93, "laptop": 0.03, "tablet": 0.02},
            unknown_probability=0.02,
        )


class MisclassificationSupervisor:
    """Stub supervisor: disagrees with a confident decision — the core OC-016 claim."""

    async def review(self, request: ReviewRequest) -> ReviewResult:
        return ReviewResult(
            provider="stub-supervisor",
            model="audit-stub",
            finding=SupervisorFinding.POSSIBLE_MISCLASSIFICATION,
            confidence=0.87,
            recommendation=ReviewRecommendation.CHECK_CLASSIFICATION,
            rationale=(
                "The observation describes a tablet; phone was selected with high confidence."
            ),
            suspected_class="tablet",
        )


def test_confident_mistake_is_flagged_without_rewriting_history(database_url: str) -> None:
    body = {
        "slug": "device-type",
        "name": "Device type",
        "classes": [
            {"canonical_name": "phone", "display_name": "Phone"},
            {"canonical_name": "laptop", "display_name": "Laptop"},
            {"canonical_name": "tablet", "display_name": "Tablet"},
        ],
    }
    app = create_app(
        Settings(database_url=database_url),
        ConfidentMistakeProvider(),
        MisclassificationSupervisor(),
    )
    with TestClient(app) as client:
        created = client.post("/api/v1/classifiers", json=body)
        assert created.status_code == 201
        base = f"/api/v1/classifiers/{created.json()['id']}"
        result = client.post(f"{base}/classify", json={"observation": "iPad Pro tablet"}).json()
        # UNKNOWN detection sees a confident known result; it cannot audit correctness.
        assert result["selected_class"] == "phone"
        assert result["novelty"]["state"] == "known"
        review = client.post(f"{base}/runs/{result['id']}/reviews").json()
        assert review["result"]["finding"] == "possible_misclassification"
        assert review["result"]["suspected_class"] == "tablet"
        assert review["result"]["recommendation"] == "check_classification"
        # The historical run, the ontology and the unknown pool remain exactly as before.
        assert (
            client.get(f"{base}/runs/{result['id']}").json()["result"]["selected_class"] == "phone"
        )
        versions = client.get(f"{base}/ontology/versions").json()
        assert [version["version_number"] for version in versions] == [1]
        assert {c["canonical_name"] for c in versions[0]["classes"]} == {
            "phone",
            "laptop",
            "tablet",
        }
        assert client.get(f"{base}/unknowns").json() == []
        assert len(client.get(f"{base}/reviews").json()) == 1
