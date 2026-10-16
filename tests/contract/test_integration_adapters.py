"""Transport contracts verify real HTTP normalization without online accounts."""

from uuid import uuid4

import httpx
import pytest
from openclass_core.integrations import IntegrationConfig, IntegrationStatus, IntegrationType
from openclass_server.integration_adapters import EnvironmentSecrets, HTTPIntegrationProbe


async def test_mcp_initializes_before_listing_and_keeps_session_header():
    import json

    seen = []

    def handle(request):
        payload = json.loads(request.content)
        seen.append(payload["method"])
        if payload["method"] == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "synthetic-session"},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "fixture", "version": "1"},
                    },
                },
            )
        assert request.headers["Mcp-Session-Id"] == "synthetic-session"
        assert request.headers["MCP-Protocol-Version"] == "2025-03-26"
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"tools": [{"name": "lookup", "inputSchema": {"type": "object"}}]},
            },
        )

    report = await HTTPIntegrationProbe(EnvironmentSecrets(), httpx.MockTransport(handle)).check(
        IntegrationConfig(
            project_id=uuid4(),
            name="mcp",
            type=IntegrationType.MCP,
            endpoint="https://mcp.example/rpc",
        )
    )
    assert report.status == IntegrationStatus.CONNECTED
    assert report.capabilities == ("lookup",)
    assert seen == ["initialize", "notifications/initialized", "tools/list"]


@pytest.mark.parametrize(
    "code,expected", [(200, "connected"), (302, "degraded"), (401, "degraded"), (503, "degraded")]
)
async def test_rest_probe_verifies_http_without_inventing_capabilities(
    monkeypatch: pytest.MonkeyPatch,
    code: int,
    expected: str,
) -> None:
    monkeypatch.setenv("TEST_REST_TOKEN", "test-rest-credential")
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-rest-credential"
        return httpx.Response(
            code, headers={"Location": "https://elsewhere.invalid"}, text="private response"
        )

    probe = HTTPIntegrationProbe(EnvironmentSecrets(), httpx.MockTransport(handle))
    report = await probe.check(
        IntegrationConfig(
            project_id=uuid4(),
            name="REST",
            type=IntegrationType.REST_API,
            endpoint="https://example.invalid/health",
            secret_ref="TEST_REST_TOKEN",
            capabilities=("unverified_capability",),
        )
    )
    assert report.status.value == expected
    assert report.capabilities == ()
    assert len(requests) == 1
    assert "private response" not in report.model_dump_json()


async def test_transport_errors_are_secret_safe() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("upstream secret-bearing exception", request=request)

    report = await HTTPIntegrationProbe(EnvironmentSecrets(), httpx.MockTransport(handle)).check(
        IntegrationConfig(
            project_id=uuid4(),
            name="REST",
            type=IntegrationType.REST_API,
            endpoint="http://example.invalid",
        )
    )
    assert report.status == IntegrationStatus.DISCONNECTED
    assert "secret-bearing" not in report.model_dump_json()


@pytest.mark.parametrize(
    "endpoint",
    [
        None,
        "file:///etc/passwd",
        "https://user:password@example.invalid",
        "http://[",
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:7331/health",
        "http://localhost:8000/api/v1/system/health",
        "http://10.0.0.1/internal",
        "http://192.168.1.1/admin",
        "http://[::1]:8000/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://postgres:5432/",
    ],
)
async def test_invalid_endpoint_is_not_contacted(endpoint: str | None) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid or SSRF endpoint must not be contacted")

    report = await HTTPIntegrationProbe(EnvironmentSecrets(), httpx.MockTransport(handle)).check(
        IntegrationConfig(
            project_id=uuid4(), name="REST", type=IntegrationType.REST_API, endpoint=endpoint
        )
    )
    assert report.status == IntegrationStatus.DISCONNECTED


