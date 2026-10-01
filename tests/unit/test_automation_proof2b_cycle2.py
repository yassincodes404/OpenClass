"""Synthetic tests of Proof #2B cycle 2; no model, network or live-artifact dependency."""

import importlib
import json

import pytest


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    return (
        importlib.import_module("automation_applicability"),
        importlib.import_module("automation_proof2b"),
        importlib.import_module("automation_proof2b_cycle2"),
    )


def prior_candidate():
    return {
        "id": "prior-1",
        "base_policy_id": "policy-1",
        "status": "candidate",
        "approved": False,
        "proposal": {
            "proposal_type": "GENERALIZE_TRIGGER",
            "semantic_description": "simulated",
            "applicability_spec": {
                "require_test_attempted": True,
                "require_failed_test": True,
                "require_result_inspected": True,
                "raw_failure_signals": ["Address in use"],
                "normalization_rules": [],
                "required_failure_category": None,
            },
            "rationale": "simulated claim",
            "confidence": 1.0,
        },
    }


def prior_evaluation():
    return {
        "candidate_id": "prior-1",
        "status": "failed",
        "cases": [{"id": f"case_{i}"} for i in range(12)],
        "baseline_correct": 9,
        "candidate_correct": 9,
        "regressions": ["case_1", "case_2"],
        "promotion_allowed": False,
    }


def recorded_report(run_number, output):
    state = {
        "test_attempted": True,
        "test_result": {"exit_code": 1, "output": output, "port": 3100},
        "result_inspected": True,
    }
    return {
        "run": run_number,
        "trace": [{"selected_action": "recover_from_port_conflict", "state": json.dumps(state)}],
    }


def full_report(run_number, output):
    report = recorded_report(run_number, output)
    report["status"] = "premature_done" if run_number == 3 else "done"
    report["postconditions_verified"] = True
    report["macro_selected_by_jev"] = True
    report["macro_selected_at_observed_inspected_conflict"] = run_number == 2
    report["discovery_calls"] = 0
    report["trace"][0]["decision"] = {"probability": 1.0}
    report["trace"][0]["executor"] = {"steps": 4}
    report["trace"].append({"selected_action": "done"})
    return report


def category_mode_proposal(m):
    rule = m.FailureRule(
        category="port_bind_conflict",
        signals=("Address already in use", "Address in use", "EADDRINUSE"),
    )
    spec = m.ApplicabilitySpec(
        require_test_attempted=True,
        require_failed_test=True,
        require_result_inspected=True,
        raw_failure_signals=(),
        normalization_rules=(rule,),
        required_failure_category="port_bind_conflict",
    )
    return m.ApplicabilityProposal(
        proposal_type="ADD_STATE_NORMALIZATION",
        semantic_description="authored passability probe",
        applicability_spec=spec,
        rationale="authored in tests; never sent to discovery",
        confidence=1.0,
    )


def author_history(tmp_path):
    source = tmp_path / "source"
    prior = tmp_path / "prior"
    source.mkdir()
    prior.mkdir()
    (source / "policy-v2.json").write_text(
        json.dumps(
            {
                "id": "policy-1",
                "candidate": {"procedure": ["run_tests", "write_report"]},
            }
        )
    )
    for run_number, output in (
        (2, "OSError: [Errno 98] Address already in use"),
        (3, "OSError: [Errno 98] Address in use"),
    ):
        directory = source / f"run-{run_number}"
        directory.mkdir()
        (directory / "report.json").write_text(json.dumps(full_report(run_number, output)))
    (tmp_path / "freeze.json").write_text(json.dumps({"files": {}}))
    (prior / "protocol.json").write_text(json.dumps({"implementation_sha256": {}}))
    (prior / "candidate.json").write_text(json.dumps(prior_candidate()))
    (prior / "evaluation.json").write_text(json.dumps(prior_evaluation()))
    (prior / "report.json").write_text(json.dumps({"candidate_id": "prior-1"}))
    return source, prior, tmp_path / "freeze.json"


def patch_history(monkeypatch, cycle2, tmp_path):
    source, prior, freeze = author_history(tmp_path)
    monkeypatch.setattr(cycle2, "SOURCE", source)
    monkeypatch.setattr(cycle2, "PRIOR", prior)
    monkeypatch.setattr(cycle2, "FREEZE", freeze)
    monkeypatch.setattr(cycle2, "verify_frozen", lambda: None)
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "fixture-key")
    return source, prior


def test_verdict_discloses_counts_only(modules):
    _, _, cycle2 = modules
    assert cycle2.disclosed_verdict(prior_evaluation()) == {
        "status": "failed",
        "case_count": 12,
        "candidate_correct": 9,
        "baseline_correct": 9,
        "regression_count": 2,
        "cases_disclosed": False,
    }


