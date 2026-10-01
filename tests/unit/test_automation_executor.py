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
