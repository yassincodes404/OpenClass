"""Budgeted live Teacher calls: identical-request retries only, full attempt records."""

import asyncio
import json
import time
from typing import Any

import httpx

from .canonical import digest

GATEWAY = "https://ai-gateway.vercel.sh/v1/chat/completions"
RETRY_STATUS = {429, 500, 502, 503, 504}


class TeacherBudget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.successful = 0
        self.retries = 0

    def allow(self) -> bool:
        return self.successful < self.limit


class TeacherTransportExhausted(Exception):
    pass


def wire_payload(model: str, packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": model,
        "temperature": packet["temperature"],
        "max_tokens": packet["max_tokens"],
        "messages": packet["messages"],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "teacher_candidate",
                "strict": True,
                "schema": packet["response_schema"],
            },
        },
    }


async def call_teacher(
    model: str,
    packet: dict[str, Any],
    key: str,
    budget: TeacherBudget,
    attempts: list[dict[str, Any]],
    max_retries: int = 2,
) -> dict[str, Any]:
    """One logical call; retries resubmit byte-identical content. Returns a record."""
    if not budget.allow():
        raise TeacherTransportExhausted
    payload = wire_payload(model, packet)
    started = time.perf_counter()
    last_status: int | None = None
    for number in range(1, max_retries + 2):
        attempt_started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
                response = await client.post(
                    GATEWAY,
                    headers={"Authorization": f"Bearer {key}"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            attempts.append(
                {
                    "attempt": number,
                    "status": "transport_failed",
                    "error_type": type(exc).__name__,
                    "latency_ms": (time.perf_counter() - attempt_started) * 1000,
                }
            )
            last_status = None
            if number > max_retries:
                break
            await asyncio.sleep(2**number)
            continue
        record = {
            "attempt": number,
            "status": "http",
            "http_status": response.status_code,
            "latency_ms": (time.perf_counter() - attempt_started) * 1000,
        }
        attempts.append(record)
        if response.status_code == 200:
            budget.successful += 1
            body = response.json()
            content = (body.get("choices") or [{}])[0].get("message", {}).get("content")
            usage = body.get("usage") or {}
            finish = (body.get("choices") or [{}])[0].get("finish_reason")
            stripped = content.strip() if isinstance(content, str) else content
            if isinstance(stripped, str) and stripped.startswith("```json"):
                stripped = stripped[7:-3].strip() if stripped.endswith("```") else stripped
            return {
                "infrastructure_status": "ok" if finish == "stop" else "truncated",
                "content": stripped,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
                "reported_cost": _cost(body),
                "packet_hash": digest(packet),
                "model": model,
            }
        last_status = response.status_code
        # v1 observed transient 400s on large identical payloads; retry once, identically.
        retryable = response.status_code in RETRY_STATUS or (
            response.status_code == 400 and number == 1
        )
        if not retryable or number > max_retries:
            attempts[-1]["body_excerpt"] = response.text[:300]
            break
        budget.retries += 1
        await asyncio.sleep(2**number)
    return {
        "infrastructure_status": "failed",
        "content": None,
        "latency_ms": (time.perf_counter() - started) * 1000,
        "input_tokens": None,
        "output_tokens": None,
        "reported_cost": None,
        "packet_hash": digest(packet),
        "model": model,
        "last_http_status": last_status,
    }


def _cost(body: dict[str, Any]) -> float | None:
    gateway = (body.get("provider_metadata") or {}).get("gateway")
    if isinstance(gateway, dict):
        value = gateway.get("cost")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None
    return None


def secret_safe(value: Any) -> str:
    return json.dumps(value, indent=2, default=str)
