import json

import httpx
import pytest
from openclass_sdk import OpenClass


def test_sdk_uses_public_protocol() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/classifiers/support-intent/classify"
        assert json.loads(request.content) == {"observation": "hello", "metadata": {}}
        return httpx.Response(200, json={"selected_class": None})

    with OpenClass(transport=httpx.MockTransport(handle)) as client:
        assert (
            client.classify(classifier="support-intent", observation="hello")["selected_class"]
            is None
        )


def test_sdk_does_not_hide_http_errors() -> None:
    with OpenClass(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        with pytest.raises(httpx.HTTPStatusError):
            client.health()


def test_sdk_requests_runs_and_reviews_over_public_routes() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/api/v1/classifiers/support-intent/runs/run-1/reviews"
            assert json.loads(request.content) == {"trigger": "manual"}
            return httpx.Response(201, json={"id": "review", "result": {"finding": "no_issue"}})
        if request.url.path == "/api/v1/classifiers/support-intent/runs/run-1":
            return httpx.Response(200, json={"observation": {"content": "x"}, "result": {}})
        assert request.url.path in (
            "/api/v1/classifiers/support-intent/runs",
            "/api/v1/classifiers/support-intent/reviews",
        )
        return httpx.Response(200, json=[])

    with OpenClass(transport=httpx.MockTransport(handle)) as client:
        assert client.review_run(classifier="support-intent", run_id="run-1")["id"] == "review"
        assert client.reviews("support-intent") == []
        assert client.runs("support-intent") == []
        assert client.run("support-intent", "run-1")["observation"]["content"] == "x"


def test_sdk_rejects_candidate_over_public_route() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        base = "/api/v1/classifiers/a%2Fb/candidates"
        if request.method == "GET":
            assert request.url.raw_path.decode() == base
            return httpx.Response(200, json=[{"id": "candidate-1", "status": "candidate"}])
        assert request.url.raw_path.decode() == f"{base}/candidate-1/reject"
        assert json.loads(request.content) == {"reason": "Wrong concept"}
        return httpx.Response(200, json={"id": "candidate-1", "status": "rejected"})

    with OpenClass(transport=httpx.MockTransport(handle)) as client:
        assert client.candidates("a/b")[0]["id"] == "candidate-1"
        assert client.reject_candidate("a/b", "candidate-1", "Wrong concept")["status"] == (
            "rejected"
        )


def test_sdk_requests_events_and_provider_status() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/projects/my-proj/events" and request.method == "POST":
            data = json.loads(request.content)
            assert data["content"] == "some event text"
            return httpx.Response(201, json={"id": "evt-1", **data})
        if request.url.path == "/api/v1/projects/my-proj/events/batch" and request.method == "POST":
            data = json.loads(request.content)
            assert len(data["items"]) == 2
            return httpx.Response(
                207,
                json={
                    "items": [
                        {"index": 0, "status": 201, "deduped": False, "event": {"id": "evt-2"}},
                        {"index": 1, "status": 201, "deduped": False, "event": {"id": "evt-3"}},
                    ]
                },
            )
        if request.url.path == "/api/v1/projects/my-proj/events" and request.method == "GET":
            return httpx.Response(200, json=[{"id": "evt-1"}])
        if request.url.path == "/api/v1/projects/my-proj/events/evt-1":
            return httpx.Response(200, json={"id": "evt-1", "content": "some event text"})
        if request.url.path == "/api/v1/providers/status":
            return httpx.Response(
                200, json={"default_provider": "laya", "laya": {"status": "ready"}}
            )
        return httpx.Response(404)

    with OpenClass(transport=httpx.MockTransport(handle)) as client:
        created = client.create_event("my-proj", content="some event text")
        assert created["id"] == "evt-1"
        batch = client.create_events_batch("my-proj", items=[{"content": "a"}, {"content": "b"}])
        assert len(batch) == 2
        listed = client.events("my-proj")
        assert len(listed) == 1
        fetched = client.event("my-proj", "evt-1")
        assert fetched["content"] == "some event text"
        status = client.provider_status()
        assert status["default_provider"] == "laya"


def test_sdk_requests_decision_services_and_runs() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        base = "/api/v1/projects/my-proj/decision-services"
        if path == base and method == "POST":
            data = json.loads(request.content)
            assert data["name"] == "Lead Routing"
            return httpx.Response(201, json={"id": "svc-1", "slug": "lead-routing", **data})
        if path == base and method == "GET":
            return httpx.Response(200, json=[{"id": "svc-1", "name": "Lead Routing"}])
        if path == f"{base}/svc-1" and method == "GET":
            return httpx.Response(200, json={"id": "svc-1", "name": "Lead Routing"})
        if path == f"{base}/svc-1" and method == "PATCH":
            data = json.loads(request.content)
            return httpx.Response(200, json={"id": "svc-1", "name": data.get("name")})
        if path == f"{base}/svc-1/runs" and method == "POST":
            data = json.loads(request.content)
            assert data["raw_event_ids"] == ["evt-1"]
            return httpx.Response(201, json=[{"id": "run-1", "selected_choice": "ENTERPRISE"}])
        if path == "/api/v1/projects/my-proj/runs" and method == "GET":
            return httpx.Response(200, json=[{"id": "run-1"}])
        if path == "/api/v1/projects/my-proj/runs/run-1" and method == "GET":
            return httpx.Response(200, json={"id": "run-1", "selected_choice": "ENTERPRISE"})
        return httpx.Response(404)

    with OpenClass(transport=httpx.MockTransport(handle)) as client:
        svc = client.create_decision_service(
            "my-proj",
            name="Lead Routing",
            instructions="Route leads",
            choices=[{"key": "ENTERPRISE", "label": "Enterprise"}],
        )
        assert svc["id"] == "svc-1"
        services = client.decision_services("my-proj")
        assert len(services) == 1
        service_single = client.decision_service("my-proj", "svc-1")
        assert service_single["id"] == "svc-1"
        updated = client.update_decision_service("my-proj", "svc-1", name="Updated Routing")
        assert updated["name"] == "Updated Routing"
        runs = client.execute_decision_runs("my-proj", "svc-1", raw_event_ids=["evt-1"])
        assert len(runs) == 1
        assert runs[0]["selected_choice"] == "ENTERPRISE"
        runs_list = client.decision_runs("my-proj")
        assert len(runs_list) == 1
        single_run = client.decision_run("my-proj", "run-1")
        assert single_run["selected_choice"] == "ENTERPRISE"


def test_sdk_requests_evidence_and_evolution() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        if path == "/api/v1/projects/my-proj/evidence" and method == "GET":
            return httpx.Response(200, json=[{"id": "ev-1", "status": "pending"}])
        if path == "/api/v1/projects/my-proj/evidence/ev-1" and method == "GET":
            return httpx.Response(200, json={"id": "ev-1", "status": "pending"})
        if path == "/api/v1/projects/my-proj/evidence/ev-1/triage" and method == "PATCH":
            body = json.loads(request.content)
            return httpx.Response(200, json={"id": "ev-1", "status": "triaged", **body})
        if path == "/api/v1/projects/my-proj/evidence/ev-1/transition" and method == "POST":
            body = json.loads(request.content)
            return httpx.Response(200, json={"id": "ev-1", "status": body["target_status"]})
        if path == "/api/v1/projects/my-proj/evidence/ev-1/ai-diagnose" and method == "POST":
            return httpx.Response(
                200,
                json={
                    "diagnosis": "decision_space",
                    "rationale": "Missing option",
                    "confidence": 0.9,
                    "recommended_action": "Add choice",
                    "provider": "gemini",
                    "model": "gemini-2.5-flash",
                    "simulated": False,
                },
            )
        if path == "/api/v1/projects/my-proj/runs/run-1/feedback" and method == "POST":
            body = json.loads(request.content)
            return httpx.Response(201, json={"id": "fb-1", **body})
        if path == "/api/v1/projects/my-proj/runs/run-1/feedback" and method == "GET":
            return httpx.Response(200, json=[{"id": "fb-1", "action": "confirm"}])
        if path == "/api/v1/projects/my-proj/evidence-cases" and method == "POST":
            body = json.loads(request.content)
            return httpx.Response(201, json={"id": "case-1", **body})
        if path == "/api/v1/projects/my-proj/evidence-cases" and method == "GET":
            return httpx.Response(200, json=[{"id": "case-1", "title": "Case 1"}])
        if path == "/api/v1/projects/my-proj/evidence-cases/case-1" and method == "GET":
            return httpx.Response(200, json={"id": "case-1", "title": "Case 1"})
        if path == "/api/v1/projects/my-proj/evidence-cases/case-1/evidence" and method == "GET":
            return httpx.Response(200, json=[{"id": "ev-1"}])
        if path == "/api/v1/projects/my-proj/evidence-cases/case-1/evidence" and method == "POST":
            return httpx.Response(200, json={"id": "case-1"})
        if path == "/api/v1/projects/my-proj/evolution/summary" and method == "GET":
            return httpx.Response(200, json={"project_id": "my-proj", "pending_evidence": 1})
        return httpx.Response(404)

    with OpenClass(transport=httpx.MockTransport(handle)) as client:
        ev_list = client.evidence("my-proj")
        assert len(ev_list) == 1
        ev = client.evidence_item("my-proj", "ev-1")
        assert ev["id"] == "ev-1"
        triaged = client.triage_evidence("my-proj", "ev-1", diagnosis="decision_space")
        assert triaged["status"] == "triaged"
        trans = client.transition_evidence("my-proj", "ev-1", target_status="ready_for_evolution")
        assert trans["status"] == "ready_for_evolution"
        diag = client.ai_diagnose_evidence("my-proj", "ev-1")
        assert diag["diagnosis"] == "decision_space"
        fb = client.submit_run_feedback("my-proj", "run-1", action="confirm")
        assert fb["id"] == "fb-1"
        fb_list = client.run_feedback("my-proj", "run-1")
        assert len(fb_list) == 1
        case = client.create_evidence_case("my-proj", title="Case 1")
        assert case["id"] == "case-1"
        cases = client.evidence_cases("my-proj")
        assert len(cases) == 1
        single_case = client.evidence_case("my-proj", "case-1")
        assert single_case["id"] == "case-1"
        case_ev = client.case_evidence("my-proj", "case-1")
        assert len(case_ev) == 1
        added = client.add_evidence_to_case("my-proj", "case-1", evidence_id="ev-1")
        assert added["id"] == "case-1"
        summary = client.evolution_summary("my-proj")
        assert summary["pending_evidence"] == 1


def test_project_candidate_and_evolution_public_protocol() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method

        if path == "/api/v1/projects/my-proj/candidates" and method == "GET":
            return httpx.Response(200, json=[{"id": "cand-1", "status": "candidate"}])
        if path == "/api/v1/projects/my-proj/candidates/cand-1" and method == "GET":
            return httpx.Response(200, json={"id": "cand-1", "status": "candidate"})
        if (
            path == "/api/v1/projects/my-proj/decision-services/svc-1/candidates"
            and method == "POST"
        ):
            body = json.loads(request.content)
            return httpx.Response(201, json={"id": "cand-1", "evidence_run_ids": body["run_ids"]})
        if path == "/api/v1/projects/my-proj/evolution/propose" and method == "POST":
            return httpx.Response(201, json={"id": "cand-2", "status": "candidate"})
        if path == "/api/v1/projects/my-proj/candidates/cand-1/evaluate" and method == "POST":
            return httpx.Response(
                200,
                json={
                    "candidate_id": "cand-1",
                    "decision_service_id": "svc-1",
                    "passed": True,
                    "accuracy_on_knowns": 1.0,
                    "disambiguation_rate": 1.0,
                    "regressions": [],
                },
            )
        if path == "/api/v1/projects/my-proj/candidates/cand-1/promote" and method == "POST":
            return httpx.Response(
                200,
                json={
                    "candidate": {"id": "cand-1", "status": "promoted"},
                    "decision_service": {"id": "svc-1", "status": "active"},
                },
            )
        if path == "/api/v1/projects/my-proj/candidates/cand-1/reject" and method == "POST":
            body = json.loads(request.content)
            return httpx.Response(
                200,
                json={"id": "cand-1", "status": "rejected", "rejection_reason": body["reason"]},
            )
        return httpx.Response(404)

    with OpenClass(transport=httpx.MockTransport(handle)) as client:
        cands = client.project_candidates("my-proj")
        assert len(cands) == 1
        cand = client.project_candidate("my-proj", "cand-1")
        assert cand["id"] == "cand-1"
        proposed = client.propose_project_choice("my-proj", "svc-1", run_ids=["r1", "r2", "r3"])
        assert proposed["id"] == "cand-1"
        from_ev = client.propose_from_evidence(
            "my-proj", service_id="svc-1", evidence_ids=["e1", "e2", "e3"]
        )
        assert from_ev["id"] == "cand-2"
        eval_res = client.evaluate_project_candidate("my-proj", "cand-1")
        assert eval_res["passed"] is True
        promoted = client.promote_project_candidate("my-proj", "cand-1", note="Approved")
        assert promoted["candidate"]["status"] == "promoted"
        rejected = client.reject_project_choice("my-proj", "cand-1", reason="Duplicate")
        assert rejected["status"] == "rejected"


def test_sdk_integrations_and_system_health() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        if path == "/api/v1/system/health" and method == "GET":
            return httpx.Response(
                200,
                json={
                    "status": "healthy",
                    "database": {"connected": True, "latency_ms": 2.1},
                    "decision_provider": "laya",
                    "discovery_provider": "mock",
                    "version": "0.0.1",
                },
            )
        if path == "/api/v1/projects/my-proj/integrations" and method == "GET":
            return httpx.Response(200, json=[{"id": "int-1", "name": "MCP Server", "type": "mcp"}])
        if path == "/api/v1/projects/my-proj/integrations" and method == "POST":
            body = json.loads(request.content)
            return httpx.Response(201, json={"id": "int-1", "status": "pending", **body})
        if path == "/api/v1/projects/my-proj/integrations/int-1" and method == "GET":
            return httpx.Response(200, json={"id": "int-1", "name": "MCP Server", "type": "mcp"})
        if path == "/api/v1/projects/my-proj/integrations/int-1" and method == "PATCH":
            body = json.loads(request.content)
            return httpx.Response(200, json={"id": "int-1", **body})
        if path == "/api/v1/projects/my-proj/integrations/int-1" and method == "DELETE":
            return httpx.Response(204)
        if path == "/api/v1/projects/my-proj/integrations/int-1/test" and method == "POST":
            return httpx.Response(
                200,
                json={
                    "integration_id": "int-1",
                    "status": "connected",
                    "latency_ms": 12.0,
                    "capabilities": ["tools/list"],
                    "error_message": None,
                },
            )
        return httpx.Response(404)

    with OpenClass(transport=httpx.MockTransport(handle)) as client:
        health = client.system_health()
        assert health["status"] == "healthy"
        assert health["database"]["connected"] is True

        created = client.create_project_integration(
            "my-proj",
            name="MCP Server",
            type="mcp",
            endpoint="https://mcp.internal",
            capabilities=["tools/list"],
        )
        assert created["id"] == "int-1"
        assert created["name"] == "MCP Server"

        integrations = client.project_integrations("my-proj")
        assert len(integrations) == 1
        assert integrations[0]["id"] == "int-1"

        detail = client.project_integration("my-proj", "int-1")
        assert detail["id"] == "int-1"

        updated = client.update_project_integration("my-proj", "int-1", name="Updated MCP")
        assert updated["name"] == "Updated MCP"

        tested = client.test_project_integration("my-proj", "int-1")
        assert tested["status"] == "connected"
        assert tested["latency_ms"] == 12.0

        client.delete_project_integration("my-proj", "int-1")


def test_sdk_webhook_identity_and_token_are_separate() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/projects/my-proj/integrations/int-1/webhook"
        assert request.headers["X-OpenClass-Token"] == "test-token"
        body = json.loads(request.content)
        assert body["event_key"] == "ticket:revision:1"
        assert "test-token" not in request.content.decode()
        return httpx.Response(200, json={"status": "duplicate", "event_id": "existing-event"})

    with OpenClass(transport=httpx.MockTransport(handle)) as client:
        response = client.ingest_integration_webhook(
            "my-proj",
            "int-1",
            event_key="ticket:revision:1",
            content="Customer message",
            token="test-token",
        )
        assert response["status"] == "duplicate"
