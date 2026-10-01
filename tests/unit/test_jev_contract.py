# ruff: noqa: E402
"""Offline contract tests. Invented distributions are fixtures, never empirical evidence."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openclass_core.models import ChoiceResult
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.jev_contract.calibration import Rule, load_dataset, score, select_on_calibration
from scripts.jev_contract.canonical import (
    Choice,
    DecisionNode,
    ResolvedDecision,
    StateFeature,
    StateSchema,
    StateSnapshot,
    compile_state,
    digest,
)
from scripts.jev_contract.jev import (
    DecisionTelemetry,
    EscalationPolicy,
    JevDecisionCompiler,
    ProviderCompatibilityError,
    telemetry,
)
from scripts.jev_contract.knowledge import (
    Evidence,
    JevKnowledgeBase,
    JevProfile,
    ProfileJournal,
    assess_profile,
    require_current,
    save_new,
)
from scripts.jev_contract.precision import (
    HiddenEvaluation,
    TeacherResponse,
    evaluate_one,
    packet,
)
from scripts.jev_contract.prepare_benchmarks import fixture_graph
from scripts.jev_contract.runtime import EventStore, ProviderCall, execute_macro, run_graph
from scripts.jev_contract.teacher import (
    Capability,
    Payload,
    TeacherCandidate,
    TeacherRequest,
    apply_candidate,
    messages,
)

BASE = Path("benchmarks/jev-contract/v1")


@pytest.fixture
def profile():
    return JevProfile.model_validate_json((BASE / "profile.json").read_text())


@pytest.fixture
def snapshot():
    return StateSnapshot(
        schema_id="service_state",
        schema_version=1,
        facts={"attempted": True},
        raw_evidence=("bind: address in use",),
    )


def node(count=2):
    return DecisionNode(
        id="route",
        question="Which concrete failure explains the evidence?",
        choices=tuple(
            Choice(
                id=f"choice_{i}",
                meaning=f"Failure concept {i}",
                target_kind="terminal",
                target_id=None,
            )
            for i in range(count)
        ),
    )


def result(probs, unknown):
    return ChoiceResult(
        provider="jev",
        model="typesafe-ai/jev",
        probabilities=probs,
        unknown_probability=unknown,
        input_tokens=12,
        output_tokens=3,
    )


def record(profile, snapshot, probabilities=None, unknown=0.2):
    return telemetry(
        JevDecisionCompiler(profile).compile(node(), snapshot),
        profile,
        result(probabilities or {"choice_0": 0.7, "choice_1": 0.1}, unknown),
        latency_ms=4,
        retry_count=0,
        simulated=True,
    )


def test_canonical_has_no_vendor_limit_and_compiler_has_measured_bound(profile, snapshot):
    assert len(node(33).choices) == 33
    assert "jev" not in fixture_graph().model_dump_json().lower()
    assert (
        len(JevDecisionCompiler(profile).compile(node(32), snapshot).request.ontology.classes) == 32
    )
    with pytest.raises(ProviderCompatibilityError, match="max_tested"):
        JevDecisionCompiler(profile).compile(node(33), snapshot)


def test_compiler_preserves_raw_evidence_and_resolved_state(profile, snapshot):
    prior = ResolvedDecision(node_id="parent", choice_id="port", meaning="Occupied network port")
    explicit = snapshot.model_copy(update={"resolved_decisions": (prior,)})
    compiled = JevDecisionCompiler(profile).compile(node(), explicit)
    content = json.loads(compiled.request.observation.content)
    assert content["raw_evidence"] == ["bind: address in use"]
    assert content["resolved_prior_decisions"][0]["meaning"] == prior.meaning
    assert "UNKNOWN" in content["instruction"]
    changed = explicit.model_copy(update={"raw_evidence": ("different evidence",)})
    assert changed.id != explicit.id
    assert (
        JevDecisionCompiler(profile).compile(node(), changed).decision_spec_id
        == compiled.decision_spec_id
    )
    assert (
        JevDecisionCompiler(profile).compile(node(3), explicit).choice_set_hash
        != compiled.choice_set_hash
    )


def test_compiler_rejects_anaphora_and_unjustified_hierarchy(profile, snapshot):
    bad = node().model_copy(update={"question": "What should the selected one do?"})
    with pytest.raises(ProviderCompatibilityError, match="anaphoric"):
        JevDecisionCompiler(profile).compile(bad, snapshot)
    branch = node(1).model_copy(
        update={
            "choices": (
                Choice(
                    id="branch",
                    meaning="Concrete domain branch",
                    target_kind="node",
                    target_id="leaf",
                ),
            )
        }
    )
    with pytest.raises(ProviderCompatibilityError, match="hierarchy"):
        JevDecisionCompiler(profile).compile(branch, snapshot)


def test_state_compiler_does_not_invent_semantics_or_coerce_missing_facts():
    schema = StateSchema(
        id="sensor",
        version=1,
        features=(StateFeature(id="exit_code", kind="integer", sensor_field="exit_code"),),
    )
    raw = "OSError: [Errno 98] Address in use"
    state = compile_state(schema, {"exit_code": 1}, (raw,))
    assert state.facts == {"exit_code": 1}
    assert state.raw_evidence == (raw,)
    with pytest.raises(ValueError, match="missing sensor"):
        compile_state(schema, {})
    with pytest.raises(ValueError, match="wrong sensor type"):
        compile_state(schema, {"exit_code": True})


@pytest.mark.parametrize(
    "change",
    [
        {"provider": "another"},
        {"model": "new_model"},
        {"model_revision": "revision-2"},
        {"api_behavior": "different"},
        {"distribution_schema": "v2"},
        {"major_version": "2"},
    ],
)
def test_identity_changes_make_profile_stale_without_rewriting(profile, change, tmp_path):
    before = profile.model_dump_json()
    journal = ProfileJournal(tmp_path / "journal")
    event = journal.observe(profile, profile.identity.model_copy(update=change))
    assert event and journal.status(profile) == "STALE"
    assert ProfileJournal(journal.root).status(profile) == "STALE"
    journal.observe(profile, profile.identity)
    assert journal.status(profile) == "STALE"
    with pytest.raises(ValueError, match="STALE"):
        require_current(profile, journal.events())
    assert profile.model_dump_json() == before


def test_sustained_drift_evidence_invalidates_profile(profile):
    evidence = Evidence(path="drift.json", sha256="a" * 64)
    event = assess_profile(profile, profile.identity, datetime.now(UTC), (evidence,))
    assert event and event.reasons == ("sustained_runtime_drift",)


def test_telemetry_top_two_include_unknown_and_unknown_wins_tie(profile, snapshot):
    r = record(profile, snapshot, {"choice_0": 0.4, "choice_1": 0.2}, 0.4)
    assert r.selected_choice == "UNKNOWN"
    assert r.top_probability == r.second_probability == 0.4 and r.margin == 0
    assert r.reported_cost is None
    with pytest.raises(ValidationError, match="telemetry mismatch"):
        DecisionTelemetry.model_validate({**r.model_dump(), "margin": 0.9})
    with pytest.raises(ValidationError, match="snapshot hash"):
        DecisionTelemetry.model_validate({**r.model_dump(), "state_snapshot_id": "wrong"})


def test_transport_failure_has_no_synthetic_unknown(profile, snapshot):
    compiled = JevDecisionCompiler(profile).compile(node(), snapshot)
    r = telemetry(
        compiled,
        profile,
        None,
        latency_ms=3,
        retry_count=2,
        simulated=True,
        failure="http",
        http_status=502,
    )
    assert r.event == "provider.failed"
    assert r.selected_choice is None and r.unknown_probability is None and r.distribution is None
    with pytest.raises(ValidationError, match="not a semantic"):
        DecisionTelemetry.model_validate({**r.model_dump(), "selected_choice": "UNKNOWN"})
    with pytest.raises(ValueError, match="compiled choices"):
        telemetry(
            compiled,
            profile,
            result({"wrong": 0.8}, 0.2),
            latency_ms=1,
            retry_count=0,
            simulated=True,
        )


def test_supervision_has_no_invented_default_threshold(profile, snapshot):
    r = record(profile, snapshot)
    gate = EscalationPolicy(id="unvalidated", profile_hash=r.profile_hash)
    assert gate.decide(r, node()) == "escalate"
    researched = gate.model_copy(
        update={
            "min_margin": 0.1,
            "max_unknown": 0.3,
            "reviewed": True,
            "validation_artifact_hash": "test-only",
        }
    )
    assert researched.decide(r, node()) == "continue"
    assert researched.decide(r, node().model_copy(update={"risk": "high"})) == "escalate"


def test_evidence_integrity_and_observed_value_are_verified(tmp_path):
    import hashlib

    p = tmp_path / "evidence.json"
    p.write_text('{"count": 2}')
    e = Evidence(
        path="evidence.json", sha256=hashlib.sha256(p.read_bytes()).hexdigest(), pointer="/count"
    )
    assert e.read(tmp_path) == 2
    p.write_text('{"count": 3}')
    with pytest.raises(ValueError, match="hash mismatch"):
        e.read(tmp_path)
    with pytest.raises(FileExistsError):
        save_new(p, {"count": 4})


def test_registry_observed_values_match_available_historical_artifacts():
    kb = JevKnowledgeBase.model_validate_json((BASE / "knowledge.json").read_text())
    if not all(Path(e.path).exists() for o in kb.observations for e in o.evidence):
        pytest.skip("historical local research artifact archive unavailable")
    kb.verify(Path.cwd())
    assert {o.status for o in kb.observations} == {"OBSERVED", "INFERRED", "UNKNOWN"}


def requests():
    return {
        p["id"]: TeacherRequest.model_validate(p)
        for p in json.loads((BASE / "teacher-packages.json").read_text())
    }


def candidate(req, operator, target, payload):
    return TeacherCandidate(
        operator=operator,
        target_id=target,
        payload=payload,
        base_policy_hash=req.graph_slice.content_hash,
        semantic_description="Test candidate",
        rationale="Fixture evidence",
        confidence=0.5,
    )


def test_teacher_packets_do_not_disclose_hidden_evaluations():
    req = requests()["authored-procedure"]
    packet_value = packet(req)
    assert packet_value["messages"] == messages(req)
    content = packet_value["messages"][1]["content"]
    assert "JEV OPERATING PROFILE" in content
    assert "candidate_history" in content and "capabilities" in content
    assert "payload_checks" not in content and "expected_env_name" not in content
    invalid = req.model_dump()
    invalid["feedback"] = {
        "protocol_id": "not-predeclared",
        "evaluated": 2,
        "passed": 1,
        "regressions": 0,
    }
    with pytest.raises(ValidationError, match="not predeclared"):
        TeacherRequest.model_validate(invalid)


def test_teacher_cannot_change_wrong_layer_or_stale_base():
    req = requests()["authored-procedure"]
    wrong = candidate(req, "ADD_CHOICE", "route", Payload(choice=node(1).choices[0]))
    with pytest.raises(ValueError, match="wrong diagnosed layer"):
        apply_candidate(req, wrong)
    stale = candidate(req, "INSUFFICIENT_EVIDENCE", "", Payload()).model_copy(
        update={"base_policy_hash": "old"}
    )
    with pytest.raises(ValueError, match="stale candidate"):
        apply_candidate(req, stale)


def test_teacher_valid_procedure_repair_preserves_routing_and_version():
    req = requests()["authored-procedure"]
    graph = req.graph_slice
    steps = list(graph.macros[0].steps)
    steps[1] = steps[1].model_copy(update={"arguments": {"name": "SERVICE_TEST_PORT"}})
    proposal = candidate(req, "REPLACE_PROCEDURE", "recover", Payload(steps=tuple(steps)))
    evolved = apply_candidate(req, proposal)
    assert evolved.nodes == graph.nodes
    assert evolved.parent_hash == graph.content_hash and evolved.version == 2
    assert graph.macros[0].steps[1].arguments["name"] == "TEST_PORT"
    hidden = HiddenEvaluation.model_validate(
        json.loads((BASE / "teacher-hidden.json").read_text())[req.id]
    )
    response = TeacherResponse(
        package_id=req.id,
        model="simulated-test",
        packet_hash=digest(packet(req)),
        content=proposal.model_dump_json(),
        infrastructure_status="ok",
        latency_ms=1,
        simulated=True,
    )
    assert evaluate_one(req, hidden, response)["evaluation_passed"]
    wrong = proposal.model_copy(update={"target_id": "wrong_macro"})
    score_value = evaluate_one(
        req, hidden, response.model_copy(update={"content": wrong.model_dump_json()})
    )
    assert score_value["schema_valid"] and not score_value["target_correct"]
    assert not score_value["evaluation_passed"]


def test_unknown_capability_rejected_before_macro_side_effects():
    class World:
        def observe(self):
            return StateSnapshot(
                schema_id="s", schema_version=1, facts={"attempted": True, "authorized": True}
            )

        def execute(self, step):
            raise AssertionError("must validate all capabilities first")

    assert (
        execute_macro(
            fixture_graph().macros[0],
            World(),
            (Capability(id="choose_available_test_port", arguments={"preferred": "integer"}),),
        )
        == "MISSING_CAPABILITY"
    )


def test_calibration_dataset_disjoint_and_supervision_tradeoff(profile):
    dataset = load_dataset(BASE)
    assert len(dataset.cases) == 48
    assert {c.stratum for c in dataset.cases if c.split == "calibration"} == {
        c.stratum for c in dataset.cases if c.split == "validation"
    }
    cases = dataset.cases[:2]
    records = {}
    for case in cases:
        compiled = JevDecisionCompiler(profile).compile(case.node, case.snapshot)
        records[case.id] = telemetry(
            compiled,
            profile,
            result(
                {
                    "ready": 0.55,
                    "account_hold": 0.4,
                    "inventory_hold": 0.01,
                    "identity_check": 0.01,
                },
                0.03,
            ),
            latency_ms=1,
            retry_count=0,
            simulated=True,
        )
    baseline = Rule(family="probability_only", min_top=0.5, min_margin=0, max_unknown=1)
    joint = Rule(family="margin_unknown", min_top=0, min_margin=0.2, max_unknown=0.3)
    assert score(baseline, cases, dataset.labels, records)["continued"] == 2
    assert score(joint, cases, dataset.labels, records)["continued"] == 0
    curve = [score(baseline, cases, dataset.labels, records)]
    assert select_on_calibration(curve, "probability_only") is None  # too few observations


async def test_runtime_failure_escalates_and_persists_no_semantic_evidence(profile, tmp_path):
    class World:
        def observe(self):
            return StateSnapshot(
                schema_id="service_state", schema_version=1, facts={"attempted": True}
            )

        def execute(self, step):
            raise AssertionError("must never execute")

    async def provider(_):
        raise RuntimeError("secret-test-token must not be persisted")

    store = EventStore(tmp_path / "run", secrets=("secret-test-token",))
    gate = EscalationPolicy(id="unvalidated", profile_hash=digest(profile.model_dump(mode="json")))
    output = await run_graph(
        fixture_graph(),
        World(),
        profile,
        profile.identity,
        provider,
        gate,
        (),
        store,
        ProfileJournal(tmp_path / "profiles"),
    )
    assert output.status == "escalated" and output.diagnosis == "INFRASTRUCTURE"
    assert output.decisions[0].selected_choice is None
    store.freeze()
    assert "secret-test-token" not in "".join(p.read_text() for p in store.root.iterdir())


async def test_runtime_unknown_never_diagnoses_missing_choice(profile, tmp_path):
    class World:
        def observe(self):
            return StateSnapshot(
                schema_id="service_state", schema_version=1, facts={"attempted": True}
            )

        def execute(self, step):
            raise AssertionError("must never execute")

    async def provider(_):
        return ProviderCall(result=result({"port": 0.1}, 0.9), simulated=True)

    store = EventStore(tmp_path / "run")
    gate = EscalationPolicy(id="unvalidated", profile_hash=digest(profile.model_dump(mode="json")))
    output = await run_graph(
        fixture_graph(),
        World(),
        profile,
        profile.identity,
        provider,
        gate,
        (),
        store,
        ProfileJournal(tmp_path / "profiles"),
    )
    assert output.diagnosis == "INSUFFICIENT_EVIDENCE"
    assert output.decisions[0].selected_choice == "UNKNOWN"


def test_calibration_selection_does_not_force_unknown_heavy_cases_through():
    # Research objective preserves correct known coverage, not an artificial overall quota.
    row = {
        "rule": {"family": "margin_unknown"},
        "semantic_responses": 24,
        "coverage": 10 / 24,
        "correct_known_coverage": 1.0,
        "false_known": 0,
        "selective_errors": 0,
        "continued": 10,
    }
    assert select_on_calibration([row], "margin_unknown") == row


def test_teacher_schema_has_catalog_specific_closed_argument_objects():
    schema = packet(requests()["authored-procedure"])["response_schema"]
    steps = schema["$defs"]["Step"]["anyOf"]
    environment = next(
        s for s in steps if s["properties"]["capability"]["enum"] == ["set_environment"]
    )
    args = environment["properties"]["arguments"]
    assert args["additionalProperties"] is False
    assert args["required"] == ["name"]
    assert args["properties"]["name"]["enum"] == ["TEST_PORT", "SERVICE_TEST_PORT"]
    with pytest.raises(ValidationError, match="operator-specific"):
        TeacherCandidate(
            operator="NO_CHANGE",
            target_id="",
            payload=Payload(choice=node(1).choices[0]),
            base_policy_hash="test",
            semantic_description="test",
            rationale="test",
            confidence=0.5,
        )
