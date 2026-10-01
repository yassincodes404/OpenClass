"""Provider health and readiness detection for Laya and Jev."""

from enum import StrEnum

import httpx
from pydantic import BaseModel, ConfigDict


class LayaStatus(StrEnum):
    READY = "ready"
    LOADING = "loading"
    UNAVAILABLE = "unavailable"


class JevStatus(StrEnum):
    CONFIGURED = "configured"
    NOT_CONFIGURED = "not_configured"


class ProviderStatusReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    laya: dict[str, str | bool | None]
    jev: dict[str, str | bool | None]


async def check_laya_endpoint(
    base_url: str = "http://127.0.0.1:8000",
    request_timeout: float = 2.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LayaStatus:
    """Probe the HTTP daemon; installed packages are not evidence of readiness."""
    try:
        async with httpx.AsyncClient(transport=transport, timeout=request_timeout) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/health")
            if resp.status_code == 200:
                is_json = resp.headers.get("content-type", "").startswith("application/json")
                data = resp.json() if is_json else {}
                if data.get("status") == "loading":
                    return LayaStatus.LOADING
                return LayaStatus.READY
            if resp.status_code == 503:
                return LayaStatus.LOADING
    except (httpx.RequestError, OSError, ValueError):
        pass

    return LayaStatus.UNAVAILABLE


def check_jev_status(api_key: str | None) -> JevStatus:
    if api_key and api_key.strip():
        return JevStatus.CONFIGURED
    return JevStatus.NOT_CONFIGURED
