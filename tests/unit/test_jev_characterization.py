"""Offline tests of the Jev characterization harness; no network, no live artifacts."""

import importlib
import json

import httpx
import pytest
from openclass_provider_jev import UNKNOWN as WIRE_UNKNOWN

KEY = "synthetic-test-credential"


@pytest.fixture
def jc(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    return importlib.import_module("jev_characterization")


def wire_body(criteria: dict[str, object], chosen: str) -> dict[str, object]:
    middles = [name for name in criteria if name not in (chosen, WIRE_UNKNOWN)]
    rest = (1 - 0.7 - 0.05) / len(middles) if middles else 0.0
    unknown_value = 0.05 + ((1 - 0.7 - 0.05) if not middles else 0.0)
    probabilities = {
        name: 0.7 if name == chosen else unknown_value if name == WIRE_UNKNOWN else rest
        for name in criteria
    }
    return {
        "model": "typesafe-ai/jev",
        "answers": {
            "classification": {
                "type": "choice",
                "choice": chosen,
                "confidence": 0.8,
                "probabilities": probabilities,
            }
        },
        "usage": {"input_tokens": 100, "output_tokens": 10},
        "provider_metadata": {"gateway": {"cost": "0.0001"}},
    }


def mock_transport(jc, state, budget, record, fail_on=None):
    def handle(request: httpx.Request) -> httpx.Response:
        state["count"] += 1
        if fail_on is not None and state["count"] == fail_on:
            return httpx.Response(500)
        criteria = json.loads(request.content)["questions"]["classification"]["criteria"]
        chosen = next(name for name in criteria if name != WIRE_UNKNOWN)
        return httpx.Response(200, json=wire_body(criteria, chosen))

    inner = httpx.MockTransport(handle)
    return jc.BudgetedJevTransport(budget, record, inner=inner)


def test_manifest_is_locked_and_complete(jc):
    cases = jc.load_cases(jc.MANIFEST)
    assert len(cases) == 176
    suites = {case["suite"] for case in cases}
    assert len(suites) == 14
    assert sum(1 for c in cases if c["expected"] == "UNKNOWN") == 14


def test_decision_rule_treats_unknown_tie_as_unknown(jc):
    result = jc.ChoiceResult(
        provider="jev",
        model="typesafe-ai/jev",
        probabilities={"a": 0.6, "b": 0.3},
        unknown_probability=0.1,
    )
    assert jc.decide(result) == "a"
    tied = result.model_copy(update={"unknown_probability": 0.6})
    assert jc.decide(tied) == "UNKNOWN"


def test_ontology_building_is_deterministic(jc):
    entry = jc.load_cases(jc.MANIFEST)[0]
    first = jc.ontology_for(entry).model_dump(mode="json")
    second = jc.ontology_for(entry).model_dump(mode="json")
    assert first == second


def test_transport_allowlists_url_and_enforces_budget(jc, monkeypatch):
    async def instant(_seconds):
        pass

    monkeypatch.setattr("asyncio.sleep", instant)
    budget = jc.Budget(1)

    def record(attempt):
        pass

    async def drive():
        calls = {"count": 0}

        def handle(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            return httpx.Response(500 if calls["count"] == 1 else 201)

        transport = jc.BudgetedJevTransport(budget, record, inner=httpx.MockTransport(handle))
        foreign = httpx.Request("POST", "https://example.com/v1/systemone")
        with pytest.raises(AssertionError):
            await transport.handle_async_request(foreign)
        jev_request = httpx.Request("POST", jc.JEV_URL, content=b"{}")
        # A server failure reaches no model and consumes no budget.
        rejected = await transport.handle_async_request(jev_request)
        assert rejected.status_code == 500
        assert budget.accepted == 0
        ok = await transport.handle_async_request(jev_request)
        assert ok.status_code == 201
        assert budget.accepted == 1
        with pytest.raises(jc.BudgetExhausted):
            await transport.handle_async_request(jev_request)
        assert budget.accepted == 1

    import asyncio

    asyncio.run(drive())


def test_rate_limited_requests_are_retried_and_not_counted(jc, monkeypatch):
    state = {"count": 0}

    async def instant(_seconds):
        pass

    monkeypatch.setattr("asyncio.sleep", instant)

    def handle(request: httpx.Request) -> httpx.Response:
        state["count"] += 1
        return httpx.Response(200 if state["count"] > 2 else 429, json={"ok": True})

    budget = jc.Budget(5)

    async def drive():
        transport = jc.BudgetedJevTransport(
            budget, lambda attempt: None, inner=httpx.MockTransport(handle)
        )
        response = await transport.handle_async_request(
            httpx.Request("POST", jc.JEV_URL, content=b"{}")
        )
        assert response.status_code == 200
        assert budget.accepted == 1
        assert budget.rate_limited == 2

    import asyncio

    asyncio.run(drive())


def test_run_completes_and_records_infrastructure_failure(jc, monkeypatch, tmp_path):
    state = {"count": 0}
    monkeypatch.setattr(jc, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        jc,
        "build_transport",
        lambda budget, record: mock_transport(jc, state, budget, record, fail_on=9),
    )
    exit_code = jc.execute(tmp_path, jc.MANIFEST, KEY)
    report = json.loads((tmp_path / "report.json").read_text())
    assert exit_code == 0
    assert report["status"] == "completed"
    assert report["cases_executed"] == 176
    assert report["accepted_inferences"] == 175
    assert report["rate_limited_requests"] == 0
    assert report["budget_used_including_this_run"] == 175
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["planned_cases"] == 176
    assert summary["infrastructure_failures"] == 1
    assert summary["ok_cases"] == 175
    assert summary["overall_accuracy"] is not None


def test_budget_exhaustion_stops_the_run_without_sending(jc, monkeypatch, tmp_path):
    state = {"count": 0}
    monkeypatch.setattr(jc, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        jc,
        "build_transport",
        lambda budget, record: mock_transport(jc, state, budget, record),
    )
    exit_code = jc.execute(tmp_path, jc.MANIFEST, KEY, budget_limit=10)
    report = json.loads((tmp_path / "report.json").read_text())
    assert exit_code == 3
    assert report["status"] == "budget_exhausted"
    assert report["accepted_inferences"] == 10
    assert report["cases_executed"] == 10
    jc.freeze(tmp_path, KEY)
    integrity = json.loads((tmp_path / "integrity.json").read_text())
    assert integrity["secret_material_absent"]


def test_freeze_detects_secret_material(jc, tmp_path):
    (tmp_path / "report.json").write_text(json.dumps({"request_budget": 250}))
    (tmp_path / "case-001.json").write_text(json.dumps({"note": KEY}))
    with pytest.raises(ValueError, match="secret"):
        jc.freeze(tmp_path, KEY)
    integrity = json.loads((tmp_path / "integrity.json").read_text())
    assert not integrity["secret_material_absent"]


def test_summary_metrics_from_synthetic_records(jc):
    def record(rid, suite, expected, selected, correct=True, **extra):
        probabilities = {expected: 0.8} if expected != "UNKNOWN" else {"x": 0.9}
        return {
            "id": rid,
            "suite": suite,
            "status": "ok",
            "expected": expected,
            "selected": selected,
            "correct": correct,
            "margin": 0.5,
            "latency_ms": 10.0,
            "input_tokens": 1,
            "output_tokens": 1,
            "estimated_cost": 0.0,
            "probabilities": probabilities,
            **extra,
        }

    records = [
        record("a1", "A_semantic_clarity", "restart_service", "restart_service"),
        record("h1", "H_unknown_behavior", "UNKNOWN", "UNKNOWN"),
        record("h2", "H_unknown_behavior", "UNKNOWN", "restart_service", correct=False),
        record("k1", "E_input_representation", "clear_cache", "UNKNOWN", correct=False),
        record("f1a", "F_paraphrase", "clear_cache", "clear_cache", pair=1),
        record(
            "f1b",
            "F_paraphrase",
            "clear_cache",
            "scale_deployment",
            correct=False,
            pair=1,
        ),
        record("g1a", "G_order_sensitivity", "disk_full", "disk_full", group=1, order="a"),
        record("g1b", "G_order_sensitivity", "disk_full", "disk_full", group=1, order="b"),
        record("ks1d1", "K_decision_depth", "web", "web", scenario="s", depth=1),
        record("ks1d2", "K_decision_depth", "crash_loop", "crash_loop", scenario="s", depth=2),
        record(
            "ks1d3",
            "K_decision_depth",
            "rollback",
            "escalate",
            correct=False,
            scenario="s",
            depth=3,
        ),
        record(
            "j1f",
            "J_flat_vs_hierarchical",
            "recycle_pod",
            "recycle_pod",
            scenario="s1",
            stage="flat",
        ),
        record(
            "j1l1",
            "J_flat_vs_hierarchical",
            "compute_actions",
            "compute_actions",
            scenario="s1",
            stage="hierarchy_level1",
        ),
        record(
            "j1l2",
            "J_flat_vs_hierarchical",
            "recycle_pod",
            "reboot_host",
            correct=False,
            scenario="s1",
            stage="hierarchy_level2",
        ),
        record(
            "n1s1",
            "N_reobservation",
            "restart_service",
            "restart_service",
            scenario="n1",
            step=1,
        ),
        record(
            "n1s2",
            "N_reobservation",
            "verify_deployment",
            "verify_deployment",
            scenario="n1",
            step=2,
        ),
    ]
    summary = jc.summarize(records, [{"id": "x"}] * 16)
    assert summary["overall_accuracy"] == pytest.approx(11 / 16)
    assert summary["false_known_rate"] == pytest.approx(0.5)
    assert summary["false_unknown_rate"] == pytest.approx(1 / 14, abs=1e-4)
    assert summary["unknown_recall"] == pytest.approx(0.5)
    assert summary["F_paraphrase_disagreement_rate"] == 1.0
    assert summary["G_order_stable_rate"] == 1.0
    assert summary["K_path_success_by_depth"] == {
        "depth_1": 1.0,
        "depth_2": 1.0,
        "depth_3": 0.0,
    }
    assert summary["J_hierarchy_path_accuracy"] == 0.0
    assert summary["J_flat_accuracy"] == 1.0
    assert summary["N_both_steps_correct_rate"] == 1.0
