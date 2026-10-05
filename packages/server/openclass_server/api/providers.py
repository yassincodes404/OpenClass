"""Public providers routes over typed services and repository ports."""

from __future__ import annotations

from importlib.util import find_spec
from time import monotonic
from typing import Any
from uuid import uuid4

from fastapi import APIRouter
from openclass_core.models import ChoiceRequest, Observation, OntologyClass, OntologyVersion
from openclass_core.providers import ProviderError
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from openclass_server.provider_config import resolve_decision_provider
from openclass_server.settings import Settings


class ProviderTestRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    config_ref: str | None = Field(default=None, max_length=200)


def providers_router(
    config: Settings, sessions: async_sessionmaker[AsyncSession] | None = None
) -> APIRouter:
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

    @router.post("/api/v1/providers/test")
    async def providers_test(body: ProviderTestRequest) -> dict[str, Any]:
        """Dry-run a provider against a two-class fixture; nothing is persisted."""
        started = monotonic()
        try:
            provider = resolve_decision_provider(config, body.provider)
        except ValueError:
            return {"ok": False, "provider": body.provider, "error": "unsupported provider"}
        ontology = OntologyVersion(
            classifier_id=uuid4(),
            version_number=1,
            classes=(
                OntologyClass(canonical_name="billing", display_name="Billing"),
                OntologyClass(canonical_name="technical", display_name="Technical"),
            ),
            created_by="provider-test",
        )
        request = ChoiceRequest(
            observation=Observation(content="I was charged twice"), ontology=ontology
        )
        try:
            result = await provider.choice(request)
        except ProviderError as error:
            return {"ok": False, "provider": body.provider, "error": str(error)}
        top = max(result.probabilities, key=lambda key: result.probabilities[key])
        return {
            "ok": True,
            "provider": body.provider,
            "model": result.model,
            "simulated": bool(result.provider_metadata.get("simulated", body.provider == "mock")),
            "latency_ms": round((monotonic() - started) * 1000, 2),
            "normalized_preview": {
                "selected": top
                if result.probabilities.get(top, 0) > result.unknown_probability
                else "UNKNOWN",
                "top_probability": result.probabilities.get(top, 0.0),
                "unknown_probability": result.unknown_probability,
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
