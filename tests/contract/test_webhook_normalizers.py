"""Synthetic raw-byte vendor signature contracts; never contact vendors."""

import base64
import hashlib
import hmac
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from openclass_core.integrations import IntegrationConfig, IntegrationType, WebhookSignature
from openclass_server.integration_adapters import EnvironmentSecrets, WebhookAuthenticationError
from openclass_server.webhook_normalizers import normalize_webhook, verify_webhook


def configured(mode):
    return IntegrationConfig(
        project_id=uuid4(),
        name="signed",
        type=IntegrationType.WEBHOOK,
        secret_ref="TEST_SIGNING_SECRET",
        signature=WebhookSignature(mode=mode),
    )


def test_zendesk_exact_raw_signature_and_timestamp(monkeypatch):
    monkeypatch.setenv("TEST_SIGNING_SECRET", "synthetic-only-secret")
    raw = b'{ "id":"evt-1", "detail":{"subject":"Billing","description":"Help"} }'
    timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    signature = base64.b64encode(
        hmac.digest(b"synthetic-only-secret", timestamp.encode() + raw, "sha256")
    ).decode()
    headers = {
        "x-zendesk-webhook-signature": signature,
        "x-zendesk-webhook-signature-timestamp": timestamp,
    }
    integration = configured("zendesk")
    verify_webhook(integration, raw, headers, EnvironmentSecrets())
    delivery = normalize_webhook(integration, raw)
    assert delivery.event_key == "evt-1"
    assert "Billing" in delivery.content
    with pytest.raises(WebhookAuthenticationError):
        verify_webhook(integration, raw + b" ", headers, EnvironmentSecrets())
    with pytest.raises(WebhookAuthenticationError):
        verify_webhook(integration, raw, {}, EnvironmentSecrets())
    with pytest.raises(WebhookAuthenticationError):
        verify_webhook(
            integration,
            raw,
            {**headers, "x-zendesk-webhook-signature-timestamp": "2000-01-01T00:00:00Z"},
            EnvironmentSecrets(),
        )


def test_intercom_is_explicit_sha1_not_invented_sha256(monkeypatch):
    monkeypatch.setenv("TEST_SIGNING_SECRET", "synthetic-only-secret")
    raw = b'{"id":"notif-1","topic":"conversation.user.created","data":{"item":{"body":"Help"}}}'
    signature = "sha1=" + hmac.new(b"synthetic-only-secret", raw, hashlib.sha1).hexdigest()
    integration = configured("intercom_sha1")
    verify_webhook(integration, raw, {"x-hub-signature": signature}, EnvironmentSecrets())
    assert normalize_webhook(integration, raw).event_key == "notif-1"
    with pytest.raises(WebhookAuthenticationError):
        verify_webhook(
            integration,
            raw,
            {"authorization": "Bearer synthetic-only-secret"},
            EnvironmentSecrets(),
        )


@pytest.mark.parametrize(
    "seconds,accepted", [(-301, False), (-300, True), (300, True), (301, False)]
)
def test_zendesk_timestamp_window_includes_future_skew(monkeypatch, seconds, accepted):
    from datetime import timedelta

    monkeypatch.setenv("TEST_SIGNING_SECRET", "synthetic-only-secret")
    now = datetime(2026, 1, 1, tzinfo=UTC)
    timestamp = (now + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
    raw = b'{"id":"evt","detail":{"subject":"Hello"}}'
    headers = {
        "x-zendesk-webhook-signature-timestamp": timestamp,
        "x-zendesk-webhook-signature": base64.b64encode(
            hmac.digest(b"synthetic-only-secret", timestamp.encode() + raw, "sha256")
        ).decode(),
    }
    if accepted:
        verify_webhook(configured("zendesk"), raw, headers, EnvironmentSecrets(), now=now)
    else:
        with pytest.raises(WebhookAuthenticationError):
            verify_webhook(configured("zendesk"), raw, headers, EnvironmentSecrets(), now=now)


def test_customer_envelope_is_explicitly_not_native_freshdesk(monkeypatch):
    monkeypatch.setenv("TEST_SIGNING_SECRET", "synthetic-only-secret")
    raw = (
        b'{"event_key":"fd:123:rev:2","source":"freshdesk-customer-adapter","content":"Help",'
        b'"metadata":{"vendor":"freshdesk","ticket_id":"123","authorization":"discard","signature":"discard"}}'
    )
    timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    headers = {
        "x-openclass-timestamp": timestamp,
        "x-openclass-signature": base64.b64encode(
            hmac.digest(b"synthetic-only-secret", timestamp.encode() + raw, "sha256")
        ).decode(),
    }
    integration = configured("customer_hmac_sha256")
    verify_webhook(integration, raw, headers, EnvironmentSecrets())
    delivery = normalize_webhook(integration, raw)
    assert delivery.source == "freshdesk-customer-adapter"
    assert set(delivery.metadata) == {"vendor", "ticket_id", "raw_sha256"}
    with pytest.raises(WebhookAuthenticationError):
        verify_webhook(integration, raw + b" ", headers, EnvironmentSecrets())
