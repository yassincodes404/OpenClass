"""Typed boundaries for the experimental adaptive automation loop.

The core describes actions and policies. Executors own side effects and providers
only choose from the currently registered action names.
"""

import asyncio
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from openclass_core.automation_applicability import (
    ApplicabilityOutcome,
    ApplicabilitySpec,
    AutomationContract,
    FailureState,
    StateGuard,
    check_applicability,
    guard_facts,
    schema_compatible,
)
from openclass_core.automation_applicability import FailureRule as FailureRule
from openclass_core.automation_applicability import applicable as applicable
from openclass_core.automation_applicability import compile_state as compile_state
from openclass_core.automation_applicability import matches_signal as matches_signal
from openclass_core.automation_verification import (
    AutomationVerifier,
    PostconditionId,
    VerificationOutcome,
    VerificationRequest,
    VerificationStatus,
)
from openclass_core.models import Model


def now() -> datetime:
    return datetime.now(UTC)


class AutomationActionName(StrEnum):
    LIST_DIRECTORY = "list_directory"
    READ_FILE = "read_file"
    CHANGE_DIRECTORY = "change_directory"
    RUN_PYTHON_TESTS = "run_python_tests"
    RUN_NODE_TESTS = "run_node_tests"
    RUN_MAKE_TESTS = "run_make_tests"
    CHECK_EXIT_CODE = "check_exit_code"
    CHECK_FILE_EXISTS = "check_file_exists"
    INSPECT_PORT = "inspect_port"
    CHOOSE_AVAILABLE_TEST_PORT = "choose_available_test_port"
    SET_ENVIRONMENT = "set_environment"
    RERUN_PREVIOUS = "rerun_previous"
    WRITE_REPORT = "write_report"
    DONE = "done"
    BLOCKED = "blocked"


class AutomationAction(AutomationContract):
    name: AutomationActionName | str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    arguments: dict[
        Annotated[str, Field(min_length=1, max_length=64)],
        Annotated[str, Field(max_length=2000)],
    ] = Field(default_factory=dict, max_length=16)