def test_failure_informed_evidence_adds_prior_without_evaluation_cases(modules):
    _, _, cycle2 = modules
    base = {"question": "Base question.", "observations": [{"output": "Address already in use"}]}
    evidence = cycle2.failure_informed(
        base, prior_candidate(), cycle2.disclosed_verdict(prior_evaluation())
    )
    encoded = json.dumps(evidence)
    assert evidence["question"].startswith("Base question.")
    assert "final applicability assessment" in evidence["question"]
    assert evidence["prior_attempt"]["proposal"]["rationale"] == "simulated claim"
    assert evidence["prior_attempt"]["verdict"]["regression_count"] == 2
    for hidden in (
        "EADDRINUSE",
        "Connection refused",
        "Permission denied",
        "File not found",
        "expected",
        "human_case",
        "recorded_run",
        "case_1",
        "regressions",
    ):
        assert hidden not in encoded
    assert base == {
        "question": "Base question.",
        "observations": [{"output": "Address already in use"}],
    }


def test_load_prior_accepts_only_inactive_rejected_history(modules, tmp_path):
    _, _, cycle2 = modules

    def write(candidate_data, evaluation_data):
        (tmp_path / "protocol.json").write_text(json.dumps({"implementation_sha256": {}}))
        (tmp_path / "candidate.json").write_text(json.dumps(candidate_data))
        (tmp_path / "evaluation.json").write_text(json.dumps(evaluation_data))

    write(prior_candidate(), prior_evaluation())
    protocol, candidate, evaluation = cycle2.load_prior(tmp_path)
    assert protocol == {"implementation_sha256": {}}
    assert candidate["id"] == evaluation["candidate_id"] == "prior-1"

    write(prior_candidate() | {"id": "other"}, prior_evaluation())
    with pytest.raises(ValueError, match="disagree"):
        cycle2.load_prior(tmp_path)

    write(prior_candidate(), prior_evaluation() | {"status": "passed"})
    with pytest.raises(ValueError, match="rejected"):
        cycle2.load_prior(tmp_path)

    write(prior_candidate() | {"approved": True}, prior_evaluation())
    with pytest.raises(ValueError, match="inactive"):
        cycle2.load_prior(tmp_path)


def test_chain_rejects_changed_reused_code(modules):
    _, _, cycle2 = modules
    with pytest.raises(ValueError, match="changed since the prior round"):
        cycle2.verify_chain({"implementation_sha256": {"automation_attempts.py": "0" * 64}})


def test_benchmark_admits_passing_candidate_and_matches_baseline_gap(modules):
    m, harness, _ = modules
    cases = harness.fixtures(
        [
            recorded_report(2, "OSError: [Errno 98] Address already in use"),
            recorded_report(3, "OSError: [Errno 98] Address in use"),
        ]
    )
    assert len(cases) == 12
    result = harness.evaluate(category_mode_proposal(m), cases)
    assert result["status"] == "passed" and result["candidate_correct"] == 12

    literal = m.ApplicabilitySpec(
        require_test_attempted=True,
        require_failed_test=True,
        require_result_inspected=True,
        raw_failure_signals=("Address already in use",),
        normalization_rules=(),
        required_failure_category=None,
    )
    baseline_like = m.ApplicabilityProposal(
        proposal_type="GENERALIZE_TRIGGER",
        semantic_description="simulated",
        applicability_spec=literal,
        rationale="simulated",
        confidence=1.0,
    )
    baseline_result = harness.evaluate(baseline_like, cases)
    assert baseline_result["baseline_correct"] == baseline_result["candidate_correct"] == 9


def test_run_records_passing_candidate_as_inactive_and_unapproved(modules, monkeypatch, tmp_path):
    m, _, cycle2 = modules
    patch_history(monkeypatch, cycle2, tmp_path)

    async def fake_discover(payload, key, root):
        encoded = json.dumps(payload)
        for hidden in ("EADDRINUSE", "Connection refused", "Permission denied", "File not found"):
            assert hidden not in encoded
        assert key == "fixture-key"
        assert "regression_count" in encoded and "case_1" not in encoded
        return category_mode_proposal(m), [{"attempt": 1, "status": "validated"}]

    monkeypatch.setattr(cycle2, "discover", fake_discover)
    assert cycle2.run(tmp_path / "out") == 0
    run_dir = next((tmp_path / "out").iterdir())
    report = json.loads((run_dir / "report.json").read_text())
    assert report["status"] == "passed" and report["cycle"] == 2
    assert report["approval_required"] and not report["policy_v3_created"]
    candidate = json.loads((run_dir / "candidate.json").read_text())
    assert not candidate["approved"] and candidate["prior_candidate_id"] == "prior-1"
    evaluation = json.loads((run_dir / "evaluation.json").read_text())
    assert evaluation["status"] == "passed" and evaluation["candidate_correct"] == 12


def test_run_retains_rejected_no_change_without_promotion(modules, monkeypatch, tmp_path):
    m, _, cycle2 = modules
    patch_history(monkeypatch, cycle2, tmp_path)

    async def fake_discover(payload, key, root):
        return m.ApplicabilityProposal(
            proposal_type="NO_CHANGE",
            semantic_description="simulated",
            applicability_spec=None,
            rationale="simulated",
            confidence=0.4,
        ), []

    monkeypatch.setattr(cycle2, "discover", fake_discover)
    assert cycle2.run(tmp_path / "out") == 1
    run_dir = next((tmp_path / "out").iterdir())
    report = json.loads((run_dir / "report.json").read_text())
    assert report["status"] == "not_evaluated" and not report["approval_required"]
    evaluation = json.loads((run_dir / "evaluation.json").read_text())
    assert not evaluation["promotion_allowed"]
