"""Bounded in-process dispatch; credentials exist only at the network boundary."""

import asyncio
from uuid import UUID

import httpx
from openclass_core.outbound import (
    DeliveryClaim,
    DeliveryStore,
    OutboundSender,
    ReceiptReconciler,
    SendResult,
)

from .integration_adapters import EnvironmentSecrets, IntegrationConfigurationError
from .security import (
    PublicHTTPTransport,
    UnsafeOutboundDestination,
    contains_secret,
    validate_outbound_url,
)


class HTTPOutboundSender:
    def __init__(
        self, *, timeout: float = 5, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.timeout = timeout
        self.transport = transport

    async def send(self, claim: DeliveryClaim) -> SendResult:
        try:
            endpoint = validate_outbound_url(claim.intent.endpoint, resolve_dns=False)
            secret = EnvironmentSecrets().resolve(claim.intent.secret_ref)
            if contains_secret(claim.intent.model_dump(mode="json"), secret):
                return SendResult(status="not_sent", code="credential")
        except IntegrationConfigurationError:
            return SendResult(status="not_sent", code="credential")
        except ValueError:
            return SendResult(status="not_sent", code="destination")
        try:
            async with asyncio.timeout(self.timeout):
                async with httpx.AsyncClient(
                    transport=self.transport or PublicHTTPTransport(),
                    timeout=self.timeout,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    # Do not buffer, log or persist any upstream response body.
                    async with client.stream(
                        "POST",
                        endpoint,
                        headers={
                            "Authorization": f"Bearer {secret}",
                            "Idempotency-Key": claim.intent.idempotency_key,
                            "X-OpenClass-Request-Hash": claim.intent.request_hash,
                        },
                        json=claim.intent.payload(),
                    ) as response:
                        if 200 <= response.status_code < 300:
                            return SendResult(status="accepted", code="http_2xx")
                        return SendResult(status="ambiguous", code="http_rejected")
        except UnsafeOutboundDestination:
            return SendResult(status="not_sent", code="destination")
        except (httpx.HTTPError, TimeoutError, OSError, ValueError):
            return SendResult(status="ambiguous", code="transport")


class OutboundDispatcher:
    def __init__(
        self,
        store: DeliveryStore,
        sender: OutboundSender,
        *,
        batch_size: int = 10,
        timeout: float = 30,
    ) -> None:
        self.store = store
        self.sender = sender
        self.batch_size = min(100, max(1, batch_size))
        self.timeout = timeout

    async def reconcile(self, delivery_id: UUID, reconciler: ReceiptReconciler) -> bool:
        intent = await self.store.get_uncertain_intent(delivery_id)
        if intent is None:
            return False
        try:
            async with asyncio.timeout(self.timeout):
                receipt = await reconciler.reconcile(intent)
            return await self.store.reconcile(delivery_id, receipt)
        except Exception:
            return False

    async def drain(self) -> int:
        await self.store.recover()
        count = 0
        for _ in range(self.batch_size):
            claim = await self.store.claim()
            if claim is None:
                break
            if not await self.store.begin_send(claim):
                continue
            try:
                async with asyncio.timeout(self.timeout):
                    result = await self.sender.send(claim)
            except asyncio.CancelledError:
                # Never clear a potentially-sent claim on shutdown. Expiry is
                # recovered conservatively, with token fencing on all finishes.
                raise
            except Exception:
                result = SendResult(status="ambiguous", code="transport")
            await self.store.finish(claim, result)
            count += 1
        return count

    async def run(self, poll_seconds: float) -> None:
        while True:
            try:
                await self.drain()
            except asyncio.CancelledError:
                raise
            except Exception:
                # DB/client failures must not kill lifespan or erase claims.
                pass
            await asyncio.sleep(poll_seconds)
