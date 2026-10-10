"""Phase 13 replay evaluation: metric math on fixtures, gates, blocking behavior."""

from __future__ import annotations

from fastapi.testclient import TestClient
from openclass_core.evaluation_metrics import (
    Gates,
    accuracy,
    coverage,
    false_novelty_rate,
    macro_f1,
    per_class_accuracy,
    unknown_precision_recall,
)


def test_accuracy_hand_computed():
    pairs = [("BILLING", "BILLING"), ("BILLING", "UNKNOWN"), ("REFUND", "REFUND")]
    assert accuracy(pairs) == 2 / 3
    assert accuracy([]) is None


def test_per_class_accuracy_and_regression_detection():
    pairs = [
        ("BILLING", "BILLING"),
        ("BILLING", "BILLING"),
        ("BILLING", "OTHER"),
        ("REFUND", "REFUND"),
    ]
    assert per_class_accuracy(pairs, "BILLING") == 2 / 3
    assert per_class_accuracy(pairs, "ABSENT") is None


def test_macro_f1_hand_computed():
    # Perfect predictions → F1 = 1.
    assert macro_f1([("A", "A"), ("B", "B")]) == 1.0
    # All wrong → F1 = 0.
    assert macro_f1([("A", "B"), ("B", "A")]) == 0.0
    assert macro_f1([]) is None


def test_unknown_precision_recall():
    pairs = [
        ("UNKNOWN", "UNKNOWN"),
        ("UNKNOWN", "BILLING"),
        ("BILLING", "UNKNOWN"),
        ("BILLING", "BILLING"),
    ]
    precision, recall = unknown_precision_recall(pairs)
    assert precision == 1 / 2  # 1 true UNKNOWN of 2 predicted UNKNOWN
    assert recall == 1 / 2  # 1 of 2 gold UNKNOWN caught


def test_false_novelty_rate():
    pairs = [("BILLING", "UNKNOWN"), ("BILLING", "BILLING"), ("UNKNOWN", "UNKNOWN")]
    assert false_novelty_rate(pairs) == 1 / 2
    assert false_novelty_rate([]) is None


def test_coverage():
    assert coverage([("A", "A"), ("UNKNOWN", "UNKNOWN")]) == 0.5


def test_gates_block_on_regression_and_novelty():
    baseline = [("BILLING", "BILLING"), ("CANCEL_PLAN", "UNKNOWN")]
    candidate = [("BILLING", "UNKNOWN"), ("CANCEL_PLAN", "CANCEL_PLAN")]
    result = Gates(protected_classes=("BILLING",)).evaluate(baseline, candidate)
    by_gate = {gate["gate"]: gate for gate in result["gates"]}
    assert by_gate["no_billing_regression"]["passed"] is False
    assert result["overall_passed"] is False


def test_gates_pass_when_improving():
    baseline = [("BILLING", "BILLING"), ("CANCEL_PLAN", "UNKNOWN")]
    candidate = [("BILLING", "BILLING"), ("CANCEL_PLAN", "CANCEL_PLAN")]
    result = Gates(protected_classes=("BILLING",)).evaluate(baseline, candidate)
    assert result["overall_passed"] is True
    assert result["accuracy_delta"] == 0.5


def test_gates_fail_closed_on_undefined():
    result = Gates().evaluate([], [])
    assert result["overall_passed"] is False


def _setup_project(client: TestClient) -> tuple[str, str, str]:
    slug = client.post("/api/v1/projects", json={"name": "Replay Co"}).json()["slug"]
    service = client.post(
        f"/api/v1/projects/{slug}/decision-services",
        json={
            "name": "Router",
            "instructions": "Route the request.",
            "choices": [
                {"key": "BILLING", "label": "Billing"},
                {"key": "REFUND", "label": "Refund"},
            ],
        },
    ).json()["id"]
    return slug, service, ""


