"""Local execution fencing around a renewable database checkpoint lease.

Cancellation cannot prove that a remote inference stopped. On disconnect or
ownership loss we cancel local execution, stop renewal, and leave the claim
alone; stale recovery (or explicit privileged force recovery) is a separate
operator decision. No cancellation handler blindly makes the checkpoint runnable.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import suppress
from typing import TypeVar

from openclass_core.models import ChoiceRequest, ChoiceResult
from openclass_core.providers import DecisionProvider
from openclass_core.repositories import ConflictError

T = TypeVar("T")


class CheckpointLease:
    """Renew before every provider call and at TTL/3 while the executor runs."""

    def __init__(self, renew: Callable[[], Awaitable[None]], ttl_seconds: float) -> None:
        self._renew = renew
        self._interval = ttl_seconds / 3.0
        self._lock = asyncio.Lock()
        self._stopped = False
        self.provider_started = False

    def ensure_active(self) -> None:
        if self._stopped:
            raise ConflictError("Decision run resume lease is no longer valid")

    async def renew(self) -> None:
        async with self._lock:
            self.ensure_active()
            try:
                await self._renew()
            except Exception as exc:
                self._stopped = True
                raise ConflictError("Decision run resume lease is no longer valid") from exc

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self.renew()

    async def run(self, operation: Callable[[], Coroutine[object, object, T]]) -> T:
        await self.renew()
        executor: asyncio.Task[T] = asyncio.create_task(operation())
        heartbeat = asyncio.create_task(self._heartbeat())
        try:
            done, _ = await asyncio.wait({executor, heartbeat}, return_when=asyncio.FIRST_COMPLETED)
            # Prefer lease loss even if the provider finished at the same time.
            if heartbeat in done:
                await heartbeat
            self.ensure_active()
            return await executor
        finally:
            self._stopped = True
            heartbeat.cancel()
            with suppress(asyncio.CancelledError, ConflictError):
                await heartbeat
            if not executor.done():
                executor.cancel()
            # A misbehaving adapter may suppress cancellation. Never wait for it
            # indefinitely; the wrapper's post-call fence prevents further nodes.
            executor.add_done_callback(self._consume_result)

    @staticmethod
    def _consume_result(task: asyncio.Task[T]) -> None:
        if not task.cancelled():
            task.exception()

    def provider(self, provider: DecisionProvider) -> DecisionProvider:
        return _LeasedDecisionProvider(provider, self)


class _LeasedDecisionProvider:
    def __init__(self, provider: DecisionProvider, lease: CheckpointLease) -> None:
        self._provider = provider
        self._lease = lease

    async def choice(self, request: ChoiceRequest) -> ChoiceResult:
        await self._lease.renew()
        self._lease.provider_started = True
        result = await self._provider.choice(request)
        self._lease.ensure_active()
        return result
