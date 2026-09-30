"""Proof #2B: bounded declarative state normalization and applicability evaluation.

This module cannot execute actions or modify policy. Raw failure text is evidence.
Signals are escaped literals, never model-generated code or regular expressions.
"""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Signal = Annotated[str, Field(min_length=2, max_length=160, pattern=r".*\S.*")]
Category = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)


class FailureState(Frozen):
    test_attempted: bool
    exit_code: int | None
    output: str = Field(max_length=12000)
    result_inspected: bool
    port: int | None = Field(ge=1, le=65535)


class FailureRule(Frozen):
    category: Category
    signals: tuple[Signal, ...] = Field(min_length=1, max_length=12)


class ApplicabilitySpec(Frozen):
    require_test_attempted: bool
    require_failed_test: bool
    require_result_inspected: bool
    raw_failure_signals: tuple[Signal, ...] = Field(max_length=12)
    normalization_rules: tuple[FailureRule, ...] = Field(max_length=8)
    required_failure_category: Category | None

    @model_validator(mode="after")
    def check_mode(self) -> "ApplicabilitySpec":
        if self.required_failure_category is None:
            if not self.raw_failure_signals or self.normalization_rules:
                raise ValueError("literal mode requires signals and no normalization rules")
        else:
            categories = [r.category for r in self.normalization_rules]
            if (
                self.raw_failure_signals
                or len(categories) != len(set(categories))
                or self.required_failure_category not in categories
            ):
                raise ValueError(
                    "category mode requires a unique declared category and no raw signals"
                )
        return self


class ApplicabilityProposal(Frozen):
    proposal_type: Literal[
        "GENERALIZE_TRIGGER",
        "ADD_FAILURE_ALIAS",
        "ADD_STATE_NORMALIZATION",
        "SPLIT_MACRO",
        "NO_CHANGE",
        "INSUFFICIENT_EVIDENCE",
    ]
    semantic_description: str = Field(min_length=1, max_length=2000)
    applicability_spec: ApplicabilitySpec | None
    rationale: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_scope(self) -> "ApplicabilityProposal":
        change = self.proposal_type in {
            "GENERALIZE_TRIGGER",
            "ADD_FAILURE_ALIAS",
            "ADD_STATE_NORMALIZATION",
        }
        if change != (self.applicability_spec is not None):
            raise ValueError("supported changes require a spec; other proposals must leave it null")
        return self


def matches_signal(output: str, signal: str) -> bool:
    literal = r"\s+".join(re.escape(word) for word in signal.casefold().split())
    return re.search(r"(?<!\w)" + literal + r"(?!\w)", output.casefold()) is not None


class NormalizedFailure(Frozen):
    category: Category | None
    port: int | None


class CompiledState(Frozen):
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
            if any(matches_signal(state.output, s) for s in rule.signals)
        }
    )
    # Conflicting normalizations are UNKNOWN, not a model-selected fact.
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


def applicable(state: FailureState, spec: ApplicabilitySpec) -> bool:
    if spec.require_test_attempted and not state.test_attempted:
        return False
    if spec.require_failed_test and (state.exit_code is None or state.exit_code == 0):
        return False
    if spec.require_result_inspected and not state.result_inspected:
        return False
    if spec.required_failure_category is not None:
        return compile_state(state, spec).failure.category == spec.required_failure_category
    return any(matches_signal(state.output, signal) for signal in spec.raw_failure_signals)


class Outcome(Frozen):
    """Orthogonal research outcomes; never retroactively replace historical reports."""

    task_outcome: Literal["success", "failed", "not_run", "infrastructure_failed"]
    routing_outcome: Literal["macro_selected", "not_selected", "not_run"]
    procedure_outcome: Literal["success", "failed", "not_run"]
    postconditions: Literal["passed", "failed", "not_run"]
    applicability_gate: Literal["passed", "failed", "not_evaluated"]
    generalization_checkpoint: Literal["passed", "failed", "not_evaluated"]
    discovery_calls: int = Field(ge=0)
