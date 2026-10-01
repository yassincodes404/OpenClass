"""Safe primitive executor for the automation experiment.

This executor maps a closed action enum to fixed operations. It never invokes a
shell string. The caller must place it inside a disposable container.
"""

import asyncio
import json
import os
import socket
from pathlib import Path

from openclass_core.automation import (
    AutomationAction,
    AutomationActionName,
    AutomationActionResult,
    AutomationState,
)


class SafeSandboxExecutor:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _path(self, value: str, *, output_only: bool = False) -> Path:
        path = (self.workspace / value).resolve()
        if self.workspace not in path.parents and path != self.workspace:
            raise ValueError("path escapes automation workspace")
        if output_only and self.workspace / "output" not in path.parents:
            raise ValueError("writes are restricted to workspace/output")
        return path

    async def execute(
        self, action: AutomationAction, state: AutomationState
    ) -> AutomationActionResult:
        name = action.name
        if name == AutomationActionName.LIST_DIRECTORY:
            directory = self._path(action.arguments.get("path", "."))
            output = "\n".join(sorted(p.name for p in directory.iterdir()))
            return AutomationActionResult(action=action, output=output)
        if name == AutomationActionName.READ_FILE:
            path = self._path(action.arguments["path"])
            return AutomationActionResult(action=action, output=path.read_text()[:12000])
        if name == AutomationActionName.CHECK_FILE_EXISTS:
            exists = self._path(action.arguments["path"]).exists()
            return AutomationActionResult(action=action, output=str(exists).lower())
        if name == AutomationActionName.CHANGE_DIRECTORY:
            path = self._path(action.arguments["path"])
            if not path.is_dir():
                return AutomationActionResult(action=action, exit_code=1, output="not a directory")
            return AutomationActionResult(
                action=action, state_patch={"cwd": str(path.relative_to(self.workspace))}
            )
        if name == AutomationActionName.WRITE_REPORT:
            path = self._path(action.arguments.get("path", "output/report.json"), output_only=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "goal": state.goal,
                "history": [a.model_dump(mode="json") for a in state.history],
            }
            path.write_text(json.dumps(payload, indent=2))
            return AutomationActionResult(
                action=action, output=str(path.relative_to(self.workspace))
            )
        if name == AutomationActionName.INSPECT_PORT:
            port = int(action.arguments.get("port", "8000"))
            with socket.socket() as sock:
                occupied = sock.connect_ex(("127.0.0.1", port)) == 0
            return AutomationActionResult(action=action, output=str(occupied).lower())
        if name == AutomationActionName.CHOOSE_AVAILABLE_TEST_PORT:
            for port in range(8001, 8010):
                with socket.socket() as sock:
                    if sock.connect_ex(("127.0.0.1", port)) != 0:
                        return AutomationActionResult(
                            action=action, output=str(port), state_patch={"test_port": str(port)}
                        )
            return AutomationActionResult(action=action, exit_code=1, output="no permitted port")
        if name in {
            AutomationActionName.RUN_PYTHON_TESTS,
            AutomationActionName.RUN_NODE_TESTS,
            AutomationActionName.RUN_MAKE_TESTS,
        }:
            command = {
                AutomationActionName.RUN_PYTHON_TESTS: ["uv", "run", "pytest"],
                AutomationActionName.RUN_NODE_TESTS: ["npm", "test"],
                AutomationActionName.RUN_MAKE_TESTS: ["make", "test"],
            }[name]
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=self._path(state.cwd),
                env={k: v for k, v in os.environ.items() if not k.endswith("API_KEY")},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await process.communicate()
            return AutomationActionResult(
                action=action,
                exit_code=process.returncode or 0,
                output=stdout.decode(errors="replace")[:12000],
            )
        if name == AutomationActionName.CHECK_EXIT_CODE:
            return AutomationActionResult(action=action, output=str(state.last_exit_code or 0))
        raise ValueError(f"unsupported automation action: {name}")
