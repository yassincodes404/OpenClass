"""Remote delivery identities and safety rules belong to core."""

from uuid import uuid4

import pytest
from openclass_core.outbound import OutboundIntent
from pydantic import ValidationError


def intent(**changes):
    return OutboundIntent(
        project_id=changes.pop("project_id", uuid4()),
        integration_id=uuid4(),
        run_id="run",
        route_id="route",
        event_id=uuid4(),
        selected_choice=changes.pop("selected_choice", "BILLING"),
        action="tag",
        action_value="billing",
        endpoint="https://receiver.example/actions",
        secret_ref="TEST_OUTBOUND_TOKEN",
        **changes,
    )


def test_unknown_cannot_authorize_external_action():
    with pytest.raises(ValidationError):
        intent(selected_choice="UNKNOWN")


def test_request_identity_binds_destination_and_action_not_secret_value():
    item = intent()
    assert item.idempotency_key == f"{item.project_id}:run:route"
    assert item.request_hash == item.model_copy().request_hash
    assert (
        item.request_hash
        != item.model_copy(update={"endpoint": "https://other.example"}).request_hash
    )
    assert len(item.request_hash) == 64
