"""Laya decision provider profile.

Maintains strict separation between provider-declared capability and
OpenClass empirical knowledge. Does NOT copy empirical Jev assumptions.
"""

from typing import Any, Literal

from openclass_core.models import Model
from openclass_core.supervision import OperatingProfile
from pydantic import Field


class LayaDeclaredCapabilities(Model):
    local: bool = True
    choice: bool = True
    score: bool = True
    yes_no: bool = True
    max_declared_choices: int = 254


class LayaMeasuredKnowledge(Model):
    """Empirical measurements by OpenClass. Initialized to None/UNKNOWN until characterized."""

    max_choice_count_tested: int | None = None
    margin_behavior: str | None = None
    unknown_behavior: str | None = None
    calibration_status: Literal["unknown", "uncalibrated", "calibrated"] = "uncalibrated"
    validation_artifact_hash: str | None = None
    accuracy: float | None = None


class LayaProfile(Model):
    provider: str = "laya"
    model: str = "laya-router"
    declared: LayaDeclaredCapabilities = Field(default_factory=LayaDeclaredCapabilities)
    measured_by_openclass: LayaMeasuredKnowledge = Field(default_factory=LayaMeasuredKnowledge)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def as_operating_profile(self) -> OperatingProfile:
        """Declared limits are not tested limits; UNKNOWN occupies one choice."""
        tested = self.measured_by_openclass.max_choice_count_tested
        return OperatingProfile(
            calibration_status=self.measured_by_openclass.calibration_status,
            validation_artifact_hash=self.measured_by_openclass.validation_artifact_hash,
            declared_max_choices=self.declared.max_declared_choices + 1,
            measured_max_choices=tested + 1 if tested is not None else None,
        )
