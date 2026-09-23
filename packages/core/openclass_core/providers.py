"""Adapters implement these ports; they never receive a writable repository."""

from typing import Protocol

from openclass_core.models import ChoiceRequest, ChoiceResult


class ProviderError(Exception):
    """Safe public failure; adapters must not include secrets or request bodies."""


class DecisionProvider(Protocol):
    async def choice(self, request: ChoiceRequest) -> ChoiceResult: ...
