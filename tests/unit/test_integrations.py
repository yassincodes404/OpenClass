"""Unit tests for integrations domain models and business rules."""

from uuid import uuid4

import pytest
from openclass_core.integrations import (
    IntegrationConfig,
    IntegrationCreate,
    IntegrationHealthReport,
    IntegrationStatus,
    IntegrationType,
    IntegrationUpdate,
    WebhookIngestResult,
)
from pydantic import ValidationError


def test_integration_create_defaults() -> None:
    create = IntegrationCreate(
        name="HubSpot CRM",
        type=IntegrationType.REST_API,
        endpoint="https://api.hubapi.com/v1",
        capabilities=("sync_contacts", "fetch_deals"),
    )
    assert create.name == "HubSpot CRM"
    assert create.type == IntegrationType.REST_API
    assert create.endpoint == "https://api.hubapi.com/v1"
    assert create.capabilities == ("sync_contacts", "fetch_deals")
    assert create.metadata == {}


def test_integration_config_defaults() -> None:
    pid = uuid4()
    config = IntegrationConfig(
        project_id=pid,
        name="MCP DevOps Server",
        type=IntegrationType.MCP,
        endpoint="https://mcp.internal.net",
    )
    assert config.project_id == pid
    assert config.status == IntegrationStatus.PENDING
    assert config.latency_ms is None
    assert config.error_message is None
    assert config.created_at is not None


def test_integration_update_requires_at_least_one_change() -> None:
    with pytest.raises(ValidationError):
        IntegrationUpdate()

    update = IntegrationUpdate(status=IntegrationStatus.CONNECTED)
    assert update.status == IntegrationStatus.CONNECTED


def test_integration_health_report() -> None:
    iid = uuid4()
    report = IntegrationHealthReport(
        integration_id=iid,
        status=IntegrationStatus.CONNECTED,
        latency_ms=14.2,
        capabilities=("tool_1", "tool_2"),
    )
    assert report.integration_id == iid
    assert report.status == IntegrationStatus.CONNECTED
    assert report.latency_ms == 14.2
    assert len(report.capabilities) == 2


def test_webhook_ingest_result() -> None:
    eid = uuid4()
    pid = uuid4()
    iid = uuid4()
    result = WebhookIngestResult(
        event_id=eid,
        project_id=pid,
        integration_id=iid,
        source="stripe_webhook",
    )
    assert result.event_id == eid
    assert result.status == "ingested"
    assert result.source == "stripe_webhook"
