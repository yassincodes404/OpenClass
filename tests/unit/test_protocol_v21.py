"""Offline regressions for Teacher Protocol v2.1 against observed live failures.

Each test replays a failure actually recorded in the live-validation stages:
invented identifiers, copied machine fields, dual targets, empty argument
objects, stale-target choices. The v2.1 schema or deterministic applier must
make each structurally impossible.
"""

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.jev_contract.canonical import (
    Choice,
    DecisionNode,
    Macro,
    PolicyGraph,
    Predicate,
    StateFeature,
    StateSchema,
    Step,
    digest,
)
from scripts.jev_contract.protocol_v21 import (
    CandidateEnvelope,
    FeatureProposal,
    ProposalRejected,
    StateSource,
    TeacherProposal,
    apply_proposal,
    derive_feature,
    parse_proposal,
    proposal_schema,
    valid_targets,
    wrap,
)
from scripts.jev_contract.teacher import Capability


def make_graph() -> PolicyGraph:
    schema = StateSchema(
        id="service_state",
        version=1,
        features=(
            StateFeature(id="attempted", kind="boolean", sensor_field="attempted", required=True),
        ),
    )
    route = DecisionNode(
        id="route",
        question="Which failure recovery fits?",
        choices=(
            Choice(
                id="permission",
                meaning="Permission failures need account review.",
                target_kind="terminal",
                target_id=None,
            ),
            Choice(
                id="port",
                meaning="Port conflicts need port recovery.",
                target_kind="macro",
                target_id="recover",
            ),
        ),
    )
    macro = Macro(
        id="recover",
        purpose="Recover from port conflicts.",
        steps=(Step(capability="set_environment", arguments={"name": "TEST_PORT"}),),
        postconditions=(Predicate(field="attempted", equals=True),),
    )
    return PolicyGraph(
        id="g1",
        version=1,
        state_schema=schema,
        entry_node="route",
        nodes=(route,),
        macros=(macro,),
    )


CAPABILITIES = (
    Capability(
        id="set_environment",
        arguments={"name": "string"},
        permitted_values={"name": ("TEST_PORT",)},
    ),
    Capability(id="run_tests", arguments={}),
)


def add_choice_proposal(**overrides) -> TeacherProposal:
    data = dict(
        operator="ADD_CHOICE",
        target_id="route",
        choice=Choice(
            id="certificate",
            meaning="Certificate failures need certificate rotation.",
            target_kind="macro",
            target_id="recover",
        ),
        semantic_description="Add a certificate failure choice.",
        rationale="Evidence shows certificate failures with no offered choice.",
        confidence=0.8,
    )
    return TeacherProposal(**(data | overrides))


def test_regression_permission_denied_invented_identifier():
    """Live failure: model proposed choice id `permission_denied` when the only
    existing convention was `permission`. v2.1: NEW choice ids are coinages, but
    the schema forbids colliding with existing ids, and target selection uses
    enums — an invented TARGET is structurally impossible."""
    graph = make_graph()
    schema = proposal_schema(graph, CAPABILITIES, ("ADD_CHOICE", "MISSING_CAPABILITY"))
    # Non-change answers keep the empty-string target; change answers target nodes.
    branches = schema["properties"]["target_id"]["anyOf"]
    enums = [b.get("enum") for b in branches if "enum" in b]
    assert enums == [["route"]]  # empty-string enums are provider-illegal
    assert "permission_denied" not in str(schema)
    # Duplicate ids are not schema-excluded (provider-compatible schemas drop
    # `not`); the deterministic applier remains the collision gate.
    flattened = json.dumps(schema)
    assert '"not"' not in flattened  # provider compatibility: no unsupported constructs


