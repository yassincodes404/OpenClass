from fastapi.testclient import TestClient
from openclass_core.models import ChoiceRequest, ChoiceResult
from openclass_core.providers import ProviderError
from openclass_server.main import create_app
from openclass_server.settings import Settings


def test_readiness_and_validation(client: TestClient, classifier_body: dict) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/health/ready").json()["status"] == "ready"
    assert client.get("/api/v1/classifiers/missing").status_code == 404
    assert client.post("/api/v1/classifiers", json=classifier_body).status_code == 201
    assert client.post("/api/v1/classifiers", json=classifier_body).status_code == 409
    assert (
        client.post(
            "/api/v1/classifiers/support-intent/classify", json={"observation": " "}
        ).status_code
        == 422
    )
    assert client.get("/api/v1/classifiers/support-intent/unknowns?limit=1000").status_code == 422
    classifier_body["slug"] = "another"
    classifier_body["classes"][1]["aliases"] = ["charged"]
    assert client.post("/api/v1/classifiers", json=classifier_body).status_code == 422


def test_openapi_documents_result_and_has_no_unguarded_promotion(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "ClassificationResult" in schema["components"]["schemas"]
    assert not any("promote" in path for path in schema["paths"])


def test_unmigrated_database_is_not_ready(tmp_path) -> None:
    with TestClient(
        create_app(Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}"))
    ) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health/ready").status_code == 503
        assert client.get("/api/v1/classifiers").json() == {"detail": "Database unavailable"}


class BrokenProvider:
    async def choice(self, request: ChoiceRequest) -> ChoiceResult:
        raise ProviderError("sensitive upstream detail")


class WrongLabelsProvider:
    async def choice(self, request: ChoiceRequest) -> ChoiceResult:
        return ChoiceResult(
            provider="invalid",
            model="invalid",
            probabilities={"invented": 0.9},
            unknown_probability=0.1,
        )


def test_provider_errors_are_safe_and_do_not_persist_runs(
    database_url: str, classifier_body: dict
) -> None:
    for index, provider in enumerate((BrokenProvider(), WrongLabelsProvider())):
        classifier_body["slug"] = f"test-{index}"
        with TestClient(create_app(Settings(database_url=database_url), provider)) as client:
            client.post("/api/v1/classifiers", json=classifier_body).raise_for_status()
            response = client.post(
                f"/api/v1/classifiers/test-{index}/classify", json={"observation": "charged"}
            )
            assert response.status_code == 502
            assert "sensitive" not in response.text
            events = client.get(f"/api/v1/classifiers/test-{index}/events").json()
            assert len(events) == 1  # Initial ontology only; no fabricated completed run.
