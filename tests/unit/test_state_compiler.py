"""Runtime representation failures are not semantic UNKNOWN observations."""

from uuid import uuid4

import pytest
from openclass_core.decision import StateFeature, StateSchema
from openclass_core.projects import RawEvent
from openclass_core.state_compiler import StateBudgets, StateCompilationError, compile_runtime_state


def schema(**kwargs):
    return StateSchema(
        id="runtime_state",
        version=1,
        features=(StateFeature(id="enabled", kind="boolean", sensor_field="enabled", **kwargs),),
    )


def test_missing_false_and_null_are_distinct():
    event = RawEvent(project_id=uuid4(), content="test", metadata={"enabled": False})
    snapshot = compile_runtime_state(event, [], schema(), StateBudgets())
    assert snapshot["facts"] == {"enabled": False}
    assert snapshot["provenance"]["enabled"]["source"] == "metadata"
    assert snapshot["provenance"]["enabled"]["event_id"] == str(event.id)
    assert (
        compile_runtime_state(
            event.model_copy(update={"metadata": {}}), [], schema(required=False), StateBudgets()
        )["provenance"]["enabled"]["status"]
        == "missing"
    )
    nullable = compile_runtime_state(
        event.model_copy(update={"metadata": {"enabled": None}}),
        [],
        schema(nullable=True),
        StateBudgets(),
    )
    assert nullable["facts"] == {"enabled": None}
    assert nullable["provenance"]["enabled"]["status"] == "null"


@pytest.mark.parametrize("value", [0, 1, "false", None, float("nan"), {"secret": "hidden"}])
def test_no_coercion_or_content_echo(value):
    event = RawEvent(project_id=uuid4(), content="test", metadata={"enabled": value})
    with pytest.raises(StateCompilationError) as error:
        compile_runtime_state(event, [], schema(), StateBudgets())
    assert "hidden" not in str(error.value)


def test_multibyte_and_total_limits_do_not_truncate():
    text_schema = StateSchema(
        id="runtime_state",
        version=1,
        features=(StateFeature(id="message", kind="string", sensor_field="message"),),
    )
    event = RawEvent(project_id=uuid4(), content="test", metadata={"message": "界" * 10})
    with pytest.raises(StateCompilationError):
        compile_runtime_state(event, [], text_schema, StateBudgets(max_field_bytes=29))
    with pytest.raises(StateCompilationError):
        compile_runtime_state(event, [], text_schema, StateBudgets(max_total_bytes=30))


def test_prior_decision_source_is_captured_not_metadata_authority():
    prior_schema = StateSchema(
        id="runtime_state",
        version=1,
        features=(
            StateFeature(id="route", kind="string", sensor_field="router", source="prior_decision"),
        ),
    )
    event = RawEvent(project_id=uuid4(), content="test", metadata={"router": "FORGED"})
    actual = [
        {"node_id": str(uuid4()), "node_name": "router", "choice": "BILLING", "label": "Billing"}
    ]
    state = compile_runtime_state(event, actual, prior_schema, StateBudgets())
    assert state["facts"] == {"route": "BILLING"}
    assert state["provenance"]["route"]["source"] == "prior_decision"


@pytest.mark.parametrize("value", [float("inf"), object(), (1, 2), {1: "not-json"}, "\ud800"])
def test_unsupported_source_representations_fail_safely(value):
    event = RawEvent(project_id=uuid4(), content="test", metadata={"undeclared": value})
    with pytest.raises(StateCompilationError):
        compile_runtime_state(event, [], None, StateBudgets())


@pytest.mark.parametrize("value", [object(), (1, 2), {1: "not-json"}])
def test_unsupported_values_report_distinct_code(value):
    event = RawEvent(project_id=uuid4(), content="test", metadata={"undeclared": value})
    with pytest.raises(StateCompilationError) as error:
        compile_runtime_state(event, [], None, StateBudgets())
    assert error.value.code == "unsupported_value"


@pytest.mark.parametrize("value", [float("inf"), chr(0xD800)])
def test_unserializable_values_report_invalid_json(value):
    event = RawEvent(project_id=uuid4(), content="test", metadata={"undeclared": value})
    with pytest.raises(StateCompilationError) as error:
        compile_runtime_state(event, [], None, StateBudgets())
    assert error.value.code == "invalid_json"


def test_zero_integer_and_estimated_token_boundary():
    integer_schema = StateSchema(
        id="runtime_state",
        version=1,
        features=(StateFeature(id="count", kind="integer", sensor_field="count"),),
    )
    event = RawEvent(project_id=uuid4(), content="test", metadata={"count": 0})
    snapshot = compile_runtime_state(event, [], integer_schema, StateBudgets())
    assert type(snapshot["facts"]["count"]) is int
    with pytest.raises(StateCompilationError):
        compile_runtime_state(
            event.model_copy(update={"metadata": {"count": False}}),
            [],
            integer_schema,
            StateBudgets(),
        )
    from openclass_core.state_compiler import strict_json

    size = len(strict_json(snapshot).encode())
    assert (
        compile_runtime_state(
            event,
            [],
            integer_schema,
            StateBudgets(max_estimated_tokens=size),
        )
        == snapshot
    )
    with pytest.raises(StateCompilationError):
        compile_runtime_state(
            event,
            [],
            integer_schema,
            StateBudgets(max_estimated_tokens=size - 1),
        )
