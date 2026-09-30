"""Evidence registry, profile provenance and append-only staleness events."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from pydantic import Field, JsonValue, model_validator

from .canonical import Frozen, digest


class Evidence(Frozen):
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pointer: str = ""
    format: Literal["json", "text"] = "json"

    def read(self, root: Path) -> JsonValue:
        path = (root / self.path).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("evidence path escapes repository")
        if hashlib.sha256(path.read_bytes()).hexdigest() != self.sha256:
            raise ValueError("evidence hash mismatch")
        if self.format == "text":
            if self.pointer:
                raise ValueError("text evidence cannot use a JSON pointer")
            return path.read_text()
        value = json.loads(path.read_text())
        for part in self.pointer.split("/")[1:]:
            key = part.replace("~1", "/").replace("~0", "~")
            value = value[int(key)] if isinstance(value, list) else value[key]
        return cast(JsonValue, value)


class Observation(Frozen):
    id: str
    claim: str
    status: Literal["OBSERVED", "INFERRED", "UNKNOWN"]
    provider: str | None
    model: str | None
    model_revision: str | None = None
    observed_at: str | None
    benchmark: str
    run: str
    evidence: tuple[Evidence, ...] = Field(min_length=1)
    observed_value: JsonValue
    scope: str
    limitations: tuple[str, ...] = Field(min_length=1)
    strength: Literal["strong_within_benchmark", "limited", "hypothesis", "unestablished"]
    recommendation: str | None = None

    @model_validator(mode="after")
    def epistemic_status(self) -> "Observation":
        if self.status == "UNKNOWN" and self.strength != "unestablished":
            raise ValueError("unknown claim must remain unestablished")
        if self.status == "INFERRED" and self.strength != "hypothesis":
            raise ValueError("inference must remain a hypothesis")
        return self


class JevKnowledgeBase(Frozen):
    id: str
    version: int = Field(ge=1)
    imported_at: str
    observations: tuple[Observation, ...]

    @model_validator(mode="after")
    def unique(self) -> "JevKnowledgeBase":
        if len({o.id for o in self.observations}) != len(self.observations):
            raise ValueError("duplicate observation id")
        return self

    def verify(self, root: Path) -> None:
        for observation in self.observations:
            values = [e.read(root) for e in observation.evidence]
            if observation.status == "OBSERVED" and observation.observed_value != values[0]:
                raise ValueError(f"observed value differs from evidence: {observation.id}")


class ProviderIdentity(Frozen):
    provider: str
    model: str
    model_revision: str | None
    api_behavior: str
    distribution_schema: str
    major_version: str


class DecisionProviderProfile(Frozen):
    id: str
    version: int = Field(ge=1)
    identity: ProviderIdentity
    measured_at: str
    knowledge_base_hash: str
    observation_ids: tuple[str, ...]
    limitations: tuple[str, ...]


class JevProfile(DecisionProviderProfile):
    max_tested_flat_choices: int = Field(ge=1)
    count_convention: Literal["known_choices_excluding_unknown"]
    recommendations: tuple[str, ...]

    def manual(self) -> str:
        return "\n".join(
            [
                "JEV OPERATING PROFILE (experimental, not an accuracy guarantee)",
                f"Profile: {self.id} v{self.version}; measured {self.measured_at}",
                f"Provider/model: {self.identity.provider} / {self.identity.model}",
                f"Immutable revision: {self.identity.model_revision or 'not reported'}",
                f"Max tested flat known choices: {self.max_tested_flat_choices}; "
                "UNKNOWN additional",
                *[f"Recommendation (inferred): {r}" for r in self.recommendations],
                *[f"Limit: {r}" for r in self.limitations],
            ]
        )


class ProfileEvent(Frozen):
    kind: Literal["profile.stale"] = "profile.stale"
    profile_id: str
    profile_version: int
    profile_hash: str
    observed_at: datetime
    reasons: tuple[str, ...] = Field(min_length=1)
    identity: ProviderIdentity
    drift_evidence: tuple[Evidence, ...] = ()


def assess_profile(
    profile: JevProfile,
    identity: ProviderIdentity,
    at: datetime,
    sustained_drift: tuple[Evidence, ...] = (),
) -> ProfileEvent | None:
    reasons = tuple(
        key
        for key, value in profile.identity.model_dump().items()
        if identity.model_dump()[key] != value
    )
    if sustained_drift:
        reasons += ("sustained_runtime_drift",)
    if not reasons:
        return None
    return ProfileEvent(
        profile_id=profile.id,
        profile_version=profile.version,
        profile_hash=digest(profile.model_dump(mode="json")),
        observed_at=at,
        reasons=reasons,
        identity=identity,
        drift_evidence=sustained_drift,
    )


def require_current(profile: JevProfile, events: tuple[ProfileEvent, ...]) -> None:
    fingerprint = digest(profile.model_dump(mode="json"))
    if any(e.profile_hash == fingerprint for e in events):
        raise ValueError("STALE profile: re-characterization required for new development")


def save_new(path: Path, value: JsonValue) -> None:
    """Exclusive creation: historical profiles and events cannot be overwritten."""
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


class ProfileJournal:
    """Durable staleness tombstones; a matching alias never clears prior drift."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def events(self) -> tuple[ProfileEvent, ...]:
        return tuple(
            ProfileEvent.model_validate_json(p.read_text())
            for p in sorted(self.root.glob("*.json"))
        )

    def observe(
        self,
        profile: JevProfile,
        identity: ProviderIdentity,
        sustained_drift: tuple[Evidence, ...] = (),
    ) -> ProfileEvent | None:
        event = assess_profile(profile, identity, datetime.now().astimezone(), sustained_drift)
        if event:
            save_new(self.root / f"{uuid4().hex}.json", event.model_dump(mode="json"))
        return event

    def status(self, profile: JevProfile) -> Literal["CURRENT", "STALE"]:
        try:
            require_current(profile, self.events())
        except ValueError:
            return "STALE"
        return "CURRENT"
