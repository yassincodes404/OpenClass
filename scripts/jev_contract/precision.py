"""Paired Teacher scoring: independent identical packets, deterministic hidden evaluation."""

import argparse
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, JsonValue

from .canonical import Frozen, StateSnapshot, Step, digest
from .knowledge import save_new
from .runtime import execute_macro
from .teacher import TeacherCandidate, TeacherRequest, apply_candidate, candidate_schema, messages


class Check(Frozen):
    pointer: str
    expected: JsonValue


class MacroFixture(Frozen):
    macro_id: str
    expected_env_name: str
    expected_pass: bool
    facts: dict[str, JsonValue]


class HiddenEvaluation(Frozen):
    operator: str
    target_id: str
    payload_checks: tuple[Check, ...]
    graph_checks: tuple[Check, ...]
    regressions: tuple[Check, ...]
    macro_fixtures: tuple[MacroFixture, ...] = ()


class TeacherResponse(Frozen):
    package_id: str
    model: str
    packet_hash: str
    content: str | None
    infrastructure_status: Literal["ok", "failed"]
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reported_cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    simulated: bool = False


def packet(request: TeacherRequest) -> dict[str, Any]:
    return {
        "messages": messages(request),
        "temperature": 0,
        "max_tokens": 4096,
        "response_schema": candidate_schema(request),
    }


def checks(value: dict[str, Any], requirements: tuple[Check, ...]) -> bool:
    for check in requirements:
        current: Any = value
        try:
            for key in check.pointer.split("/")[1:]:
                key = key.replace("~1", "/").replace("~0", "~")
                current = current[int(key)] if isinstance(current, list) else current[key]
        except (KeyError, IndexError, TypeError, ValueError):
            return False
        if current != check.expected:
            return False
    return True


class FixtureWorld:
    """Authored deterministic fixture, never claimed as real-world execution."""

    def __init__(self, fixture: MacroFixture) -> None:
        self.fixture = fixture
        self.facts = dict(fixture.facts)

    def observe(self) -> StateSnapshot:

        return StateSnapshot(schema_id="service_state", schema_version=1, facts=self.facts)

    def execute(self, step: Step) -> bool:
        if step.capability == "choose_available_test_port":
            self.facts["port_selected"] = True
        elif step.capability == "set_environment":
            self.facts["env_name"] = step.arguments["name"]
        elif step.capability == "run_tests":
            self.facts["tests_passed"] = (
                self.facts.get("env_name") == self.fixture.expected_env_name
                and self.facts.get("port_selected") is True
            )
            return self.facts["tests_passed"] is True
        elif step.capability == "write_report":
            self.facts["report_written"] = self.facts.get("tests_passed") is True
            return self.facts["report_written"] is True
        elif step.capability == "inspect_result":
            self.facts["inspected"] = True
        else:
            return False
        return True


