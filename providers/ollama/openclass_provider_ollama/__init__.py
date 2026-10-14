"""Ollama local OpenAI-compatible decision and advisory supervisor adapters."""

from __future__ import annotations

import math

import httpx
from openclass_core.models import ChoiceRequest, ChoiceResult
from openclass_provider_glm import GatewayDecisionProvider, OpenAICompatibleSupervisorProvider
from pydantic import SecretStr

DEFAULT_OLLAMA_API_KEY = SecretStr("ollama")
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_OLLAMA_MODEL = "llama3.2"


class OllamaDecisionProvider(GatewayDecisionProvider):
    """Local Ollama decision adapter over OpenAI-compatible /v1/chat/completions."""

    def __init__(
        self,
        *,
        api_key: SecretStr = DEFAULT_OLLAMA_API_KEY,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        model: str = DEFAULT_OLLAMA_MODEL,
        timeout: float = 60,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if (
            not api_key.get_secret_value().strip()
            or not base_url.startswith(("http://", "https://"))
            or "@" in base_url
            or not model
            or not math.isfinite(timeout)
            or not 0 < timeout <= 120
        ):
            raise ValueError("Invalid Ollama decision provider configuration")
        super().__init__(
            api_key=api_key,
            base_url="https://127.0.0.1:11434/v1",
            model=model,
            timeout=timeout,
            transport=transport,
        )
        self.url = base_url.rstrip("/")
        self.base_url = self.url
        self.api_key = self.key

    async def choice(self, request: ChoiceRequest) -> ChoiceResult:
        result = await super().choice(request)
        return result.model_copy(
            update={
                "provider": "ollama",
                "provider_metadata": {
                    **result.provider_metadata,
                    "gateway": "ollama",
                },
            }
        )


class OllamaSupervisorProvider(OpenAICompatibleSupervisorProvider):
    """Local Ollama advisory Supervisor adapter over OpenAI-compatible /v1/chat/completions."""

    def __init__(
        self,
        *,
        api_key: SecretStr = DEFAULT_OLLAMA_API_KEY,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        model: str = DEFAULT_OLLAMA_MODEL,
        provider_name: str = "ollama",
        timeout: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if (
            not api_key.get_secret_value().strip()
            or not base_url.startswith(("http://", "https://"))
            or "@" in base_url
            or not model
            or not math.isfinite(timeout)
            or not 0 < timeout <= 120
        ):
            raise ValueError("Invalid Ollama Supervisor provider configuration")
        super().__init__(
            api_key=api_key,
            base_url="https://127.0.0.1:11434/v1",
            model=model,
            provider_name=provider_name,
            timeout=timeout,
            transport=transport,
        )
        self.url = base_url.rstrip("/")
        self.base_url = self.url
        self.api_key = self.key


__all__ = [
    "DEFAULT_OLLAMA_API_KEY",
    "DEFAULT_OLLAMA_BASE_URL",
    "DEFAULT_OLLAMA_MODEL",
    "OllamaDecisionProvider",
    "OllamaSupervisorProvider",
]
