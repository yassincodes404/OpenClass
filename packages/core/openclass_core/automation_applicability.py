"""Declarative automation applicability. Evidence is data, never execution authority."""

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Signal = Annotated[str, Field(min_length=2, max_length=160, pattern=r".*\S.*")]
Category = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")]
Capability = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")]
GuardValue = str | int | bool | None


class AutomationContract(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
        hide_input_in_errors=True,
        revalidate_instances="always",
    )


class FailureState(AutomationContract):
    schema_id: str = Field(default="automation", min_length=1, max_length=80)
    schema_version: int = Field(default=1, ge=1)
    observed_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    test_attempted: bool
    exit_code: int | None
    output: str = Field(max_length=12000)
    result_inspected: bool
    port: int | None = Field(ge=1, le=65535)


class FailureRule(AutomationContract):
    category: Category
    signals: tuple[Signal, ...] = Field(min_length=1, max_length=12)


class StateGuard(AutomationContract):
    """Closed, type-sensitive predicates; missing/None never satisfies a guard."""

    field: Literal["cwd", "test_port", "test_attempted", "exit_code", "result_inspected", "port"]
    operator: Literal["equals", "not_equals", "present"] = "equals"
    value: str | int | bool | None = None

    @model_validator(mode="after")
    def valid_operand(self) -> "StateGuard":
        if (self.operator == "present") != (self.value is None):
            raise ValueError("present takes no value; comparison requires a value")
        if isinstance(self.value, str) and len(self.value) > 2000:
            raise ValueError("guard value is too long")
        return self

    def matches(self, facts: Mapping[str, GuardValue]) -> bool:
        actual = facts.get(self.field)
        if actual is None:
            return False
        if self.operator == "present":
            return True
        if type(actual) is not type(self.value):
            return False
        equal = actual == self.value
        return equal if self.operator == "equals" else not equal


class ApplicabilitySpec(AutomationContract):
    schema_id: str = Field(default="automation", min_length=1, max_length=80)
    schema_version: int = Field(default=1, ge=1)
    max_age_seconds: int = Field(default=300, ge=1, le=86400)
    require_test_attempted: bool
    require_failed_test: bool
    require_result_inspected: bool
    raw_failure_signals: tuple[Signal, ...] = Field(max_length=12)
    normalization_rules: tuple[FailureRule, ...] = Field(max_length=8)
    required_failure_category: Category | None
    preconditions: tuple[StateGuard, ...] = Field(default=(), max_length=16)
    required_capabilities: tuple[Capability, ...] = Field(default=(), max_length=32)
    safety_guards: tuple[StateGuard, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def check_mode(self) -> "ApplicabilitySpec":
        if self.required_failure_category is None:
            if not self.raw_failure_signals or self.normalization_rules:
                raise ValueError("literal mode requires signals and no normalization rules")
        else:
            categories = [rule.category for rule in self.normalization_rules]
            if (
                self.raw_failure_signals
                or len(categories) != len(set(categories))
                or self.required_failure_category not in categories
                or self.required_failure_category == "unknown"
            ):
                raise ValueError(
                    "category mode requires a unique known category and no raw signals"
                )
        return self


def matches_signal(output: str, signal: str) -> bool:
    literal = r"\s+".join(re.escape(word) for word in signal.casefold().split())
    return re.search(r"(?<!\w)" + literal + r"(?!\w)", output.casefold()) is not None


class NormalizedFailure(AutomationContract):
    category: Category | None
    port: int | None


class CompiledState(AutomationContract):
    test_attempted: bool
    exit_code: int | None
    result_inspected: bool
    failure: NormalizedFailure
    normalization_ambiguous: bool


def compile_state(state: FailureState, spec: ApplicabilitySpec) -> CompiledState:
    categories = sorted(
        {
            rule.category
            for rule in spec.normalization_rules
            if any(matches_signal(state.output, signal) for signal in rule.signals)
        }
    )
    category = categories[0] if len(categories) == 1 else None
    if state.exit_code is None or state.exit_code == 0 or not state.test_attempted:
        category = None
    return CompiledState(
        test_attempted=state.test_attempted,
        exit_code=state.exit_code,
        result_inspected=state.result_inspected,
        failure=NormalizedFailure(category=category, port=state.port),
        normalization_ambiguous=len(categories) > 1,
    )


class ApplicabilityGate(StrEnum):
    SCHEMA = "schema_compatibility"
    PRECONDITIONS = "preconditions"
    FAILURE = "failure_signature"
    CAPABILITIES = "required_capabilities"
    SAFETY = "safety_guards"


class GateOutcome(AutomationContract):
    gate: ApplicabilityGate
    passed: bool


class ApplicabilityOutcome(AutomationContract):
    gates: tuple[GateOutcome, ...] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def complete_gates(self) -> "ApplicabilityOutcome":
        if tuple(gate.gate for gate in self.gates) != tuple(ApplicabilityGate):
            raise ValueError("all five applicability gates are required in order")
        return self

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.gates)