@pytest.mark.parametrize(
    "forbidden_ref",
    [
        "OPENCLASS_DATABASE_URL",
        "DATABASE_URL",
        "OPENCLASS_JEV_API_KEY",
        "OPENCLASS_GLM_API_KEY",
        "AI_GATEWAY_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "PATH",
    ],
)
async def test_forbidden_system_secret_refs_cannot_be_exfiltrated(
    monkeypatch: pytest.MonkeyPatch,
    forbidden_ref: str,
) -> None:
    monkeypatch.setenv(forbidden_ref, "sensitive-system-secret-value")

    def handle(request: httpx.Request) -> httpx.Response:
        pytest.fail("Probe must not contact external endpoint with forbidden system secret")

    report = await HTTPIntegrationProbe(EnvironmentSecrets(), httpx.MockTransport(handle)).check(
        IntegrationConfig(
            project_id=uuid4(),
            name="Exfil Probe",
            type=IntegrationType.REST_API,
            endpoint="https://example.invalid/exfil",
            secret_ref=forbidden_ref,
        )
    )
    assert report.status == IntegrationStatus.DISCONNECTED
    assert "sensitive-system-secret-value" not in report.model_dump_json()


@pytest.mark.parametrize(
    "secret", ['test-quote-"-token', "test-unicode-☃-token", "test-escape-\\-token"]
)
def test_decoded_secret_content_cannot_escape_redaction(
    monkeypatch: pytest.MonkeyPatch,
    secret: str,
) -> None:
    monkeypatch.setenv("TEST_ESCAPED_TOKEN", secret)
    integration = IntegrationConfig(
        project_id=uuid4(),
        name="Webhook",
        type=IntegrationType.WEBHOOK,
        secret_ref="TEST_ESCAPED_TOKEN",
    )
    with pytest.raises(ValueError, match="Input contains an integration credential"):
        EnvironmentSecrets().reject_secret_content(integration, {"metadata": {"nested": [secret]}})


@pytest.mark.parametrize(
    "fault",
    [
        "json",
        "rpc_error",
        "id",
        "version",
        "no_tools",
        "sse",
        "oversized",
        "cursor",
        "session",
        "secret",
        "notify_session",
        "cursor_null",
        "empty_schema",
    ],
)
async def test_mcp_invalid_protocol_never_invents_capabilities(monkeypatch, fault):
    import json

    monkeypatch.setenv("TEST_MCP_TOKEN", "synthetic-mcp-token")
    methods = []

    def handle(request):
        payload = json.loads(request.content)
        methods.append(payload["method"])
        if payload["method"] == "initialize":
            if fault == "json":
                return httpx.Response(
                    200, text="not json", headers={"Content-Type": "application/json"}
                )
            if fault == "sse":
                return httpx.Response(
                    200, text="data: {}", headers={"Content-Type": "text/event-stream"}
                )
            if fault == "oversized":
                return httpx.Response(
                    200, content=b" " * 64_001, headers={"Content-Type": "application/json"}
                )
            if fault == "rpc_error":
                return httpx.Response(
                    200,
                    json={"jsonrpc": "2.0", "id": 1, "error": {"message": "synthetic-mcp-token"}},
                )
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "session-one"},
                json={
                    "jsonrpc": "2.0",
                    "id": 999 if fault == "id" else 1,
                    "result": {
                        "protocolVersion": "unknown" if fault == "version" else "2025-03-26",
                        "capabilities": {} if fault == "no_tools" else {"tools": {}},
                        "serverInfo": {"name": "mock", "version": "1"},
                    },
                },
            )
        if payload["method"] == "notifications/initialized":
            return httpx.Response(
                202,
                headers={"Mcp-Session-Id": "other" if fault == "notify_session" else "session-one"},
            )
        result = {
            "tools": [
                {
                    "name": "synthetic-mcp-token" if fault == "secret" else "lookup",
                    "inputSchema": {} if fault == "empty_schema" else {"type": "object"},
                }
            ]
        }
        if fault == "cursor":
            result["nextCursor"] = "same-forever"
        if fault == "cursor_null":
            result["nextCursor"] = None
        return httpx.Response(
            200,
            headers={"Mcp-Session-Id": "session-two" if fault == "session" else "session-one"},
            json={"jsonrpc": "2.0", "id": payload["id"], "result": result},
        )

    report = await HTTPIntegrationProbe(EnvironmentSecrets(), httpx.MockTransport(handle)).check(
        IntegrationConfig(
            project_id=uuid4(),
            name="mcp",
            type=IntegrationType.MCP,
            endpoint="https://mcp.example/rpc",
            secret_ref="TEST_MCP_TOKEN",
        )
    )
    assert report.status == IntegrationStatus.DISCONNECTED
    assert report.capabilities == ()
    assert "synthetic-mcp-token" not in report.model_dump_json()
    assert len(methods) <= 5


