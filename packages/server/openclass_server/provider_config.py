"""Environment-configured adapters live at the composition boundary, never in core."""

import os
from typing import Any

from fastapi import HTTPException
from openclass_core.candidates import (
    ClusterDiscoveryProvider,
    ClusterDiscoveryRequest,
    ClusterDiscoveryResult,
    MockClusterDiscoveryProvider,
)
from openclass_core.embeddings import EmbeddingProvider
from openclass_core.evidence import DiagnosisProvider, DiagnosisResult
from openclass_core.models import DiscoveryRequest, DiscoveryResult
from openclass_core.project_evolution import ChoiceProposal, ChoiceTeacher
from openclass_core.projects import DecisionRun, DecisionService
from openclass_core.providers import (
    DecisionProvider,
    DiscoveryProvider,
    ProviderError,
    SupervisorProvider,
)
from openclass_provider_glm import (
    GatewayClusterDiscovery,
    GatewayDecisionProvider,
    GatewayEmbedder,
    GLMDiscoveryProvider,
    OpenAICompatibleChoiceTeacher,
    OpenAICompatibleDiagnosisProvider,
    OpenAICompatibleSupervisorProvider,
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
from pydantic import SecretStr

from openclass_server.embeddings_local import HashLexicalEmbedder
from openclass_server.security import contains_secret
from openclass_server.settings import Settings


class DisabledDiscoveryProvider:
    async def discover(self, request: DiscoveryRequest) -> DiscoveryResult:
        raise ProviderError(
            "Discovery/teacher provider is disabled (discovery_provider='none')",
            kind="unsupported",
        )


class DisabledClusterDiscoveryProvider:
    async def discover(self, request: ClusterDiscoveryRequest) -> ClusterDiscoveryResult:
        raise ProviderError(
            "Discovery/teacher provider is disabled (discovery_provider='none')",
            kind="unsupported",
        )


class DisabledChoiceTeacher:
    async def propose(
        self, service: DecisionService, runs: tuple[DecisionRun, ...]
    ) -> ChoiceProposal:
        raise ProviderError(
            "Discovery/teacher provider is disabled (discovery_provider='none')",
            kind="unsupported",
        )


class DisabledDiagnosisProvider:
    async def diagnose(self, context: dict[str, Any]) -> DiagnosisResult:
        raise ProviderError(
            "Discovery/teacher provider is disabled (discovery_provider='none')",
            kind="unsupported",
        )


def gateway_key(settings: Settings) -> SecretStr:
    return SecretStr(
        settings.discovery_api_key.get_secret_value()
        or settings.glm_api_key.get_secret_value()
        or os.getenv("AI_GATEWAY_API_KEY", "")
    )


def resolve_decision_provider(settings: Settings, override: str | None = None) -> DecisionProvider:
    choice = (override or settings.decision_provider).strip().lower()
    gateway_model = settings.discovery_model or "openai/gpt-4.1-mini"
    if choice.startswith("openai-compatible:"):
        gateway_model = choice.split(":", 1)[1]
        if gateway_model not in {"openai/gpt-4.1-mini", "google/gemini-2.5-flash"}:
            raise ValueError("Unsupported gateway decision model")
        choice = "openai-compatible"
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
    if choice == "openai-compatible":
        return GatewayDecisionProvider(
            api_key=gateway_key(settings),
            base_url=settings.discovery_base_url or "https://ai-gateway.vercel.sh/v1",
            model=gateway_model,
            timeout=settings.discovery_timeout_seconds,
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


def embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "openai-compatible":
        return GatewayEmbedder(
            api_key=gateway_key(settings),
            base_url=settings.discovery_base_url or "https://ai-gateway.vercel.sh/v1",
            model=settings.embedding_model,
            timeout=settings.discovery_timeout_seconds,
        )
    return HashLexicalEmbedder()


def cluster_discovery_provider(
    settings: Settings,
) -> tuple[ClusterDiscoveryProvider, str]:
    if settings.discovery_provider == "none":
        return DisabledClusterDiscoveryProvider(), "none"
    if settings.discovery_provider == "mock":
        return MockClusterDiscoveryProvider(), "mock"
    default_url = (
        "https://ai-gateway.vercel.sh/v1"
        if settings.discovery_provider == "openai-compatible"
        else "https://api.z.ai/api/paas/v4"
    )
    default_model = (
        "openai/gpt-4.1-mini"
        if settings.discovery_provider == "openai-compatible"
        else "glm-5.3-flash"
    )
    provider = GatewayClusterDiscovery(
        api_key=gateway_key(settings),
        base_url=settings.discovery_base_url or settings.glm_base_url or default_url,
        model=settings.discovery_model or settings.glm_model or default_model,
        timeout=settings.discovery_timeout_seconds,
    )
    return provider, f"{settings.discovery_provider}:{provider.model}"


def supervisor_provider(settings: Settings) -> SupervisorProvider:
    if settings.supervisor_provider == "mock":
        return MockSupervisorProvider()
    default_url = (
        "https://ai-gateway.vercel.sh/v1"
        if settings.supervisor_provider == "openai-compatible"
        else "https://api.z.ai/api/paas/v4"
    )
    default_model = (
        "alibaba/qwen-3-32b"
        if settings.supervisor_provider == "openai-compatible"
        else "glm-5.3-flash"
    )
    return OpenAICompatibleSupervisorProvider(
        api_key=gateway_key(settings),
        base_url=settings.discovery_base_url or settings.glm_base_url or default_url,
        model=settings.discovery_model or settings.glm_model or default_model,
        provider_name=settings.supervisor_provider,
        timeout=settings.discovery_timeout_seconds,
    )


def discovery_provider(settings: Settings) -> DiscoveryProvider:
    if settings.discovery_provider == "none":
        return DisabledDiscoveryProvider()
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
    if settings.discovery_provider == "none":
        return DisabledChoiceTeacher()
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
    if settings.discovery_provider == "none":
        return DisabledDiagnosisProvider()
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
    for secret in (
        settings.jev_api_key,
        settings.glm_api_key,
        settings.discovery_api_key,
        settings.internal_token,
    ):
        key = secret.get_secret_value()
        if contains_secret(value, key):
            raise HTTPException(status_code=422, detail="Input contains a configured credential")