def schema_compatible(
    state: FailureState, spec: ApplicabilitySpec, *, at: datetime | None = None
) -> bool:
    current_time = at or datetime.now(UTC)
    if current_time.utcoffset() is None:
        return False
    age = (current_time - state.observed_at).total_seconds()
    return (
        state.schema_id == spec.schema_id
        and state.schema_version == spec.schema_version
        and 0 <= age <= spec.max_age_seconds
    )


def guard_facts(
    state: FailureState, *, cwd: str | None = None, test_port: str | None = None
) -> dict[str, GuardValue]:
    return {
        "cwd": cwd,
        "test_port": test_port,
        "test_attempted": state.test_attempted,
        "exit_code": state.exit_code,
        "result_inspected": state.result_inspected,
        "port": state.port,
    }


def check_applicability(
    state: FailureState,
    spec: ApplicabilitySpec,
    *,
    available_capabilities: frozenset[str] = frozenset(),
    required_capabilities: frozenset[str] = frozenset(),
    cwd: str | None = None,
    test_port: str | None = None,
    at: datetime | None = None,
) -> ApplicabilityOutcome:
    facts = guard_facts(state, cwd=cwd, test_port=test_port)
    preconditions = (
        (not spec.require_test_attempted or state.test_attempted)
        and (not spec.require_failed_test or state.exit_code not in (None, 0))
        and (not spec.require_result_inspected or state.result_inspected)
        and all(guard.matches(facts) for guard in spec.preconditions)
    )
    failure = (
        compile_state(state, spec).failure.category == spec.required_failure_category
        if spec.required_failure_category is not None
        else any(matches_signal(state.output, signal) for signal in spec.raw_failure_signals)
    )
    checks = (
        (ApplicabilityGate.SCHEMA, schema_compatible(state, spec, at=at)),
        (ApplicabilityGate.PRECONDITIONS, preconditions),
        (ApplicabilityGate.FAILURE, failure),
        (
            ApplicabilityGate.CAPABILITIES,
            (set(spec.required_capabilities) | required_capabilities) <= available_capabilities,
        ),
        (ApplicabilityGate.SAFETY, all(guard.matches(facts) for guard in spec.safety_guards)),
    )
    return ApplicabilityOutcome(
        gates=tuple(GateOutcome(gate=gate, passed=passed) for gate, passed in checks)
    )


def applicable(
    state: FailureState,
    spec: ApplicabilitySpec,
    *,
    available_capabilities: frozenset[str] = frozenset(),
    required_capabilities: frozenset[str] = frozenset(),
    cwd: str | None = None,
    test_port: str | None = None,
    at: datetime | None = None,
) -> bool:
    """Boolean convenience; use check_applicability for bounded gate diagnostics."""
    return check_applicability(
        state,
        spec,
        available_capabilities=available_capabilities,
        required_capabilities=required_capabilities,
        cwd=cwd,
        test_port=test_port,
        at=at,
    ).passed
