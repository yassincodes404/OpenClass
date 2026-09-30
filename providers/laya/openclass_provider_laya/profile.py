"""Laya decision provider profile.

Maintains strict separation between provider-declared capability and
OpenClass empirical knowledge. Does NOT copy empirical Jev assumptions.
"""

from typing import Any

from openclass_core.models import Model
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
    calibration_status: str = "uncalibrated"
    accuracy: float | None = None


class LayaProfile(Model):
    provider: str = "laya"
    model: str = "laya-router"
    declared: LayaDeclaredCapabilities = Field(default_factory=LayaDeclaredCapabilities)
    measured_by_openclass: LayaMeasuredKnowledge = Field(default_factory=LayaMeasuredKnowledge)
    metadata: dict[str, Any] = Field(default_factory=dict)
