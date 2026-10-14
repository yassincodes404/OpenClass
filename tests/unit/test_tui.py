from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from openclass_sdk import OpenClass

_TUI_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "packages" / "tui"
if str(_TUI_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_TUI_PACKAGE_ROOT))

from openclass_tui import (  # noqa: E402
    OpenClassInspector,
    main,
    render_classifier_dashboard,
    render_project_dashboard,
)


def _build_project_mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/health/ready":
            return httpx.Response(200, json={"status": "ready", "schema": "0016_ops"})
        if path == "/api/v1/projects":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "proj-1",
                        "slug": "support-ops",
                        "name": "Support Ops",
                        "status": "active",
                    }
                ],
            )
        if path == "/api/v1/projects/support-ops":
            return httpx.Response(
                200,
                json={
                    "id": "proj-1",
                    "slug": "support-ops",
                    "name": "Support Ops",
                    "status": "active",
                },
            )
        if path == "/api/v1/projects/support-ops/summary":
            return httpx.Response(
                200,
                json={
                    "events": 14,
                    "decision_runs": 11,
                    "unknowns": 3,
                    "pending_evidence": 2,
                    "active_policy": "triage-v1",
                    "pending_candidates": 1,
                    "audit_events": 9,
                },
            )
        if path == "/api/v1/projects/support-ops/runs":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "run-101",
                        "selected_choice": "BILLING",
                        "supervision_outcome": "accepted",
                        "unknown_probability": 0.08,
                        "provider": "laya",
                        "execution_mode": "in_process",
                        "real_inference": True,
                    },
                    {
                        "id": "run-102",
                        "selected_choice": "UNKNOWN",
                        "supervision_outcome": "abstained_unknown",
                        "unknown_probability": 0.76,
                        "provider": "mock",
                        "execution_mode": "mock",
                        "real_inference": False,
                    },
                ],
            )
        if path == "/api/v1/projects/support-ops/unknowns":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "run_id": "run-102",
                            "content": "Please cancel my annual subscription immediately",
                            "unknown_probability": 0.76,
                            "triage": {"status": "triaged", "category": "novel_concept"},
                            "recurrence": 3,
                        }
                    ],
                    "next_cursor": None,
                },
            )
        if path == "/api/v1/projects/support-ops/unknowns/clusters":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "cluster-01",
                        "algorithm": "greedy-cosine-first-fit",
                        "model": "hash-lexical-v1",
                        "threshold": 0.82,
                        "size": 3,
                        "simulated": True,
                    }
                ],
            )
        if path == "/api/v1/projects/support-ops/discovery-candidates":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "cand-01",
                        "cluster_id": "cluster-01",
                        "type": "new_class",
                        "canonical_name": "cancellation",
                        "display_name": "Subscription Cancellation",
                        "confidence": 0.89,
                        "status": "validating",
                        "provider": "mock",
                        "simulated": True,
                        "evidence_count": 3,
                    }
                ],
            )
        return httpx.Response(404, json={"detail": f"Not found: {path}"})

    return httpx.MockTransport(handler)


def test_render_project_dashboard_renders_metrics_runs_unknowns_clusters_and_candidates() -> None:
    transport = _build_project_mock_transport()
    with OpenClass("http://testserver:7331", transport=transport) as client:
        output = render_project_dashboard(client, "support-ops")

    assert "OpenClass Terminal Inspector" in output
    assert "http://testserver:7331" in output
    assert "ready (schema 0016_ops)" in output
    assert "Support Ops (support-ops)" in output

    assert "events: 14" in output
    assert "decision_runs: 11" in output
    assert "unknowns: 3" in output
    assert "pending_evidence: 2" in output
    assert "pending_candidates: 1" in output
    assert "audit_events: 9" in output
    assert "active_policy: triage-v1" in output

    for column in (
        "id",
        "selected_choice",
        "supervision_outcome",
        "unknown_probability",
        "provider",
    ):
        assert column in output
    assert "run-101" in output
    assert "BILLING" in output
    assert "accepted" in output
    assert "0.08" in output
    assert "laya" in output
    assert "run-102" in output
    assert "abstained_unknown" in output
    assert "0.76" in output
    assert "mock [simulated]" in output

    assert "Unknown Pool & Clusters" in output
    assert "total unknowns: 3" in output
    assert "clusters: 1" in output
    assert "discovery candidates: 1" in output
    assert "cluster-01" in output
    assert "size=3" in output
    assert "threshold=0.82" in output
    assert "cand-01" in output
    assert "cancellation" in output
    assert "status=validating" in output
    assert "confidence=0.89" in output


