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
    "endpoint", [None, "file:///etc/passwd", "https://user:password@example.invalid", "http://["]
)
async def test_invalid_endpoint_is_not_contacted(endpoint: str | None) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid endpoint must not be contacted")

    report = await HTTPIntegrationProbe(EnvironmentSecrets(), httpx.MockTransport(handle)).check(
        IntegrationConfig(
            project_id=uuid4(), name="REST", type=IntegrationType.REST_API, endpoint=endpoint
        )
    )
    assert report.status == IntegrationStatus.DISCONNECTED


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
