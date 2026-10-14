"""OpenAI-compatible decision, embedding, discovery, teacher, supervisor, and diagnosis adapters."""

from __future__ import annotations

import httpx
from openclass_provider_glm import (
    GatewayClusterDiscovery,
    GatewayDecisionProvider,
    GatewayEmbedder,
    OpenAICompatibleChoiceTeacher,
    OpenAICompatibleDiagnosisProvider,
    OpenAICompatibleSupervisorProvider,
)
from pydantic import SecretStr


class OpenAICompatibleDecisionProvider(GatewayDecisionProvider):
    """OpenAI-compatible bounded decision provider."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str = "https://ai-gateway.vercel.sh/v1",
        model: str = "openai/gpt-4.1-mini",
        timeout: float = 60,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            transport=transport,
        )
        self.base_url = self.url
        self.api_key = self.key


class OpenAICompatibleEmbedder(GatewayEmbedder):
    """OpenAI-compatible embedding provider."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str = "https://ai-gateway.vercel.sh/v1",
        model: str = "openai/text-embedding-3-small",
        timeout: float = 60,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            transport=transport,
        )
        self.base_url = self.url
        self.api_key = self.key


class OpenAICompatibleClusterDiscovery(GatewayClusterDiscovery):
    """OpenAI-compatible cluster discovery provider."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str = "https://ai-gateway.vercel.sh/v1",
        model: str = "openai/gpt-4.1-mini",
        timeout: float = 60,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            transport=transport,
        )
        self.base_url = self.url
        self.api_key = self.key


__all__ = [
    "OpenAICompatibleChoiceTeacher",
    "OpenAICompatibleClusterDiscovery",
    "OpenAICompatibleDecisionProvider",
    "OpenAICompatibleDiagnosisProvider",
    "OpenAICompatibleEmbedder",
    "OpenAICompatibleSupervisorProvider",
]
