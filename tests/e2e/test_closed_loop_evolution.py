"""End-to-end closed-loop evolution, holdout separation, provenance guards, and live proof."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openclass_core.candidates import ClusterDiscoveryRequest
from openclass_core.evaluation import EvaluationExample
from openclass_core.evidence import DiagnosisResult
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
from openclass_core.project_evolution import ChoiceProposal
from openclass_core.projects import DecisionRun, DecisionService
from openclass_provider_glm import (
    GatewayClusterDiscovery,
    GatewayDecisionProvider,
    GatewayEmbedder,
    OpenAICompatibleSupervisorProvider,
)
from openclass_server.main import create_app
from openclass_server.settings import Settings
from pydantic import SecretStr

# ---------------------------------------------------------------------------
# Strictly Disjoint Datasets (Discovery / Calibration / Regression / Holdout / Transfer)
# ---------------------------------------------------------------------------

DISCOVERY_INPUTS: tuple[str, ...] = (
    "Customer asks to cancel plan for their enterprise subscription immediately",
    "Request from admin to cancel plan at end of current contract term",
    "User wants to cancel plan because their project has concluded",
    "Member submitted a ticket to cancel plan for the team tier",
    "Client requested to cancel plan and discontinue subscription service",
)

CALIBRATION_DEV_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("Customer invoice shows a duplicate charge on the statement", "BILLING"),
    ("Application crash occurs during mobile dashboard login", "TECHNICAL"),
    ("Requesting to cancel plan after trial period ends", "__PROMOTED_CHOICE__"),
)

REGRESSION_BASELINE_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("My credit card was charged twice on the latest billing invoice", "BILLING"),
    ("Unexpected charge appeared on our quarterly invoice receipt", "BILLING"),
    ("Production outage returning HTTP 500 timeout across endpoints", "TECHNICAL"),
    ("Backend service crash triggered an outage alert in monitoring", "TECHNICAL"),
)

UNSEEN_HOLDOUT_EXAMPLES: tuple[str, ...] = (
    "Kindly cancel plan effective upon upcoming renewal date",
    "Would someone cancel plan plus deactivate annual membership",
    "Please cancel plan permanently since our trial finished",
)

STAGE_6_UNSEEN_TRANSFER_INPUTS: tuple[str, ...] = (
    "Organization owner needs support to cancel plan effective Friday",
    "Account holder instructed us to cancel plan regarding departed seats",
)


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().casefold().split())


def _token_set(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-z0-9]+", text.casefold()) if tok}


def _jaccard_similarity(left: str, right: str) -> float:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return len(left_tokens & right_tokens) / len(union)


def assert_strictly_disjoint_datasets(max_jaccard: float = 0.55) -> None:
    """Verify zero normalized text overlap across all 5 sets and low token Jaccard overlap."""
    named_sets: list[tuple[str, tuple[str, ...]]] = [
        ("DISCOVERY_INPUTS", DISCOVERY_INPUTS),
        ("CALIBRATION_DEV_EXAMPLES", tuple(text for text, _ in CALIBRATION_DEV_EXAMPLES)),
        ("REGRESSION_BASELINE_EXAMPLES", tuple(text for text, _ in REGRESSION_BASELINE_EXAMPLES)),
        ("UNSEEN_HOLDOUT_EXAMPLES", UNSEEN_HOLDOUT_EXAMPLES),
        ("STAGE_6_UNSEEN_TRANSFER_INPUTS", STAGE_6_UNSEEN_TRANSFER_INPUTS),
    ]
    seen_by_set: dict[str, set[str]] = {}
    for name, texts in named_sets:
        norms = {_normalize_text(t) for t in texts}
        assert len(norms) == len(texts), f"Duplicate text inside {name}"
        for other_name, other_norms in seen_by_set.items():
            overlap = norms & other_norms
            assert not overlap, (
                f"Normalized text overlap between {name} and {other_name}: {overlap}"
            )
        seen_by_set[name] = norms

    for disc_text in DISCOVERY_INPUTS:
        for holdout_text in (*UNSEEN_HOLDOUT_EXAMPLES, *STAGE_6_UNSEEN_TRANSFER_INPUTS):
            jaccard = _jaccard_similarity(disc_text, holdout_text)
            assert jaccard < max_jaccard, (
                f"Token Jaccard overlap {jaccard:.3f} >= {max_jaccard} between "
                f"discovery '{disc_text}' and holdout/transfer '{holdout_text}'"
            )


class _DisabledChoiceTeacher:
    """Fails closed if Stage 6 runtime classification ever invokes a Teacher."""

    async def propose(
        self, service: DecisionService, runs: tuple[DecisionRun, ...]
    ) -> ChoiceProposal:
        raise AssertionError("ChoiceTeacher must not be invoked during Stage 6 runtime replay")


class _DisabledDiagnosisProvider:
    """Fails closed if Stage 6 runtime classification ever invokes diagnosis."""

    async def diagnose(self, context: dict[str, Any]) -> DiagnosisResult:
        raise AssertionError("DiagnosisProvider must not be invoked during Stage 6 runtime replay")


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


def _create_support_service(client: TestClient, project_id: str) -> dict[str, Any]:
    svc_resp = client.post(
        f"/api/v1/projects/{project_id}/decision-services",
        json={
            "name": "Intent Router",
            "instructions": (
                "Route customer support requests to the matching queue. "
                "Use BILLING only for invoice or charge questions, and TECHNICAL only for "
                "crashes or outages. Route unrepresented intents such as subscription "
                "cancellation to UNKNOWN unless a cancellation choice is active."
            ),
            "choices": [
                {
                    "key": "BILLING",
                    "label": "Billing",
                    "description": "Billing statements, invoice questions, and duplicate charges.",
                    "aliases": ["invoice", "charge"],
                },
                {
                    "key": "TECHNICAL",
                    "label": "Technical",
                    "description": "Technical troubleshooting, application crashes, and outages.",
                    "aliases": ["outage", "crash"],
                },
            ],
        },
    )
    assert svc_resp.status_code == 201, svc_resp.text
    return svc_resp.json()


def test_six_stage_closed_loop_unknown_to_promoted_ontology_and_teacher_disabled_replay(
    database_url: str,
) -> None:
    assert_strictly_disjoint_datasets()

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

        service = _create_support_service(client, project_id)
        service_id = service["id"]
        assert service["version_number"] == 1

        # Stage 2: Observe Known (BILLING & TECHNICAL) & Permanent UNKNOWN
        for baseline_text, expected_choice in REGRESSION_BASELINE_EXAMPLES[:2]:
            known_resp = client.post(
                f"/api/v1/projects/{project_id}/decision-services/{service_id}/runs",
                json={"content": baseline_text},
            )
            assert known_resp.status_code == 201, known_resp.text
            known_run = known_resp.json()[0]
            assert known_run["selected_choice"] == expected_choice
            assert known_run["supervision_outcome"] == "TRUSTED"

        unknown_run_ids: list[str] = []
        for text in DISCOVERY_INPUTS:
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
        assert len(unknown_pool["items"]) == len(DISCOVERY_INPUTS)

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

        # Stage 5: Verified Disjoint Holdout + Regression Replay Gate
        ds_resp = client.post(
            f"/api/v1/projects/{project_id}/eval-datasets",
            json={
                "name": "support-cancel-holdout-eval",
                "description": "Strictly disjoint calibration, regression, and holdout suite.",
            },
        )
        assert ds_resp.status_code == 201, ds_resp.text
        dataset_id = ds_resp.json()["id"]

        for idx, (text, raw_label) in enumerate(CALIBRATION_DEV_EXAMPLES):
            resolved_label = (
                promoted_choice_key if raw_label == "__PROMOTED_CHOICE__" else raw_label
            )
            ex_resp = client.post(
                f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}/examples",
                json={
                    "text": text,
                    "label": resolved_label,
                    "source": "human",
                    "source_type": "human_verified",
                    "annotator": "qa-lead@acme.io",
                    "split": "calibration",
                    "metadata": {
                        "source_type": "human_verified",
                        "label_source": "human_verified",
                        "verified_by": "qa-lead@acme.io",
                        "evidence_refs": [f"cal-ref-{idx + 1}"],
                    },
                },
            )
            assert ex_resp.status_code == 201, ex_resp.text

        for idx, (text, label) in enumerate(REGRESSION_BASELINE_EXAMPLES):
            ex_resp = client.post(
                f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}/examples",
                json={
                    "text": text,
                    "label": label,
                    "source": "human",
                    "source_type": "human_verified",
                    "annotator": "qa-lead@acme.io",
                    "split": "regression",
                    "metadata": {
                        "source_type": "human_verified",
                        "label_source": "human_verified",
                        "verified_by": "qa-lead@acme.io",
                        "evidence_refs": [f"reg-ref-{idx + 1}"],
                    },
                },
            )
            assert ex_resp.status_code == 201, ex_resp.text

        for idx, text in enumerate(UNSEEN_HOLDOUT_EXAMPLES):
            ex_resp = client.post(
                f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}/examples",
                json={
                    "text": text,
                    "label": promoted_choice_key,
                    "source": "verified_external",
                    "source_type": "verified_holdout",
                    "annotator": "qa-lead@acme.io",
                    "split": "holdout",
                    "metadata": {
                        "source_type": "verified_holdout",
                        "label_source": "human_verified",
                        "verified_by": "qa-lead@acme.io",
                        "evidence_refs": [f"holdout-ref-{idx + 1}"],
                    },
                },
            )
            assert ex_resp.status_code == 201, ex_resp.text

        seal_resp = client.post(f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}/seal")
        assert seal_resp.status_code == 200, seal_resp.text
        assert seal_resp.json()["sealed"] is True
        assert len(seal_resp.json()["dataset_hash"]) == 64

        ds_detail = client.get(f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}").json()
        holdout_examples = [ex for ex in ds_detail["examples"] if ex["split"] == "holdout"]
        assert len(holdout_examples) == len(UNSEEN_HOLDOUT_EXAMPLES)

        eval_resp = client.post(
            f"/api/v1/projects/{project_id}/evaluations",
            json={"dataset_id": dataset_id, "candidate_id": candidate_id},
        )
        assert eval_resp.status_code == 201, eval_resp.text
        evaluation = eval_resp.json()
        assert evaluation["overall_passed"] is True
        assert evaluation["metrics"]["regressions"] == 0
        assert evaluation["metrics"]["zero_regressions"] is True
        assert evaluation["metrics"]["holdout_metrics"]["holdout_examples"] == len(
            UNSEEN_HOLDOUT_EXAMPLES
        )
        assert (
            evaluation["metrics"]["baseline"]["coverage"]
            < evaluation["metrics"]["candidate"]["coverage"]
        )
        assert evaluation["metrics"]["candidate"]["accuracy"] == 1.0
        gates_by_name = {g["gate"]: g for g in evaluation["gates"]}
        assert gates_by_name["zero_regressions"]["passed"] is True
        assert gates_by_name["no_billing_regression"]["passed"] is True
        assert gates_by_name["no_technical_regression"]["passed"] is True

        # Stage 6: Versioned Promotion & Teacher-Disabled Replay
        promote_resp = client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{candidate_id}/promote",
            json={
                "evaluation_id": evaluation["id"],
                "reviewer": "lead-reviewer@acme.io",
                "rationale": "Disjoint holdout replay passed with zero regressions.",
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

        # Linked unknowns auto-transition to "resolved" in triage state while runs remain immutable
        unknowns_after = client.get(f"/api/v1/projects/{project_id}/unknowns").json()["items"]
        unknowns_by_run = {item["run_id"]: item for item in unknowns_after}
        for run_id in unknown_run_ids:
            assert unknowns_by_run[run_id]["status"] == "resolved"
            assert unknowns_by_run[run_id]["triage"]["status"] == "resolved"

        # Historical UNKNOWN runs remain permanent and immutable under v1
        first_unknown = client.get(
            f"/api/v1/projects/{project_id}/runs/{unknown_run_ids[0]}"
        ).json()
        assert first_unknown["selected_choice"] == "UNKNOWN"
        assert first_unknown["decision_service_version_id"] != promoted["version"]["id"]

    # Restart with discovery_provider="none" and Teacher/Diagnosis providers explicitly disabled
    replay_app = create_app(
        Settings(
            database_url=database_url,
            decision_provider="mock",
            discovery_provider="none",
        ),
        choice_teacher=_DisabledChoiceTeacher(),
        diagnosis_provider=_DisabledDiagnosisProvider(),
    )
    with TestClient(replay_app) as replay_client:
        disabled_disc = replay_client.post(
            f"/api/v1/projects/{project_id}/clusters/{cluster_id}/discover"
        )
        assert disabled_disc.status_code == 502, disabled_disc.text
        assert disabled_disc.json().get("kind") == "unsupported"

        for transfer_text in STAGE_6_UNSEEN_TRANSFER_INPUTS:
            replay_resp = replay_client.post(
                f"/api/v1/projects/{project_id}/decision-services/{service_id}/runs",
                json={"content": transfer_text},
            )
            assert replay_resp.status_code == 201, replay_resp.text
            replay_run = replay_resp.json()[0]
            assert replay_run["selected_choice"] == promoted_choice_key
            assert replay_run["supervision_outcome"] == "TRUSTED"
            assert replay_run["decision_service_version_id"] == promoted["version"]["id"]

        # Verify retention of previously verified BILLING and TECHNICAL behavior on v2
        for baseline_text, expected_choice in REGRESSION_BASELINE_EXAMPLES:
            reg_resp = replay_client.post(
                f"/api/v1/projects/{project_id}/decision-services/{service_id}/runs",
                json={"content": baseline_text},
            )
            assert reg_resp.status_code == 201, reg_resp.text
            reg_run = reg_resp.json()[0]
            assert reg_run["selected_choice"] == expected_choice
            assert reg_run["supervision_outcome"] == "TRUSTED"
            assert reg_run["decision_service_version_id"] == promoted["version"]["id"]


def test_evolution_rejects_holdout_leakage_and_prediction_ground_truth(
    database_url: str,
) -> None:
    # 1. Core model boundary rejects prediction label_source directly
    for forbidden_source in ("prediction", "model_prediction", "unverified_prediction"):
        with pytest.raises(
            ValueError, match="Predictions cannot be used as evaluation ground truth"
        ):
            EvaluationExample(
                text="Customer invoice shows a duplicate charge",
                label="BILLING",
                source="human",
                annotator="qa-lead@acme.io",
                metadata={"label_source": forbidden_source},
            )

    settings = Settings(
        database_url=database_url,
        decision_provider="mock",
        discovery_provider="mock",
    )
    with TestClient(create_app(settings)) as client:
        proj = client.post("/api/v1/projects", json={"name": "Leakage Guard Ops"}).json()
        project_id = proj["id"]
        service = _create_support_service(client, project_id)
        service_id = service["id"]

        for text in DISCOVERY_INPUTS:
            client.post(
                f"/api/v1/projects/{project_id}/decision-services/{service_id}/runs",
                json={"content": text},
            )
        client.post(f"/api/v1/projects/{project_id}/unknowns/cluster", json={"threshold": 0.15})
        clusters = client.get(f"/api/v1/projects/{project_id}/unknowns/clusters").json()
        cluster_id = max(clusters, key=lambda entry: entry["size"])["id"]
        candidate = client.post(
            f"/api/v1/projects/{project_id}/clusters/{cluster_id}/discover"
        ).json()
        promoted_key = candidate["canonical_name"].upper()

        ds = client.post(
            f"/api/v1/projects/{project_id}/eval-datasets",
            json={"name": "leaky-holdout-suite"},
        ).json()
        dataset_id = ds["id"]

        # 2. API rejects evaluation example with metadata={"label_source": "prediction"} with 422
        pred_resp = client.post(
            f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}/examples",
            json={
                "text": UNSEEN_HOLDOUT_EXAMPLES[0],
                "label": promoted_key,
                "source": "human",
                "annotator": "qa-lead@acme.io",
                "split": "holdout",
                "metadata": {"label_source": "prediction"},
            },
        )
        assert pred_resp.status_code == 422, pred_resp.text

        # 3. Sealing a dataset where a verified_holdout example duplicates a DISCOVERY_INPUTS
        #    observation is rejected with 409 Conflict (Holdout leakage detected).
        leaked_add = client.post(
            f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}/examples",
            json={
                "text": DISCOVERY_INPUTS[0],
                "label": promoted_key,
                "source": "verified_external",
                "source_type": "verified_holdout",
                "annotator": "qa-lead@acme.io",
                "split": "holdout",
                "metadata": {
                    "source_type": "verified_holdout",
                    "label_source": "human_verified",
                    "verified_by": "qa-lead@acme.io",
                    "evidence_refs": ["leaked-ref-1"],
                },
            },
        )
        assert leaked_add.status_code == 201, leaked_add.text

        seal_resp = client.post(f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}/seal")
        assert seal_resp.status_code == 409, seal_resp.text
        assert "Holdout leakage detected" in seal_resp.json()["detail"]


def test_evolution_rejects_invalid_and_regressive_candidates(
    database_url: str,
) -> None:
    settings = Settings(
        database_url=database_url,
        decision_provider="mock",
        discovery_provider="mock",
    )
    with TestClient(create_app(settings)) as client:
        proj = client.post("/api/v1/projects", json={"name": "Regression Guard Ops"}).json()
        project_id = proj["id"]
        service = _create_support_service(client, project_id)
        service_id = service["id"]

        unknown_run_ids: list[str] = []
        for text in DISCOVERY_INPUTS:
            resp = client.post(
                f"/api/v1/projects/{project_id}/decision-services/{service_id}/runs",
                json={"content": text},
            )
            unknown_run_ids.append(resp.json()[0]["id"])

        client.post(f"/api/v1/projects/{project_id}/unknowns/cluster", json={"threshold": 0.15})
        clusters = client.get(f"/api/v1/projects/{project_id}/unknowns/clusters").json()
        cluster_id = max(clusters, key=lambda entry: entry["size"])["id"]

        # 1. Unapproved candidate promotion is rejected with 409
        unapproved_cand = client.post(
            f"/api/v1/projects/{project_id}/clusters/{cluster_id}/discover"
        ).json()
        unapproved_promote = client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{unapproved_cand['id']}/promote",
            json={
                "evaluation_id": str(uuid4()),
                "reviewer": "lead-reviewer@acme.io",
                "rationale": "Attempting to promote without human approval.",
            },
        )
        assert unapproved_promote.status_code == 409, unapproved_promote.text
        assert "approved" in unapproved_promote.json()["detail"].lower()

        # 2. Colliding choice key/alias candidate promotion is rejected with 409
        colliding_cand = client.post(
            f"/api/v1/projects/{project_id}/clusters/{cluster_id}/discover",
            json={"canonical_name": "billing", "aliases": ["invoice"]},
        ).json()
        colliding_id = colliding_cand["id"]
        client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{colliding_id}/collect",
            json={"unknown_ids": unknown_run_ids},
        )
        client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{colliding_id}/request-review"
        )
        client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{colliding_id}/review",
            json={"decision": "approve", "rationale": "Approving to test collision guard."},
        )
        colliding_promote = client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{colliding_id}/promote",
            json={
                "evaluation_id": str(uuid4()),
                "reviewer": "lead-reviewer@acme.io",
                "rationale": "Attempting to promote colliding choice key.",
            },
        )
        assert colliding_promote.status_code == 409, colliding_promote.text
        assert "collides" in colliding_promote.json()["detail"].lower()

        # 3. Regressive candidate with broad aliases ("invoice", "charged", "500", "timeout")
        #    hijacks verified BILLING and TECHNICAL examples -> regressions > 0,
        #    overall_passed is False, and /promote is blocked with 409.
        regressive_cand = client.post(
            f"/api/v1/projects/{project_id}/clusters/{cluster_id}/discover",
            json={
                "canonical_name": "broad_escalation",
                "aliases": ["invoice", "charged", "500", "timeout"],
            },
        ).json()
        regressive_id = regressive_cand["id"]
        client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{regressive_id}/collect",
            json={"unknown_ids": unknown_run_ids},
        )
        client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{regressive_id}/request-review"
        )
        client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{regressive_id}/review",
            json={"decision": "approve", "rationale": "Approving to test regression gate."},
        )

        ds = client.post(
            f"/api/v1/projects/{project_id}/eval-datasets",
            json={"name": "regression-guard-suite"},
        ).json()
        dataset_id = ds["id"]
        for idx, (text, label) in enumerate(REGRESSION_BASELINE_EXAMPLES):
            add_resp = client.post(
                f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}/examples",
                json={
                    "text": text,
                    "label": label,
                    "source": "human",
                    "source_type": "human_verified",
                    "annotator": "qa-lead@acme.io",
                    "split": "regression",
                    "metadata": {
                        "source_type": "human_verified",
                        "label_source": "human_verified",
                        "verified_by": "qa-lead@acme.io",
                        "evidence_refs": [f"reg-guard-{idx + 1}"],
                    },
                },
            )
            assert add_resp.status_code == 201, add_resp.text

        seal_resp = client.post(f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}/seal")
        assert seal_resp.status_code == 200, seal_resp.text

        eval_resp = client.post(
            f"/api/v1/projects/{project_id}/evaluations",
            json={"dataset_id": dataset_id, "candidate_id": regressive_id},
        )
        assert eval_resp.status_code == 201, eval_resp.text
        eval_body = eval_resp.json()
        assert eval_body["overall_passed"] is False
        assert eval_body["metrics"]["regressions"] > 0
        assert eval_body["metrics"]["zero_regressions"] is False
        gates_by_name = {g["gate"]: g for g in eval_body["gates"]}
        assert gates_by_name["zero_regressions"]["passed"] is False
        assert gates_by_name["no_billing_regression"]["passed"] is False
        assert gates_by_name["no_technical_regression"]["passed"] is False

        reg_promote = client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{regressive_id}/promote",
            json={
                "evaluation_id": eval_body["id"],
                "reviewer": "lead-reviewer@acme.io",
                "rationale": "Attempting to promote regressive candidate.",
            },
        )
        assert reg_promote.status_code == 409, reg_promote.text


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
            member_texts=DISCOVERY_INPUTS,
            existing_classes=("billing", "technical"),
            provider="openai-compatible",
        )
    )
    assert discovery_result.type == "NEW_CLASS"
    assert discovery_result.canonical_name is not None
    assert discovery_result.canonical_name not in {"billing", "technical"}
    assert 0.0 <= discovery_result.confidence <= 1.0
    assert bool(discovery_result.reason.strip())

    # 3. Live GatewayEmbedder
    embedder = GatewayEmbedder(
        api_key=secret_key,
        base_url=base_url,
        model="cohere/embed-v4.0",
        timeout=30.0,
    )
    vectors = await embedder.embed(DISCOVERY_INPUTS[:2])
    assert len(vectors) == 2
    assert len(vectors[0]) == embedder.dimensions

    # 4. Live OpenAICompatibleSupervisorProvider
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


@pytest.mark.live
def test_live_closed_loop_evolution_end_to_end(database_url: str) -> None:
    if os.getenv("OPENCLASS_RUN_LIVE_TESTS") != "1":
        pytest.skip("Set OPENCLASS_RUN_LIVE_TESTS=1 to run live closed-loop evolution proof")

    api_key = _load_gateway_key()
    if not api_key:
        pytest.skip("AI_GATEWAY_API_KEY is not configured in environment or .env")

    assert_strictly_disjoint_datasets()

    secret_key = SecretStr(api_key)
    live_settings = Settings(
        database_url=database_url,
        decision_provider="openai-compatible",
        discovery_provider="openai-compatible",
        supervisor_provider="openai-compatible",
        embedding_provider="openai-compatible",
        embedding_model="cohere/embed-v4.0",
        discovery_api_key=secret_key,
        discovery_base_url="https://ai-gateway.vercel.sh/v1",
        discovery_model="openai/gpt-4.1-mini",
        discovery_timeout_seconds=60.0,
    )

    def _post_live(c: TestClient, url: str, **kwargs: Any) -> Any:
        for attempt in range(5):
            resp = c.post(url, **kwargs)
            if resp.status_code == 429 and attempt < 4:
                time.sleep(5.0 * (attempt + 1))
                continue
            return resp
        raise RuntimeError("unreachable")

    with TestClient(create_app(live_settings)) as client:
        # Stage 1: Project & Decision Service v1
        proj = client.post("/api/v1/projects", json={"name": "Live Support Operations"}).json()
        project_id = proj["id"]
        service = _create_support_service(client, project_id)
        service_id = service["id"]

        # Stage 2: Live UNKNOWN observations on unrepresented cancellation intent
        unknown_run_ids: list[str] = []
        for text in DISCOVERY_INPUTS:
            unk_resp = _post_live(
                client,
                f"/api/v1/projects/{project_id}/decision-services/{service_id}/runs",
                json={"content": text},
            )
            assert unk_resp.status_code == 201, unk_resp.text
            unk_run = unk_resp.json()[0]
            assert unk_run["selected_choice"] == "UNKNOWN"
            assert unk_run["real_inference"] is True
            assert unk_run["provider"] == "openai-compatible"
            unknown_run_ids.append(unk_run["id"])

        # Stage 3: Live Embedding & Clustering
        cluster_resp = _post_live(
            client,
            f"/api/v1/projects/{project_id}/unknowns/cluster",
            json={"threshold": 0.45},
        )
        assert cluster_resp.status_code == 200, cluster_resp.text
        cluster_data = cluster_resp.json()
        assert cluster_data["simulated"] is False
        assert cluster_data["cluster_count"] >= 1

        clusters = client.get(f"/api/v1/projects/{project_id}/unknowns/clusters").json()
        biggest_cluster = max(clusters, key=lambda entry: entry["size"])
        cluster_id = biggest_cluster["id"]
        assert biggest_cluster["size"] >= 3

        # Stage 4: Live Cluster Discovery & Human Approval
        discover_resp = _post_live(
            client, f"/api/v1/projects/{project_id}/clusters/{cluster_id}/discover"
        )
        assert discover_resp.status_code == 201, discover_resp.text
        candidate = discover_resp.json()
        candidate_id = candidate["id"]
        assert candidate["type"] == "NEW_CLASS"
        assert candidate["simulated"] is False
        promoted_choice_key = candidate["canonical_name"].upper()

        collect_resp = client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{candidate_id}/collect",
            json={"unknown_ids": unknown_run_ids},
        )
        assert collect_resp.status_code == 200, collect_resp.text
        assert collect_resp.json()["evidence"] >= 5

        req_review = client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{candidate_id}/request-review"
        )
        assert req_review.status_code == 200, req_review.text

        review_resp = client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{candidate_id}/review",
            json={
                "decision": "approve",
                "rationale": "Live cluster discovery confirmed recurring cancellation intent.",
            },
        )
        assert review_resp.status_code == 200, review_resp.text
        assert review_resp.json()["status"] == "approved"

        # Stage 5: Live Disjoint Holdout + Regression Replay Evaluation
        ds_resp = client.post(
            f"/api/v1/projects/{project_id}/eval-datasets",
            json={"name": "live-disjoint-holdout-suite"},
        )
        assert ds_resp.status_code == 201, ds_resp.text
        dataset_id = ds_resp.json()["id"]

        for idx, (text, label) in enumerate(REGRESSION_BASELINE_EXAMPLES[:2]):
            ex_resp = client.post(
                f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}/examples",
                json={
                    "text": text,
                    "label": label,
                    "source": "human",
                    "source_type": "human_verified",
                    "annotator": "qa-lead@acme.io",
                    "split": "regression",
                    "metadata": {
                        "source_type": "human_verified",
                        "label_source": "human_verified",
                        "verified_by": "qa-lead@acme.io",
                        "evidence_refs": [f"live-reg-{idx + 1}"],
                    },
                },
            )
            assert ex_resp.status_code == 201, ex_resp.text

        for idx, text in enumerate(UNSEEN_HOLDOUT_EXAMPLES[:1]):
            ex_resp = client.post(
                f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}/examples",
                json={
                    "text": text,
                    "label": promoted_choice_key,
                    "source": "verified_external",
                    "source_type": "verified_holdout",
                    "annotator": "qa-lead@acme.io",
                    "split": "holdout",
                    "metadata": {
                        "source_type": "verified_holdout",
                        "label_source": "human_verified",
                        "verified_by": "qa-lead@acme.io",
                        "evidence_refs": [f"live-holdout-{idx + 1}"],
                    },
                },
            )
            assert ex_resp.status_code == 201, ex_resp.text

        seal_resp = client.post(f"/api/v1/projects/{project_id}/eval-datasets/{dataset_id}/seal")
        assert seal_resp.status_code == 200, seal_resp.text

        eval_resp = _post_live(
            client,
            f"/api/v1/projects/{project_id}/evaluations",
            json={"dataset_id": dataset_id, "candidate_id": candidate_id},
        )
        assert eval_resp.status_code == 201, eval_resp.text
        evaluation = eval_resp.json()
        assert evaluation["is_simulated"] is False
        assert evaluation["overall_passed"] is True
        assert evaluation["metrics"]["regressions"] == 0
        assert evaluation["metrics"]["zero_regressions"] is True
        assert evaluation["metrics"]["holdout_metrics"]["holdout_examples"] >= 1
        assert (
            evaluation["metrics"]["baseline"]["coverage"]
            < evaluation["metrics"]["candidate"]["coverage"]
        )

        # Stage 6: Live Promotion to v2
        promote_resp = client.post(
            f"/api/v1/projects/{project_id}/discovery-candidates/{candidate_id}/promote",
            json={
                "evaluation_id": evaluation["id"],
                "reviewer": "lead-reviewer@acme.io",
                "rationale": "Live holdout evaluation passed with zero regressions.",
            },
        )
        assert promote_resp.status_code == 200, promote_resp.text
        promoted = promote_resp.json()
        assert promoted["version"]["version_number"] == 2
        assert promoted["added_class"] == promoted_choice_key

        unknowns_after = client.get(f"/api/v1/projects/{project_id}/unknowns").json()["items"]
        unknowns_by_run = {item["run_id"]: item for item in unknowns_after}
        for run_id in unknown_run_ids:
            assert unknowns_by_run[run_id]["status"] == "resolved"
            assert unknowns_by_run[run_id]["triage"]["status"] == "resolved"

    # Stage 6b: Fresh app with Teacher/discovery disabled classifies unseen transfer inputs on v2
    runtime_only_settings = Settings(
        database_url=database_url,
        decision_provider="openai-compatible",
        discovery_provider="none",
        supervisor_provider="mock",
        discovery_api_key=secret_key,
        discovery_base_url="https://ai-gateway.vercel.sh/v1",
        discovery_model="openai/gpt-4.1-mini",
        discovery_timeout_seconds=60.0,
    )
    replay_app = create_app(
        runtime_only_settings,
        choice_teacher=_DisabledChoiceTeacher(),
        diagnosis_provider=_DisabledDiagnosisProvider(),
    )
    with TestClient(replay_app) as replay_client:
        disabled_disc = replay_client.post(
            f"/api/v1/projects/{project_id}/clusters/{cluster_id}/discover"
        )
        assert disabled_disc.status_code == 502, disabled_disc.text
        assert disabled_disc.json().get("kind") == "unsupported"

        for transfer_text in STAGE_6_UNSEEN_TRANSFER_INPUTS[:1]:
            transfer_resp = _post_live(
                replay_client,
                f"/api/v1/projects/{project_id}/decision-services/{service_id}/runs",
                json={"content": transfer_text},
            )
            assert transfer_resp.status_code == 201, transfer_resp.text
            transfer_run = transfer_resp.json()[0]
            assert transfer_run["selected_choice"] == promoted_choice_key
            assert transfer_run["real_inference"] is True
            assert transfer_run["decision_service_version_id"] == promoted["version"]["id"]