STATE_PATCH_ALLOWED_KEYS = frozenset({"cwd", "test_port"})
_ENV_KEY = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_FORBIDDEN_ENV_KEYS = frozenset({"PATH", "LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "PYTHONPATH"})


class AutomationState(AutomationContract):
    goal: str = Field(min_length=1, max_length=2000)
    cwd: str = Field(min_length=1, max_length=2000)
    files: tuple[str, ...] = ()
    test_port: str | None = Field(default=None, pattern=r"^[0-9]{1,5}$")
    env_vars: dict[str, str] = Field(default_factory=dict)
    last_action: AutomationActionName | str | None = None
    last_exit_code: int | None = None
    last_output: str = Field(default="", max_length=12000)
    history: tuple[AutomationAction, ...] = ()
    failure: FailureState | None = None

    @field_validator("test_port")
    @classmethod
    def unprivileged_port(cls, value: str | None) -> str | None:
        if value is not None and not 1024 <= int(value) <= 65535:
            raise ValueError("test port outside unprivileged range")
        return value


class AutomationDecision(AutomationContract):
    action: AutomationAction
    rationale: str = Field(min_length=1, max_length=2000)


class AutomationActionResult(AutomationContract):
    action: AutomationAction
    exit_code: int = 0
    output: str = Field(default="", max_length=12000)
    state_patch: dict[str, str] = Field(default_factory=dict, max_length=16)
    verifications: tuple[VerificationOutcome, ...] = Field(default=(), max_length=33)

    @property
    def verified(self) -> bool:
        """Only loop-issued read-back outcomes establish verified success."""
        return (
            self.exit_code == 0
            and bool(self.verifications)
            and all(outcome.status == VerificationStatus.PASSED for outcome in self.verifications)
        )


class AutomationMacroResult(AutomationActionResult):
    """Aggregate receipt, not an executor's primitive patch.

    Each allowed patch-producing primitive changes at most one key, so the
    32-step macro bound permits at most 32 distinct aggregate keys.
    """

    state_patch: dict[str, str] = Field(default_factory=dict, max_length=32)


class AutomationStepContract(AutomationContract):
    preconditions: tuple[StateGuard, ...] = Field(default=(), max_length=16)
    postconditions: tuple[PostconditionId, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def unique_postconditions(self) -> "AutomationStepContract":
        if len(set(self.postconditions)) != len(self.postconditions):
            raise ValueError("duplicate postconditions")
        return self


class AutomationMacro(AutomationContract):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    description: str = Field(min_length=1, max_length=2000)
    actions: tuple[AutomationAction, ...] = Field(min_length=1, max_length=32)
    applicability_spec: ApplicabilitySpec
    step_contracts: tuple[AutomationStepContract, ...] = Field(min_length=1, max_length=32)
    postconditions: tuple[PostconditionId, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def bounded_procedure(self) -> "AutomationMacro":
        if self.name in set(AutomationActionName) | {"unknown"}:
            raise ValueError("macro name shadows a primitive or UNKNOWN")
        if len(self.actions) != len(self.step_contracts):
            raise ValueError("every macro action requires a step contract")
        if len(set(self.postconditions)) != len(self.postconditions):
            raise ValueError("duplicate postconditions")
        allowed = set(AutomationActionName) - {
            AutomationActionName.DONE,
            AutomationActionName.BLOCKED,
        }
        if any(action.name not in allowed for action in self.actions):
            raise ValueError("macros contain only nonterminal primitives; no nested macros")
        return self


class AutomationPolicyVersion(AutomationContract):
    id: UUID = Field(default_factory=uuid4)
    version_number: int = Field(ge=1)
    primitives: tuple[AutomationActionName, ...] = Field(min_length=1)
    macros: tuple[AutomationMacro, ...] = ()
    done_postconditions: tuple[PostconditionId, ...] = Field(default=(), max_length=16)
    created_at: datetime = Field(default_factory=now)

    @model_validator(mode="after")
    def registered_macro_steps(self) -> "AutomationPolicyVersion":
        names = [macro.name for macro in self.macros]
        if len(set(names)) != len(names) or len(set(self.primitives)) != len(self.primitives):
            raise ValueError("duplicate policy registration")
        if any(action.name not in self.primitives for m in self.macros for action in m.actions):
            raise ValueError("macro primitive is not registered in the active automation policy")
        if len(set(self.done_postconditions)) != len(self.done_postconditions):
            raise ValueError("duplicate postconditions")
        return self


class AutomationMacroCandidate(Model):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    description: str = Field(min_length=1, max_length=2000)
    actions: tuple[AutomationAction, ...] = Field(min_length=1)
    base_policy_version_id: UUID
    evidence: tuple[str, ...] = Field(min_length=1)
    status: str = Field(default="candidate", pattern=r"^(candidate|approved|rejected)$")
    created_at: datetime = Field(default_factory=now)


class AutomationDecisionProvider(Protocol):
    async def decide(
        self, state: AutomationState, policy: AutomationPolicyVersion
    ) -> AutomationDecision: ...


class AutomationExecutor(Protocol):
    async def execute(
        self, action: AutomationAction, state: AutomationState
    ) -> AutomationActionResult: ...


class AutomationDiscoveryProvider(Protocol):
    async def discover_macro(
        self, state: AutomationState, policy: AutomationPolicyVersion
    ) -> AutomationMacroCandidate: ...


class AutomationErrorCode(StrEnum):
    INVALID_STATE = "invalid_state"
    INVALID_POLICY = "invalid_policy"
    INVALID_DECISION = "invalid_decision"
    DECISION_FAILED = "decision_failed"
    UNREGISTERED_ACTION = "unregistered_action"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    APPLICABILITY_FAILED = "applicability_failed"
    PRECONDITION_FAILED = "precondition_failed"
    POSTCONDITIONS_REQUIRED = "postconditions_required"
    VERIFIER_UNAVAILABLE = "verifier_unavailable"
    VERIFICATION_FAILED = "verification_failed"
    VERIFICATION_INVALID = "verification_invalid"
    RESULT_IDENTITY_MISMATCH = "result_identity_mismatch"
    INVALID_RESULT = "invalid_result"
    EXECUTION_FAILED = "execution_failed"
    UNSAFE_RERUN = "unsafe_rerun"


class AutomationRuntimeError(ValueError):
    """Safe bounded diagnostics; state is retained for reconciliation, not blind retry."""

    def __init__(
        self,
        code: AutomationErrorCode,
        state: AutomationState,
        *,
        step_index: int | None = None,
        applicability: ApplicabilityOutcome | None = None,
        verification: VerificationOutcome | None = None,
        action: AutomationAction | None = None,
        may_have_executed: bool = False,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.state = state
        self.step_index = step_index
        self.applicability = applicability
        self.verification = verification
        self.action = action
        self.may_have_executed = may_have_executed


def _macro_result(
    state: AutomationState,
    action: AutomationAction,
    outputs: list[str],
    state_patch: dict[str, str],
    verifications: list[VerificationOutcome],
    *,
    exit_code: int = 0,
    step_index: int | None = None,
) -> AutomationMacroResult:
    try:
        return AutomationMacroResult(
            action=action,
            exit_code=exit_code,
            output="\n".join(outputs)[:12000],
            state_patch=state_patch,
            verifications=tuple(verifications),
        )
    except (ValueError, TypeError):
        raise AutomationRuntimeError(
            AutomationErrorCode.INVALID_RESULT,
            state,
            step_index=step_index,
            action=action,
            may_have_executed=True,
        ) from None


def _apply_action_result(state: AutomationState, result: AutomationActionResult) -> AutomationState:
    env_vars = dict(state.env_vars)
    direct_updates: dict[str, object] = {}
    for key, value in result.state_patch.items():
        if key.startswith("env:"):
            env_key = key[4:]
            if (
                result.action.name != AutomationActionName.SET_ENVIRONMENT
                or env_key != result.action.arguments.get("key", "").strip()
                or value != result.action.arguments.get("value", "")
                or not _ENV_KEY.fullmatch(env_key)
                or env_key in _FORBIDDEN_ENV_KEYS
                or env_key.startswith("OPENCLASS_")
            ):
                raise ValueError("unauthorized environment patch")
            env_vars[env_key] = value
        elif key in STATE_PATCH_ALLOWED_KEYS:
            allowed_action = (
                AutomationActionName.CHANGE_DIRECTORY
                if key == "cwd"
                else AutomationActionName.CHOOSE_AVAILABLE_TEST_PORT
            )
            if result.action.name != allowed_action:
                raise ValueError("state patch does not match executed action")
            direct_updates[key] = value
        else:
            raise ValueError(f"unsupported state_patch field: {key}")
    payload = state.model_dump()
    failure = state.failure
    if result.action.name in _TEST_ACTIONS:
        port = int(state.test_port) if state.test_port and state.test_port.isdecimal() else None
        failure = FailureState(
            schema_id=failure.schema_id if failure else "automation",
            schema_version=failure.schema_version if failure else 1,
            test_attempted=True,
            exit_code=result.exit_code,
            output=result.output,
            result_inspected=False,
            port=port,
        )
    elif (
        result.action.name == AutomationActionName.CHECK_EXIT_CODE
        and result.exit_code == 0
        and failure is not None
        and failure.test_attempted
        and failure.exit_code is not None
        and result.output.strip() == str(failure.exit_code)
    ):
        # Only inspection of this retained test result counts. Do not refresh
        # its age or mistake the last intervening primitive's exit for evidence.
        failure = failure.model_copy(update={"result_inspected": True})
    payload.update(
        {
            "last_action": result.action.name,
            "last_exit_code": result.exit_code,
            "last_output": result.output[:12000],
            "history": (*state.history, result.action),
            "env_vars": env_vars,
            "failure": failure,
            **direct_updates,
        }
    )
    return AutomationState.model_validate(payload)


_TEST_ACTIONS = frozenset(
    {
        AutomationActionName.RUN_PYTHON_TESTS,
        AutomationActionName.RUN_NODE_TESTS,
        AutomationActionName.RUN_MAKE_TESTS,
    }
)
_RERUN_SKIP = frozenset(
    {
        AutomationActionName.RERUN_PREVIOUS,
        AutomationActionName.INSPECT_PORT,
        AutomationActionName.CHOOSE_AVAILABLE_TEST_PORT,
        AutomationActionName.SET_ENVIRONMENT,
    }
)


class AutomationLoop:
    """One typed decision/execution step; it never executes generated shell text."""

    def __init__(
        self,
        decision_provider: AutomationDecisionProvider,
        executor: AutomationExecutor,
        *,
        available_capabilities: frozenset[AutomationActionName] = frozenset(),
        verifier: AutomationVerifier | None = None,
        verification_timeout_seconds: float = 10.0,
    ) -> None:
        if not 0 < verification_timeout_seconds <= 60:
            raise ValueError("verification timeout must be within (0, 60] seconds")
        if verifier is not None and id(verifier) in {id(executor), id(decision_provider)}:
            raise ValueError("verifier must be independent of the executor and decision provider")
        self.decision_provider = decision_provider
        self.executor = executor
        self.available_capabilities = frozenset(
            AutomationActionName(capability) for capability in available_capabilities
        )
        self.verifier = verifier
        self.verification_timeout_seconds = verification_timeout_seconds

    def _require_capability(self, action: AutomationAction, state: AutomationState) -> None:
        if action.name not in self.available_capabilities:
            raise AutomationRuntimeError(AutomationErrorCode.CAPABILITY_UNAVAILABLE, state)

    def _rerun_target(
        self, action: AutomationAction, state: AutomationState, policy: AutomationPolicyVersion
    ) -> AutomationAction:
        if action.name != AutomationActionName.RERUN_PREVIOUS:
            return action
        previous = next((a for a in reversed(state.history) if a.name not in _RERUN_SKIP), None)
        if previous is None or previous.name not in _TEST_ACTIONS:
            raise AutomationRuntimeError(AutomationErrorCode.UNSAFE_RERUN, state)
        if previous.name not in policy.primitives:
            raise AutomationRuntimeError(AutomationErrorCode.UNREGISTERED_ACTION, state)
        self._require_capability(previous, state)
        return previous

    async def _execute(
        self, action: AutomationAction, state: AutomationState, policy: AutomationPolicyVersion
    ) -> tuple[AutomationState, AutomationActionResult]:
        self._require_capability(action, state)
        target = self._rerun_target(action, state, policy)
        executor_state = state.model_copy(deep=True)
        if (
            action.name == AutomationActionName.CHECK_EXIT_CODE
            and state.failure is not None
            and state.failure.exit_code is not None
        ):
            # The existing primitive reads last_exit_code. Bind that read-only
            # input to the retained test, not to an intervening successful action.
            executor_state = executor_state.model_copy(
                update={"last_exit_code": state.failure.exit_code}
            )
        try:
            result = await self.executor.execute(action.model_copy(deep=True), executor_state)
        except Exception:
            # Never propagate adapter errors, which may contain credentials.
            raise AutomationRuntimeError(
                AutomationErrorCode.EXECUTION_FAILED, state, action=action, may_have_executed=True
            ) from None
        if not isinstance(result, AutomationActionResult):
            raise AutomationRuntimeError(
                AutomationErrorCode.INVALID_RESULT, state, action=action, may_have_executed=True
            )
        try:
            result = AutomationActionResult.model_validate(result)
        except (ValueError, TypeError):
            raise AutomationRuntimeError(
                AutomationErrorCode.INVALID_RESULT, state, action=action, may_have_executed=True
            ) from None
        if result.action != action:
            raise AutomationRuntimeError(
                AutomationErrorCode.RESULT_IDENTITY_MISMATCH,
                state,
                action=action,
                may_have_executed=True,
            )
        # Executor-supplied verification claims have no authority.
        result = result.model_copy(update={"verifications": ()}, deep=True)
        try:
            next_state = _apply_action_result(state, result)
            if action.name == AutomationActionName.RERUN_PREVIOUS:
                observed = _apply_action_result(state, result.model_copy(update={"action": target}))
                next_state = next_state.model_copy(update={"failure": observed.failure})
        except (ValueError, TypeError):
            raise AutomationRuntimeError(
                AutomationErrorCode.INVALID_RESULT, state, action=action, may_have_executed=True
            ) from None
        return next_state, result

    async def _verify(
        self,
        state: AutomationState,
        policy: AutomationPolicyVersion,
        action: AutomationAction,
        postconditions: tuple[str, ...],
        *,
        scope: Literal["step", "macro", "done"],
        step_index: int | None = None,
    ) -> VerificationOutcome:
        if not postconditions:
            raise AutomationRuntimeError(AutomationErrorCode.POSTCONDITIONS_REQUIRED, state)
        if self.verifier is None:
            raise AutomationRuntimeError(AutomationErrorCode.VERIFIER_UNAVAILABLE, state)
        request = VerificationRequest(
            policy_version_id=policy.id,
            action_name=str(action.name),
            scope=scope,
            step_index=step_index,
            cwd=state.cwd,
            test_port=state.test_port,
            postconditions=postconditions,
        )
        clock = asyncio.get_running_loop()
        deadline = clock.time() + self.verification_timeout_seconds
        try:
            async with asyncio.timeout_at(deadline):
                raw_outcome = await self.verifier.verify(request)
            # Cancellation is cooperative: blocking or cancellation-suppressing
            # adapters can return after expiry without asyncio raising.
            if clock.time() >= deadline:
                raise TimeoutError
        except Exception:
            raise AutomationRuntimeError(
                AutomationErrorCode.VERIFIER_UNAVAILABLE,
                state,
                step_index=step_index,
                action=action,
                may_have_executed=scope != "done",
            ) from None
        try:
            outcome = VerificationOutcome.model_validate(raw_outcome)
        except (ValueError, TypeError):
            raise AutomationRuntimeError(
                AutomationErrorCode.VERIFICATION_INVALID,
                state,
                step_index=step_index,
                action=action,
                may_have_executed=scope != "done",
            ) from None
        if outcome.request_id != request.id or (
            outcome.status == VerificationStatus.PASSED
            and {check.postcondition for check in outcome.checks} != set(postconditions)
        ):
            raise AutomationRuntimeError(
                AutomationErrorCode.VERIFICATION_INVALID,
                state,
                step_index=step_index,
                action=action,
                may_have_executed=scope != "done",
            )
        if outcome.status != VerificationStatus.PASSED:
            raise AutomationRuntimeError(
                AutomationErrorCode.VERIFICATION_FAILED,
                state,
                step_index=step_index,
                verification=outcome,
                action=action,
                may_have_executed=scope != "done",
            )
        if clock.time() >= deadline:
            raise AutomationRuntimeError(
                AutomationErrorCode.VERIFIER_UNAVAILABLE,
                state,
                step_index=step_index,
                action=action,
                may_have_executed=scope != "done",
            )
        return outcome

    async def step(
        self, state: AutomationState, policy: AutomationPolicyVersion
    ) -> tuple[AutomationState, AutomationActionResult]:
        try:
            state = AutomationState.model_validate(state)
        except (ValueError, TypeError):
            raise AutomationRuntimeError(AutomationErrorCode.INVALID_STATE, state) from None
        try:
            policy = AutomationPolicyVersion.model_validate(policy)
        except (ValueError, TypeError):
            raise AutomationRuntimeError(AutomationErrorCode.INVALID_POLICY, state) from None
        try:
            raw_decision = await self.decision_provider.decide(
                state.model_copy(deep=True), policy.model_copy(deep=True)
            )
        except Exception:
            raise AutomationRuntimeError(AutomationErrorCode.DECISION_FAILED, state) from None
        if not isinstance(raw_decision, AutomationDecision):
            raise AutomationRuntimeError(AutomationErrorCode.INVALID_DECISION, state)
        try:
            decision = AutomationDecision.model_validate(raw_decision)
        except (ValueError, TypeError):
            raise AutomationRuntimeError(AutomationErrorCode.INVALID_DECISION, state) from None
        matched_macro = next(
            (macro for macro in policy.macros if macro.name == decision.action.name), None
        )
        if decision.action.name not in policy.primitives and matched_macro is None:
            raise AutomationRuntimeError(AutomationErrorCode.UNREGISTERED_ACTION, state)

        if matched_macro is not None:
            if state.failure is None:
                raise AutomationRuntimeError(AutomationErrorCode.APPLICABILITY_FAILED, state)
            applicability = check_applicability(
                state.failure,
                matched_macro.applicability_spec,
                available_capabilities=frozenset(self.available_capabilities),
                required_capabilities=frozenset(str(a.name) for a in matched_macro.actions),
                cwd=state.cwd,
                test_port=state.test_port,
            )
            if not applicability.passed:
                raise AutomationRuntimeError(
                    AutomationErrorCode.APPLICABILITY_FAILED, state, applicability=applicability
                )
            if self.verifier is None:
                raise AutomationRuntimeError(AutomationErrorCode.VERIFIER_UNAVAILABLE, state)
            current_state = state
            outputs: list[str] = []
            combined_patch: dict[str, str] = {}
            verifications: list[VerificationOutcome] = []
            for index, (sub_action, contract) in enumerate(
                zip(matched_macro.actions, matched_macro.step_contracts, strict=True)
            ):
                failure = current_state.failure
                if failure is None or not schema_compatible(
                    failure, matched_macro.applicability_spec
                ):
                    raise AutomationRuntimeError(
                        AutomationErrorCode.APPLICABILITY_FAILED, current_state, step_index=index
                    )
                facts = guard_facts(
                    failure, cwd=current_state.cwd, test_port=current_state.test_port
                )
                if not all(
                    guard.matches(facts)
                    for guard in (
                        *matched_macro.applicability_spec.safety_guards,
                        *contract.preconditions,
                    )
                ):
                    raise AutomationRuntimeError(
                        AutomationErrorCode.PRECONDITION_FAILED, current_state, step_index=index
                    )
                current_state, sub_result = await self._execute(sub_action, current_state, policy)
                if sub_result.output:
                    outputs.append(sub_result.output)
                combined_patch.update(sub_result.state_patch)
                if sub_result.exit_code != 0:
                    return current_state, _macro_result(
                        current_state,
                        decision.action,
                        outputs,
                        combined_patch,
                        verifications,
                        exit_code=sub_result.exit_code,
                        step_index=index,
                    )
                verifications.append(
                    await self._verify(
                        current_state,
                        policy,
                        sub_action,
                        contract.postconditions,
                        scope="step",
                        step_index=index,
                    )
                )
            verifications.append(
                await self._verify(
                    current_state,
                    policy,
                    decision.action,
                    matched_macro.postconditions,
                    scope="macro",
                )
            )
            macro_result = _macro_result(
                current_state, decision.action, outputs, combined_patch, verifications
            )
            return current_state, macro_result

        if decision.action.name == AutomationActionName.DONE:
            outcome = await self._verify(
                state, policy, decision.action, policy.done_postconditions, scope="done"
            )
            result = AutomationActionResult(action=decision.action, verifications=(outcome,))
            return _apply_action_result(state, result), result
        return await self._execute(decision.action, state, policy)
