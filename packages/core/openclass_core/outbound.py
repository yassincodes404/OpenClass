"""Durable effect contracts, not prediction labels or exactly-once promises."""

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from pydantic import Field, model_validator

from .models import Model


class DeliveryState(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    SENDING = "sending"
    SENT = "sent"
    UNCERTAIN = "uncertain"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutboundPolicy(Model):
    enabled: bool = False
    # Operator assertion about the receiver, not a property of our DB lease.
    receiver_enforces_idempotency: bool = False


class OutboundIntent(Model):
    project_id: UUID
    integration_id: UUID
    event_id: UUID
    run_id: str = Field(min_length=1, max_length=100)
    route_id: str = Field(min_length=1, max_length=100)
    selected_choice: str = Field(min_length=1, max_length=100)
    action: Literal["tag", "assign_queue"]
    action_value: str = Field(min_length=1, max_length=200)
    endpoint: str = Field(min_length=1, max_length=1000)
    secret_ref: str = Field(min_length=1, max_length=200)
    receiver_enforces_idempotency: bool = False

    @model_validator(mode="after")
    def known_only(self) -> "OutboundIntent":
        if self.selected_choice.upper() == "UNKNOWN" or self.route_id in {"default", "escalate"}:
            raise ValueError("External delivery requires an explicit known-choice route")
        return self

    @property
    def idempotency_key(self) -> str:
        return f"{self.project_id}:{self.run_id}:{self.route_id}"

    @property
    def request_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def payload(self) -> dict[str, str]:
        return {
            "event_id": str(self.event_id),
            "run_id": self.run_id,
            "route_id": self.route_id,
            "action": self.action,
            "value": self.action_value,
        }


class DeliveryClaim(Model):
    id: UUID
    token: str
    intent: OutboundIntent
    attempt: int
    lease_until: datetime


class SendResult(Model):
    # Even rejected requests may have effects; adapters cannot assume otherwise.
    status: Literal["accepted", "ambiguous", "not_sent"]
    code: Literal["http_2xx", "http_rejected", "transport", "credential", "destination"]


class AuthoritativeReceipt(Model):
    applied: bool
    idempotency_key: str = Field(min_length=1, max_length=300)
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    # Identifier supplied only by a trusted receiver-specific readback adapter.
    receipt_id: str = Field(min_length=1, max_length=200)


class OutboundSender(Protocol):
    async def send(self, claim: DeliveryClaim) -> SendResult: ...


class ReceiptReconciler(Protocol):
    async def reconcile(self, intent: OutboundIntent) -> AuthoritativeReceipt: ...


class DeliveryStore(Protocol):
    async def claim(self, *, now: datetime | None = None) -> DeliveryClaim | None: ...
    async def begin_send(self, claim: DeliveryClaim, *, now: datetime | None = None) -> bool: ...
    async def finish(
        self, claim: DeliveryClaim, result: SendResult, *, now: datetime | None = None
    ) -> bool: ...
    async def recover(self, *, now: datetime | None = None, limit: int = 100) -> None: ...
    async def get_uncertain_intent(self, delivery_id: UUID) -> OutboundIntent | None: ...
    async def reconcile(self, delivery_id: UUID, receipt: AuthoritativeReceipt) -> bool: ...
