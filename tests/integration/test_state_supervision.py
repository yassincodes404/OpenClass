"""Real HTTP service flow, synthetic provider transports, immutable snapshots."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from openclass_core.models import ChoiceRequest, ChoiceResult
from openclass_core.supervision import (
    InferenceProvenance,
    OperatingProfile,
    ProvenancedChoiceResult,
)
from openclass_provider_glm.gateway import GatewayDecisionProvider
from openclass_provider_jev import JevDecisionProvider
from openclass_provider_laya import LayaDecisionProvider
from openclass_server.main import create_app
from openclass_server.settings import Settings
from pydantic import SecretStr


@pytest.mark.parametrize("provider_kind", ["jev", "laya", "gateway"])
@pytest.mark.parametrize("upstream_simulation", [False, True])
def test_calibrated_http_continuation_requires_adapter_inference_provenance(
    database_url,
    provider_kind,
    upstream_simulation,
):
    metadata = {
        "simulated": upstream_simulation,
        "real_inference": not upstream_simulation,
        "calibration_status": "calibrated",
        "inference_provenance": {"execution_mode": "api", "simulated": False},
    }

    def handler(request):
        if provider_kind == "gateway":
            body = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "probabilities": {"billing": 0.9, "UNKNOWN": 0.1},
                                }
                            )
                        }
                    }
                ]
            }
        else:
            body = {
                "model": "jev" if provider_kind == "jev" else "laya-fixture",
                "answers": {
                    "classification": {
                        "type": "choice",
                        "choice": "billing",
                        "confidence": 0.9,
                        "probabilities": {"billing": 0.9, "OPENCLASS_UNKNOWN": 0.1},
                    }
                },
            }
        return httpx.Response(200, json={**body, "provider_metadata": metadata})

    wire = httpx.MockTransport(handler)
    if provider_kind == "jev":
        provider = JevDecisionProvider(
            api_key=SecretStr("synthetic-key"),
            base_url="https://api.typesafe.ai",
            model="jev",
            transport=wire,
        )
    elif provider_kind == "laya":
        provider = LayaDecisionProvider(transport=wire)
    else:
        provider = GatewayDecisionProvider(
            api_key=SecretStr("synthetic-key"),
            base_url="https://example.test",
            model="fixture-model",
            transport=wire,
        )
    runtime = config()
    runtime["operating_profile"] = {
        "calibration_status": "calibrated",
        "measured_max_choices": 3,
        "validation_artifact_hash": "synthetic-fixture-not-empirical",
    }
    with TestClient(create_app(Settings(database_url=database_url), provider=provider)) as client:
        slug, service = setup(client, runtime)
        event = client.post(
            f"/api/v1/projects/{slug}/events",
            json={
                "content": "billing",
                "metadata": {"blocked": False},
            },
        ).json()
        response = client.post(
            f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
            json={"raw_event_ids": [event["id"]]},
        )
        assert response.status_code == 201, response.text
        run = response.json()[0]
        assert run["supervision_outcome"] == ("REVIEW" if upstream_simulation else "TRUSTED")
        assert run["real_inference"] is not upstream_simulation
        provenance = run["steps"][0]["inference_provenance"]
        assert (provenance is None) is upstream_simulation
        if not upstream_simulation:
            assert provenance["simulated"] is False
            assert provenance["execution_mode"] == ("api" if provider_kind == "jev" else "daemon")


def config():
    return {
        "state_schema": {
            "id": "customer_state",
            "version": 1,
            "features": [
                {"id": "blocked", "kind": "boolean", "sensor_field": "blocked"},
                {
                    "id": "comment",
                    "kind": "string",
                    "sensor_field": "comment",
                    "required": False,
                    "nullable": True,
                },
            ],
        },
        "node_preconditions": {"default": [{"field": "blocked", "equals": False}]},
    }


def setup(client, runtime_config=None):
    project = client.post("/api/v1/projects", json={"name": "State proof"}).json()
    service = client.post(
        f"/api/v1/projects/{project['slug']}/decision-services",
        json={
            "name": "Bounded routing",
            "instructions": "Classify billing requests.",
            "choices": [{"key": "BILLING", "label": "Billing"}],
            "runtime_config": runtime_config or config(),
        },
    )
    assert service.status_code == 201, service.text
    return project["slug"], service.json()


@pytest.mark.parametrize("provider_kind", ["jev", "laya", "gateway"])
def test_http_metadata_controls_preconditions_and_actual_wire_context(database_url, provider_kind):
    captured = []

    def transport(request):
        captured.append(json.loads(request.content))
        if provider_kind == "gateway":
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"probabilities": {"billing": 0.9, "UNKNOWN": 0.1}}
                                )
                            }
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "model": "jev" if provider_kind == "jev" else "laya-test",
                "answers": {
                    "classification": {
                        "type": "choice",
                        "choice": "billing",
                        "confidence": 0.9,
                        "probabilities": {"billing": 0.9, "OPENCLASS_UNKNOWN": 0.1},
                    }
                },
            },
        )

    wire = httpx.MockTransport(transport)
    if provider_kind == "jev":
        provider = JevDecisionProvider(
            api_key=SecretStr("synthetic-key"),
            base_url="https://api.typesafe.ai",
            model="jev",
            transport=wire,
        )
    elif provider_kind == "laya":
        provider = LayaDecisionProvider(transport=wire)
    else:
        provider = GatewayDecisionProvider(
            api_key=SecretStr("synthetic-key"),
            base_url="https://example.test",
            model="fixture-model",
            transport=wire,
        )
    with TestClient(create_app(Settings(database_url=database_url), provider=provider)) as client:
        slug, service = setup(client)
        prefix = f"/api/v1/projects/{slug}"
        raw = {
            "content": "billing please",
            "metadata": {
                "blocked": False,
                "comment": None,
                "approved_by": "forged",
                "calibration_status": "calibrated",
                "secret_not_declared": "not-forwarded",
            },
        }
        event = client.post(f"{prefix}/events", json=raw).json()
        response = client.post(
            f"{prefix}/decision-services/{service['id']}/runs",
            json={"raw_event_ids": [event["id"]]},
        )
        assert response.status_code == 201, response.text
        run = response.json()[0]
        assert run["state_snapshot"]["facts"] == {"blocked": False, "comment": None}
        assert (
            run["supervision_outcome"] == "REVIEW"
        )  # wire metadata grants no calibration authority
        assert run["input_snapshot"]["metadata"] == raw["metadata"]
        assert run["state_snapshot"]["provenance"]["blocked"]["verified_ground_truth"] is False
        payload = json.dumps(captured[0])
        assert "untrusted_state_facts" in payload
        assert "not-forwarded" not in payload
        assert "forged" not in payload
        assert "blocked" in payload and "false" in payload and "null" in payload
        if provider_kind != "gateway":
            assert "blocked" not in captured[0]["questions"]["classification"]["instructions"]
        # One structured fact changes applicability before any second inference.
        changed = client.post(
            f"{prefix}/events", json={"content": "billing changed", "metadata": {"blocked": True}}
        ).json()
        rejected = client.post(
            f"{prefix}/decision-services/{service['id']}/runs",
            json={"raw_event_ids": [changed["id"]]},
        )
        assert rejected.status_code == 422, rejected.text
        assert rejected.json()["detail"]["code"] == "precondition_unsatisfied"
        assert len(captured) == 1
        assert len(client.get(f"{prefix}/runs").json()) == 1
        audit = client.get(f"{prefix}/audit").json()
        assert any(
            e["event_type"] == "decision_run.failed"
            and e["payload"].get("stage") == "state_compilation"
            for e in audit
        )


@pytest.mark.parametrize("name", ["jev", "laya", "renamed-provider"])
def test_identical_distribution_has_provider_neutral_runtime_policy(database_url, name):
    class Fixture:
        operating_profile = OperatingProfile(
            calibration_status="simulated", allow_simulated_continuation=True
        )

        async def choice(self, request: ChoiceRequest) -> ChoiceResult:
            return ProvenancedChoiceResult(
                inference_provenance=InferenceProvenance(execution_mode="mock", simulated=True),
                provider=name,
                model="synthetic-not-empirical",
                probabilities={"billing": 0.9},
                unknown_probability=0.1,
            )

    with TestClient(create_app(Settings(database_url=database_url), provider=Fixture())) as client:
        slug, service = setup(client)
        event = client.post(
            f"/api/v1/projects/{slug}/events",
            json={"content": "billing", "metadata": {"blocked": False}},
        ).json()
        result = client.post(
            f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
            json={"raw_event_ids": [event["id"]]},
        ).json()[0]
        assert result["supervision_outcome"] == "TRUSTED"
        assert "Simulated" in result["supervision_reason"]


def test_checkpoint_retains_captured_state_schema_profile_and_limits(database_url):
    class Fixture:
        operating_profile = OperatingProfile(
            calibration_status="simulated", allow_simulated_continuation=True
        )
        requests = []

        async def choice(self, request):
            self.requests.append(request)
            name = request.ontology.classes[0].canonical_name
            return ProvenancedChoiceResult(
                inference_provenance=InferenceProvenance(execution_mode="mock", simulated=True),
                provider="synthetic",
                model="fixture",
                probabilities={name: 0.9},
                unknown_probability=0.1,
            )

    provider = Fixture()
    settings = Settings(database_url=database_url)
    with TestClient(create_app(settings, provider=provider)) as client:
        slug, service = setup(client)
        runtime = config()
        runtime["node_preconditions"] = {"downstream": [{"field": "blocked", "equals": False}]}
        update = client.patch(
            f"/api/v1/projects/{slug}/decision-services/{service['id']}",
            json={
                "runtime_config": runtime,
                "nodes": [
                    {
                        "name": "root",
                        "instructions": "Route",
                        "pause_on_review": True,
                        "choices": [
                            {"key": "BILLING", "label": "Billing", "target_node_name": "downstream"}
                        ],
                    },
                    {
                        "name": "downstream",
                        "instructions": "Resolve",
                        "choices": [{"key": "DONE", "label": "Done"}],
                    },
                ],
            },
        )
        assert update.status_code == 200, update.text
        event = client.post(
            f"/api/v1/projects/{slug}/events",
            json={"content": "billing", "metadata": {"blocked": False}},
        ).json()
        run = client.post(
            f"/api/v1/projects/{slug}/decision-services/{service['id']}/runs",
            json={"raw_event_ids": [event["id"]]},
        ).json()[0]
        assert run["run_status"] == "paused"
        # Change active representation, policy and provider configuration after pause.
        client.patch(
            f"/api/v1/projects/{slug}/decision-services/{service['id']}",
            json={
                "runtime_config": {
                    "budgets": {"max_total_bytes": 1},
                    "operating_profile": {"calibration_status": "unknown"},
                }
            },
        )
    provider.operating_profile = OperatingProfile()
    # Restart with a new application and repository instance against the same database.
    with TestClient(create_app(settings, provider=provider)) as client:
        response = client.post(
            f"/api/v1/projects/{slug}/runs/{run['id']}/resume", json={"approved_choice": "BILLING"}
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "completed"
        current = client.get(f"/api/v1/projects/{slug}/runs/{run['id']}").json()
        assert current["state_snapshot"]["facts"] == {"blocked": False}
        assert (
            current["state_snapshot"]["runtime_config"]["operating_profile"]["calibration_status"]
            == "simulated"
        )
        assert provider.requests[-1].observation.metadata["state_facts"] == {"blocked": False}