def _seed_cancel_dataset(client: TestClient, slug: str, label: str = "CANCEL_PLAN") -> str:
    dataset = client.post(
        f"/api/v1/projects/{slug}/eval-datasets", json={"name": "cancel-gold"}
    ).json()["id"]
    examples = [
        ("Cancel my plan immediately", label),
        ("How do I cancel this plan?", label),
        ("Please close my subscription", label),
        ("I want to unsubscribe", label),
        ("Terminate my recurring plan", label),
        ("Stop renewing my plan", label),
        ("I have a billing question", "BILLING"),
        ("Refund my last order", "REFUND"),
    ]
    for text, label in examples:
        response = client.post(
            f"/api/v1/projects/{slug}/eval-datasets/{dataset}/examples",
            json={
                "text": text,
                "label": label,
                "source": "human",
                "annotator": "annotator@acme.test",
            },
        )
        assert response.status_code == 201, response.text
    client.post(f"/api/v1/projects/{slug}/eval-datasets/{dataset}/seal")
    return dataset


def _seed_candidate(client: TestClient, slug: str, service: str) -> str:
    for text in [
        "Cancel my plan immediately",
        "Cancel my plan today please",
        "Cancel my plan once and for all",
        "Cancel my subscription plan now",
        "Cancel plan next month",
    ]:
        client.post(
            f"/api/v1/projects/{slug}/decision-services/{service}/runs", json={"content": text}
        )
    client.post(f"/api/v1/projects/{slug}/unknowns/cluster", json={"threshold": 0.2})
    clusters = client.get(f"/api/v1/projects/{slug}/unknowns/clusters").json()
    biggest = max(clusters, key=lambda entry: entry["size"])
    return client.post(f"/api/v1/projects/{slug}/clusters/{biggest['id']}/discover").json()["id"]


def test_replay_passes_when_cancel_improves_and_billing_holds(mock_client: TestClient):
    slug, service, _ = _setup_project(mock_client)
    candidate_id = _seed_candidate(mock_client, slug, service)
    canonical = (
        mock_client.get(f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}")
        .json()["canonical_name"]
        .upper()
    )
    dataset = _seed_cancel_dataset(mock_client, slug, label=canonical)
    evaluation = mock_client.post(
        f"/api/v1/projects/{slug}/evaluations",
        json={"dataset_id": dataset, "candidate_id": candidate_id},
    )
    assert evaluation.status_code == 201, evaluation.text
    body = evaluation.json()
    assert body["overall_passed"] is True
    gates = {gate["gate"]: gate for gate in body["gates"]}
    assert gates["no_billing_regression"]["passed"] is True
    metrics = body["metrics"]
    assert metrics["baseline"]["coverage"] < metrics["candidate"]["coverage"]
    assert metrics["simulated"] is True
    detail = mock_client.get(f"/api/v1/projects/{slug}/evaluations/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["overall_passed"] is True


def test_unsealed_dataset_cannot_be_evaluated(mock_client: TestClient):
    slug, service, _ = _setup_project(mock_client)
    dataset = client_post_dataset(mock_client, slug)
    candidate_id = _seed_candidate(mock_client, slug, service)
    response = mock_client.post(
        f"/api/v1/projects/{slug}/evaluations",
        json={"dataset_id": dataset, "candidate_id": candidate_id},
    )
    assert response.status_code == 400
    assert "sealed" in response.json()["detail"]


def client_post_dataset(client: TestClient, slug: str) -> str:
    return client.post(f"/api/v1/projects/{slug}/eval-datasets", json={"name": "unsealed"}).json()[
        "id"
    ]


def test_candidate_labels_accepted_for_gold_sets(mock_client: TestClient):
    """Annotating against a proposed class is legitimate ground truth."""
    slug, service, _ = _setup_project(mock_client)
    candidate_id = _seed_candidate(mock_client, slug, service)
    detail = mock_client.get(f"/api/v1/projects/{slug}/discovery-candidates/{candidate_id}").json()
    assert detail["canonical_name"], detail
    dataset = client_post_dataset(mock_client, slug)
    added = mock_client.post(
        f"/api/v1/projects/{slug}/eval-datasets/{dataset}/examples",
        json={
            "text": "stop my subscription",
            "label": detail["canonical_name"].upper(),
            "source": "human",
            "annotator": "annotator@acme.test",
        },
    )
    assert added.status_code == 201, added.text
