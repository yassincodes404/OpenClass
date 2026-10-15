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


def test_analytics_summary_disjoint_previous_window(mock_client: TestClient, monkeypatch):
    from datetime import UTC, datetime, timedelta

    slug = client_project(mock_client)
    service = client_service(mock_client, slug)
    # History is immutable: inject the timestamp before the INSERT, never
    # UPDATE persisted runs to manufacture a historical cohort.
    repository = mock_client.app.state.project_repository
    create_run = repository.create_decision_run
    ten_days_ago = datetime.now(UTC) - timedelta(days=10)

    async def create_historical_run(run):
        await create_run(run.model_copy(update={"created_at": ten_days_ago}))

    with monkeypatch.context() as patch:
        patch.setattr(repository, "create_decision_run", create_historical_run)
        _seed_runs(mock_client, slug, service, ["mystery old one", "mystery old two"])
    # Seed 2 KNOWN runs in current window (today)
    _seed_runs(mock_client, slug, service, ["billing today one", "billing today two"])
    summary = mock_client.get(f"/api/v1/projects/{slug}/analytics/summary?days=7").json()
    assert summary["unknown_rate"] == 0.0
    assert summary["previous_unknown_rate"] == 1.0
    assert summary["unknown_rate_delta"] == -1.0


def test_hour_cost_alert_excludes_earlier_same_day_cost_and_reports_missing_prices(
    mock_client: TestClient,
    monkeypatch,
):
    from datetime import UTC, datetime, timedelta

    import openclass_server.api.operations as operations

    anchor = datetime(2026, 5, 25, 12, tzinfo=UTC)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return anchor if tz else anchor.replace(tzinfo=None)

    monkeypatch.setattr(operations, "datetime", FrozenDatetime)
    repository = mock_client.app.state.project_repository
    create_run = repository.create_decision_run

    async def timestamped_run(run):
        content = run.input_snapshot["content"]
        earlier = "earlier" in content
        metadata = {} if "unpriced" in content else {"estimated_cost": 1000.0 if earlier else 2.0}
        await create_run(
            run.model_copy(
                update={
                    "created_at": anchor
                    - (timedelta(hours=3) if earlier else timedelta(minutes=30)),
                    "provider_metadata": metadata,
                }
            )
        )

    monkeypatch.setattr(repository, "create_decision_run", timestamped_run)
    slug = client_project(mock_client)
    service = client_service(mock_client, slug)
    _seed_runs(mock_client, slug, service, ["billing earlier", "billing recent"])
    created = mock_client.post(
        f"/api/v1/projects/{slug}/alerts/rules",
        json={"metric": "cost", "threshold": 5},
    )
    assert created.status_code == 201
    evaluated = mock_client.post(f"/api/v1/projects/{slug}/alerts/evaluate").json()
    assert evaluated["fired"] == 0
    assert evaluated["measurements"]["cost"] == 2.0
    assert evaluated["measurements"]["cost_window"]["status"] == "complete"
    _seed_runs(mock_client, slug, service, ["billing unpriced"])
    evaluated = mock_client.post(f"/api/v1/projects/{slug}/alerts/evaluate").json()
    assert evaluated["fired"] == 0  # unknown is not a measured breach or a zero charge
    assert evaluated["measurements"]["cost"] is None
    assert evaluated["measurements"]["cost_window"]["status"] == "partial"
    assert evaluated["measurements"]["cost_window"]["declared_cost"] == 2.0
    assert evaluated["measurements"]["cost_window"]["missing_cost_attempts"] == 1


def test_summary_cost_windows_split_boundary_day_by_persisted_timestamps(
    mock_client: TestClient,
    monkeypatch,
):
    from datetime import UTC, datetime, timedelta

    import openclass_server.api.operations as operations

    anchor = datetime(2026, 5, 25, 12, tzinfo=UTC)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return anchor if tz else anchor.replace(tzinfo=None)

    monkeypatch.setattr(operations, "datetime", FrozenDatetime)
    repository = mock_client.app.state.project_repository
    create_run = repository.create_decision_run
    boundary = anchor - timedelta(days=7)

    async def timestamped_run(run):
        previous = "previous" in run.input_snapshot["content"]
        await create_run(
            run.model_copy(
                update={
                    "created_at": boundary + timedelta(minutes=-30 if previous else 30),
                    "provider_metadata": {"estimated_cost": 9.0 if previous else 3.0},
                }
            )
        )

    monkeypatch.setattr(repository, "create_decision_run", timestamped_run)
    slug = client_project(mock_client)
    service = client_service(mock_client, slug)
    _seed_runs(mock_client, slug, service, ["billing previous", "billing current"])
    response = mock_client.get(f"/api/v1/projects/{slug}/analytics/summary?days=7")
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["provider_cost"] == 3.0
    assert summary["previous_provider_cost"] == 9.0
    assert summary["provider_cost_measurement"]["status"] == "complete"
    assert summary["previous_provider_cost_measurement"]["status"] == "complete"
