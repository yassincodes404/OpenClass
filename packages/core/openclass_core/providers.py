"""Adapters implement these ports; they never receive a writable repository."""

from typing import Literal, Protocol

from openclass_core.models import (
    ChoiceRequest,
    ChoiceResult,
    DiscoveryRequest,
    DiscoveryResult,
    ReviewRequest,
    ReviewResult,
)

ProviderErrorKind = Literal[
    "timeout", "rate_limit", "auth", "bad_response", "unsupported", "unknown"
]


class ProviderError(Exception):
    """Safe public failure; adapters must not include secrets or request bodies.

    kind categorizes the failure for telemetry; the message stays safe to show.
    """

    def __init__(self, message: str, kind: ProviderErrorKind = "unknown") -> None:
        super().__init__(message)
        self.kind = kind


class DecisionProvider(Protocol):
    async def choice(self, request: ChoiceRequest) -> ChoiceResult: ...


class SupervisorProvider(Protocol):
    """Slow advisory reasoning over a historical run; it never mutates any state."""

    async def review(self, request: ReviewRequest) -> ReviewResult: ...


class DiscoveryProvider(Protocol):
    async def discover(self, request: DiscoveryRequest) -> DiscoveryResult: ...
