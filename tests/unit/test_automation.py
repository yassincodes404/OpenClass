import pytest
from openclass_core.automation import (
    AutomationAction,
    AutomationActionName,
    AutomationActionResult,
    AutomationDecision,
    AutomationLoop,
    AutomationMacro,
    AutomationPolicyVersion,
    AutomationState,
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
    loop = AutomationLoop(ScriptedDecision([AutomationActionName.LIST_DIRECTORY]), executor)
    state, result = await loop.step(
        AutomationState(goal="run tests", cwd="/workspace/project"), policy
    )
    assert result.action.name == AutomationActionName.LIST_DIRECTORY
    assert state.last_action == AutomationActionName.LIST_DIRECTORY
    assert state.history == (result.action,)

    blocked_loop = AutomationLoop(
        ScriptedDecision([AutomationActionName.RUN_PYTHON_TESTS]), executor
    )
    with pytest.raises(ValueError, match="not registered"):
        await blocked_loop.step(state, policy)


def test_policy_v2_adds_a_macro_without_mutating_v1() -> None:
    v1 = AutomationPolicyVersion(
        version_number=1,
        primitives=(AutomationActionName.RUN_PYTHON_TESTS, AutomationActionName.BLOCKED),
    )
    candidate = AutomationMacro(
        name="recover_port_conflict",
        description="Choose a permitted alternate port and rerun the test action.",
        actions=(
            AutomationAction(name=AutomationActionName.INSPECT_PORT),
            AutomationAction(name=AutomationActionName.CHOOSE_AVAILABLE_TEST_PORT),
            AutomationAction(name=AutomationActionName.RERUN_PREVIOUS),
        ),
    )
    v2 = AutomationPolicyVersion(
        version_number=2,
        primitives=v1.primitives,
        macros=(candidate,),
    )
    assert v1.version_number == 1
    assert v1.macros == ()
    assert v2.version_number == 2
    assert v2.macros[0].name == "recover_port_conflict"
