"""Authorized experimental v2 and exactly one Run 2/Run 3 each. No discovery adapter."""

import asyncio
import json
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from automation_attempts import Attempt, JevRetryTransport
from automation_policy_approval import approved_now, create_policy_v2, digest
from openclass_core.models import ChoiceRequest, Observation, OntologyVersion
from openclass_core.providers import ProviderError
from openclass_provider_jev import JevDecisionProvider
from pydantic import SecretStr

SOURCE = Path("build/automation-proof2/20260924T120323Z")
IMAGE = "sha256:4c47124a8391cb7a9f571164147d154777cf012a4ece5f86097130d7a4478111"
APPROVAL = (
    "I explicitly approve candidate d23d7342-71a7-4db6-876f-51edea836a2f, "
    "based on AutomationPolicy version b28e35ee-7f33-451c-89a0-ee9a43dc86c3, "
    "for experimental deterministic creation of AutomationPolicy v2 and execution "
    "of Proof #2 Runs 2 and 3 only."
)
SERVICE = """from http.server import BaseHTTPRequestHandler, HTTPServer

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"warehouse-ready")
    def log_message(self, *args):
        pass

def make_server(port):
    return HTTPServer(("127.0.0.1", port), HealthHandler)
"""
SERVICE_TEST = """import os
import threading
import unittest
from urllib.request import urlopen
from warehouse_service import make_server

class HealthCheck(unittest.TestCase):
    def test_warehouse_health(self):
        with make_server(int(os.environ["TEST_PORT"])) as server:
            worker = threading.Thread(target=server.handle_request, daemon=True)
            worker.start()
            with urlopen("http://127.0.0.1:%s/health" % server.server_port, timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"warehouse-ready")
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
"""


class DisabledDiscoveryProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def discover(self, request: Any) -> Any:
        self.calls += 1
        raise AssertionError("Discovery is forbidden during Proof #2 replay")


class JevOnlyTransport(JevRetryTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) != "https://ai-gateway.vercel.sh/typesafe/v1/systemone":
            raise AssertionError("Only Jev decision inference is permitted")
        return await super().handle_async_request(request)


def persist(path: Path, value: Any) -> None:
    with path.open("x") as output:
        output.write(json.dumps(value, indent=2) + "\n")


def prepare_project(path: Path, *, transfer: bool) -> None:
    path.mkdir()
    (path / "output").mkdir()
    if not transfer:
        shutil.copyfile(SOURCE / "project/README.md", path / "README.md")
    else:
        (path / "tests").mkdir()
        (path / "README.md").write_text(
            "Warehouse health service. Run tests in tests/test_health.py "
            "and write a result report.\n"
            "The service uses TEST_PORT, initially 3000.\n"
        )
        (path / "warehouse_service.py").write_text(SERVICE)
        (path / "tests/test_health.py").write_text(SERVICE_TEST)


def execute(steps: list[str], project: Path, *, transfer: bool) -> dict[str, Any]:
    scripts = Path(__file__).resolve().parent
    fixture = scripts / (
        "automation_transfer_fixture.py" if transfer else "automation_replay_fixture.py"
    )
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=32",
                "--memory=128m",
                "--cpus=1",
                "--user=65534:65534",
                "--mount",
                f"type=bind,src={project.resolve()},dst=/workspace/project,readonly",
                "--mount",
                f"type=bind,src={fixture},dst=/fixture.py,readonly",
                "--mount",
                f"type=bind,src={scripts / 'automation_replay_fixture.py'},"
                "dst=/automation_replay_fixture.py,readonly",
                "--tmpfs",
                "/workspace/project/output:rw,noexec,nosuid,size=1m,mode=1777",
                "-i",
                IMAGE,
                "python",
                "/fixture.py",
            ],
            input=json.dumps({"steps": steps}),
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("container execution failed")
        result: dict[str, Any] = json.loads(completed.stdout)
        if result.get("status") == "infrastructure_failure":
            raise RuntimeError("fixture infrastructure failed")
        result["latency_ms"] = (time.perf_counter() - started) * 1000
        return result
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise RuntimeError("executor infrastructure failed") from None


