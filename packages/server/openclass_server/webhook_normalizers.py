"""Exact-byte signatures and deliberately bounded vendor normalization."""

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from openclass_core.integrations import IntegrationConfig, WebhookDelivery

from .integration_adapters import EnvironmentSecrets, WebhookAuthenticationError

MAX_WEBHOOK_BYTES = 128_000


def _invalid_constant(value: str) -> None:
    raise ValueError("Malformed webhook payload")


def verify_webhook(
    integration: IntegrationConfig,
    raw: bytes,
    headers: Mapping[str, str],
    secrets: EnvironmentSecrets,
    *,
    now: datetime | None = None,
) -> None:
    """Signed modes never fall back to bearer. No submitted values in errors."""
    if len(raw) > MAX_WEBHOOK_BYTES:
        raise ValueError("Webhook payload is too large")
    mode = integration.signature.mode
    if mode == "bearer":
        secrets.authenticate(integration, headers)
        return
    secret = secrets.resolve(integration.secret_ref).encode()
    if mode == "intercom_sha1":
        expected = "sha1=" + hmac.new(secret, raw, hashlib.sha1).hexdigest()
        provided = headers.get("x-hub-signature", "")
    else:
        native = mode == "zendesk"
        timestamp = headers.get(
            "x-zendesk-webhook-signature-timestamp" if native else "x-openclass-timestamp", ""
        )
        if len(timestamp) > 64:
            raise WebhookAuthenticationError("Invalid webhook signature or timestamp")
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
            age = abs(((now or datetime.now(UTC)) - parsed).total_seconds())
            if age > integration.signature.replay_window_seconds:
                raise ValueError
        except (ValueError, OverflowError):
            raise WebhookAuthenticationError("Invalid webhook signature or timestamp") from None
        expected = base64.b64encode(
            hmac.digest(secret, timestamp.encode() + raw, "sha256")
        ).decode()
        provided = headers.get(
            "x-zendesk-webhook-signature" if native else "x-openclass-signature", ""
        )
    if not provided or not hmac.compare_digest(expected.encode(), provided.encode()):
        raise WebhookAuthenticationError("Invalid webhook signature or timestamp")


def normalize_webhook(integration: IntegrationConfig, raw: bytes) -> WebhookDelivery:
    """Only persist allowlisted provenance, never arbitrary vendor auth metadata."""
    if len(raw) > MAX_WEBHOOK_BYTES:
        raise ValueError("Webhook payload is too large")
    try:
        data = json.loads(raw, parse_constant=_invalid_constant)
        if not isinstance(data, dict):
            raise ValueError
        mode = integration.signature.mode
        if mode == "bearer":
            return WebhookDelivery.model_validate(data)
        if mode == "customer_hmac_sha256":
            delivery = WebhookDelivery.model_validate(data)
            envelope_metadata = {
                key: value
                for key, value in delivery.metadata.items()
                if key in {"vendor", "ticket_id"} and isinstance(value, str)
            }
            envelope_metadata["raw_sha256"] = hashlib.sha256(raw).hexdigest()
            return delivery.model_copy(update={"metadata": envelope_metadata})
        event_id = data.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError
        if mode == "zendesk":
            detail = data.get("detail", {})
            if not isinstance(detail, dict):
                raise ValueError
            ticket = detail.get("ticket", detail)
            if not isinstance(ticket, dict):
                raise ValueError
            # Zendesk event webhooks include detail; custom trigger payloads
            # must explicitly provide a stable revision/event id.
            fields = [
                ticket.get("subject"),
                ticket.get("title"),
                ticket.get("description"),
                ticket.get("comment", {}).get("body")
                if isinstance(ticket.get("comment"), dict)
                else None,
            ]
            source = "zendesk"
        else:
            item = data.get("data", {}).get("item", {})
            if not isinstance(item, dict):
                raise ValueError
            source_message = item.get("source", {})
            fields = [
                item.get("title"),
                item.get("body"),
                source_message.get("body") if isinstance(source_message, dict) else None,
            ]
            parts = (
                item.get("conversation_parts", {}).get("conversation_parts", [])
                if isinstance(item.get("conversation_parts"), dict)
                else []
            )
            if isinstance(parts, list):
                fields.extend(p.get("body") for p in parts[:100] if isinstance(p, dict))
            source = "intercom"
        content = "\n".join(f for f in fields if isinstance(f, str) and f.strip())
        metadata: dict[str, Any] = {
            "vendor_event_id": event_id,
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
        }
        return WebhookDelivery(
            event_key=event_id, source=source, content=content, metadata=metadata
        )
    except (ValueError, TypeError, AttributeError, RecursionError):
        raise ValueError("Malformed webhook payload") from None
