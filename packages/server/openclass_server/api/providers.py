"""Public providers routes over typed services and repository ports."""

from __future__ import annotations

from importlib.util import find_spec
from typing import Any

from fastapi import APIRouter

from openclass_server.settings import Settings


def providers_router(config: Settings) -> APIRouter:
    router = APIRouter(tags=["providers"])

    @router.get("/api/v1/providers/status")
    async def providers_status() -> dict[str, Any]:
        from openclass_provider_laya.status import check_jev_status, check_laya_endpoint

        laya_status = await check_laya_endpoint(
            base_url=config.laya_base_url,
            request_timeout=config.laya_timeout_seconds,
        )
        jev_status = check_jev_status(config.jev_api_key.get_secret_value())
        local_available = find_spec("laya") is not None
        return {
            "default_provider": config.decision_provider,
            "laya": {
                "status": "configured" if local_available else laya_status.value,
                "mode": "local_engine" if local_available else "daemon",
                "local_engine_available": local_available,
                "daemon_status": laya_status.value,
                "endpoint": config.laya_base_url,
                "model": config.laya_model,
                "default": config.decision_provider == "laya",
            },
            "jev": {
                "status": jev_status.value,
                "model": config.jev_model,
                "configured": jev_status.value == "configured",
                "default": config.decision_provider == "jev",
            },
        }

    @router.get("/api/v1/providers")
    async def providers() -> list[dict[str, Any]]:
        decision_model = (
            config.jev_model
            if config.decision_provider == "jev"
            else (config.laya_model if config.decision_provider == "laya" else "lexical-demo-v1")
        )
        return [
            {
                "name": config.decision_provider,
                "model": decision_model,
                "simulated": config.decision_provider == "mock",
                "capabilities": ["choice"],
            },
            {
                "name": "mock-supervisor",
                "model": "advisory-demo-v1",
                "simulated": True,
                "capabilities": ["review"],
            },
            {
                "name": config.discovery_provider,
                "model": config.discovery_model
                or config.glm_model
                or "configured-provider-default",
                "simulated": config.discovery_provider == "mock",
                "capabilities": ["discovery"],
            },
        ]

    return router
