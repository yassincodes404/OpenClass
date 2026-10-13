"""Phase 15 operations dashboard: analytics, alert rules, resumable events."""

from __future__ import annotations

from fastapi.testclient import TestClient
from openclass_core.alerting import AlertRule, evaluate_rule, evaluate_rules


def test_rule_fires_only_on_real_breach():
    rule = AlertRule(id="r1", project_id="p1", metric="unknown_rate", threshold=0.10)
    assert evaluate_rule(rule, 0.05) is None
    assert evaluate_rule(rule, None) is None  # undefined never fires
    fired = evaluate_rule(rule, 0.14)
    assert fired is not None and fired["measured"] == 0.14


def test_evaluate_rules_collects_breaches():
    rules = [
        AlertRule(id="r1", project_id="p1", metric="unknown_rate", threshold=0.10),
        AlertRule(id="r2", project_id="p1", metric="latency", threshold=100),
    ]
    alerts = evaluate_rules(rules, {"unknown_rate": 0.2, "latency": 50})
    assert [alert["rule_id"] for alert in alerts] == ["r1"]


def _seed_runs(client: TestClient, slug: str, service: str, texts: list[str]) -> None:
    for text in texts:
        client.post(
            f"/api/v1/projects/{slug}/decision-services/{service}/runs", json={"content": text}
        )


def test_analytics_summary_measures_real_runs(mock_client: TestClient):
    slug = client_project(mock_client)
    service = client_service(mock_client, slug)
    _seed_runs(
        mock_client,
        slug,
        service,
        ["billing question one", "billing question two", "mystery text a", "mystery text b"],
    )
    summary = mock_client.get(f"/api/v1/projects/{slug}/analytics/summary").json()
    assert summary["unknown_rate"] == 0.5
    assert summary["top_classes"][0]["class"] in ("BILLING", "UNKNOWN")
    assert summary["daily"]
    assert summary["pending_reviews"] == 0
    assert isinstance(summary["simulated"], bool)


def client_project(client: TestClient) -> str:
    return client.post("/api/v1/projects", json={"name": "Ops Co"}).json()["slug"]


def client_service(client: TestClient, slug: str) -> str:
    return client.post(
        f"/api/v1/projects/{slug}/decision-services",
        json={
            "name": "Router",
            "instructions": "Route the request.",
            "choices": [{"key": "BILLING", "label": "Billing"}],
        },
    ).json()["id"]


def test_alert_rule_crud_and_evaluate(mock_client: TestClient):
    slug = client_project(mock_client)
    service = client_service(mock_client, slug)
    _seed_runs(mock_client, slug, service, ["billing ok", "mystery one", "mystery two"])
    created = mock_client.post(
        f"/api/v1/projects/{slug}/alerts/rules",
        json={"metric": "unknown_rate", "threshold": 0.5},
    )
    assert created.status_code == 201
    listed = mock_client.get(f"/api/v1/projects/{slug}/alerts/rules").json()
    assert len(listed) == 1
    bad = mock_client.post(
        f"/api/v1/projects/{slug}/alerts/rules", json={"metric": "vibes", "threshold": 1}
    )
    assert bad.status_code == 400
    evaluated = mock_client.post(f"/api/v1/projects/{slug}/alerts/evaluate").json()
    assert evaluated["fired"] == 1  # 2/3 unknown > 0.5
    summary = mock_client.get(f"/api/v1/projects/{slug}/analytics/summary").json()
    assert len(summary["recent_alerts"]) == 1


def test_event_stream_resumes_by_cursor(mock_client: TestClient):
    slug = client_project(mock_client)
    client_service(mock_client, slug)
    page_one = mock_client.get(f"/api/v1/projects/{slug}/ops/events?after=").json()
    assert isinstance(page_one["next_cursor"], str)
    cursor = page_one["next_cursor"]
    page_two = mock_client.get(f"/api/v1/projects/{slug}/ops/events?after={cursor}").json()
    assert page_two["next_cursor"] == cursor  # nothing new → cursor unchanged
    # SSE transport streams immediately and closes after idle.
    with mock_client.stream("GET", f"/api/v1/projects/{slug}/ops/events/stream?after=") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        chunks = b"".join(response.iter_bytes())
    assert b": keep-alive" in chunks or b"event: openclass" in chunks


def test_analytics_summary_disjoint_previous_window(mock_client: TestClient, database_url: str):
    from datetime import UTC, datetime, timedelta

    import sqlalchemy as sa

    slug = client_project(mock_client)
    service = client_service(mock_client, slug)
    # Seed 2 UNKNOWN runs that we backdate to 10 days ago (previous window)
    _seed_runs(mock_client, slug, service, ["mystery old one", "mystery old two"])
    sync_url = database_url.replace("+aiosqlite", "")
    engine = sa.create_engine(sync_url)
    ten_days_ago = datetime.now(UTC) - timedelta(days=10)
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE decision_runs SET created_at = :ts"),
            {"ts": ten_days_ago},
        )
    engine.dispose()
    # Seed 2 KNOWN runs in current window (today)
    _seed_runs(mock_client, slug, service, ["billing today one", "billing today two"])
    summary = mock_client.get(f"/api/v1/projects/{slug}/analytics/summary?days=7").json()
    assert summary["unknown_rate"] == 0.0
    assert summary["previous_unknown_rate"] == 1.0
    assert summary["unknown_rate_delta"] == -1.0
