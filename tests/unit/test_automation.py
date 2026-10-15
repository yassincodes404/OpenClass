import pytest
from openclass_core.automation import (
    AutomationAction,
    AutomationActionName,
    AutomationActionResult,
    AutomationDecision,
    AutomationLoop,
    AutomationMacro,
    AutomationPolicyVersion,
    AutomationRuntimeError,
    AutomationState,
    AutomationStepContract,
)
from openclass_core.automation_applicability import ApplicabilitySpec, FailureState
from openclass_core.automation_verification import (
    PostconditionOutcome,
    VerificationOutcome,
    VerificationStatus,
)


def recovery_macro():
    actions = (
        AutomationAction(name=AutomationActionName.INSPECT_PORT),
        AutomationAction(name=AutomationActionName.CHOOSE_AVAILABLE_TEST_PORT),
        AutomationAction(name=AutomationActionName.RUN_PYTHON_TESTS),
    )
    return AutomationMacro(
        name="recover_port_conflict",
        description="Choose a permitted alternate port and rerun the test action.",
        actions=actions,
        applicability_spec=ApplicabilitySpec(
            require_test_attempted=True,
            require_failed_test=True,
            require_result_inspected=True,
            raw_failure_signals=("Address already in use",),
            normalization_rules=(),
            required_failure_category=None,
        ),
        step_contracts=tuple(
            AutomationStepContract(postconditions=(f"observed_{a.name}",)) for a in actions
        ),
        postconditions=("recovery_verified",),
    )


class ScriptedVerifier:
    """Simulated read-back for expansion mechanics, not a real outcome claim."""

    async def verify(self, request):
        return VerificationOutcome(
            request_id=request.id,
            status=VerificationStatus.PASSED,
            checks=tuple(
                PostconditionOutcome(postcondition=name, status=VerificationStatus.PASSED)
                for name in request.postconditions
            ),
        )


class ScriptedDecision:
    def __init__(self, actions: list[AutomationActionName]) -> None:
        self.actions = iter(actions)

    async def decide(self, state, policy):
        action = next(self.actions)
        return AutomationDecision(action=AutomationAction(name=action), rationale="scripted")


class RecordingExecutor:
    def __init__(self) -> None:
        self.actions: list[AutomationActionName] = []

    async def execute(self, action, state):
        self.actions.append(action.name)
        return AutomationActionResult(action=action, output=action.name)


@pytest.mark.asyncio
async def test_loop_accepts_only_registered_typed_actions() -> None:
    policy = AutomationPolicyVersion(
        version_number=1,
        primitives=(AutomationActionName.LIST_DIRECTORY, AutomationActionName.BLOCKED),
    )
    executor = RecordingExecutor()
    loop = AutomationLoop(
        ScriptedDecision([AutomationActionName.LIST_DIRECTORY]),
        executor,
        available_capabilities=frozenset(policy.primitives),
    )
    state, result = await loop.step(
        AutomationState(goal="run tests", cwd="/workspace/project"), policy
    )
    assert result.action.name == AutomationActionName.LIST_DIRECTORY
    assert state.last_action == AutomationActionName.LIST_DIRECTORY
    assert state.history == (result.action,)

    blocked_loop = AutomationLoop(
        ScriptedDecision([AutomationActionName.RUN_PYTHON_TESTS]), executor
    )
    with pytest.raises(AutomationRuntimeError, match="unregistered_action"):
        await blocked_loop.step(state, policy)


def test_policy_v2_adds_a_macro_without_mutating_v1() -> None:
    v1 = AutomationPolicyVersion(
        version_number=1,
        primitives=(AutomationActionName.RUN_PYTHON_TESTS, AutomationActionName.BLOCKED),
    )
    candidate = recovery_macro()
    v2 = AutomationPolicyVersion(
        version_number=2,
        primitives=(
            *v1.primitives,
            AutomationActionName.INSPECT_PORT,
            AutomationActionName.CHOOSE_AVAILABLE_TEST_PORT,
        ),
        macros=(candidate,),
    )
    assert v1.version_number == 1
    assert v1.macros == ()
    assert v2.version_number == 2
    assert v2.macros[0].name == "recover_port_conflict"


@pytest.mark.asyncio
async def test_loop_expands_registered_macro_and_validates_state_patch() -> None:
    macro = recovery_macro()
    policy = AutomationPolicyVersion(
        version_number=2,
        primitives=(
            AutomationActionName.RUN_PYTHON_TESTS,
            AutomationActionName.BLOCKED,
            AutomationActionName.INSPECT_PORT,
            AutomationActionName.CHOOSE_AVAILABLE_TEST_PORT,
        ),
        macros=(macro,),
    )

    class MacroDecision:
        async def decide(self, state, policy):
            return AutomationDecision(
                action=AutomationAction(name="recover_port_conflict"),
                rationale="Port conflict detected; run recovery macro.",
            )

    class PatchingExecutor:
        def __init__(self) -> None:
            self.executed: list[str] = []

        async def execute(self, action, state):
            self.executed.append(str(action.name))
            if action.name == AutomationActionName.CHOOSE_AVAILABLE_TEST_PORT:
                return AutomationActionResult(
                    action=action, output="8002", state_patch={"test_port": "8002"}
                )
            return AutomationActionResult(action=action, output=str(action.name))

    executor = PatchingExecutor()
    loop = AutomationLoop(
        MacroDecision(),
        executor,
        available_capabilities=frozenset(policy.primitives),
        verifier=ScriptedVerifier(),
    )
    next_state, result = await loop.step(
        AutomationState(
            goal="fix port conflict",
            cwd="/workspace/project",
            failure=FailureState(
                test_attempted=True,
                exit_code=1,
                output="Address already in use",
                result_inspected=True,
                port=8000,
            ),
        ),
        policy,
    )
    assert executor.executed == [
        AutomationActionName.INSPECT_PORT,
        AutomationActionName.CHOOSE_AVAILABLE_TEST_PORT,
        AutomationActionName.RUN_PYTHON_TESTS,
    ]
    assert next_state.test_port == "8002"
    assert len(next_state.history) == 3
    assert result.action.name == "recover_port_conflict"
    assert result.verified and len(result.verifications) == 4

    class BadPatchExecutor:
        async def execute(self, action, state):
            return AutomationActionResult(action=action, state_patch={"undeclared_field": "hacked"})

    bad_loop = AutomationLoop(
        ScriptedDecision([AutomationActionName.RUN_PYTHON_TESTS]),
        BadPatchExecutor(),
        available_capabilities=frozenset(policy.primitives),
    )
    with pytest.raises(AutomationRuntimeError, match="invalid_result"):
        await bad_loop.step(next_state, policy)
