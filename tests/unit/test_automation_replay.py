"""Behavioral checks of the synthetic recovery fixture; no model-quality claim."""

import importlib.util
import socket
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "automation_replay_fixture", Path("scripts/automation_replay_fixture.py")
)
assert SPEC and SPEC.loader
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "README.md").write_text("Run tests and write a report.")
    return tmp_path


def replay(steps, project):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return fixture.replay(steps, project, occupied_port=port)


@pytest.mark.parametrize(
    "steps",
    [
        ["run_tests", "write_report"],
        ["choose_available_test_port", "run_tests", "write_report"],
        ["choose_available_test_port", "set_environment", "run_tests"],
        ["write_report", "choose_available_test_port", "set_environment", "run_tests"],
        ["read_file", "write_report"],
    ],
)
def test_missing_recovery_or_report_fails(steps, project):
    assert replay(steps, project)["status"] == "failed"


@pytest.mark.parametrize("test_action", ["run_tests", "rerun_previous"])
def test_recovery_is_behavioral_and_accepts_alternative_sequences(test_action, project):
    result = replay(
        [
            "inspect_port",
            "choose_available_test_port",
            "set_environment",
            test_action,
            "check_exit_code",
            "write_report",
            "done",
        ],
        project,
    )
    assert result["status"] == "passed"
    assert result["report"]["exit_code"] == 0
    assert (project / "output/report.json").is_file()


@pytest.mark.parametrize(
    "steps", [[], ["run_tests --recovered"], ["arbitrary_shell"], ["read_file"] * 21]
)
def test_invalid_steps_rejected_before_execution(steps, project):
    assert replay(steps, project)["status"] == "rejected"
    assert not (project / "output").exists()


def test_terminal_actions_cannot_be_followed_by_hidden_recovery(project):
    result = replay(
        ["blocked", "choose_available_test_port", "set_environment", "run_tests", "write_report"],
        project,
    )
    assert result["status"] == "failed"
    assert len(result["trace"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content,finish_reason,error",
    [
        ('{"proposal_type":', "stop", ValueError),
        ("{}", "length", ValueError),
        ('{"credential":"fixture-secret"}', "stop", ValueError),
    ],
)
async def test_discovery_rejects_invalid_incomplete_or_secret_response(
    monkeypatch, content, finish_reason, error
):
    import importlib

    import httpx

    monkeypatch.syspath_prepend("scripts")
    harness = importlib.import_module("automation_proof2_stage_a")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
            },
        )
    )
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        harness.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    with pytest.raises(error):
        await harness.discover_macro("fixture-secret", "https://example.invalid", "fixture", {})