@pytest.mark.parametrize("fails", [False, True])
async def test_database_executes_only_bounded_select_and_always_disposes(monkeypatch, fails):
    from openclass_server import integration_adapters

    monkeypatch.setenv(
        "OPENCLASS_INTEGRATION_DATABASE_FIXTURE_SECRET",
        "postgresql+asyncpg://probe:synthetic-db-password@internal-db/probe",
    )
    seen = []

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def scalar(self, sql):
            seen.append(str(sql))
            if fails:
                raise RuntimeError("synthetic-db-password")
            return 1

    class Engine:
        def connect(self):
            return Connection()

        async def dispose(self):
            seen.append("disposed")

    def engine(url, **kwargs):
        assert url.host == "internal-db"
        assert kwargs["connect_args"]["command_timeout"] == 3
        assert kwargs["connect_args"]["server_settings"]["default_transaction_read_only"] == "on"
        return Engine()

    monkeypatch.setattr(integration_adapters, "create_async_engine", engine)
    report = await HTTPIntegrationProbe(EnvironmentSecrets()).check(
        IntegrationConfig(
            project_id=uuid4(),
            name="db",
            type=IntegrationType.DATABASE,
            secret_ref="OPENCLASS_INTEGRATION_DATABASE_FIXTURE_SECRET",
        )
    )
    assert seen == ["SELECT 1", "disposed"]
    assert report.status == (
        IntegrationStatus.DISCONNECTED if fails else IntegrationStatus.CONNECTED
    )
    assert report.capabilities == (() if fails else ("select_1",))
    assert "synthetic-db-password" not in report.model_dump_json()


@pytest.mark.parametrize(
    "reference,dsn,endpoint,metadata",
    [
        ("OPENCLASS_DATABASE_URL", "postgresql+asyncpg://probe@db/probe", None, {}),
        (
            "OPENCLASS_INTEGRATION_DATABASE_FIXTURE_SECRET",
            "sqlite+aiosqlite:///sensitive.db",
            None,
            {},
        ),
        (
            "OPENCLASS_INTEGRATION_DATABASE_FIXTURE_SECRET",
            "postgresql+asyncpg://probe@db/probe",
            "https://attacker.example",
            {},
        ),
        (
            "OPENCLASS_INTEGRATION_DATABASE_FIXTURE_SECRET",
            "postgresql+asyncpg://probe@db/probe",
            None,
            {"query": "DROP TABLE evidence"},
        ),
    ],
)
async def test_database_cannot_use_global_secret_file_or_caller_override(
    monkeypatch, reference, dsn, endpoint, metadata
):
    from openclass_server import integration_adapters

    monkeypatch.setenv(reference, dsn)

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid database target must never create an engine")

    monkeypatch.setattr(integration_adapters, "create_async_engine", forbidden)
    report = await HTTPIntegrationProbe(EnvironmentSecrets()).check(
        IntegrationConfig(
            project_id=uuid4(),
            name="db",
            type=IntegrationType.DATABASE,
            endpoint=endpoint,
            metadata=metadata,
            secret_ref=reference,
        )
    )
    assert report.status == IntegrationStatus.DISCONNECTED
    assert report.capabilities == ()
