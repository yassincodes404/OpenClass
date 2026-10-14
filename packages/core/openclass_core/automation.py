"""Typed boundaries for the experimental adaptive automation loop.

The core describes actions and policies. Executors own side effects and providers
only choose from the currently registered action names.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import Field

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


class AutomationAction(Model):
    name: AutomationActionName | str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    arguments: dict[str, str] = Field(default_factory=dict)


STATE_PATCH_ALLOWED_KEYS = frozenset({"cwd", "test_port"})


class AutomationState(Model):
    goal: str = Field(min_length=1, max_length=2000)
    cwd: str = Field(min_length=1, max_length=2000)
    files: tuple[str, ...] = ()
    test_port: str | None = None
    env_vars: dict[str, str] = Field(default_factory=dict)
    last_action: AutomationActionName | str | None = None
    last_exit_code: int | None = None
    last_output: str = Field(default="", max_length=12000)
    history: tuple[AutomationAction, ...] = ()


class AutomationDecision(Model):
    action: AutomationAction
    rationale: str = Field(min_length=1, max_length=2000)


class AutomationActionResult(Model):
    action: AutomationAction
    exit_code: int = 0
    output: str = Field(default="", max_length=12000)
    state_patch: dict[str, str] = Field(default_factory=dict)


class AutomationMacro(Model):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    description: str = Field(min_length=1, max_length=2000)
    actions: tuple[AutomationAction, ...] = Field(min_length=1)


class AutomationPolicyVersion(Model):
    id: UUID = Field(default_factory=uuid4)
    version_number: int = Field(ge=1)
    primitives: tuple[AutomationActionName, ...] = Field(min_length=1)
    macros: tuple[AutomationMacro, ...] = ()
    created_at: datetime = Field(default_factory=now)


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


def _apply_action_result(state: AutomationState, result: AutomationActionResult) -> AutomationState:
    env_vars = dict(state.env_vars)
    direct_updates: dict[str, object] = {}
    for key, value in result.state_patch.items():
        if key.startswith("env:"):
            env_key = key[4:]
            if not env_key:
                raise ValueError("empty env key in state_patch")
            env_vars[env_key] = value
        elif key in STATE_PATCH_ALLOWED_KEYS:
            direct_updates[key] = value
        else:
            raise ValueError(f"unsupported state_patch field: {key}")
    payload = state.model_dump()
    payload.update(
        {
            "last_action": result.action.name,
            "last_exit_code": result.exit_code,
            "last_output": result.output[:12000],
            "history": (*state.history, result.action),
            "env_vars": env_vars,
            **direct_updates,
        }
    )
    return AutomationState.model_validate(payload)


class AutomationLoop:
    """One typed decision/execution step; it never executes generated shell text."""

    def __init__(
        self,
        decision_provider: AutomationDecisionProvider,
        executor: AutomationExecutor,
    ) -> None:
        self.decision_provider = decision_provider
        self.executor = executor

    async def step(
        self, state: AutomationState, policy: AutomationPolicyVersion
    ) -> tuple[AutomationState, AutomationActionResult]:
        decision = await self.decision_provider.decide(state, policy)
        matched_macro = next(
            (macro for macro in policy.macros if macro.name == decision.action.name), None
        )
        if decision.action.name not in policy.primitives and matched_macro is None:
            raise ValueError("decision is not registered in the active automation policy")

        if matched_macro is not None:
            current_state = state
            outputs: list[str] = []
            combined_patch: dict[str, str] = {}
            last_exit_code = 0
            for sub_action in matched_macro.actions:
                sub_result = await self.executor.execute(sub_action, current_state)
                current_state = _apply_action_result(current_state, sub_result)
                if sub_result.output:
                    outputs.append(sub_result.output)
                combined_patch.update(sub_result.state_patch)
                last_exit_code = sub_result.exit_code
                if last_exit_code != 0:
                    break
            macro_result = AutomationActionResult(
                action=decision.action,
                exit_code=last_exit_code,
                output="\n".join(outputs)[:12000],
                state_patch=combined_patch,
            )
            return current_state, macro_result

        result = await self.executor.execute(decision.action, state)
        next_state = _apply_action_result(state, result)
        return next_state, result