def evaluate_one(
    request: TeacherRequest,
    expected: HiddenEvaluation,
    response: TeacherResponse,
    actual_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    binding = actual_packet if actual_packet is not None else packet(request)
    if response.package_id != request.id or response.packet_hash != digest(binding):
        raise ValueError("response must bind to the identical frozen prompt/schema/evidence")
    report = {
        "schema_valid": False,
        "operator_correct": False,
        "target_correct": False,
        "payload_correct": False,
        "evaluation_passed": False,
        "regression": False,
        "evaluation_attempted": False,
        "missing_capability_correct": False,
        "insufficient_evidence_correct": False,
    }
    if response.infrastructure_status != "ok":
        return {**report, "status": "infrastructure_failure"}
    try:
        candidate = TeacherCandidate.model_validate_json(response.content or "")
    except ValueError:
        return {**report, "status": "schema_invalid"}
    report["schema_valid"] = True
    report["operator_correct"] = candidate.operator == expected.operator
    report["target_correct"] = candidate.target_id == expected.target_id
    report["payload_correct"] = checks(
        candidate.payload.model_dump(mode="json"), expected.payload_checks
    )
    report["missing_capability_correct"] = (
        expected.operator == candidate.operator == "MISSING_CAPABILITY"
    )
    report["insufficient_evidence_correct"] = (
        expected.operator == candidate.operator == "INSUFFICIENT_EVIDENCE"
    )
    try:
        graph = apply_candidate(request, candidate)
    except ValueError:
        return {**report, "status": "application_rejected"}
    report["evaluation_attempted"] = True
    value = graph.model_dump(mode="json")
    fixtures_pass = True
    for fixture in expected.macro_fixtures:
        macro = next((m for m in graph.macros if m.id == fixture.macro_id), None)
        passed = (
            macro is not None
            and execute_macro(macro, FixtureWorld(fixture), request.capabilities) is None
        )
        fixtures_pass &= passed == fixture.expected_pass
    report["regression"] = not checks(value, expected.regressions)
    report["evaluation_passed"] = (
        report["operator_correct"]
        and report["target_correct"]
        and report["payload_correct"]
        and checks(value, expected.graph_checks)
        and fixtures_pass
        and not report["regression"]
    )
    return {**report, "status": "evaluated"}


def compare(
    requests: tuple[TeacherRequest, ...],
    hidden: dict[str, HiddenEvaluation],
    responses: tuple[TeacherResponse, ...],
    models: tuple[str, str],
    packets: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """packets optionally supplies the exact packets actually sent per request id
    (protocol amendments must bind responses to what was really submitted)."""
    if len(set(models)) != 2:
        raise ValueError("two distinct predeclared models required")
    keys = [(r.model, r.package_id) for r in responses]
    required = {(m, r.id) for m in models for r in requests}
    packet_for = packets or {r.id: packet(r) for r in requests}
    if len(keys) != len(set(keys)) or set(keys) != required:
        raise ValueError(
            "exactly one first response per model/package required, including failures"
        )
    if any(r.simulated for r in responses):
        raise ValueError("simulated responses cannot establish Teacher model capability")
    index = {r.id: r for r in requests}
    for r in responses:
        if r.packet_hash != digest(packet_for[r.package_id]):
            raise ValueError("response must bind to the packet actually sent")
    output = {}
    for model in models:
        rows = [
            (
                r,
                evaluate_one(
                    index[r.package_id], hidden[r.package_id], r, packet_for[r.package_id]
                ),
            )
            for r in responses
            if r.model == model
        ]
        semantic = [result for r, result in rows if r.infrastructure_status == "ok"]
        metrics = {}
        for metric in (
            "schema_valid",
            "operator_correct",
            "target_correct",
            "payload_correct",
            "evaluation_passed",
            "regression",
        ):
            denominator = (
                sum(x["evaluation_attempted"] for x in semantic)
                if metric == "regression"
                else len(semantic)
            )
            metrics[metric + "_rate"] = (
                sum(x[metric] for x in semantic) / denominator if denominator else None
            )
        for operator, metric in (
            ("MISSING_CAPABILITY", "missing_capability_correct"),
            ("INSUFFICIENT_EVIDENCE", "insufficient_evidence_correct"),
        ):
            eligible = [
                result
                for r, result in rows
                if hidden[r.package_id].operator == operator and r.infrastructure_status == "ok"
            ]
            metrics[metric + "_rate"] = (
                sum(x[metric] for x in eligible) / len(eligible) if eligible else None
            )
        for field in ("input_tokens", "output_tokens", "reported_cost"):
            values = [getattr(r, field) for r, _ in rows]
            metrics[field] = sum(values) if all(v is not None for v in values) else None
            metrics[field + "_reported_calls"] = sum(v is not None for v in values)
        metrics["latency_ms_total"] = sum(r.latency_ms for r, _ in rows)
        metrics["infrastructure_failures"] = len(rows) - len(semantic)
        output[model] = {"metrics": metrics, "cases": {r.package_id: x for r, x in rows}}
    return {
        "models": output,
        "teacher_switch_authorized": False,
        "limitations": "Small authored benchmark. Deterministic structural and macro fixture "
        "evaluation only; Jev semantic replay must be assessed separately. "
        "Paired model differences do not isolate protocol causality.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("responses", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--models", nargs=2, required=True)
    parser.add_argument("--dataset", type=Path, default=Path("benchmarks/jev-contract/v1"))
    args = parser.parse_args()
    requests = tuple(
        TeacherRequest.model_validate(x)
        for x in json.loads((args.dataset / "teacher-packages.json").read_text())
    )
    hidden = {
        k: HiddenEvaluation.model_validate(v)
        for k, v in json.loads((args.dataset / "teacher-hidden.json").read_text()).items()
    }
    responses = tuple(
        TeacherResponse.model_validate(x) for x in json.loads(args.responses.read_text())
    )
    save_new(args.output, compare(requests, hidden, responses, tuple(args.models)))


if __name__ == "__main__":
    main()
