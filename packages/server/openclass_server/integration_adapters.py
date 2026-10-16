"""Runtime adapters for integration secrets and supported health checks."""

import asyncio
import hmac
import json
import os
import time
from collections.abc import Mapping
from typing import Any

import httpx
from openclass_core.integrations import (
    IntegrationConfig,
    IntegrationHealthReport,
    IntegrationStatus,
    IntegrationType,
)
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from .security import (
    PublicHTTPTransport,
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
    """HTTP JSON MCP 2025-03-26 only; no SSE/legacy HTTP fallback."""

    def __init__(
        self, secrets: EnvironmentSecrets, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.secrets = secrets
        self.transport = transport

    async def check(self, integration: IntegrationConfig) -> IntegrationHealthReport:
        started = time.perf_counter()
        status = IntegrationStatus.DISCONNECTED
        error: str | None = "Integration endpoint could not be reached"
        capabilities: tuple[str, ...] = ()
        try:
            async with asyncio.timeout(8):
                if integration.type == IntegrationType.WEBHOOK:
                    self.secrets.resolve(integration.secret_ref)
                    auth = (
                        "token_authentication"
                        if integration.signature.mode == "bearer"
                        else "signature_authentication"
                    )
                    capabilities = ("event_ingestion", auth, "idempotent_ingestion")
                    status, error = IntegrationStatus.CONNECTED, None
                elif (
                    integration.type == IntegrationType.DATABASE and not integration.secret_ref
                ) or (
                    integration.type in {IntegrationType.MCP, IntegrationType.PROVIDER}
                    and not integration.endpoint
                ):
                    status, error = (
                        IntegrationStatus.PENDING,
                        "Operator connection configuration is required",
                    )
                elif integration.type == IntegrationType.DATABASE:
                    await self._database(integration)
                    status, error = IntegrationStatus.CONNECTED, None
                    capabilities = ("select_1",)
                else:
                    endpoint = validate_outbound_url(integration.endpoint, resolve_dns=False)
                    headers = {"Accept-Encoding": "identity"}
                    if integration.secret_ref:
                        headers["Authorization"] = (
                            f"Bearer {self.secrets.resolve(integration.secret_ref)}"
                        )
                    async with httpx.AsyncClient(
                        timeout=3,
                        follow_redirects=False,
                        trust_env=False,
                        transport=self.transport or PublicHTTPTransport(),
                    ) as client:
                        if integration.type == IntegrationType.MCP:
                            capabilities = await self._mcp(client, endpoint, headers)
                            if integration.secret_ref and contains_secret(
                                capabilities, self.secrets.resolve(integration.secret_ref)
                            ):
                                capabilities = ()
                                raise ValueError("Credential in result")
                            status, error = IntegrationStatus.CONNECTED, None
                        else:
                            async with client.stream("GET", endpoint, headers=headers) as response:
                                # Reachability is not evidence of provider inference authority.
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
            error = "Integration credential is unavailable or not permitted"
        except (httpx.HTTPError, ValueError, TypeError, KeyError, TimeoutError, OSError):
            error = "Integration protocol, destination or connectivity check failed"
        except Exception:
            # Driver exceptions may contain DSNs/passwords. Persist no exception text.
            error = "Integration connectivity check failed"
        return IntegrationHealthReport(
            integration_id=integration.id,
            status=status,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            capabilities=capabilities,
            error_message=error,
        )

    async def _database(self, integration: IntegrationConfig) -> None:
        reference = integration.secret_ref or ""
        if not reference.startswith("OPENCLASS_INTEGRATION_DATABASE_") or not reference.endswith(
            "_SECRET"
        ):
            raise IntegrationConfigurationError("Dedicated operator database reference required")
        # Deliberately separate from HTTP credentials: this DSN is operator supplied,
        # may address an internal DB, and is NEVER combined with caller endpoint data.
        dsn = os.environ.get(reference, "")
        url = make_url(dsn)
        if (
            url.drivername != "postgresql+asyncpg"
            or not url.host
            or integration.endpoint
            or integration.metadata
        ):
            raise ValueError("Only an operator PostgreSQL DSN is supported")
        engine = create_async_engine(
            url,
            poolclass=NullPool,
            hide_parameters=True,
            connect_args={
                "timeout": 3,
                "command_timeout": 3,
                "server_settings": {
                    "default_transaction_read_only": "on",
                    "statement_timeout": "3000",
                },
            },
        )
        try:
            async with engine.connect() as connection:
                if await connection.scalar(text("SELECT 1")) != 1:
                    raise ValueError("Database check failed")
        finally:
            await engine.dispose()

    @staticmethod
    async def _rpc(
        client: httpx.AsyncClient, endpoint: str, headers: dict[str, str], payload: dict[str, Any]
    ) -> tuple[dict[str, Any], str | None]:
        async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
            if (
                not 200 <= response.status_code < 300
                or response.headers.get("content-type", "").split(";")[0] != "application/json"
                or response.headers.get("content-encoding", "identity") != "identity"
            ):
                raise ValueError("Unsupported MCP transport or HTTP response")
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                if len(raw) + len(chunk) > 64_000:
                    raise ValueError("MCP response too large")
                raw.extend(chunk)
            result = json.loads(raw)
            if (
                not isinstance(result, dict)
                or result.get("jsonrpc") != "2.0"
                or type(result.get("id")) is not int
                or result["id"] != payload["id"]
                or "error" in result
                or not isinstance(result.get("result"), dict)
            ):
                raise ValueError("Invalid MCP JSON-RPC result")
            session = response.headers.get("mcp-session-id")
            if session is not None and (
                not session
                or len(session) > 200
                or any(ord(c) < 33 or ord(c) > 126 for c in session)
            ):
                raise ValueError("Invalid MCP session")
            if (
                payload["method"] != "initialize"
                and session
                and session != headers.get("Mcp-Session-Id")
            ):
                raise ValueError("MCP session changed")
            return result["result"], session

    async def _mcp(
        self, client: httpx.AsyncClient, endpoint: str, headers: dict[str, str]
    ) -> tuple[str, ...]:
        headers = {**headers, "Accept": "application/json, text/event-stream"}
        result, session = await self._rpc(
            client,
            endpoint,
            headers,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "openclass-health", "version": "0.0.1"},
                },
            },
        )
        if (
            result.get("protocolVersion") != "2025-03-26"
            or not isinstance(result.get("capabilities"), dict)
            or not isinstance(result.get("serverInfo"), dict)
        ):
            raise ValueError("Unsupported MCP initialization")
        if any(
            not isinstance(result["serverInfo"].get(key), str)
            or not result["serverInfo"][key].strip()
            for key in ("name", "version")
        ):
            raise ValueError("Invalid MCP server identity")
        if "tools" not in result["capabilities"] or not isinstance(
            result["capabilities"]["tools"], dict
        ):
            raise ValueError("MCP tools unavailable")
        headers["MCP-Protocol-Version"] = "2025-03-26"
        if session:
            headers["Mcp-Session-Id"] = session
        async with client.stream(
            "POST",
            endpoint,
            headers=headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        ) as response:
            if response.status_code != 202:
                raise ValueError("MCP initialization notification rejected")
            if response.headers.get("mcp-session-id", session) != session:
                raise ValueError("MCP session changed")
        names: list[str] = []
        cursor: str | None = None
        cursors: set[str] = set()
        for page in range(3):
            result, _ = await self._rpc(
                client,
                endpoint,
                headers,
                {
                    "jsonrpc": "2.0",
                    "id": page + 2,
                    "method": "tools/list",
                    "params": {"cursor": cursor} if cursor else {},
                },
            )
            tools = result.get("tools")
            if not isinstance(tools, list) or len(tools) > 100:
                raise ValueError("Invalid MCP tools")
            for tool in tools:
                if (
                    not isinstance(tool, dict)
                    or not isinstance(tool.get("name"), str)
                    or not tool["name"].strip()
                    or len(tool["name"]) > 100
                    or not isinstance(tool.get("inputSchema"), dict)
                    or tool["inputSchema"].get("type") != "object"
                ):
                    raise ValueError("Invalid MCP tool")
                names.append(tool["name"])
            cursor = result.get("nextCursor")
            if "nextCursor" in result and cursor is None:
                raise ValueError("Invalid MCP cursor")
            if cursor is None:
                # Tool names are observed availability, not execution grants.
                return tuple(dict.fromkeys(names))
            if not isinstance(cursor, str) or not cursor or len(cursor) > 500 or cursor in cursors:
                raise ValueError("Invalid MCP cursor")
            cursors.add(cursor)
        raise ValueError("MCP pagination bound exceeded")