def test_regression_base_policy_hash_copying_impossible():
    """Live failure: v1 required echoing a hash the model never saw. v2.1: the
    schema has no such field, and the proposal model rejects extra fields."""
    schema = proposal_schema(make_graph(), CAPABILITIES, ("ADD_CHOICE",))
    flattened = str(schema)
    assert "base_policy_hash" not in flattened
    with pytest.raises(ValidationError):
        add_choice_proposal(base_policy_hash="e1b2a056")
    with pytest.raises(ValidationError):
        CandidateEnvelope.model_validate(
            dict(
                candidate_id="c",
                base_policy_id="g1",
                base_policy_hash="h",
                teacher_provider="p",
                teacher_model="m",
                protocol_version="teacher-protocol-v2.0",
                jevprofile_id="p1",
                jevprofile_hash="h1",
                context_pack_hash="h2",
                schema_hash="h3",
                created_at="2026-09-25T00:00:00Z",
                proposal=add_choice_proposal().model_dump(),
            )
        )


def test_regression_dual_target_choice():
    """Live failure: a choice with both target_node and target_macro. The
    canonical Choice model itself permits at most one target kind."""
    with pytest.raises(ValidationError):
        Choice(
            id="bad",
            meaning="Dual targeted choice that must be invalid.",
            target_kind="terminal",
            target_id="recover",
        )


def test_regression_empty_argument_objects():
    """Live failure: strict mode stripped open-ended args so `set_environment`
    lost its value. v2.1: argument schemas are closed per capability with
    explicit required fields and permitted value enums."""
    schema = proposal_schema(make_graph(), CAPABILITIES, ("REPLACE_PROCEDURE",))
    step = schema["properties"]["payload"]["properties"]["steps"]["items"]["anyOf"][0]
    assert step["properties"]["capability"]["enum"] == ["set_environment"]
    args = step["properties"]["arguments"]
    assert args["required"] == ["name"]
    assert args["properties"]["name"]["enum"] == ["TEST_PORT"]


def test_regression_stale_macro_target():
    """Live failure: a routing choice targeted the OLD macro id after a new
    macro was registered. v2.1: the choice target enum contains only existing
    macro ids, and apply_proposal rejects unknown macro targets."""
    graph = make_graph()
    schema = proposal_schema(graph, CAPABILITIES, ("ADD_CHOICE",))
    choice = schema["properties"]["payload"]["properties"]["choice"]
    target_enum = choice["properties"]["target_id"]["anyOf"][0]["enum"]
    assert target_enum == ["recover"]
    stale = add_choice_proposal(
        choice=Choice(
            id="certificate",
            meaning="Certificate failure routed to a stale macro.",
            target_kind="macro",
            target_id="recover_v2",
        )
    )
    with pytest.raises(ProposalRejected, match="unknown macro"):
        apply_proposal(graph, stale)


def test_envelope_binds_proposal_and_graph():
    graph = make_graph()
    proposal = add_choice_proposal()
    envelope = wrap(
        proposal, graph, _profile(), "google/gemini-2.5-flash", "ctx-hash", "schema-hash"
    )
    assert envelope.base_policy_hash == graph.content_hash
    assert envelope.candidate_id not in proposal.model_dump()
    updated = apply_proposal(graph, proposal, CAPABILITIES)
    assert updated.version == 2 and updated.parent_hash == graph.content_hash
    assert [c.id for c in updated.nodes[0].choices] == ["permission", "port", "certificate"]


def test_parse_proposal_normalizes_provider_sentinels():
    """Providers emit {} for null-only branches and null for the empty target;
    parse_proposal must normalize both without inventing content."""
    raw = (
        '{"operator": "ADD_CHOICE", "target_id": "route", '
        '"payload": {"choice": {"id": "certificate", '
        '"meaning": "Expired certificates need rotation.", '
        '"target_kind": "macro", "target_id": "recover"}, '
        '"steps": {}, "feature": {}, "predicates": {}}, '
        '"semantic_description": "Add certificate handling.", '
        '"rationale": "Certificate failures lack a choice.", "confidence": 0.9}'
    )
    proposal = parse_proposal(raw)
    assert proposal.target_id == "route"
    assert proposal.steps is None and proposal.feature is None and proposal.predicates is None
    assert proposal.choice is not None and proposal.choice.id == "certificate"
    non_change = parse_proposal(
        '{"operator": "MISSING_CAPABILITY", "target_id": null, '
        '"payload": {"choice": {}, "steps": {}, "feature": {}, "predicates": {}}, '
        '"semantic_description": "No primitive exists.", '
        '"rationale": "Required capability unregistered.", "confidence": 0.7}'
    )
    assert non_change.target_id == "" and non_change.operator == "MISSING_CAPABILITY"


