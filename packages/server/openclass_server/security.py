"""Inspect decoded values for configured credentials and guard outbound integration URLs."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlsplit

_SECRET_REF_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,199}$")

FORBIDDEN_INTEGRATION_SECRET_REFS: frozenset[str] = frozenset(
    {
        "DATABASE_URL",
        "OPENCLASS_DATABASE_URL",
        "POSTGRES_PASSWORD",
        "PGPASSWORD",
        "AI_GATEWAY_API_KEY",
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "ZHIPU_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "KEYCLOAK_CLIENT_SECRET",
        "JWT_SECRET",
        "PATH",
        "HOME",
        "USERPROFILE",
    }
)

FORBIDDEN_INTERNAL_HOSTS: frozenset[str] = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
        "instance-data",
        "postgres",
        "db",
        "redis",
        "keycloak",
        "engine",
        "control-plane",
        "host.docker.internal",
    }
)


def contains_secret(value: object, secret: str) -> bool:
    if not secret:
        return False
    if isinstance(value, str):
        return secret in value
    if isinstance(value, dict):
        return any(
            contains_secret(key, secret) or contains_secret(item, secret)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(contains_secret(item, secret) for item in value)
    return False


def is_allowed_integration_secret_ref(reference: str | None) -> bool:
    """Ensure integrations can only resolve dedicated webhook/integration secret env vars."""
    if not reference or not _SECRET_REF_RE.match(reference):
        return False
    if reference in FORBIDDEN_INTEGRATION_SECRET_REFS:
        return False
    if reference.startswith("OPENCLASS_"):
        return reference.startswith(("OPENCLASS_INTEGRATION_SECRET_", "OPENCLASS_WEBHOOK_"))
    if reference.startswith("TEST_"):
        return True
    return reference.endswith(("_SECRET", "_TOKEN"))


def _check_ip_allowed(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address, *, allow_loopback: bool
) -> None:
    if ip.is_loopback:
        if not allow_loopback:
            raise ValueError("Outbound URL targets a loopback address")
        return
    if (
        ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    ):
        raise ValueError("Outbound URL targets a restricted private or link-local IP address")


def validate_outbound_url(
    url: str | None,
    *,
    allow_loopback: bool = False,
    resolve_dns: bool = True,
) -> str:
    """Validate that an outbound HTTP(S) URL does not target loopback, RFC1918, or metadata IPs."""
    if not url or not isinstance(url, str):
        raise ValueError("A credential-free HTTP endpoint is required")
    try:
        parsed = urlsplit(url.strip())
    except ValueError as exc:
        raise ValueError("A credential-free HTTP endpoint is required") from exc

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("A credential-free HTTP endpoint is required")

    hostname = parsed.hostname.strip().lower().rstrip(".")
    if not allow_loopback and (
        hostname in FORBIDDEN_INTERNAL_HOSTS
        or hostname.endswith((".localhost", ".local", ".internal"))
    ):
        raise ValueError("Outbound URL targets a restricted internal host")

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        _check_ip_allowed(literal_ip, allow_loopback=allow_loopback)
        return url.strip()

    if resolve_dns:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            addr_info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError("Integration endpoint could not be reached") from exc
        if not addr_info:
            raise ValueError("Integration endpoint could not be reached")
        for _family, _type, _proto, _canonname, sockaddr in addr_info:
            resolved_ip = ipaddress.ip_address(sockaddr[0])
            _check_ip_allowed(resolved_ip, allow_loopback=allow_loopback)

    return url.strip()

