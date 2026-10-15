"""Real local HTTP/CLI regression; SQLite is NOT the full-stack PostgreSQL gate."""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
CLI = [sys.executable, "-c", "from openclass_cli.main import main; main()"]


@pytest.mark.parametrize("authenticated", [False, True], ids=["base-no-key", "private-engine"])
def test_quickstart_http_and_cli(tmp_path: Path, authenticated: bool) -> None:
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("OPENCLASS_", "AI_GATEWAY_"))
    }
    env.update(
        OPENCLASS_DATABASE_URL=f"sqlite+aiosqlite:///{(tmp_path / 'engine.db').as_posix()}",
        OPENCLASS_DECISION_PROVIDER="mock",
        OPENCLASS_AUTH_REQUIRED=str(authenticated).lower(),
        OPENCLASS_INTERNAL_TOKEN=secrets.token_hex(32) if authenticated else "",
        OPENCLASS_SERVER_URL=url,
        OPENCLASS_SMOKE_BASE_URL=url,
    )

    def run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            arguments,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
            timeout=30,
        )

    run([sys.executable, "-m", "alembic", "upgrade", "head"])
    with (tmp_path / "server.log").open("w") as output:
        server = subprocess.Popen(
            [*CLI, "serve", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            with httpx.Client(base_url=url, timeout=1) as client:
                deadline = time.monotonic() + 15
                while True:
                    try:
                        if client.get("/health/ready").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    assert server.poll() is None, "Owned test server exited before readiness"
                    assert time.monotonic() < deadline, "Owned test server readiness timed out"
                    time.sleep(0.05)
                assert client.get("/api/v1/classifiers").status_code == (
                    401 if authenticated else 200
                )
            smoke = run([sys.executable, "-m", "scripts.live_stack.engine_smoke"])
            assert ("internal-token" if authenticated else "local-anonymous") in smoke.stdout
            if not authenticated:
                # The exact documented commands, with only a scoped test URL.
                created = run([*CLI, "init", "examples/support-intents/classifier.json"])
                assert json.loads(created.stdout)["slug"] == "support-intent"
                classified = run([*CLI, "classify", "Cancel my plan"])
                assert isinstance(json.loads(classified.stdout), dict)
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
