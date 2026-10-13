from pathlib import Path

import pytest
from openclass_core.automation import AutomationAction, AutomationActionName, AutomationState
from openclass_server.automation_executor import SafeSandboxExecutor


@pytest.mark.asyncio
async def test_executor_is_workspace_bound_and_writes_only_output(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n")
    executor = SafeSandboxExecutor(tmp_path)
    state = AutomationState(goal="inspect", cwd=".")
    listed = await executor.execute(
        AutomationAction(name=AutomationActionName.LIST_DIRECTORY), state
    )
    assert "pyproject.toml" in listed.output
    with pytest.raises(ValueError, match="escapes"):
        await executor.execute(
            AutomationAction(name=AutomationActionName.READ_FILE, arguments={"path": "../secret"}),
            state,
        )
    report = await executor.execute(AutomationAction(name=AutomationActionName.WRITE_REPORT), state)
    assert report.exit_code == 0
    assert (tmp_path / "output/report.json").exists()


@pytest.mark.asyncio
async def test_executor_env_isolation_port_bounds_and_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENCLASS_DATABASE_URL", "postgresql://secret:pass@db/openclass")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "super-secret-aws-key")
    executor = SafeSandboxExecutor(tmp_path, timeout_seconds=5.0)
    state = AutomationState(
        goal="test actions",
        cwd=".",
        test_port="8005",
        env_vars={"APP_ENV": "test", "OPENCLASS_SECRET": "ignored"},
        history=(AutomationAction(name=AutomationActionName.LIST_DIRECTORY),),
    )
    env = executor._build_env(state)
    assert "OPENCLASS_DATABASE_URL" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "OPENCLASS_SECRET" not in env
    assert env["APP_ENV"] == "test"
    assert env["TEST_PORT"] == "8005"

    # Port range guard
    with pytest.raises(ValueError, match="unprivileged range"):
        await executor.execute(
            AutomationAction(name=AutomationActionName.INSPECT_PORT, arguments={"port": "22"}),
            state,
        )

    # SET_ENVIRONMENT
    set_env = await executor.execute(
        AutomationAction(
            name=AutomationActionName.SET_ENVIRONMENT,
            arguments={"key": "FEATURE_FLAG", "value": "1"},
        ),
        state,
    )
    assert set_env.state_patch == {"env:FEATURE_FLAG": "1"}
    with pytest.raises(ValueError, match="disallowed environment variable"):
        await executor.execute(
            AutomationAction(
                name=AutomationActionName.SET_ENVIRONMENT,
                arguments={"key": "LD_PRELOAD", "value": "bad.so"},
            ),
            state,
        )

    # RERUN_PREVIOUS, DONE, BLOCKED
    rerun = await executor.execute(
        AutomationAction(name=AutomationActionName.RERUN_PREVIOUS), state
    )
    assert rerun.exit_code == 0
    done = await executor.execute(
        AutomationAction(name=AutomationActionName.DONE, arguments={"summary": "completed"}),
        state,
    )
    assert done.exit_code == 0 and done.output == "completed"
    blocked = await executor.execute(
        AutomationAction(name=AutomationActionName.BLOCKED, arguments={"reason": "missing tool"}),
        state,
    )
    assert blocked.exit_code == 1 and blocked.output == "missing tool"
