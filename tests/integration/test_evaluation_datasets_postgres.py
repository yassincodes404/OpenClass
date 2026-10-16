"""PostgreSQL proof for evaluation dataset sealing.

decision_runs.payload is a plain JSON column; PostgreSQL has no equality
operator for json, so holdout-leakage screening must not run DISTINCT or
GROUP BY over the raw payload. SQLite stores JSON as text and cannot catch
this regression, which is why this proof requires a real database.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from openclass_core.models import ChoiceResult
from openclass_server.main import create_app
from openclass_server.settings import Settings

pytestmark = pytest.mark.postgres


class MockForcedUnknownProvider:
    async def choice(self, request) -> ChoiceResult:
        return ChoiceResult(
            provider="mock-forced",
            model="forced-v1",
            probabilities={"support": 0.1},
            unknown_probability=0.9,
        )


def test_seal_screens_holdout_against_json_run_payloads(postgres_url: str) -> None:
    with TestClient(
        create_app(Settings(database_url=postgres_url), provider=MockForcedUnknownProvider())
    ) as client:
        project = client.post(
            "/api/v1/projects", json={"name": f"Eval Seal {uuid.uuid4().hex[:8]}"}
        )
        assert project.status_code == 201
        slug = project.json()["slug"]

        event = client.post(
            f"/api/v1/projects/{slug}/events",
            json={"content": "Billing portal double charged my card", "source_type": "text"},
        )
        assert event.status_code == 201

        service = client.post(
            f"/api/v1/projects/{slug}/decision-services",
            json={
                "name": "Router",
                "instructions": "Route the request.",
                "choices": [{"key": "BILLING", "label": "Billing"}],
            },
        )
        assert service.status_code == 201

        # Persist a real decision run whose JSON payload the seal screen reads.
        run = client.post(
            f"/api/v1/projects/{slug}/decision-services/{service.json()['id']}/runs",
            json={"raw_event_ids": [event.json()["id"]]},
        )
        assert run.status_code == 201, run.text

        dataset = client.post(f"/api/v1/projects/{slug}/eval-datasets", json={"name": "Gold v1"})
        assert dataset.status_code == 201
        dataset_id = dataset.json()["id"]

        # Holdout-leakage screening (which reads run payloads) only runs when an
        # example is marked verified_holdout; without it the PG-sensitive query
        # is never reached and this test would be vacuous.
        example = client.post(
            f"/api/v1/projects/{slug}/eval-datasets/{dataset_id}/examples",
            json={
                "text": "verified billing question from ticket history",
                "label": "BILLING",
                "source": "human",
                "source_type": "verified_holdout",
                "annotator": "annotator@acme.test",
                "rationale": "verified from ticket history",
            },
        )
        assert example.status_code == 201, example.text

        seal = client.post(f"/api/v1/projects/{slug}/eval-datasets/{dataset_id}/seal")
        assert seal.status_code == 200, seal.text
        assert seal.json()["sealed"] is True
        assert seal.json()["dataset_hash"]

        reseal = client.post(f"/api/v1/projects/{slug}/eval-datasets/{dataset_id}/seal")
        assert reseal.status_code == 409
