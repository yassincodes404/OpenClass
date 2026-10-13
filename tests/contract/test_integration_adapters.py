"""Transport contracts verify real HTTP normalization without online accounts."""

from uuid import uuid4

import httpx
import pytest
from openclass_core.integrations import IntegrationConfig, IntegrationStatus, IntegrationType
from openclass_server.integration_adapters import EnvironmentSecrets, HTTPIntegrationProbe


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

