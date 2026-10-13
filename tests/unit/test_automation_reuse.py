"""Approval integrity and discovery isolation; tests never use real inference."""

import importlib
import json
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    return (
        importlib.import_module("automation_policy_approval"),
        importlib.import_module("automation_proof2_reuse"),
    )


@pytest.fixture
def reviewed(tmp_path):
    # Self-contained simulated review artifacts; live evidence is not required by CI.
    from openclass_core.models import OntologyClass, OntologyVersion

    root = tmp_path / "reviewed"
    (root / "review").mkdir(parents=True)
    base = OntologyVersion(
        classifier_id="00000000-0000-0000-0000-000000000001",
        version_number=1,
        classes=(OntologyClass(canonical_name="run_tests", display_name="Run tests"),),
        created_by="simulated",
    )
    candidate = {
        "id": "00000000-0000-0000-0000-000000000002",
        "base_policy_version_id": str(base.id),
        "status": "candidate",
        "proposal": {
            "canonical_name": "recovery",
            "description": "simulated",
            "trigger": "unchanged literal trigger",
            "steps": ["run_tests"],
            "success_condition": "simulated",
        },
        "procedure": {"steps": ["run_tests"]},
    }
    evaluation = {"status": "passed", "postcondition_verified": True}
    data = {
        "policy_v1": base.model_dump(mode="json"),
        "macro_candidate": candidate,
        "evaluation": evaluation,
    }
    for name, value in [
        ("store.json", data),
        ("review/candidate.json", candidate),
        ("review/replay.json", evaluation),
    ]:
        (root / name).write_text(json.dumps(value))
    import hashlib

    hashes = {
        n: hashlib.sha256((root / n).read_bytes()).hexdigest()
        for n in ("store.json", "review/candidate.json", "review/replay.json")
    }
    (root / "review/sha256.json").write_text(json.dumps(hashes))
    return root, data, hashes


def approval_for(service, data, hashes):
    from datetime import UTC, datetime

    return service.HumanApproval(
        candidate_id=data["macro_candidate"]["id"],
        base_policy_id=data["policy_v1"]["id"],
        candidate_sha256=hashes["review/candidate.json"],
        authority="human_user_in_conversation",
        scope="experimental_policy_v2_and_runs_2_3_only",
        statement="simulated approval",
        recorded_at=datetime.now(UTC),
    )


def test_approval_preserves_candidate_and_base_and_refuses_overwrite(modules, reviewed, tmp_path):
    service, _ = modules
    source, data, hashes = reviewed
    before = (source / "store.json").read_bytes()
    path = tmp_path / "v2.json"
    approval = approval_for(service, data, hashes)
    v2 = service.create_policy_v2(source, path, approval)
    assert v2["candidate"] == data["macro_candidate"]
    assert v2["base_policy"] == data["policy_v1"]
    assert v2["decision_space"]["classes"][:-1] == data["policy_v1"]["classes"]
    assert (source / "store.json").read_bytes() == before
    with pytest.raises(FileExistsError):
        service.create_policy_v2(source, path, approval)


def test_approval_rejects_modified_candidate(modules, reviewed, tmp_path):
    service, _ = modules
    source, data, hashes = reviewed
    (source / "review/candidate.json").write_text("{}")
    with pytest.raises(service.ApprovalError):
        service.create_policy_v2(source, tmp_path / "v2.json", approval_for(service, data, hashes))


def test_approval_rejects_wrong_base(modules, reviewed, tmp_path):
    service, _ = modules
    source, data, hashes = reviewed
    approval = approval_for(service, data, hashes).model_copy(
        update={"base_policy_id": "00000000-0000-0000-0000-000000000099"}
    )
    with pytest.raises(service.ApprovalError):
        service.create_policy_v2(source, tmp_path / "v2.json", approval)


@pytest.mark.asyncio
async def test_discovery_is_physically_disabled(modules):
    _, reuse = modules
    disabled = reuse.DisabledDiscoveryProvider()
    with pytest.raises(AssertionError, match="forbidden"):
        await disabled.discover({})
    assert disabled.calls == 1
    transport = reuse.JevOnlyTransport(
        lambda record: None, httpx.MockTransport(lambda req: httpx.Response(200))
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(AssertionError, match="Only Jev"):
            await client.post("https://ai-gateway.vercel.sh/v1/chat/completions", json={})


def test_transfer_is_a_different_project(modules, tmp_path):
    _, reuse = modules
    project = tmp_path / "warehouse"
    reuse.prepare_project(project, transfer=True)
    assert (project / "warehouse_service.py").is_file()
    assert (project / "tests/test_health.py").is_file()
    assert "3000" in (project / "README.md").read_text()


def test_frozen_fixture_unchanged():
    import hashlib

    raw_bytes = Path("scripts/automation_replay_fixture.py").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw_bytes).hexdigest() == (
        "b2dc266a03a6ce24ef8a926371de85f91a39b51cdaf97188b0767a52e5535c66"
    )


def test_transfer_fixture_has_real_failure_and_truthful_report(modules, tmp_path, monkeypatch):
    import socket

    _, reuse = modules
    monkeypatch.syspath_prepend("scripts")
    transfer = importlib.import_module("automation_transfer_fixture")
    project = tmp_path / "warehouse"
    reuse.prepare_project(project, transfer=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    failed = transfer.replay(["run_tests"], project, occupied_port=port)
    assert failed["result"]["exit_code"] != 0
    assert "Address already in use" in failed["result"]["output"]
    assert not failed["postcondition_verified"]
    # Scripted fixture validation only, not a learned-routing/generalization claim.
    passed = transfer.replay(
        ["choose_available_test_port", "set_environment", "run_tests", "write_report"],
        project,
        occupied_port=port,
    )
    assert passed["postcondition_verified"]
    assert "OK" in passed["result"]["output"]
    assert json.loads((project / "output/report.json").read_text()) == passed["result"]