def test_main_renders_project_dashboard_and_json_snapshot(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    transport = _build_project_mock_transport()
    original_init = OpenClass.__init__

    def patched_init(
        self: OpenClass, base_url: str = "http://localhost:7331", **kwargs: Any
    ) -> None:
        kwargs["transport"] = transport
        original_init(self, base_url, **kwargs)

    monkeypatch.setattr(OpenClass, "__init__", patched_init)

    main(["--server", "http://testserver:7331", "--project", "support-ops"])
    rendered = capsys.readouterr().out
    assert "Support Ops (support-ops)" in rendered
    assert "Recent Decision Runs" in rendered
    assert "Unknown Pool & Clusters" in rendered

    main(["--server", "http://testserver:7331", "--project", "support-ops", "--json"])
    snapshot = json.loads(capsys.readouterr().out)
    assert snapshot["kind"] == "project"
    assert snapshot["project"]["slug"] == "support-ops"
    assert snapshot["summary"]["events"] == 14
    assert len(snapshot["decision_runs"]) == 2
    assert snapshot["unknown_pool"]["total_unknowns"] == 3
    assert snapshot["unknown_pool"]["clusters"][0]["id"] == "cluster-01"
    assert snapshot["unknown_pool"]["discovery_candidates"][0]["canonical_name"] == "cancellation"


def test_main_auto_selects_first_project_and_supports_legacy_classifier(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def classifier_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/health/ready":
            return httpx.Response(200, json={"status": "ready"})
        if path == "/api/v1/classifiers/support-intent/ontology":
            return httpx.Response(
                200,
                json={"classifier_id": "clf-1", "version_number": 2, "classes": []},
            )
        if path == "/api/v1/classifiers/support-intent/runs":
            return httpx.Response(
                200,
                json=[
                    {
                        "observation": {"id": "obs-1", "content": "billing issue"},
                        "result": {
                            "id": "crun-1",
                            "selected_class": "billing",
                            "decision": {"provider": "mock", "unknown_probability": 0.12},
                            "novelty": {"state": "known"},
                        },
                    }
                ],
            )
        if path == "/api/v1/classifiers/support-intent/unknowns":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "unk-1",
                        "review_state": "pending",
                        "observation": {"content": "unfamiliar request"},
                    }
                ],
            )
        if path == "/api/v1/classifiers/support-intent/candidates":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "ccand-1",
                        "canonical_name": "refund_status",
                        "proposal_type": "new_class",
                        "status": "candidate",
                        "confidence": 0.81,
                        "discovery_provider": "mock",
                    }
                ],
            )
        return httpx.Response(404, json={"detail": "Not found"})

    transport = httpx.MockTransport(classifier_handler)
    with OpenClass("http://testserver:7331", transport=transport) as client:
        output = render_classifier_dashboard(client, "support-intent")
        assert "support-intent" in output
        assert "crun-1" in output
        assert "refund_status" in output

    project_transport = _build_project_mock_transport()
    original_init = OpenClass.__init__

    def patched_init(
        self: OpenClass, base_url: str = "http://localhost:7331", **kwargs: Any
    ) -> None:
        kwargs["transport"] = project_transport
        original_init(self, base_url, **kwargs)

    monkeypatch.setattr(OpenClass, "__init__", patched_init)
    main(["--server", "http://testserver:7331"])
    auto_out = capsys.readouterr().out
    assert "Support Ops (support-ops)" in auto_out


def test_http_errors_and_connection_failures_are_handled_cleanly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def not_found_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health/ready":
            return httpx.Response(200, json={"status": "ready"})
        return httpx.Response(404, json={"detail": "Project missing-proj not found"})

    error_transport = httpx.MockTransport(not_found_handler)
    with OpenClass("http://testserver:7331", transport=error_transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            OpenClassInspector(client).render_project("missing-proj")

    original_init = OpenClass.__init__

    def patched_http_error_init(
        self: OpenClass, base_url: str = "http://localhost:7331", **kwargs: Any
    ) -> None:
        kwargs["transport"] = error_transport
        original_init(self, base_url, **kwargs)

    monkeypatch.setattr(OpenClass, "__init__", patched_http_error_init)
    with pytest.raises(SystemExit) as http_exit:
        main(["--project", "missing-proj"])
    assert http_exit.value.code == 1
    err_output = capsys.readouterr().err
    assert "HTTP 404" in err_output

    def connect_error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    connect_transport = httpx.MockTransport(connect_error_handler)

    def patched_connect_error_init(
        self: OpenClass, base_url: str = "http://localhost:7331", **kwargs: Any
    ) -> None:
        kwargs["transport"] = connect_transport
        original_init(self, base_url, **kwargs)

    monkeypatch.setattr(OpenClass, "__init__", patched_connect_error_init)
    with pytest.raises(SystemExit) as conn_exit:
        main(["--project", "support-ops"])
    assert conn_exit.value.code == 1
    conn_err = capsys.readouterr().err
    assert "could not reach server" in conn_err
