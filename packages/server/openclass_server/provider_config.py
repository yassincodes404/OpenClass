"""Environment-configured adapters live at the composition boundary, never in core."""

import os
from typing import Any

from fastapi import HTTPException
from openclass_core.evidence import DiagnosisProvider
from openclass_core.project_evolution import ChoiceTeacher
from openclass_core.providers import DecisionProvider, DiscoveryProvider, SupervisorProvider
from openclass_provider_glm import (
    GLMDiscoveryProvider,
    OpenAICompatibleChoiceTeacher,
    OpenAICompatibleDiagnosisProvider,
)
from openclass_provider_jev import JevDecisionProvider
from openclass_provider_laya import LayaDecisionProvider
from openclass_provider_mock import (
    MockChoiceTeacher,
    MockDecisionProvider,
    MockDiagnosisProvider,
    MockDiscoveryProvider,
    MockSupervisorProvider,
)

from openclass_server.security import contains_secret
from openclass_server.settings import Settings


def resolve_decision_provider(settings: Settings, override: str | None = None) -> DecisionProvider:
    choice = (override or settings.decision_provider).strip().lower()
    if choice == "mock":
        return MockDecisionProvider()
    if choice == "jev":
        return JevDecisionProvider(
            api_key=settings.jev_api_key,
            base_url=settings.jev_base_url,
            model=settings.jev_model,
            timeout=settings.provider_timeout_seconds,
            max_retries=settings.provider_max_retries,
        )
    if choice == "laya":
        return LayaDecisionProvider(
            base_url=settings.laya_base_url,
            model=settings.laya_model,
            timeout=settings.laya_timeout_seconds,
            max_retries=settings.laya_max_retries,
            allow_fallback=settings.laya_allow_fallback,
        )
    raise ValueError(f"Unsupported decision provider: {choice}")


def decision_provider(settings: Settings) -> DecisionProvider:
    return resolve_decision_provider(settings)


def supervisor_provider(settings: Settings) -> SupervisorProvider:
    # Settings rejects unsupported supervisor providers, including GLM for this stage.
    return MockSupervisorProvider()


def discovery_provider(settings: Settings) -> DiscoveryProvider:
    if settings.discovery_provider == "mock":
        return MockDiscoveryProvider()
    key = settings.discovery_api_key
    if not key.get_secret_value().strip():
        key = settings.glm_api_key
    if not key.get_secret_value().strip() and settings.discovery_provider == "openai-compatible":
        from pydantic import SecretStr

        key = SecretStr(os.getenv("AI_GATEWAY_API_KEY", ""))
    default_url = (
        "https://ai-gateway.vercel.sh/v1"
        if settings.discovery_provider == "openai-compatible"
        else "https://api.z.ai/api/paas/v4"
    )
    default_model = (
        "alibaba/qwen-3-32b"
        if settings.discovery_provider == "openai-compatible"
        else "glm-5.3-flash"
    )
    return GLMDiscoveryProvider(
        api_key=key,
        base_url=settings.discovery_base_url or settings.glm_base_url or default_url,
        model=settings.discovery_model or settings.glm_model or default_model,
        timeout=settings.discovery_timeout_seconds,
    )


def project_teacher_provider(settings: Settings) -> ChoiceTeacher:
    if settings.discovery_provider == "mock":
        return MockChoiceTeacher()
    key = settings.discovery_api_key
    if not key.get_secret_value().strip():
        key = settings.glm_api_key
    if not key.get_secret_value().strip():
        from pydantic import SecretStr

        key = SecretStr(os.getenv("AI_GATEWAY_API_KEY", ""))
    default_url = (
        "https://ai-gateway.vercel.sh/v1"
        if settings.discovery_provider == "openai-compatible"
        else "https://api.z.ai/api/paas/v4"
    )
    default_model = (
        "alibaba/qwen-3-32b"
        if settings.discovery_provider == "openai-compatible"
        else "glm-5.3-flash"
    )
    return OpenAICompatibleChoiceTeacher(
        api_key=key,
        base_url=settings.discovery_base_url or settings.glm_base_url or default_url,
        model=settings.discovery_model or settings.glm_model or default_model,
        timeout=settings.discovery_timeout_seconds,
    )


def project_diagnosis_provider(settings: Settings) -> DiagnosisProvider:
    if settings.discovery_provider == "mock":
        return MockDiagnosisProvider()
    key = settings.discovery_api_key
    if not key.get_secret_value().strip():
        key = settings.glm_api_key
    if not key.get_secret_value().strip():
        from pydantic import SecretStr

        gateway_key = (
            os.getenv("OPENCLASS_DISCOVERY_KEY", "")
            or os.getenv("OPENCLASS_VERCEL_GATEWAY_KEY", "")
            or os.getenv("AI_GATEWAY_API_KEY", "")
        )
        key = SecretStr(gateway_key)
    if not key.get_secret_value().strip():
        raise ValueError("Diagnosis provider requires an API key")
    return OpenAICompatibleDiagnosisProvider(
        api_key=key,
        base_url=settings.discovery_base_url
        or settings.glm_base_url
        or "https://ai-gateway.vercel.sh/v1",
        model=settings.discovery_model or settings.glm_model or "google/gemini-2.5-flash",
        timeout=settings.discovery_timeout_seconds,
    )


def reject_credentials(value: Any, settings: Settings) -> None:
    for secret in (settings.jev_api_key, settings.glm_api_key, settings.discovery_api_key):
        key = secret.get_secret_value()
        if contains_secret(value, key):
            raise HTTPException(status_code=422, detail="Input contains a configured credential")
