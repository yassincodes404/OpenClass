"""Run 3 executor: same primitive contracts, a separate HTTP-service unittest project."""

import json
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from automation_replay_fixture import PRIMITIVES


def replay(steps: list[str], project: Path, occupied_port: int = 3000) -> dict[str, Any]:
    if not steps or len(steps) > 20 or any(s not in PRIMITIVES for s in steps):
        return {"status": "rejected", "reason": "expected 1–20 exact registered primitives"}
    configured = occupied_port
    selected = None
    result: dict[str, Any] = {"exit_code": 1, "output": "tests not run"}
    trace = []
    report = None
    stopped_blocked = False
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", occupied_port))
        blocker.listen()
        for step in steps:
            output: Any = None
            if step == "list_directory":
                output = sorted(p.name for p in project.iterdir())
            elif step == "read_file":
                output = (project / "README.md").read_text()[:2000]
            elif step == "inspect_port":
                with socket.socket() as probe:
                    output = probe.connect_ex(("127.0.0.1", configured)) == 0
            elif step == "choose_available_test_port":
                for port in range(occupied_port + 1, occupied_port + 10):
                    with socket.socket() as probe:
                        try:
                            probe.bind(("127.0.0.1", port))
                        except OSError:
                            continue
                        selected = port
                        break
                if selected is None:
                    return {"status": "failed", "reason": "no permitted port"}
                output = selected
            elif step == "set_environment":
                if selected is None:
                    return {"status": "failed", "reason": "no port selected"}
                configured = selected
                output = {"TEST_PORT": configured}
            elif step in {"run_tests", "rerun_previous"}:
                completed = subprocess.run(
                    [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                    cwd=project,
                    env={"TEST_PORT": str(configured)},
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                result = {
                    "exit_code": completed.returncode,
                    "output": (completed.stdout + completed.stderr)[-12000:],
                    "port": configured,
                }
                output = dict(result)
            elif step in {"inspect_result", "check_exit_code"}:
                output = dict(result)
            elif step == "write_report":
                report_path = project / "output" / "report.json"
                report_path.parent.mkdir(exist_ok=True)
                report_path.write_text(json.dumps(result))
                report = json.loads(report_path.read_text())
                output = "output/report.json"
            elif step == "blocked":
                stopped_blocked = True
            trace.append({"action": step, "output": output})
            if step in {"done", "blocked"}:
                break
    passed = not stopped_blocked and result["exit_code"] == 0 and report == result
    return {
        "status": "passed" if passed else "failed",
        "trace": trace,
        "result": result,
        "report": report,
        "postcondition_verified": passed,
    }


if __name__ == "__main__":
    try:
        request = json.loads(sys.stdin.read())
        outcome = replay(request["steps"], Path("/workspace/project"))
    except (OSError, ValueError, KeyError, TypeError):
        outcome = {"status": "infrastructure_failure", "reason": "fixture execution failed"}
    print(json.dumps(outcome))