async def replay_run(
    root: Path,
    policy: dict[str, Any],
    key: str,
    *,
    transfer: bool,
    discovery: DisabledDiscoveryProvider,
) -> dict[str, Any]:
    """Let real Jev choose every action; only its selected macro can invoke the procedure."""
    project = root / "project"
    prepare_project(project, transfer=transfer)
    space = OntologyVersion.model_validate(policy["decision_space"])
    proposal = policy["candidate"]["proposal"]
    trace: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    started = time.perf_counter()
    status = "decision_budget_exhausted"
    verified = False
    macro_used = False
    macro_at_failure = False
    test_result = None
    inspected = False
    state: str = "Goal: run tests and write a report. Project directory has not been inspected."
    error = None

    def record(attempt: Attempt) -> None:
        value = {
            "sequence": len(attempts) + 1,
            "decision_step": len(trace) + 1,
            **attempt.model_dump(),
        }
        attempts.append(value)
        persist(root / f"attempt-{len(attempts):03}.json", value)

    try:
        for _ in range(12):
            provider = JevDecisionProvider(
                api_key=SecretStr(key),
                base_url="https://ai-gateway.vercel.sh/typesafe",
                model="typesafe-ai/jev",
                timeout=60,
                max_retries=0,
                transport=JevOnlyTransport(record),
            )
            decision = await provider.choice(
                ChoiceRequest(observation=Observation(content=state), ontology=space)
            )
            top = max(decision.probabilities, key=lambda name: decision.probabilities[name])
            if decision.unknown_probability >= decision.probabilities[top]:
                top = "UNKNOWN"
            entry: dict[str, Any] = {
                "step": len(trace) + 1,
                "state": state,
                "selected_action": top,
                "decision": decision.model_dump(mode="json"),
            }
            trace.append(entry)
            # Persist the decision even if execution later fails.
            persist(root / f"decision-{len(trace):02}.json", entry)
            if top == "done":
                status = (
                    "passed" if verified and macro_used and macro_at_failure else "premature_done"
                )
                break
            if top in {"blocked", "UNKNOWN"}:
                status = (
                    "semantic_blocked"
                    if test_result and test_result["exit_code"] != 0
                    else "incomplete_execution"
                )
                break
            if top == proposal["canonical_name"]:
                macro_at_failure = bool(
                    test_result
                    and test_result["exit_code"] != 0
                    and "Address already in use" in test_result["output"]
                    and inspected
                )
                result = execute(proposal["steps"], project, transfer=transfer)
                macro_used = True
                test_result = result.get("result")
                verified = result.get("postcondition_verified") is True
            elif top == "inspect_result":
                inspected = True
                result = {"result": test_result}
            elif top in {"list_directory", "read_file", "run_tests", "write_report"}:
                result = execute([top], project, transfer=transfer)
                if top == "run_tests":
                    test_result = result["result"]
                    inspected = False
                    verified = False
                elif top == "write_report":
                    # An isolated report action cannot manufacture the previous successful result.
                    verified = result.get("postcondition_verified") is True
            else:
                raise AssertionError("unregistered decision")
            entry["executor"] = result
            persist(root / f"executor-{len(trace):02}.json", result)
            actions = [t["selected_action"] for t in trace]
            state = json.dumps(
                {
                    "question": "Which registered action should execute next to advance the goal?",
                    "goal": "Run tests and write a report.",
                    "files_listed": "list_directory" in actions,
                    "readme_read": "read_file" in actions,
                    "test_attempted": test_result is not None,
                    "test_result": test_result,
                    "result_inspected": inspected,
                    "report_exists": verified,
                    "last_action": top,
                    "project_files": sorted(
                        str(p.relative_to(project)) for p in project.rglob("*") if p.is_file()
                    ),
                    "policy_version": 2,
                }
            )
    except (ProviderError, RuntimeError):
        status = "infrastructure_failed"
        error = "provider or executor failed; no synthetic BLOCKED evidence"
    except AssertionError:
        status = "safety_failed"
        error = "forbidden capability or unregistered action"
    if discovery.calls:
        status = "safety_failed"
    report = {
        "run": 3 if transfer else 2,
        "status": status,
        "error": error,
        "policy_id": policy["id"],
        "base_policy_id": policy["parent_version_id"],
        "candidate_id": policy["candidate"]["id"],
        "macro_selected_by_jev": macro_used,
        "macro_selected_at_observed_inspected_conflict": macro_at_failure,
        "postconditions_verified": verified,
        "trace": trace,
        "provider_attempts": attempts,
        "discovery_provider": "disabled_assertion_sentinel",
        "discovery_calls": discovery.calls,
        "network_allowlist": ["https://ai-gateway.vercel.sh/typesafe/v1/systemone"],
        "image": IMAGE,
        "occupied_port": 3000 if transfer else 8000,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }
    persist(root / "report.json", report)
    return report


def main() -> int:
    key = os.environ["OPENCLASS_JEV_API_KEY"]
    os.environ.pop("AI_GATEWAY_API_KEY", None)
    os.environ.pop("OPENCLASS_DISCOVERY_API_KEY", None)
    os.environ["OPENCLASS_DISCOVERY_PROVIDER"] = "disabled"
    root = Path("build/automation-proof2-reuse") / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root.mkdir(parents=True)
    source_before = {str(p): digest(p.read_bytes()) for p in SOURCE.rglob("*") if p.is_file()}
    policy = create_policy_v2(SOURCE, root / "policy-v2.json", approved_now(APPROVAL))
    # Exact reviewed bytes are retained, not reserialized or edited.
    shutil.copyfile(SOURCE / "review/candidate.json", root / "approved-candidate.json")
    policy_hash = digest((root / "policy-v2.json").read_bytes())
    results = []
    for number in (2, 3):
        folder = root / f"run-{number}"
        folder.mkdir()
        report = asyncio.run(
            replay_run(
                folder, policy, key, transfer=number == 3, discovery=DisabledDiscoveryProvider()
            )
        )
        results.append({"run": number, "status": report["status"]})
        print(
            json.dumps(
                {"run": number, "status": report["status"], "report": str(folder / "report.json")}
            )
        )
    source_unchanged = all(digest(Path(p).read_bytes()) == h for p, h in source_before.items())
    assert source_unchanged and digest((root / "policy-v2.json").read_bytes()) == policy_hash
    persist(
        root / "integrity.json",
        {
            "source_before": source_before,
            "source_unchanged": source_unchanged,
            "policy_v2_sha256": policy_hash,
            "base_policy_sha256": policy["base_policy_sha256"],
            "candidate_sha256": policy["candidate_sha256"],
        },
    )
    print(json.dumps({"root": str(root), "results": results, "policy_id": policy["id"]}))
    return 0 if all(r["status"] == "passed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
