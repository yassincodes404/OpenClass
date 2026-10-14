"""End-to-end closed-loop evolution and opt-in live Vercel AI Gateway proof (OC-038 / OC-039)."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openclass_core.candidates import ClusterDiscoveryRequest
from openclass_core.models import (
    ChoiceRequest,
    ClassificationResult,
    NoveltyAssessment,
    NoveltySignals,
    Observation,
    OntologyClass,
    OntologyVersion,
    ReviewRecommendation,
    ReviewRequest,
    SupervisorFinding,
)
from openclass_provider_glm import (
    GatewayClusterDiscovery,
    GatewayDecisionProvider,
    OpenAICompatibleSupervisorProvider,
)
from openclass_server.main import create_app
from openclass_server.settings import Settings
from pydantic import SecretStr


def _load_gateway_key() -> str:
    env_key = os.getenv("AI_GATEWAY_API_KEY", "").strip()
    if env_key:
        return env_key
    env_path = Path(".env")
    if env_path.is_file():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "AI_GATEWAY_API_KEY":
                return value.strip().strip("'\"")
    return ""


def test_six_stage_closed_loop_unknown_to_promoted_ontology_and_teacher_disabled_replay(
    database_url: str,
) -> None:
    settings = Settings(
        database_url=database_url,
        decision_provider="mock",
        discovery_provider="mock",
    )
    with TestClient(create_app(settings)) as client:
        # Stage 1: Project & Decision Service v1
        proj_resp = client.post("/api/v1/projects", json={"name": "Support Operations"})
        assert proj_resp.status_code == 201, proj_resp.text
        project = proj_resp.json()
        project_id = project["id"]

        svc_resp = client.post(
            f"/api/v1/projects/{project_id}/decision-services",
            json={
                "name": "Intent Router",
                "instructions": "Route customer support requests to the matching queue.",
                "choices": [
                    {
                        "key": "BILLING",
                        "label": "Billing",
                        "description": "Billing, invoice, and charge inquiries.",
                        "aliases": ["invoice", "charge"],
                    },
                    {
                        "key": "TECHNICAL",
                        "label": "Technical",
                        "description": "Technical troubleshooting and outages.",
                        "aliases": ["outage", "crash"],
                    },
                ],
            },
        )
        assert svc_resp.status_code == 201, svc_resp.text
        service = svc_resp.json()
        service_id = service["id"]
        assert service["version_number"] == 1

        # Stage 2: Observe Known & Permanent UNKNOWN
        known_resp = client.post(
            f"/api/v1/projects/{project_id}/decision-services/{service_id}/runs",
            json={"content": "Double charge on invoice"},
        )
        assert known_resp.status_code == 201, known_resp.text
        known_run = known_resp.json()[0]
        assert known_run["selected_choice"] == "BILLING"
        assert known_run["supervision_outcome"] == "TRUSTED"

        unknown_texts = [
            "Cancel my subscription immediately",
            "Please cancel my account renewal",
            "How do I cancel my plan and stop renewal?",
            "Cancel my plan today please",
            "Cancel plan next month",
        ]
        unknown_run_ids: list[str] = []
        for text in unknown_texts:
            unk_resp = client.post(
                f"/api/v1/projects/{project_id}/decision-services/{service_id}/runs",
                json={"content": text},
            )
            assert unk_resp.status_code == 201, unk_resp.text
            unk_run = unk_resp.json()[0]
            assert unk_run["selected_choice"] == "UNKNOWN"
            assert unk_run["supervision_outcome"] == "UNKNOWN"
            unknown_run_ids.append(unk_run["id"])

        unknown_pool = client.get(f"/api/v1/projects/{project_id}/unknowns?limit=50").json()
        assert len(unknown_pool["items"]) == len(unknown_texts)

        # Stage 3: Cluster & Evidence
        cluster_resp = client.post(
            f"/api/v1/projects/{project_id}/unknowns/cluster",
            json={"threshold": 0.15},
        )
        assert cluster_resp.status_code == 200, cluster_resp.text
        assert cluster_resp.json()["cluster_count"] >= 1

        clusters = client.get(f"/api/v1/projects/{project_id}/unknowns/clusters").json()
        assert len(clusters) >= 1
        biggest_cluster = max(clusters, key=lambda entry: entry["size"])
        cluster_id = biggest_cluster["id"]

        # Stage 4: Discovery & Human Review
        discover_resp = client.post(f"/api/v1/projects/{project_id}/clusters/{cluster_id}/discover")
        assert discover_resp.status_code == 201, discover_resp.text
        candidate = discover_resp.json()
        candidate_id = candidate["id"]
        assert candidate["status"] == "candidate"
        assert candidate["type"] == "NEW_CLASS"
        promoted_choice_key = candidate["canonical_name"].upper()

        collect_resp = client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{candidate_id}/collect",
            json={"unknown_ids": unknown_run_ids},
        )
        assert collect_resp.status_code == 200, collect_resp.text
        assert collect_resp.json()["evidence"] >= 5

        req_review_resp = client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{candidate_id}/request-review"
        )
        assert req_review_resp.status_code == 200, req_review_resp.text
        assert req_review_resp.json()["status"] == "validating"

        review_resp = client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{candidate_id}/review",
            json={
                "decision": "approve",
                "rationale": "Five distinct cancellation observations confirm missing class.",
            },
        )
        assert review_resp.status_code == 200, review_resp.text
        assert review_resp.json()["status"] == "approved"

        # Stage 5: Verified Holdout Replay Gate
        ds_resp = client.post(
            f"/api/v1/projects/{project_id}/eval-datasets",
            json={
                "name": "support-cancel-holdout-eval",
                "description": "Verified calibration and holdout replay suite.",
            },
        )
        assert ds_resp.status_code == 201, ds_resp.text
        dataset_id = ds_resp.json()["id"]

        eval_examples = [
            ("Double charge on invoice", "BILLING", "calibration", "human"),
            ("System crash and outage on login", "TECHNICAL", "regression", "human"),
            (
                "Cancel my subscription immediately",
                promoted_choice_key,
                "holdout",
                "verified_external",
            ),
            ("Cancel plan next month", promoted_choice_key, "holdout", "verified_external"),
        ]
        for text, label, split, source in eval_examples:
            ex_resp = client.post(
                f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}/examples",
                json={
                    "text": text,
                    "label": label,
                    "source": source,
                    "annotator": "qa-lead@acme.test",
                    "split": split,
                    "metadata": {"source_type": "verified_holdout"} if split == "holdout" else {},
                },
            )
            assert ex_resp.status_code == 201, ex_resp.text

        seal_resp = client.post(f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}/seal")
        assert seal_resp.status_code == 200, seal_resp.text
        assert seal_resp.json()["sealed"] is True
        assert len(seal_resp.json()["dataset_hash"]) == 64

        ds_detail = client.get(f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}").json()
        holdout_examples = [ex for ex in ds_detail["examples"] if ex["split"] == "holdout"]
        assert len(holdout_examples) >= 1

        eval_resp = client.post(
            f"/api/v1/projects/{project_id}/evaluations",
            json={"dataset_id": dataset_id, "candidate_id": candidate_id},
        )
        assert eval_resp.status_code == 201, eval_resp.text
        evaluation = eval_resp.json()
        assert evaluation["overall_passed"] is True
        assert (
            evaluation["metrics"]["baseline"]["coverage"]
            < evaluation["metrics"]["candidate"]["coverage"]
        )
        assert evaluation["metrics"]["candidate"]["accuracy"] == 1.0

        # Stage 6: Versioned Promotion & Teacher-Disabled Replay
        promote_resp = client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{candidate_id}/promote",
            json={
                "evaluation_id": evaluation["id"],
                "reviewer": "lead-reviewer@acme.test",
                "rationale": "Holdout replay passed with zero billing or technical regressions.",
            },
        )
        assert promote_resp.status_code == 200, promote_resp.text
        promoted = promote_resp.json()
        assert promoted["status"] == "active"
        assert promoted["version"]["version_number"] == 2
        assert promoted["added_class"] == promoted_choice_key

        updated_svc = client.get(
            f"/api/v1/projects/{project_id}/decision-services/{service_id}"
        ).json()
        assert updated_svc["version_number"] == 2
        assert updated_svc["active_version_id"] == promoted["version"]["id"]

        # Historical UNKNOWN runs remain permanent and immutable under v1
        first_unknown = client.get(
            f"/api/v1/projects/{project_id}/runs/{unknown_run_ids[0]}"
        ).json()
        assert first_unknown["selected_choice"] == "UNKNOWN"
        assert first_unknown["decision_service_version_id"] != promoted["version"]["id"]

    # Restart with Teacher/discovery uninvolved and verify fast-path v2 classification
    with TestClient(
        create_app(Settings(database_url=database_url, decision_provider="mock"))
    ) as replay_client:
        replay_resp = replay_client.post(
            f"/api/v1/projects/{project_id}/decision-services/{service_id}/runs",
            json={"content": "Cancel my subscription immediately"},
        )
        assert replay_resp.status_code == 201, replay_resp.text
        replay_run = replay_resp.json()[0]
        assert replay_run["selected_choice"] == promoted_choice_key
        assert replay_run["supervision_outcome"] == "TRUSTED"
        assert replay_run["decision_service_version_id"] == promoted["version"]["id"]


@pytest.mark.live
async def test_live_vercel_ai_gateway_providers() -> None:
    if os.getenv("OPENCLASS_RUN_LIVE_TESTS") != "1":
        pytest.skip("Set OPENCLASS_RUN_LIVE_TESTS=1 to run live Vercel AI Gateway proof")

    api_key = _load_gateway_key()
    if not api_key:
        pytest.skip("AI_GATEWAY_API_KEY is not configured in environment or .env")

    secret_key = SecretStr(api_key)
    base_url = "https://ai-gateway.vercel.sh/v1"
    model = "openai/gpt-4.1-mini"

    classifier_id = uuid4()
    billing_class = OntologyClass(
        canonical_name="billing",
        display_name="Billing",
        description="Invoices, double charges, and payment issues.",
    )
    technical_class = OntologyClass(
        canonical_name="technical",
        display_name="Technical",
        description="Crashes, login failures, and software bugs.",
    )
    ontology = OntologyVersion(
        classifier_id=classifier_id,
        version_number=1,
        created_by="live-test",
        classes=(billing_class, technical_class),
    )
    observation = Observation(
        content="My credit card was charged twice on the latest monthly invoice."
    )

    # 1. Live GatewayDecisionProvider
    decision_provider = GatewayDecisionProvider(
        api_key=secret_key,
        base_url=base_url,
        model=model,
        timeout=30.0,
    )
    choice_result = await decision_provider.choice(
        ChoiceRequest(
            observation=observation,
            ontology=ontology,
            instructions="Route customer support observations to the matching category.",
        )
    )
    assert choice_result.provider == "openai-compatible"
    assert choice_result.model == model
    assert choice_result.provider_metadata.get("simulated") is False
    assert set(choice_result.probabilities) == {"billing", "technical"}
    assert (
        abs(sum(choice_result.probabilities.values()) + choice_result.unknown_probability - 1.0)
        < 1e-5
    )
    assert choice_result.probabilities["billing"] > choice_result.probabilities["technical"]

    # 2. Live GatewayClusterDiscovery
    discovery_provider = GatewayClusterDiscovery(
        api_key=secret_key,
        base_url=base_url,
        model=model,
        timeout=30.0,
    )
    discovery_result = await discovery_provider.discover(
        ClusterDiscoveryRequest(
            cluster_id=uuid4(),
            member_texts=(
                "Please cancel my subscription immediately",
                "How do I cancel my monthly plan and stop renewal?",
                "I want to terminate my recurring subscription plan today",
            ),
            existing_classes=("billing", "technical"),
            provider="openai-compatible",
        )
    )
    assert discovery_result.type == "NEW_CLASS"
    assert discovery_result.canonical_name is not None
    assert discovery_result.canonical_name not in {"billing", "technical"}
    assert 0.0 <= discovery_result.confidence <= 1.0
    assert bool(discovery_result.reason.strip())

    # 3. Live OpenAICompatibleSupervisorProvider
    supervisor_provider = OpenAICompatibleSupervisorProvider(
        api_key=secret_key,
        base_url=base_url,
        model=model,
        provider_name="openai-compatible",
        timeout=30.0,
    )
    top1 = max(choice_result.probabilities.values())
    top2 = min(choice_result.probabilities.values())
    classification = ClassificationResult(
        classifier_id=classifier_id,
        observation_id=observation.id,
        ontology_version_id=ontology.id,
        selected_class_id=billing_class.stable_class_id,
        selected_class="billing",
        decision=choice_result,
        signals=NoveltySignals(
            unknown_probability=choice_result.unknown_probability,
            top1_probability=top1,
            top2_probability=top2,
            top_margin=max(0.0, top1 - top2),
            entropy=0.1,
        ),
        novelty=NoveltyAssessment(
            score=choice_result.unknown_probability,
            state="known",
            reasons=("confident_known",),
        ),
    )
    review_result = await supervisor_provider.review(
        ReviewRequest(
            observation=observation,
            classification=classification,
            ontology=ontology,
        )
    )
    assert review_result.provider == "openai-compatible"
    assert review_result.finding in tuple(SupervisorFinding)
    assert review_result.recommendation in tuple(ReviewRecommendation)
    assert 0.0 <= review_result.confidence <= 1.0
    assert review_result.provider_metadata.get("simulated") is False
