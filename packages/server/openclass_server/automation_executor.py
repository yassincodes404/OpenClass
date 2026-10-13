"""Safe primitive executor for the automation experiment.

This executor maps a closed action enum to fixed operations. It never invokes a
shell string. The caller must place it inside a disposable container.
"""

import asyncio
import json
import os
import re
import socket
from pathlib import Path

from openclass_core.automation import (
    AutomationAction,
    AutomationActionName,
    AutomationActionResult,
    AutomationState,
)

_SAFE_ENV_KEYS = (
    "PATH",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "TMP",
    "TEMP",
    "HOME",
    "USERPROFILE",
    "LANG",
    "LC_ALL",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "UV_CACHE_DIR",
)
_ENV_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_FORBIDDEN_ENV_KEYS = frozenset({"PATH", "LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "PYTHONPATH"})


class SafeSandboxExecutor:
    def __init__(self, workspace: Path, *, timeout_seconds: float = 30.0) -> None:
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds

    def _path(self, value: str, *, output_only: bool = False) -> Path:
        path = (self.workspace / value).resolve()
        if self.workspace not in path.parents and path != self.workspace:
            raise ValueError("path escapes automation workspace")
        if output_only and self.workspace / "output" not in path.parents:
            raise ValueError("writes are restricted to workspace/output")
        return path

    def _build_env(self, state: AutomationState) -> dict[str, str]:
        env = {k: os.environ[k] for k in _SAFE_ENV_KEYS if k in os.environ}
        for key, value in state.env_vars.items():
            if _ENV_KEY_PATTERN.match(key) and not key.startswith("OPENCLASS_"):
                env[key] = value
        if state.test_port is not None:
            env["TEST_PORT"] = state.test_port
        return env

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
            if not (1024 <= port <= 65535):
                raise ValueError("port outside unprivileged range 1024..65535")
            with socket.socket() as sock:
                sock.settimeout(0.2)
                occupied = sock.connect_ex(("127.0.0.1", port)) == 0
            return AutomationActionResult(action=action, output=str(occupied).lower())
        if name == AutomationActionName.CHOOSE_AVAILABLE_TEST_PORT:
            for port in range(8001, 8010):
                with socket.socket() as sock:
                    sock.settimeout(0.2)
                    if sock.connect_ex(("127.0.0.1", port)) != 0:
                        return AutomationActionResult(
                            action=action, output=str(port), state_patch={"test_port": str(port)}
                        )
            return AutomationActionResult(action=action, exit_code=1, output="no permitted port")
        if name == AutomationActionName.SET_ENVIRONMENT:
            key = action.arguments.get("key", "").strip()
            value = action.arguments.get("value", "")
            if (
                not _ENV_KEY_PATTERN.match(key)
                or key in _FORBIDDEN_ENV_KEYS
                or key.startswith("OPENCLASS_")
            ):
                raise ValueError(f"disallowed environment variable key: {key}")
            return AutomationActionResult(
                action=action,
                output=f"{key}={value}",
                state_patch={f"env:{key}": value},
            )
        if name == AutomationActionName.RERUN_PREVIOUS:
            skip = {
                AutomationActionName.RERUN_PREVIOUS,
                AutomationActionName.INSPECT_PORT,
                AutomationActionName.CHOOSE_AVAILABLE_TEST_PORT,
                AutomationActionName.SET_ENVIRONMENT,
            }
            prev = next((a for a in reversed(state.history) if a.name not in skip), None)
            if prev is None:
                return AutomationActionResult(
                    action=action, exit_code=1, output="no previous action to rerun"
                )
            sub_res = await self.execute(prev, state)
            return AutomationActionResult(
                action=action,
                exit_code=sub_res.exit_code,
                output=sub_res.output,
                state_patch=sub_res.state_patch,
            )
        if name == AutomationActionName.DONE:
            return AutomationActionResult(
                action=action, exit_code=0, output=action.arguments.get("summary", "done")
            )
        if name == AutomationActionName.BLOCKED:
            return AutomationActionResult(
                action=action, exit_code=1, output=action.arguments.get("reason", "blocked")
            )
        if name in {
            AutomationActionName.RUN_PYTHON_TESTS,
            AutomationActionName.RUN_NODE_TESTS,
            AutomationActionName.RUN_MAKE_TESTS,
        }:
            commands: dict[str, list[str]] = {
                AutomationActionName.RUN_PYTHON_TESTS: ["uv", "run", "pytest"],
                AutomationActionName.RUN_NODE_TESTS: ["npm", "test"],
                AutomationActionName.RUN_MAKE_TESTS: ["make", "test"],
            }
            command = commands[str(name)]
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=self._path(state.cwd),
                env=self._build_env(state),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(
                    process.communicate(), timeout=self.timeout_seconds
                )
            except TimeoutError:
                process.kill()
                await process.communicate()
                return AutomationActionResult(
                    action=action, exit_code=124, output="command timed out"
                )
            return AutomationActionResult(
                action=action,
                exit_code=process.returncode or 0,
                output=stdout.decode(errors="replace")[:12000],
            )
        if name == AutomationActionName.CHECK_EXIT_CODE:
            return AutomationActionResult(action=action, output=str(state.last_exit_code or 0))
        raise ValueError(f"unsupported automation action: {name}")