def test_valid_targets_universes():
    graph = make_graph()
    assert valid_targets("ADD_CHOICE", graph) == ("route",)
    assert valid_targets("REPLACE_PROCEDURE", graph) == ("recover",)
    assert valid_targets("MISSING_CAPABILITY", graph) == ("",)


def _profile():
    from scripts.jev_contract.knowledge import JevProfile

    return JevProfile.model_validate(
        {
            "id": "profile-test",
            "version": 1,
            "identity": {
                "provider": "jev",
                "model": "typesafe-ai/jev",
                "model_revision": None,
                "api_behavior": "systemone-v1-via-vercel-typesafe",
                "distribution_schema": "core-choice-result-v1",
                "major_version": "1",
            },
            "measured_at": "2026-09-24",
            "knowledge_base_hash": digest({"test": True}),
            "observation_ids": [],
            "limitations": ("test",),
            "max_tested_flat_choices": 32,
            "count_convention": "known_choices_excluding_unknown",
            "recommendations": ("test",),
        }
    )


def test_v22_feature_required_authority_is_removed():
    """Live failure (cycle3-20260925T01): the Teacher set required=true, breaking
    compilation for probe-less scenarios. v2.2: the proposal cannot carry scope;
    OpenClass derives it from the registered source's availability contract."""
    graph = make_graph()
    sources = (
        StateSource(
            id="service_monitor", availability="always", observes="core facts on every observation"
        ),
        StateSource(
            id="resolver_probe", availability="conditional", observes="resolver incidents only"
        ),
    )
    schema = proposal_schema(graph, CAPABILITIES, ("ADD_STATE_FEATURE",), sources)
    feature = schema["properties"]["payload"]["properties"]["feature"]
    assert "required" not in feature["properties"]
    assert feature["properties"]["source"]["enum"] == ["service_monitor", "resolver_probe"]
    with pytest.raises(ValidationError):
        FeatureProposal(
            id="resolver_generation_stale",
            kind="boolean",
            sensor_field="resolver_generation_stale",
            source="resolver_probe",
            required=True,
        )


def test_v22_scope_is_derived_from_source_availability():
    sources = (
        StateSource(
            id="service_monitor", availability="always", observes="core facts on every observation"
        ),
        StateSource(
            id="resolver_probe", availability="conditional", observes="resolver incidents only"
        ),
    )
    conditional = FeatureProposal(
        id="resolver_generation_stale",
        kind="boolean",
        sensor_field="resolver_generation_stale",
        source="resolver_probe",
    )
    assert derive_feature(conditional, sources).required is False
    always = FeatureProposal(
        id="port_conflict", kind="boolean", sensor_field="port_conflict", source="service_monitor"
    )
    assert derive_feature(always, sources).required is True
    with pytest.raises(ProposalRejected, match="unknown state source"):
        derive_feature(
            FeatureProposal(id="x", kind="boolean", sensor_field="x", source="unregistered_sensor"),
            sources,
        )


def test_v22_apply_state_feature_compiles_conditionally():
    graph = make_graph()
    sources = (
        StateSource(id="service_monitor", availability="always", observes="core facts"),
        StateSource(id="resolver_probe", availability="conditional", observes="resolver incidents"),
    )
    proposal = TeacherProposal(
        operator="ADD_STATE_FEATURE",
        target_id="service_state",
        feature=FeatureProposal(
            id="resolver_generation_stale",
            kind="boolean",
            sensor_field="resolver_generation_stale",
            source="resolver_probe",
        ),
        semantic_description="Represent resolver generation staleness.",
        rationale="Raw evidence contains the fact; the compiler drops it.",
        confidence=0.9,
    )
    graph_v2 = apply_proposal(graph, proposal, sources=sources)
    feature = next(f for f in graph_v2.state_schema.features if f.id == "resolver_generation_stale")
    assert feature.required is False
    assert graph_v2.version == 2 and graph_v2.parent_hash == graph.content_hash
    assert graph.version == 1
