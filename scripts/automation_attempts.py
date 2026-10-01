"""Secret-safe attempt records and bounded transport retries for Proof #2."""

import asyncio
import json
import math
import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict


class Attempt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str
    attempt: int
    status: str
    latency_ms: float
    http_status: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reported_cost: float | None = None


def usage(body: Any) -> dict[str, Any]:
    """Allowlisted numeric telemetry only; absent values stay unknown."""
    if not isinstance(body, dict):
        return {}
    raw = body.get("usage")
    raw = raw if isinstance(raw, dict) else {}
    result: dict[str, Any] = {}
    for target, names in {
        "input_tokens": ("input_tokens", "prompt_tokens"),
        "output_tokens": ("output_tokens", "completion_tokens"),
    }.items():
        value = next((raw[n] for n in names if n in raw), None)
        if type(value) is int and value >= 0:
            result[target] = value
    metadata = body.get("provider_metadata")
    gateway = metadata.get("gateway") if isinstance(metadata, dict) else None
    cost = gateway.get("cost") if isinstance(gateway, dict) else raw.get("cost")
    if type(cost) in (str, int, float):
        try:
            number = float(cost)
            if math.isfinite(number) and number >= 0:
                result["reported_cost"] = number
        except ValueError:
            pass
    return result


class JevRetryTransport(httpx.AsyncBaseTransport):
    """Three total transport attempts; never retry semantic/validation failures."""

    def __init__(
        self, record: Callable[[Attempt], None], inner: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.record = record
        self.inner = inner or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        for number in range(1, 4):
            started = time.perf_counter()
            try:
                async with asyncio.timeout(15):
                    response = await self.inner.handle_async_request(request)
                    await response.aread()
            except (httpx.TransportError, TimeoutError):
                self.record(
                    Attempt(
                        operation="jev",
                        attempt=number,
                        status="transport_failed",
                        latency_ms=(time.perf_counter() - started) * 1000,
                    )
                )
                if number == 3:
                    raise httpx.TransportError("Jev transport attempts exhausted") from None
                await asyncio.sleep(0.25 * number)
                continue
            try:
                telemetry = usage(json.loads(response.content))
            except ValueError:
                telemetry = {}
            self.record(
                Attempt(
                    operation="jev",
                    attempt=number,
                    status="response_received",
                    http_status=response.status_code,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    **telemetry,
                )
            )
            return response
        raise AssertionError("unreachable")

    async def aclose(self) -> None:
        await self.inner.aclose()
