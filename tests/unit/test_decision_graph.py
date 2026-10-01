"""Offline tests of the experimental DecisionGraph; no network, no live calls."""

import asyncio
import importlib

import pytest
from pydantic import ValidationError


@pytest.fixture
def dg(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    return importlib.import_module("decision_graph")


def make_choice(dg, cid, target_node=None, target_macro=None, desc="simulated choice"):
    return dg.Choice(
        id=cid,
        semantic_name=cid.replace("_", " "),
        description=desc,
        target_node=target_node,
        target_macro=target_macro,
    )


def simple_graph(dg):
    macro = dg.Macro(
        id="finish_task",
        semantic_purpose="record completion",
        procedure=(dg.MacroStep(primitive="set_done"),),
        postconditions=(dg.Predicate(field="done", equals=True),),
    )
    node = dg.DecisionNode(
        id="work",
        question="What next?",
        choices=(make_choice(dg, "do_it", target_macro="finish_task"),),
        entry=True,
    )
    graph = dg.PolicyGraphVersion(
        id="graph",
        version_number=1,
        entry_node="work",
        nodes=(node,),
        macros=(macro,),
        goal=(dg.Predicate(field="done", equals=True),),
    )
    return graph, macro


def make_world(dg, fields):
    class World(dg.RegisteredWorld):
        def primitive_noop(self, **kwargs):
            return True, ""

        def primitive_set_done(self, **kwargs):
            self.fields["done"] = True
            return True, ""

        def primitive_failing(self, **kwargs):
            return False, "simulated failure"

    return World(fields)


def scripted(decisions):
    iterator = iter(decisions)

    def decide(node, snapshot):
        return next(iterator)

    return decide


def result(selected, top=0.9, unknown=0.05):
    return (selected, top, unknown, top - 0.05)


def run(dg, graph, world, decide, **kwargs):
    return asyncio.run(dg.run_graph(graph, world, decide, **kwargs))


def test_choice_targets_at_most_one_thing(dg):
    with pytest.raises(ValidationError):
        make_choice(dg, "bad", target_node="a", target_macro="b")
    terminal = make_choice(dg, "classifier_choice")
    assert terminal.target_node is None and terminal.target_macro is None


def test_graph_references_must_resolve(dg):
    node = dg.DecisionNode(
        id="work",
        question="?",
        choices=(make_choice(dg, "x", target_node="missing"),),
        entry=True,
    )
    with pytest.raises(ValidationError, match="unknown node"):
        dg.PolicyGraphVersion(id="g", version_number=1, entry_node="work", nodes=(node,))


def test_happy_path_routes_and_verifies(dg):
    graph, _ = simple_graph(dg)
    world = make_world(dg, {"done": False})
    outcome = run(dg, graph, world, scripted([result("do_it")]))
    assert outcome.status == "completed"
    assert outcome.diagnosis is None
    assert world.fields["done"] is True
    assert outcome.transitions[0].macro.postconditions_passed is True


def test_unknown_route_blocks_with_decision_space_diagnosis(dg):
    graph, _ = simple_graph(dg)
    outcome = run(dg, graph, make_world(dg, {"done": False}), scripted([result(dg.UNKNOWN)]))
    assert outcome.status == "blocked"
    assert outcome.diagnosis == dg.DiagnosisLayer.DECISION_SPACE


def test_precondition_failure_never_executes(dg):
    graph, _ = simple_graph(dg)
    guarded = dg.Macro(
        id="finish_task",
        semantic_purpose="record completion",
        preconditions=(dg.Predicate(field="allowed", equals=True),),
        procedure=(dg.MacroStep(primitive="set_done"),),
        postconditions=(dg.Predicate(field="done", equals=True),),
    )
    graph = graph.model_copy(update={"version_number": 2, "macros": (guarded,)})
    world = make_world(dg, {"allowed": False, "done": False})
    outcome = run(dg, graph, world, scripted([result("do_it")]))
    assert outcome.status == "diagnosed"
    assert outcome.diagnosis == dg.DiagnosisLayer.PRECONDITION
    assert world.fields["done"] is False
    assert outcome.transitions[0].macro.steps == ()


def test_step_failure_diagnoses_procedure(dg):
    graph, _ = simple_graph(dg)
    broken = dg.Macro(
        id="finish_task",
        semantic_purpose="record completion",
        procedure=(dg.MacroStep(primitive="failing"),),
        postconditions=(dg.Predicate(field="done", equals=True),),
    )
    graph = graph.model_copy(update={"macros": (broken,)})
    outcome = run(dg, graph, make_world(dg, {"done": False}), scripted([result("do_it")]))
    assert outcome.status == "diagnosed"
    assert outcome.diagnosis == dg.DiagnosisLayer.PROCEDURE


def test_postcondition_failure_is_diagnosed_not_hidden(dg):
    graph, _ = simple_graph(dg)
    lying = dg.Macro(
        id="finish_task",
        semantic_purpose="claims completion without doing it",
        procedure=(dg.MacroStep(primitive="noop"),),
        postconditions=(dg.Predicate(field="done", equals=True),),
    )
    graph = graph.model_copy(update={"macros": (lying,)})
    outcome = run(dg, graph, make_world(dg, {"done": False}), scripted([result("do_it")]))
    assert outcome.status == "diagnosed"
    assert outcome.diagnosis == dg.DiagnosisLayer.POSTCONDITION


def test_cycle_detection_and_depth_bound(dg):
    node_a = dg.DecisionNode(
        id="a", question="?", choices=(make_choice(dg, "to_b", target_node="b"),), entry=True
    )
    node_b = dg.DecisionNode(
        id="b", question="?", choices=(make_choice(dg, "to_a", target_node="a"),)
    )
    graph = dg.PolicyGraphVersion(id="g", version_number=1, entry_node="a", nodes=(node_a, node_b))
    outcome = run(
        dg,
        graph,
        make_world(dg, {}),
        scripted([result("to_b"), result("to_a"), result("to_b")]),
    )
    assert outcome.status == "cycle"
    outcome = run(
        dg,
        graph,
        make_world(dg, {}),
        scripted([result("to_b"), result("to_a")]),
        max_depth=2,
    )
    assert outcome.status == "depth_exceeded"


def test_teacher_candidate_envelope_and_add_choice(dg):
    graph, _ = simple_graph(dg)
    with pytest.raises(ValidationError, match="Input should be"):
        dg.TeacherCandidate(
            candidate_type="DELETE_EVERYTHING",
            target_id="work",
            semantic_description="simulated",
            rationale="simulated",
            confidence=0.5,
            base_policy_id="graph",
        )
    candidate = dg.TeacherCandidate(
        candidate_type="ADD_CHOICE",
        target_id="work",
        choice=make_choice(
            dg, "also_finish", target_macro="finish_task", desc="second completion path"
        ),
        semantic_description="Add a second completion path.",
        rationale="Evidence: router hit UNKNOWN twice with no fitting choice.",
        confidence=0.8,
        base_policy_id="graph",
    )
    with pytest.raises(ValidationError, match="requires a macro section"):
        dg.TeacherCandidate(
            candidate_type="ADD_MACRO",
            target_id="work",
            choice=candidate.choice,
            semantic_description="simulated",
            rationale="simulated",
            confidence=0.5,
            base_policy_id="graph",
        )
    with pytest.raises(ValidationError, match="carries no change sections"):
        dg.TeacherCandidate(
            candidate_type="NO_CHANGE",
            target_id="work",
            choice=candidate.choice,
            semantic_description="simulated",
            rationale="simulated",
            confidence=0.5,
            base_policy_id="graph",
        )
    next_graph = dg.apply_add_choice(graph, candidate)
    assert next_graph.version_number == 2
    assert next_graph.parent_version_id == "graph"
    assert graph.version_number == 1  # original untouched (append-only evolution)
    assert len(next_graph.nodes[0].choices) == 2
    with pytest.raises(ValueError, match="not found"):
        dg.apply_add_choice(graph, candidate.model_copy(update={"target_id": "nope"}))
    with pytest.raises(ValueError, match="already present"):
        dg.apply_add_choice(next_graph, candidate)
