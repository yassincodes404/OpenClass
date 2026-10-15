"""Independent read-back port. Executor text, model claims and exit codes are not evidence."""

from enum import StrEnum
from typing import Annotated, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from openclass_core.automation_applicability import AutomationContract

PostconditionId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")]


class VerificationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class VerificationRequest(AutomationContract):
    id: UUID = Field(default_factory=uuid4)
    policy_version_id: UUID
    scope: Literal["step", "macro", "done"]
    action_name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    step_index: int | None = Field(default=None, ge=0, le=31)
    cwd: str = Field(min_length=1, max_length=2000)
    test_port: str | None = Field(default=None, max_length=5)
    postconditions: tuple[PostconditionId, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def unique_postconditions(self) -> "VerificationRequest":
        if len(set(self.postconditions)) != len(self.postconditions):
            raise ValueError("duplicate postconditions")
        return self


class PostconditionOutcome(AutomationContract):
    postcondition: PostconditionId
    status: VerificationStatus


class VerificationOutcome(AutomationContract):
    request_id: UUID
    status: VerificationStatus
    checks: tuple[PostconditionOutcome, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def consistent_checks(self) -> "VerificationOutcome":
        names = [check.postcondition for check in self.checks]
        if len(names) != len(set(names)):
            raise ValueError("duplicate verification checks")
        if self.status == VerificationStatus.PASSED and (
            not self.checks
            or any(check.status != VerificationStatus.PASSED for check in self.checks)
        ):
            raise ValueError("passing verification requires passing checks")
        return self


class AutomationVerifier(Protocol):
    """Trusted adapter must independently observe each registered postcondition.

    No execution port is supplied. Implementations must not infer success from
    executor/model assertions; an unavailable check is not a passing check.
    """

    async def verify(self, request: VerificationRequest) -> VerificationOutcome: ...
