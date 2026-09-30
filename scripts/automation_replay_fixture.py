"""Fixed, offline Proof #2 executor. Run only in a disposable sandbox.

Inputs are closed primitive names, never code, commands, paths, or environment
values. This synthetic test project exercises a real socket bind conflict.
"""

import json
import socket
import sys
from pathlib import Path
from typing import Any

PRIMITIVES = {
    "list_directory": "List the fixed project directory.",
    "read_file": "Read the fixed project README.",
    "run_tests": "Run the socket-bind test using the configured test port.",
    "inspect_result": "Read the last test result.",
    "write_report": "Write output/report.json from the last test result.",
    "done": "Stop execution; success still requires verified tests and report.",
    "blocked": "Stop execution without success.",
    "inspect_port": "Check whether the configured test port can be bound.",
    "choose_available_test_port": "Select a bindable port from the permitted range.",
    "set_environment": "Set only TEST_PORT to the previously selected port.",
    "rerun_previous": "Repeat the previous test with the configured TEST_PORT.",
    "check_exit_code": "Read the last test exit code.",
}


def replay(steps: list[str], project: Path, occupied_port: int = 8000) -> dict[str, Any]:
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
                # The previous operation at this recovery boundary is always the failed test.
                with socket.socket() as test_socket:
                    try:
                        test_socket.bind(("127.0.0.1", configured))
                        result = {"exit_code": 0, "output": "TESTS PASSED", "port": configured}
                    except OSError:
                        result = {
                            "exit_code": 1,
                            "output": "Address already in use",
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
