"""Phase 8 UNKNOWN workspace: pool, triage, transitions, stats."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _setup(client: TestClient) -> tuple[str, str]:
    slug = client.post("/api/v1/projects", json={"name": "Unknown Co"}).json()["slug"]
    service = client.post(
        f"/api/v1/projects/{slug}/decision-services",
        json={
            "name": "Router",
            "instructions": "Route the message to an intent.",
            "choices": [{"key": "BILLING", "label": "Billing"}],
        },
    ).json()["id"]
    return slug, service


def _run(client: TestClient, slug: str, service: str, content: str) -> dict:
    runs = client.post(
        f"/api/v1/projects/{slug}/decision-services/{service}/runs", json={"content": content}
    )
    assert runs.status_code == 201, runs.text
    return runs.json()[0]


def test_unknown_pool_lists_unknown_runs_with_redacted_preview(mock_client: TestClient):
    slug, service = _setup(mock_client)
    known = _run(mock_client, slug, service, "billing question about my invoice")
    unknown = _run(mock_client, slug, service, "Someone changed my account email at a@b.co")
    pool = mock_client.get(f"/api/v1/projects/{slug}/unknowns").json()
    ids = [item["run_id"] for item in pool["items"]]
    assert unknown["id"] in ids
    assert known["id"] not in ids
    preview = next(item for item in pool["items"] if item["run_id"] == unknown["id"])
    assert "a@b.co" not in preview["content"]
    assert preview["triage"]["status"] == "needs_evidence"


def test_triage_updates_state_without_mutating_runs(mock_client: TestClient):
    slug, service = _setup(mock_client)
    run = _run(mock_client, slug, service, "weird account activity")
    triaged = mock_client.post(
        f"/api/v1/projects/{slug}/unknowns/{run['id']}/triage",
        json={"category": "missing_info", "assignee": "reviewer-1", "note": "needs more context"},
    )
    assert triaged.status_code == 200
    assert triaged.json()["category"] == "missing_info"
    assert triaged.json()["status"] == "needs_evidence"
    # The run itself is unchanged.
    detail = mock_client.get(f"/api/v1/projects/{slug}/runs/{run['id']}").json()
    assert detail["selected_choice"] == run["selected_choice"]
    # Stats now count the category.
    stats = mock_client.get(f"/api/v1/projects/{slug}/unknowns/stats").json()
    assert stats["by_category"].get("missing_info") == 1


def test_transition_validation_rejects_invalid_moves(mock_client: TestClient):
    slug, service = _setup(mock_client)
    run = _run(mock_client, slug, service, "another odd message")
    base = f"/api/v1/projects/{slug}/unknowns/{run['id']}/transition"
    assert mock_client.post(base, json={"to": "triaged"}).status_code == 200
    # triaged -> needs_evidence is not allowed.
    rejected = mock_client.post(base, json={"to": "needs_evidence"})
    assert rejected.status_code == 400
    # dismissed is terminal.
    assert mock_client.post(base, json={"to": "dismissed"}).status_code == 200
    terminal = mock_client.post(base, json={"to": "triaged"})
    assert terminal.status_code == 400


def test_unknown_stats_show_rate_and_phrases(mock_client: TestClient):
    slug, service = _setup(mock_client)
    _run(mock_client, slug, service, "billing issue here")
    for text in ("cancel my plan now", "end my membership today", "stop renewing my plan"):
        _run(mock_client, slug, service, text)
    stats = mock_client.get(f"/api/v1/projects/{slug}/unknowns/stats").json()
    assert stats["total_runs"] == 4
    assert stats["total_unknown"] == 3
    assert stats["unknown_rate"] == 0.75
    assert "plan" in stats["top_phrases"]
    assert stats["daily"]


def test_filters_and_search(mock_client: TestClient):
    slug, service = _setup(mock_client)
    run = _run(mock_client, slug, service, "cancel my plan")
    mock_client.post(
        f"/api/v1/projects/{slug}/unknowns/{run['id']}/triage", json={"category": "out_of_scope"}
    )
    assert mock_client.get(f"/api/v1/projects/{slug}/unknowns?category=out_of_scope").json()[
        "items"
    ]
    assert not mock_client.get(f"/api/v1/projects/{slug}/unknowns?category=missing_info").json()[
        "items"
    ]
    assert mock_client.get(f"/api/v1/projects/{slug}/unknowns?query=cancel").json()["items"]
    assert not mock_client.get(f"/api/v1/projects/{slug}/unknowns?query=refund").json()["items"]


def test_cross_project_unknown_is_not_listed(mock_client: TestClient):
    slug_a, service_a = _setup(mock_client)
    slug_b, _service_b = _setup(mock_client)
    run = _run(mock_client, slug_a, service_a, "mystery message from project a")
    pool_b = mock_client.get(f"/api/v1/projects/{slug_b}/unknowns").json()
    assert all(item["run_id"] != run["id"] != "" for item in pool_b["items"])


def test_project_audit_and_summary_succeed_after_triage_and_clustering(
    mock_client: TestClient,
):
    slug, service = _setup(mock_client)
    r1 = _run(mock_client, slug, service, "cancel my plan")
    _run(mock_client, slug, service, "cancel my subscription")
    _run(mock_client, slug, service, "please cancel plan")

    assert (
        mock_client.post(
            f"/api/v1/projects/{slug}/unknowns/{r1['id']}/triage",
            json={"category": "out_of_scope", "note": "candidate for cancellation"},
        ).status_code
        == 200
    )
    assert (
        mock_client.post(
            f"/api/v1/projects/{slug}/unknowns/{r1['id']}/transition",
            json={"to": "triaged"},
        ).status_code
        == 200
    )
    assert (
        mock_client.post(
            f"/api/v1/projects/{slug}/unknowns/cluster",
            json={"threshold": 0.1},
        ).status_code
        == 200
    )

    audit_res = mock_client.get(f"/api/v1/projects/{slug}/audit")
    assert audit_res.status_code == 200
    event_types = [ev["event_type"] for ev in audit_res.json()]
    assert "unknown.triaged" in event_types
    assert "unknown.transitioned" in event_types
    assert "cluster.updated" in event_types

    summary_res = mock_client.get(f"/api/v1/projects/{slug}/summary")
    assert summary_res.status_code == 200
    assert summary_res.json()["audit_events"] >= 3



