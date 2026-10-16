"""Provider-neutral runtime supervision over trusted, captured configuration.

Profiles describe operating boundaries, not provider brands. A declaration is
not a measurement and a self-reported score is not calibration evidence.
"""

from typing import Any, Literal

from pydantic import Field, model_validator

from .models import ChoiceResult, Model


class InferenceProvenance(Model):
    """Adapter-owned execution facts, not upstream metadata or calibration evidence."""

    execution_mode: Literal["in_process", "daemon", "api", "deterministic_test_fallback", "mock"]
    simulated: bool

    @model_validator(mode="after")
    def consistent_execution(self) -> "InferenceProvenance":
        if self.simulated != (self.execution_mode in {"mock", "deterministic_test_fallback"}):
            raise ValueError("inconsistent inference provenance")
        return self


class ProvenancedChoiceResult(ChoiceResult):
    """Additive provider-port result: only trusted adapter code sets this field."""

    inference_provenance: InferenceProvenance | None

    @model_validator(mode="after")
    def honest_execution_markers(self) -> "ProvenancedChoiceResult":
        metadata = dict(self.provider_metadata)
        provenance = self.inference_provenance
        if provenance is None:
            metadata["real_inference"] = False
        else:
            metadata.update(
                execution_mode=provenance.execution_mode,
                simulated=provenance.simulated,
                real_inference=not provenance.simulated,
            )
        object.__setattr__(self, "provider_metadata", metadata)
        return self


def inference_execution(
    mode: Literal["in_process", "daemon", "api"],
    upstream_metadata: Any = None,
) -> InferenceProvenance | None:
    """Adapter path establishes provenance; upstream claims can only withhold it."""
    if isinstance(upstream_metadata, dict) and (
        upstream_metadata.get("simulated") is True
        or upstream_metadata.get("real_inference") is False
        or upstream_metadata.get("execution_mode") in ("mock", "deterministic_test_fallback")
    ):
        return None
    return InferenceProvenance(execution_mode=mode, simulated=False)


class OperatingProfile(Model):
    calibration_status: Literal["unknown", "uncalibrated", "calibrated", "simulated"] = "unknown"
    validation_artifact_hash: str | None = Field(default=None, min_length=1, max_length=200)
    declared_max_choices: int = Field(default=255, ge=2, le=10000)
    measured_max_choices: int | None = Field(default=None, ge=2, le=10000)
    temperature: float = Field(default=1, gt=0, allow_inf_nan=False)
    min_margin: float = Field(default=0.25, ge=0, le=1, allow_inf_nan=False)
    max_unknown_probability: float = Field(default=0.2, ge=0, le=1, allow_inf_nan=False)
    allow_simulated_continuation: bool = False


class RuntimeSupervisionPolicy(Model):
    min_margin: float = Field(default=0.25, ge=0, le=1, allow_inf_nan=False)
    max_unknown_probability: float = Field(default=0.2, ge=0, le=1, allow_inf_nan=False)
    min_top_probability: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    max_choices: int = Field(default=50, ge=2, le=10000)


def evaluate_supervision(
    *,
    policy: RuntimeSupervisionPolicy,
    profile: OperatingProfile | None,
    selected_choice: str,
    top_probability: float,
    margin: float,
    unknown_probability: float,
    risk_level: Literal["ordinary", "high"],
    choice_count: int,
    provenance: InferenceProvenance | None = None,
) -> tuple[Literal["TRUSTED", "REVIEW", "UNKNOWN"], str]:
    if selected_choice == "UNKNOWN":
        return "UNKNOWN", "Provider selected semantic UNKNOWN outcome"
    if risk_level == "high":
        return "REVIEW", "High-risk decision node requires human review"
    if profile is None:
        return "REVIEW", "Missing operating profile requires conservative supervision"
    if profile.temperature != 1:
        return "REVIEW", "Non-unit temperature scaling has not been validated by this runtime"
    if choice_count > min(policy.max_choices, profile.declared_max_choices):
        return "REVIEW", "Choice count exceeds configured or declared operating boundary"
    simulated = profile.calibration_status == "simulated" and profile.allow_simulated_continuation
    if provenance is None:
        return "REVIEW", "Missing trusted inference provenance requires conservative supervision"
    if provenance.simulated != simulated:
        return (
            "REVIEW",
            "Execution provenance does not match calibration profile; conservative supervision",
        )
    if not simulated and (
        profile.calibration_status != "calibrated"
        or not profile.validation_artifact_hash
        or profile.measured_max_choices is None
    ):
        return "REVIEW", "Unmeasured or uncalibrated profile requires conservative supervision"
    if profile.measured_max_choices is not None and choice_count > profile.measured_max_choices:
        return "REVIEW", "Choice count exceeds measured operating boundary"
    if unknown_probability > min(policy.max_unknown_probability, profile.max_unknown_probability):
        return "REVIEW", "Unknown probability exceeds operating threshold"
    if margin < max(policy.min_margin, profile.min_margin):
        return "REVIEW", "Low decision margin requires human review"
    if top_probability < policy.min_top_probability:
        return "REVIEW", "Top probability below operating threshold"
    return (
        "TRUSTED",
        "Simulated fixture thresholds satisfied; not calibrated model confidence"
        if simulated
        else "Configured calibrated operating thresholds satisfied",
    )
