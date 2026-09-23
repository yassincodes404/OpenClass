"""Adapters implement these ports; they never receive a writable repository."""

from typing import Protocol

from openclass_core.models import ChoiceRequest, ChoiceResult, ReviewRequest, ReviewResult


class ProviderError(Exception):
    """Safe public failure; adapters must not include secrets or request bodies."""


class DecisionProvider(Protocol):
    async def choice(self, request: ChoiceRequest) -> ChoiceResult: ...


class SupervisorProvider(Protocol):
    """Slow advisory reasoning over a historical run; it never mutates any state."""

    async def review(self, request: ReviewRequest) -> ReviewResult: ...
