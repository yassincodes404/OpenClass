"""Runtime adapters for integration secrets and supported health checks."""

import hmac
import os
import time
from collections.abc import Mapping

import httpx
from openclass_core.integrations import (
    IntegrationConfig,
    IntegrationHealthReport,
    IntegrationStatus,
    IntegrationType,
)

from .security import (
    contains_secret,
    is_allowed_integration_secret_ref,
    validate_outbound_url,
)


class WebhookAuthenticationError(Exception):
    """Invalid caller credentials; message never includes supplied values."""


class IntegrationConfigurationError(Exception):
    """A secret reference cannot be resolved; no insecure fallback."""


class EnvironmentSecrets:
    def resolve(self, reference: str | None) -> str:
        if reference is None:
            raise IntegrationConfigurationError("Webhook authentication is not configured")
        if not is_allowed_integration_secret_ref(reference):
            raise IntegrationConfigurationError(
                "Secret reference is not permitted for integrations"
            )
        secret = os.environ.get(reference, "")
        if not secret.strip():
            raise IntegrationConfigurationError("Integration credential is unavailable")
        return secret

    def authenticate(self, integration: IntegrationConfig, headers: Mapping[str, str]) -> None:
        expected = self.resolve(integration.secret_ref)
        token = headers.get("x-openclass-token", "")
        authorization = headers.get("authorization", "")
        if authorization:
            scheme, separator, value = authorization.partition(" ")
            if scheme.casefold() != "bearer" or not separator:
                raise WebhookAuthenticationError("Invalid webhook token")
            if token and token != value:
                raise WebhookAuthenticationError("Conflicting webhook credentials")
            token = value
        if not token or not hmac.compare_digest(token.encode(), expected.encode()):
            raise WebhookAuthenticationError("Invalid webhook token")

    def reject_secret_content(self, integration: IntegrationConfig, value: object) -> None:
        if contains_secret(value, self.resolve(integration.secret_ref)):
            raise ValueError("Input contains an integration credential")

    def reject_configured_content(self, reference: str | None, value: object) -> None:
        if reference is None:
            return
        try:
            secret = self.resolve(reference)
        except IntegrationConfigurationError:
            # Configuration may be registered before the operator supplies its credential.
            return
        if contains_secret(value, secret):
            raise ValueError("Input contains an integration credential")


class HTTPIntegrationProbe:
    def __init__(
        self,
        secrets: EnvironmentSecrets,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.secrets = secrets
        self.transport = transport

    async def check(self, integration: IntegrationConfig) -> IntegrationHealthReport:
        started = time.perf_counter()
        status = IntegrationStatus.PENDING
        error: str | None = "Connectivity checks for this integration type are not implemented"
        capabilities: tuple[str, ...] = ()
        if integration.type == IntegrationType.WEBHOOK:
            try:
                self.secrets.resolve(integration.secret_ref)
                status, error = IntegrationStatus.CONNECTED, None
                capabilities = ("event_ingestion", "token_authentication", "idempotent_ingestion")
            except IntegrationConfigurationError:
                status = IntegrationStatus.DISCONNECTED
                error = "Webhook authentication credential is unavailable"
        elif integration.type == IntegrationType.REST_API or (
            integration.type in {IntegrationType.MCP, IntegrationType.PROVIDER}
            and (integration.endpoint or "").strip()
        ):
            endpoint = integration.endpoint or ""
            try:
                validated_endpoint = validate_outbound_url(
                    endpoint,
                    allow_loopback=False,
                    resolve_dns=self.transport is None,
                )
            except ValueError as exc:
                status = IntegrationStatus.DISCONNECTED
                error = str(exc)
            else:
                try:
                    headers = {}
                    if integration.secret_ref:
                        headers["Authorization"] = (
                            f"Bearer {self.secrets.resolve(integration.secret_ref)}"
                        )
                    async with httpx.AsyncClient(
                        timeout=5,
                        follow_redirects=False,
                        transport=self.transport,
                        trust_env=False,
                    ) as client:
                        if integration.type == IntegrationType.MCP:
                            response = await client.post(
                                validated_endpoint,
                                headers=headers,
                                json={
                                    "jsonrpc": "2.0",
                                    "id": 1,
                                    "method": "tools/list",
                                    "params": {},
                                },
                            )
                            if response.status_code == 405:
                                response = await client.get(validated_endpoint, headers=headers)
                        else:
                            response = await client.get(validated_endpoint, headers=headers)

                    if integration.type == IntegrationType.MCP:
                        if 200 <= response.status_code < 300:
                            status, error = IntegrationStatus.CONNECTED, None
                            discovered = self._extract_mcp_tools(response)
                            capabilities = discovered or ("mcp_tools", "context_fetch")
                        else:
                            status = IntegrationStatus.DEGRADED
                            error = f"HTTP {response.status_code}"
                    elif integration.type == IntegrationType.PROVIDER:
                        if 200 <= response.status_code < 300 or response.status_code in {401, 403}:
                            status, error = IntegrationStatus.CONNECTED, None
                            capabilities = ("model_inference",)
                        else:
                            status = IntegrationStatus.DEGRADED
                            error = f"HTTP {response.status_code}"
                    else:
                        status = (
                            IntegrationStatus.CONNECTED
                            if 200 <= response.status_code < 300
                            else IntegrationStatus.DEGRADED
                        )
                        error = (
                            None
                            if status == IntegrationStatus.CONNECTED
                            else f"HTTP {response.status_code}"
                        )
                except IntegrationConfigurationError:
                    status, error = (
                        IntegrationStatus.DISCONNECTED,
                        "Integration credential is unavailable",
                    )
                except (httpx.HTTPError, ValueError):
                    status, error = (
                        IntegrationStatus.DISCONNECTED,
                        "Integration endpoint could not be reached",
                    )
        return IntegrationHealthReport(
            integration_id=integration.id,
            status=status,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            capabilities=capabilities,
            error_message=error,
        )

    @staticmethod
    def _extract_mcp_tools(response: httpx.Response) -> tuple[str, ...]:
        try:
            payload = response.json()
        except ValueError:
            return ()
        if not isinstance(payload, Mapping):
            return ()
        result = payload.get("result")
        if not isinstance(result, Mapping):
            return ()
        tools = result.get("tools")
        if not isinstance(tools, list):
            return ()
        names: list[str] = []
        for item in tools:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, Mapping):
                name = item.get("name")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
        return tuple(names)
