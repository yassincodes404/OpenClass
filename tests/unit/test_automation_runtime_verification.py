"""Runtime gates against independently read simulated external state, not exit codes."""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from openclass_core.automation import (
    ApplicabilitySpec,
    AutomationAction,
    AutomationActionName,
    AutomationActionResult,
    AutomationDecision,
    AutomationErrorCode,
    AutomationLoop,
    AutomationMacro,
    AutomationMacroCandidate,
    AutomationMacroResult,
    AutomationPolicyVersion,
    AutomationRuntimeError,
    AutomationState,
    AutomationStepContract,
    FailureState,
    StateGuard,
)
from openclass_core.automation_applicability import FailureRule
from openclass_core.automation_verification import (
    PostconditionOutcome,
    VerificationOutcome,
    VerificationStatus,
)
from pydantic import ValidationError

N = AutomationActionName


def macro(**updates):
    data = dict(
        name="recover_port_conflict",
        description="Simulated recovery with independently observed tests and report.",
        actions=(
            AutomationAction(name=N.CHOOSE_AVAILABLE_TEST_PORT),
            AutomationAction(name=N.RUN_PYTHON_TESTS),
            AutomationAction(name=N.WRITE_REPORT),
        ),
        applicability_spec=ApplicabilitySpec(
            require_test_attempted=True,
            require_failed_test=True,
            require_result_inspected=True,
            raw_failure_signals=(),
            normalization_rules=(
                FailureRule(
                    category="port_conflict",
                    signals=("Address already in use", "Address in use", "EADDRINUSE"),
                ),
            ),
            required_failure_category="port_conflict",
        ),
        step_contracts=(
            AutomationStepContract(postconditions=("port_selected",)),
            AutomationStepContract(
                preconditions=(StateGuard(field="test_port", value="8002"),),
                postconditions=("tests_passed",),
            ),
            AutomationStepContract(postconditions=("report_present",)),
        ),
        postconditions=("tests_passed", "report_present"),
    )
    return AutomationMacro(**(data | updates))


def policy(recovery=None, **updates):
    return AutomationPolicyVersion(
        **(
            dict(
                version_number=2,
                primitives=(
                    N.CHOOSE_AVAILABLE_TEST_PORT,
                    N.RUN_PYTHON_TESTS,
                    N.WRITE_REPORT,
                    N.DONE,
                    N.BLOCKED,
                    N.CHECK_EXIT_CODE,
                    N.LIST_DIRECTORY,
                    N.RERUN_PREVIOUS,
                ),
                macros=(recovery or macro(),),
                done_postconditions=("tests_passed", "report_present"),
            )
            | updates
        )
    )


def state(**updates):
    return AutomationState(
        **(
            dict(
                goal="run tests and retain a report",
                cwd=".",
                failure=FailureState(
                    test_attempted=True,
                    exit_code=1,
                    output="Address already in use",
                    result_inspected=True,
                    port=8000,
                ),
            )
            | updates
        )
    )


class Decision:
    def __init__(self, action="recover_port_conflict"):
        self.action = AutomationAction(name=action, arguments={"summary": "model claims success"})

    async def decide(self, state, policy):
        return AutomationDecision(action=self.action, rationale="Simulated model assertion only.")


class ExternalExecutor:
    """Simulated adapter, deliberately separate from the read-only verifier."""

    def __init__(self, root: Path, *, misleading=False, exit_code=0):
        self.root = root
        self.misleading = misleading
        self.exit_code = exit_code
        self.actions = []

    async def execute(self, action, state):
        self.actions.append(action)
        patch = {"test_port": "8002"} if action.name == N.CHOOSE_AVAILABLE_TEST_PORT else {}
        if not self.misleading:
            if action.name == N.CHOOSE_AVAILABLE_TEST_PORT:
                (self.root / "port").write_text("8002")
            elif action.name in {N.RUN_PYTHON_TESTS, N.RERUN_PREVIOUS}:
                (self.root / "tests").write_text("passed")
            elif action.name == N.WRITE_REPORT:
                (self.root / "report").write_text("retained")
        return AutomationActionResult(
            action=action,
            exit_code=self.exit_code,
            output="Everything succeeded (assertion).",
            state_patch=patch,
        )


class ExternalVerifier:
    """Independent read-back of fixed test resources; never examines executor output."""

    def __init__(self, root: Path):
        self.root = root
        self.requests = []

    async def verify(self, request):
        self.requests.append(request)
        expected = {
            "port_selected": ("port", "8002"),
            "tests_passed": ("tests", "passed"),
            "report_present": ("report", "retained"),
        }
        checks = []
        for name in request.postconditions:
            if name not in expected:
                status = VerificationStatus.UNAVAILABLE
            else:
                filename, content = expected[name]
                path = self.root / filename
                status = (
                    VerificationStatus.PASSED
                    if path.is_file() and path.read_text() == content
                    else VerificationStatus.FAILED
                )
            checks.append(PostconditionOutcome(postcondition=name, status=status))
        return VerificationOutcome(
            request_id=request.id,
            status=VerificationStatus.PASSED
            if all(check.status == VerificationStatus.PASSED for check in checks)
            else VerificationStatus.FAILED,
            checks=tuple(checks),
        )


def loop(executor, verifier, action="recover_port_conflict", **updates):
    return AutomationLoop(
        Decision(action),
        executor,
        **(dict(available_capabilities=frozenset(N), verifier=verifier) | updates),
    )


@pytest.mark.asyncio
async def test_macro_then_done_requires_independent_readback_at_every_boundary(tmp_path):
    executor = ExternalExecutor(tmp_path)
    verifier = ExternalVerifier(tmp_path)
    active = policy()
    initial = state()
    next_state, result = await loop(executor, verifier).step(initial, active)
    assert result.verified and len(result.verifications) == 4
    assert [request.scope for request in verifier.requests] == ["step", "step", "step", "macro"]
    assert [request.step_index for request in verifier.requests] == [0, 1, 2, None]
    assert all(request.policy_version_id == active.id for request in verifier.requests)
    assert initial.history == () and initial.test_port is None
    assert next_state.test_port == "8002"
    assert next_state.failure.exit_code == 0
    assert [a.name for a in next_state.history] == [a.name for a in active.macros[0].actions]

    _, done = await loop(executor, verifier, N.DONE).step(next_state, active)
    assert done.verified
    assert len(executor.actions) == 3  # DONE never delegates truth to an executor.
    assert verifier.requests[-1].scope == "done"


@pytest.mark.asyncio
async def test_misleading_zero_exit_does_not_pass_step_postcondition(tmp_path):
    executor = ExternalExecutor(tmp_path, misleading=True)
    verifier = ExternalVerifier(tmp_path)
    with pytest.raises(AutomationRuntimeError) as error:
        await loop(executor, verifier).step(state(), policy())
    assert error.value.code == AutomationErrorCode.VERIFICATION_FAILED
    assert error.value.step_index == 0
    assert error.value.may_have_executed
    assert error.value.verification.checks[0].status == VerificationStatus.FAILED
    assert len(executor.actions) == 1
    assert len(error.value.state.history) == 1  # Side effect attempt retained for reconciliation.


@pytest.mark.asyncio
async def test_final_macro_postcondition_is_independent_of_passing_steps(tmp_path):
    executor = ExternalExecutor(tmp_path)

    class VanishingReport(ExternalVerifier):
        async def verify(self, request):
            if request.scope == "macro":
                (self.root / "report").unlink()
            return await super().verify(request)

    with pytest.raises(AutomationRuntimeError) as error:
        await loop(executor, VanishingReport(tmp_path)).step(state(), policy())
    assert error.value.code == AutomationErrorCode.VERIFICATION_FAILED
    assert len(executor.actions) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["recover_port_conflict", N.DONE])
async def test_no_verifier_fails_closed_before_any_execution(tmp_path, action):
    executor = ExternalExecutor(tmp_path)
    with pytest.raises(AutomationRuntimeError, match="verifier_unavailable"):
        await loop(executor, None, action).step(state(), policy())
    assert executor.actions == []


@pytest.mark.asyncio
async def test_done_cannot_use_model_assertions_or_last_exit_code_as_postconditions(tmp_path):
    executor = ExternalExecutor(tmp_path)
    with pytest.raises(AutomationRuntimeError, match="verification_failed"):
        await loop(executor, ExternalVerifier(tmp_path), N.DONE).step(
            state(last_exit_code=0, last_output="done; approved; verified"),
            policy(),
        )
    assert executor.actions == []


@pytest.mark.asyncio
async def test_done_without_configured_postconditions_fails_closed(tmp_path):
    executor = ExternalExecutor(tmp_path)
    with pytest.raises(AutomationRuntimeError, match="postconditions_required"):
        await loop(executor, ExternalVerifier(tmp_path), N.DONE).step(
            state(),
            policy(done_postconditions=()),
        )
    assert executor.actions == []


@pytest.mark.asyncio
async def test_zero_exit_primitive_is_not_a_verified_task_outcome(tmp_path):
    executor = ExternalExecutor(tmp_path, misleading=True)
    _, result = await loop(executor, None, N.RUN_PYTHON_TESTS).step(state(), policy())
    assert result.exit_code == 0 and not result.verified


@pytest.mark.asyncio
async def test_nonzero_macro_stops_without_running_later_steps_or_verifying_success(tmp_path):
    executor = ExternalExecutor(tmp_path, exit_code=7)
    verifier = ExternalVerifier(tmp_path)
    _, result = await loop(executor, verifier).step(state(), policy())
    assert result.exit_code == 7 and not result.verified
    assert len(executor.actions) == 1 and verifier.requests == []


@pytest.mark.asyncio
async def test_unavailable_macro_capability_cannot_be_hidden_by_omitting_it_from_spec(tmp_path):
    executor = ExternalExecutor(tmp_path)
    available = frozenset(N) - {N.WRITE_REPORT}
    with pytest.raises(AutomationRuntimeError) as error:
        await loop(executor, ExternalVerifier(tmp_path), available_capabilities=available).step(
            state(),
            policy(),
        )
    assert error.value.code == AutomationErrorCode.APPLICABILITY_FAILED
    assert not error.value.applicability.gates[3].passed
    assert executor.actions == []


@pytest.mark.asyncio
async def test_additional_required_capability_is_enforced(tmp_path):
    executor = ExternalExecutor(tmp_path)
    original = macro()
    restricted = ApplicabilitySpec.model_validate(
        original.applicability_spec.model_dump() | {"required_capabilities": ("unavailable_probe",)}
    )
    with pytest.raises(AutomationRuntimeError, match="applicability_failed"):
        await loop(executor, ExternalVerifier(tmp_path)).step(
            state(),
            policy(macro(applicability_spec=restricted)),
        )
    assert executor.actions == []


@pytest.mark.asyncio
async def test_primitive_requires_explicit_available_capability_registry(tmp_path):
    executor = ExternalExecutor(tmp_path)
    with pytest.raises(AutomationRuntimeError, match="capability_unavailable"):
        await AutomationLoop(Decision(N.RUN_PYTHON_TESTS), executor).step(state(), policy())
    assert executor.actions == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "updates",
    [
        {"schema_id": "different"},
        {"schema_version": 2},
        {"observed_at": datetime.now(UTC) - timedelta(hours=1)},
        {"observed_at": datetime.now(UTC) + timedelta(hours=1)},
        {"result_inspected": False},
        {"test_attempted": False},
        {"exit_code": None},
        {"exit_code": 0},
        {"output": "Connection refused"},
        {"output": "Permission denied"},
        {"output": "File not found"},
    ],
)
async def test_runtime_rejects_wrong_schema_staleness_and_negative_transfer(tmp_path, updates):
    executor = ExternalExecutor(tmp_path)
    observed = FailureState.model_validate(state().failure.model_dump() | updates)
    with pytest.raises(AutomationRuntimeError, match="applicability_failed"):
        await loop(executor, ExternalVerifier(tmp_path)).step(state(failure=observed), policy())
    assert executor.actions == []


@pytest.mark.asyncio
@pytest.mark.parametrize("output", ["Address already in use", "Address in use", "EADDRINUSE"])
async def test_runtime_accepts_declared_cross_environment_port_conflict_signals(tmp_path, output):
    executor = ExternalExecutor(tmp_path)
    observed = FailureState.model_validate(state().failure.model_dump() | {"output": output})
    _, result = await loop(executor, ExternalVerifier(tmp_path)).step(
        state(failure=observed),
        policy(),
    )
    assert result.verified


@pytest.mark.asyncio
async def test_missing_failure_is_not_evidence_for_macro_execution(tmp_path):
    executor = ExternalExecutor(tmp_path)
    with pytest.raises(AutomationRuntimeError, match="applicability_failed"):
        await loop(executor, ExternalVerifier(tmp_path)).step(state(failure=None), policy())
    assert executor.actions == []


@pytest.mark.asyncio
async def test_per_step_guard_uses_current_state_and_stops_before_second_action(tmp_path):
    original = macro()
    contracts = (
        original.step_contracts[0],
        AutomationStepContract(
            preconditions=(StateGuard(field="test_port", value="9999"),),
            postconditions=("tests_passed",),
        ),
        original.step_contracts[2],
    )
    executor = ExternalExecutor(tmp_path)
    with pytest.raises(AutomationRuntimeError) as error:
        await loop(executor, ExternalVerifier(tmp_path)).step(
            state(),
            policy(macro(step_contracts=contracts)),
        )
    assert error.value.code == AutomationErrorCode.PRECONDITION_FAILED
    assert error.value.step_index == 1
    assert error.value.state.test_port == "8002"
    assert len(executor.actions) == 1


@pytest.mark.asyncio
async def test_macro_safety_guard_is_checked_initially_and_between_steps(tmp_path):
    original = macro()
    spec = ApplicabilitySpec.model_validate(
        original.applicability_spec.model_dump()
        | {"safety_guards": (StateGuard(field="exit_code", value=1),)}
    )
    executor = ExternalExecutor(tmp_path)
    with pytest.raises(AutomationRuntimeError) as error:
        await loop(executor, ExternalVerifier(tmp_path)).step(
            state(),
            policy(macro(applicability_spec=spec)),
        )
    assert error.value.code == AutomationErrorCode.PRECONDITION_FAILED
    assert error.value.step_index == 2
    assert len(executor.actions) == 2


@pytest.mark.asyncio
async def test_macro_initial_guard_failure_runs_no_actions(tmp_path):
    original = macro()
    spec = ApplicabilitySpec.model_validate(
        original.applicability_spec.model_dump()
        | {"safety_guards": (StateGuard(field="cwd", value="other_workspace"),)}
    )
    executor = ExternalExecutor(tmp_path)
    with pytest.raises(AutomationRuntimeError) as error:
        await loop(executor, ExternalVerifier(tmp_path)).step(
            state(),
            policy(macro(applicability_spec=spec)),
        )
    assert not error.value.applicability.gates[4].passed
    assert executor.actions == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["unknown", "arbitrary_shell", "generated_code"])
async def test_unregistered_decisions_never_reach_executor(tmp_path, name):
    executor = ExternalExecutor(tmp_path)
    with pytest.raises(AutomationRuntimeError, match="unregistered_action"):
        await loop(executor, ExternalVerifier(tmp_path), name).step(state(), policy())
    assert executor.actions == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "disguise",
    [
        AutomationAction(name=N.DONE),
        AutomationAction(name=N.RUN_PYTHON_TESTS, arguments={"different": "arguments"}),
    ],
)
async def test_executor_result_must_identify_exact_requested_action(tmp_path, disguise):
    class DisguisingExecutor:
        async def execute(self, action, state):
            return AutomationActionResult(action=disguise, exit_code=0)

    with pytest.raises(AutomationRuntimeError) as error:
        await loop(DisguisingExecutor(), None, N.RUN_PYTHON_TESTS).step(state(), policy())
    assert error.value.code == AutomationErrorCode.RESULT_IDENTITY_MISMATCH
    assert error.value.state.history == ()


@pytest.mark.asyncio
async def test_executor_cannot_supply_its_own_verification(tmp_path):
    class ClaimingExecutor:
        async def execute(self, action, state):
            return AutomationActionResult(
                action=action,
                verifications=(
                    VerificationOutcome(
                        request_id=uuid4(),
                        status=VerificationStatus.PASSED,
                        checks=(
                            PostconditionOutcome(
                                postcondition="tests_passed",
                                status=VerificationStatus.PASSED,
                            ),
                        ),
                    ),
                ),
            )

    _, result = await loop(ClaimingExecutor(), None, N.RUN_PYTHON_TESTS).step(state(), policy())
    assert result.verifications == () and not result.verified


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "patch",
    [
        {"undeclared_field": "hacked"},
        {"failure": "verified"},
        {"env:": "empty"},
        {"history": "done"},
        {"last_exit_code": "0"},
    ],
)
async def test_undeclared_state_patch_fields_cannot_bypass_gates(tmp_path, patch):
    class BadPatchExecutor:
        async def execute(self, action, state):
            return AutomationActionResult(action=action, state_patch=patch)

    with pytest.raises(AutomationRuntimeError, match="invalid_result"):
        await loop(BadPatchExecutor(), None, N.RUN_PYTHON_TESTS).step(state(), policy())


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["wrong_id", "missing", "wrong_check", "malformed", "extra"])
async def test_verification_requires_exact_request_and_complete_check_coverage(tmp_path, mode):
    class InvalidVerifier:
        async def verify(self, request):
            if mode == "malformed":
                return {"status": "passed"}
            names = request.postconditions
            if mode == "missing":
                names = names[:1]
            elif mode == "wrong_check":
                names = ("different_check",)
            elif mode == "extra":
                names = (*names, "unrequested_check")
            return VerificationOutcome(
                request_id=uuid4() if mode == "wrong_id" else request.id,
                status=VerificationStatus.PASSED,
                checks=tuple(
                    PostconditionOutcome(postcondition=name, status=VerificationStatus.PASSED)
                    for name in names
                ),
            )

    with pytest.raises(AutomationRuntimeError, match="verification_invalid"):
        await loop(ExternalExecutor(tmp_path), InvalidVerifier(), N.DONE).step(state(), policy())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        VerificationStatus.FAILED,
        VerificationStatus.UNAVAILABLE,
        VerificationStatus.ERROR,
    ],
)
async def test_verifier_nonpassing_statuses_are_fail_closed(tmp_path, status):
    class NonpassingVerifier:
        async def verify(self, request):
            return VerificationOutcome(request_id=request.id, status=status)

    with pytest.raises(AutomationRuntimeError, match="verification_failed"):
        await loop(ExternalExecutor(tmp_path), NonpassingVerifier(), N.DONE).step(state(), policy())


@pytest.mark.asyncio
@pytest.mark.parametrize("times_out", [False, True])
async def test_verifier_exceptions_and_timeout_are_sanitized_bounded_and_not_retried(
    tmp_path,
    times_out,
):
    class BrokenVerifier:
        calls = 0

        async def verify(self, request):
            self.calls += 1
            if times_out:
                await asyncio.sleep(10)
            raise RuntimeError("fixture-secret-must-not-escape")

    verifier = BrokenVerifier()
    with pytest.raises(AutomationRuntimeError) as error:
        await loop(
            ExternalExecutor(tmp_path),
            verifier,
            N.DONE,
            verification_timeout_seconds=0.001,
        ).step(state(), policy())
    assert str(error.value) == "verifier_unavailable"
    assert verifier.calls == 1
    assert error.value.__suppress_context__


@pytest.mark.asyncio
async def test_executor_error_is_sanitized_and_not_retried(tmp_path):
    class BrokenExecutor:
        calls = 0

        async def execute(self, action, state):
            self.calls += 1
            raise RuntimeError("fixture-secret-must-not-escape")

    executor = BrokenExecutor()
    with pytest.raises(AutomationRuntimeError, match="execution_failed") as error:
        await loop(executor, None, N.RUN_PYTHON_TESTS).step(state(), policy())
    assert executor.calls == 1 and error.value.__suppress_context__


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", [N.READ_FILE, N.RUN_NODE_TESTS])
async def test_rerun_cannot_hide_non_test_or_revoked_capabilities(tmp_path, previous):
    executor = ExternalExecutor(tmp_path)
    observed = state(history=(AutomationAction(name=previous),))
    with pytest.raises(AutomationRuntimeError) as error:
        await loop(executor, None, N.RERUN_PREVIOUS).step(observed, policy())
    assert error.value.code in {
        AutomationErrorCode.UNSAFE_RERUN,
        AutomationErrorCode.UNREGISTERED_ACTION,
    }
    assert executor.actions == []


@pytest.mark.asyncio
async def test_rerun_preserves_requested_identity_and_tracks_actual_test_observation(tmp_path):
    executor = ExternalExecutor(tmp_path)
    observed = state(history=(AutomationAction(name=N.RUN_PYTHON_TESTS),))
    next_state, result = await loop(executor, None, N.RERUN_PREVIOUS).step(observed, policy())
    assert result.action.name == N.RERUN_PREVIOUS
    assert next_state.history[-1].name == N.RERUN_PREVIOUS
    assert next_state.failure.exit_code == 0
    assert not next_state.failure.result_inspected


@pytest.mark.asyncio
async def test_primitive_test_result_is_retained_through_inspection(tmp_path):
    class InspectionExecutor(ExternalExecutor):
        async def execute(self, action, observed):
            if action.name == N.CHECK_EXIT_CODE:
                return AutomationActionResult(action=action, output=str(observed.failure.exit_code))
            return await super().execute(action, observed)

    executor = InspectionExecutor(tmp_path, exit_code=1)
    initial = state(failure=None)
    after_test, _ = await loop(executor, None, N.RUN_PYTHON_TESTS).step(initial, policy())
    assert after_test.failure.test_attempted and not after_test.failure.result_inspected
    after_inspect, _ = await loop(executor, None, N.CHECK_EXIT_CODE).step(after_test, policy())
    assert after_inspect.failure.result_inspected
    assert after_inspect.failure.observed_at == after_test.failure.observed_at
    assert after_inspect.failure.output == "Everything succeeded (assertion)."
    assert after_inspect.failure.exit_code == 1


@pytest.mark.parametrize(
    "updates",
    [
        {"step_contracts": ()},
        {"postconditions": ()},
        {"actions": (AutomationAction(name=N.DONE),) * 3},
        {"actions": (AutomationAction(name="arbitrary_shell"),) * 3},
        {"actions": (AutomationAction(name="nested_macro"),) * 3},
        {"name": "unknown"},
        {"name": "run_python_tests"},
    ],
)
def test_macro_cannot_omit_contracts_hide_terminal_steps_or_shadow_primitives(updates):
    with pytest.raises(ValidationError):
        macro(**updates)


def test_macro_actions_must_all_be_registered_in_policy():
    with pytest.raises(ValidationError, match="not registered"):
        policy(primitives=(N.DONE,))


def test_legacy_macro_missing_applicability_is_not_silently_executable():
    with pytest.raises(ValidationError):
        AutomationMacro(
            name="legacy_macro",
            description="Legacy is not authorized.",
            actions=(AutomationAction(name=N.RUN_PYTHON_TESTS),),
        )


@pytest.mark.parametrize("seconds", [0, -1, 61, float("inf"), float("nan")])
def test_verification_timeout_must_be_finite_and_bounded(tmp_path, seconds):
    with pytest.raises(ValueError, match="timeout"):
        loop(ExternalExecutor(tmp_path), None, verification_timeout_seconds=seconds)


@pytest.mark.asyncio
async def test_decision_provider_cannot_mutate_active_policy_or_input_state(tmp_path):
    class MutatingProvider:
        async def decide(self, observed, active):
            observed.env_vars["INJECTED"] = "1"
            active.macros[0].actions[0].arguments["injected"] = "unreviewed"
            return AutomationDecision(
                action=AutomationAction(name="recover_port_conflict"),
                rationale="simulated",
            )

    executor = ExternalExecutor(tmp_path)
    initial = state()
    active = policy()
    runtime = AutomationLoop(
        MutatingProvider(),
        executor,
        available_capabilities=frozenset(N),
        verifier=ExternalVerifier(tmp_path),
    )
    next_state, _ = await runtime.step(initial, active)
    assert initial.env_vars == next_state.env_vars == {}
    assert active.macros[0].actions[0].arguments == {}
    assert executor.actions[0].arguments == {}


@pytest.mark.asyncio
async def test_model_copy_cannot_bypass_executor_result_type_validation(tmp_path):
    class UnvalidatedResultExecutor:
        async def execute(self, action, state):
            return AutomationActionResult(action=action).model_copy(update={"exit_code": False})

    with pytest.raises(AutomationRuntimeError, match="invalid_result"):
        await loop(UnvalidatedResultExecutor(), None, N.LIST_DIRECTORY).step(state(), policy())


@pytest.mark.asyncio
async def test_model_copy_cannot_remove_macro_contracts_from_active_policy(tmp_path):
    executor = ExternalExecutor(tmp_path)
    forged = macro().model_copy(update={"postconditions": ()})
    active = policy().model_copy(update={"macros": (forged,)})
    with pytest.raises(AutomationRuntimeError, match="invalid_policy"):
        await loop(executor, ExternalVerifier(tmp_path)).step(state(), active)
    assert executor.actions == []


@pytest.mark.asyncio
async def test_failed_inspection_does_not_claim_the_test_result_was_inspected(tmp_path):
    executor = ExternalExecutor(tmp_path, exit_code=1)
    initial = state(
        failure=FailureState.model_validate(
            state().failure.model_dump() | {"result_inspected": False}
        )
    )
    after_inspect, _ = await loop(executor, None, N.CHECK_EXIT_CODE).step(initial, policy())
    assert not after_inspect.failure.result_inspected


@pytest.mark.asyncio
async def test_done_verifies_real_sandbox_report_and_detects_later_tampering(tmp_path):
    # Test-only adapter composition; core itself has no server imports.
    from openclass_server.automation_executor import SafeSandboxExecutor

    class ReportVerifier:
        async def verify(self, request):
            report = tmp_path / "output" / "report.json"
            valid = False
            if report.is_file():
                try:
                    content = json.loads(report.read_text())
                    valid = content == {"goal": "write a verified report", "history": []}
                except (ValueError, OSError):
                    valid = False
            status = VerificationStatus.PASSED if valid else VerificationStatus.FAILED
            return VerificationOutcome(
                request_id=request.id,
                status=status,
                checks=(PostconditionOutcome(postcondition="report_valid", status=status),),
            )

    executor = SafeSandboxExecutor(tmp_path)
    verifier = ReportVerifier()
    active = AutomationPolicyVersion(
        version_number=1,
        primitives=(N.WRITE_REPORT, N.DONE),
        done_postconditions=("report_valid",),
    )
    observed = AutomationState(goal="write a verified report", cwd=".")
    with pytest.raises(AutomationRuntimeError, match="verification_failed"):
        await loop(executor, verifier, N.DONE).step(observed, active)
    after_write, written = await loop(executor, None, N.WRITE_REPORT).step(observed, active)
    assert written.exit_code == 0 and not written.verified
    _, done = await loop(executor, verifier, N.DONE).step(after_write, active)
    assert done.verified
    (tmp_path / "output" / "report.json").write_text('{"goal": "tampered"}')
    with pytest.raises(AutomationRuntimeError, match="verification_failed"):
        await loop(executor, verifier, N.DONE).step(after_write, active)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "patch",
    [
        {"test_port": "8002"},
        {"cwd": "other"},
        {"env:FEATURE_FLAG": "1"},
        {"env:LD_PRELOAD": "payload.so"},
        {"env:PATH": "other"},
    ],
)
async def test_registered_primitive_cannot_patch_another_capability_state(tmp_path, patch):
    class OverreachingExecutor:
        async def execute(self, action, state):
            return AutomationActionResult(action=action, state_patch=patch)

    with pytest.raises(AutomationRuntimeError, match="invalid_result") as error:
        await loop(OverreachingExecutor(), None, N.LIST_DIRECTORY).step(state(), policy())
    assert error.value.may_have_executed


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["PATH", "LD_PRELOAD", "PYTHONPATH", "OPENCLASS_SECRET"])
async def test_environment_patch_preserves_sandbox_forbidden_keys(tmp_path, key):
    class UnsafeEnvironmentExecutor:
        async def execute(self, action, state):
            return AutomationActionResult(action=action, state_patch={f"env:{key}": "value"})

    runtime = loop(UnsafeEnvironmentExecutor(), None)
    runtime.decision_provider = Decision()
    runtime.decision_provider.action = AutomationAction(
        name=N.SET_ENVIRONMENT,
        arguments={"key": key, "value": "value"},
    )
    with pytest.raises(AutomationRuntimeError, match="invalid_result"):
        await runtime.step(
            state(),
            policy(
                primitives=(*policy().primitives, N.SET_ENVIRONMENT),
            ),
        )


@pytest.mark.asyncio
async def test_real_sandbox_environment_and_directory_patches_remain_compatible(tmp_path):
    from openclass_server.automation_executor import SafeSandboxExecutor

    executor = SafeSandboxExecutor(tmp_path)
    (tmp_path / "child").mkdir()
    active = AutomationPolicyVersion(
        version_number=1,
        primitives=(N.SET_ENVIRONMENT, N.CHANGE_DIRECTORY),
    )
    runtime = loop(executor, None)
    runtime.decision_provider.action = AutomationAction(
        name=N.SET_ENVIRONMENT,
        arguments={"key": " FEATURE_FLAG "},
    )
    observed, _ = await runtime.step(state(), active)
    assert observed.env_vars == {"FEATURE_FLAG": ""}
    runtime.decision_provider.action = AutomationAction(
        name=N.CHANGE_DIRECTORY,
        arguments={"path": "child"},
    )
    observed, _ = await runtime.step(observed, active)
    assert observed.cwd == "child"


@pytest.mark.asyncio
async def test_rerun_rejects_registered_but_currently_unavailable_underlying_action(tmp_path):
    executor = ExternalExecutor(tmp_path)
    observed = state(history=(AutomationAction(name=N.RUN_PYTHON_TESTS),))
    with pytest.raises(AutomationRuntimeError, match="capability_unavailable"):
        await loop(
            executor,
            None,
            N.RERUN_PREVIOUS,
            available_capabilities=frozenset({N.RERUN_PREVIOUS}),
        ).step(observed, policy())
    assert executor.actions == []


def test_verifier_cannot_be_the_executor_or_decision_provider_instance(tmp_path):
    executor = ExternalExecutor(tmp_path)
    provider = Decision()
    for verifier in (executor, provider):
        with pytest.raises(ValueError, match="independent"):
            AutomationLoop(provider, executor, verifier=verifier)


@pytest.mark.asyncio
async def test_prior_verifier_success_cannot_be_replayed_for_new_done_request(tmp_path):
    class ReplayVerifier:
        outcome = None

        async def verify(self, request):
            if self.outcome is None:
                self.outcome = VerificationOutcome(
                    request_id=request.id,
                    status=VerificationStatus.PASSED,
                    checks=tuple(
                        PostconditionOutcome(
                            postcondition=name,
                            status=VerificationStatus.PASSED,
                        )
                        for name in request.postconditions
                    ),
                )
            return self.outcome

    verifier = ReplayVerifier()
    runtime = loop(ExternalExecutor(tmp_path), verifier, N.DONE)
    await runtime.step(state(), policy())
    with pytest.raises(AutomationRuntimeError, match="verification_invalid"):
        await runtime.step(state(), policy())


@pytest.mark.parametrize(
    "checks",
    [
        (),
        (PostconditionOutcome(postcondition="report_present", status=VerificationStatus.FAILED),),
        (PostconditionOutcome(postcondition="report_present", status=VerificationStatus.PASSED),)
        * 2,
        tuple(
            PostconditionOutcome(
                postcondition=f"check_{index}",
                status=VerificationStatus.PASSED,
            )
            for index in range(17)
        ),
    ],
)
def test_verification_outcomes_are_bounded_complete_and_duplicate_free(checks):
    with pytest.raises(ValidationError):
        VerificationOutcome(request_id=uuid4(), status=VerificationStatus.PASSED, checks=checks)


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate_status", ["candidate", "approved", "rejected"])
async def test_discovery_candidate_status_is_not_policy_authority(tmp_path, candidate_status):
    active = policy(macros=())
    candidate = AutomationMacroCandidate(
        name="recover_port_conflict",
        description="Unactivated simulated proposal.",
        actions=macro().actions,
        base_policy_version_id=active.id,
        evidence=("simulated evidence only",),
        status=candidate_status,
    )
    executor = ExternalExecutor(tmp_path)
    with pytest.raises(AutomationRuntimeError, match="unregistered_action"):
        await loop(executor, ExternalVerifier(tmp_path), candidate.name).step(state(), active)
    assert active.macros == () and executor.actions == []


@pytest.mark.asyncio
async def test_mutating_executor_cannot_change_request_identity_or_source_state(tmp_path):
    class MutatingExecutor:
        async def execute(self, action, observed):
            observed.env_vars["INJECTED"] = "1"
            action.arguments["injected"] = "1"
            return AutomationActionResult(action=action)

    initial = state()
    with pytest.raises(AutomationRuntimeError, match="result_identity_mismatch"):
        await loop(MutatingExecutor(), None, N.LIST_DIRECTORY).step(initial, policy())
    assert initial.env_vars == {}


@pytest.mark.asyncio
async def test_provider_failure_is_safe_and_cannot_leak_upstream_error(tmp_path):
    class BrokenProvider:
        async def decide(self, state, policy):
            raise RuntimeError("fixture-secret-must-not-escape")

    executor = ExternalExecutor(tmp_path)
    with pytest.raises(AutomationRuntimeError, match="decision_failed") as error:
        await AutomationLoop(BrokenProvider(), executor).step(state(), policy())
    assert error.value.__suppress_context__ and executor.actions == []


@pytest.mark.asyncio
async def test_invalid_decision_is_rejected_before_execution(tmp_path):
    class InvalidProvider:
        async def decide(self, state, policy):
            return {"action": {"name": N.RUN_PYTHON_TESTS}, "rationale": "not a typed decision"}

    executor = ExternalExecutor(tmp_path)
    with pytest.raises(AutomationRuntimeError, match="invalid_decision"):
        await AutomationLoop(InvalidProvider(), executor).step(state(), policy())
    assert executor.actions == []


@pytest.mark.asyncio
@pytest.mark.parametrize("intervening", [N.READ_FILE, N.LIST_DIRECTORY])
async def test_real_adapter_inspection_is_bound_to_retained_test_after_intervening_success(
    tmp_path,
    intervening,
):
    from openclass_server.automation_executor import SafeSandboxExecutor

    (tmp_path / "source.txt").write_text("unrelated successful read")
    observed = state(
        last_action=N.RUN_PYTHON_TESTS,
        last_exit_code=1,
        last_output="Address already in use",
        history=(AutomationAction(name=N.RUN_PYTHON_TESTS),),
        failure=FailureState(
            test_attempted=True,
            exit_code=1,
            output="Address already in use",
            result_inspected=False,
            port=8000,
        ),
    )
    active = policy(primitives=(*policy().primitives, N.READ_FILE))
    executor = SafeSandboxExecutor(tmp_path)
    runtime = loop(executor, None, intervening)
    runtime.decision_provider.action = AutomationAction(
        name=intervening,
        arguments={"path": "source.txt"} if intervening == N.READ_FILE else {},
    )
    after_read, _ = await runtime.step(observed, active)
    assert after_read.last_exit_code == 0
    assert not after_read.failure.result_inspected
    checked, result = await loop(executor, None, N.CHECK_EXIT_CODE).step(after_read, active)
    assert result.output == "1"
    assert checked.failure.result_inspected
    assert checked.failure.exit_code == 1
    assert checked.failure.observed_at == observed.failure.observed_at
    assert checked.failure.output == "Address already in use"
    assert after_read.last_exit_code == 0 and not after_read.failure.result_inspected


@pytest.mark.asyncio
async def test_successful_check_of_unrelated_exit_code_cannot_mark_retained_failure_inspected(
    tmp_path,
):
    class MisleadingInspection:
        async def execute(self, action, observed):
            return AutomationActionResult(action=action, output="0")

    observed = state(
        failure=FailureState(
            test_attempted=True,
            exit_code=1,
            output="Address already in use",
            result_inspected=False,
            port=8000,
        )
    )
    checked, _ = await loop(MisleadingInspection(), None, N.CHECK_EXIT_CODE).step(
        observed, policy()
    )
    assert not checked.failure.result_inspected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key_count,later_failure", [(17, False), (17, True), (32, False), (31, True)]
)
async def test_macro_aggregate_patch_retains_every_valid_key_on_success_and_nonzero_exit(
    tmp_path,
    key_count,
    later_failure,
):
    class EnvironmentExecutor:
        async def execute(self, action, observed):
            if action.name == N.RUN_PYTHON_TESTS:
                return AutomationActionResult(action=action, exit_code=7, output="test failed")
            key, value = action.arguments["key"], action.arguments["value"]
            (tmp_path / key).write_text(value)
            return AutomationActionResult(action=action, state_patch={f"env:{key}": value})

    keys = tuple(f"FEATURE_{index}" for index in range(key_count))
    actions = tuple(
        AutomationAction(
            name=N.SET_ENVIRONMENT,
            arguments={"key": key, "value": "enabled"},
        )
        for key in keys
    )
    contracts = tuple(
        AutomationStepContract(postconditions=(f"key_{index}_set",)) for index in range(key_count)
    )
    if later_failure:
        actions = (*actions, AutomationAction(name=N.RUN_PYTHON_TESTS))
        contracts = (*contracts, AutomationStepContract(postconditions=("tests_passed",)))
    procedure = macro(
        actions=actions,
        step_contracts=contracts,
        postconditions=("environment_ready",),
    )
    active = policy(procedure, primitives=(*policy().primitives, N.SET_ENVIRONMENT))

    class EnvironmentVerifier:
        calls = 0

        async def verify(self, request):
            self.calls += 1
            selected = keys if request.scope == "macro" else (keys[request.step_index],)
            assert all((tmp_path / key).read_text() == "enabled" for key in selected)
            return VerificationOutcome(
                request_id=request.id,
                status=VerificationStatus.PASSED,
                checks=tuple(
                    PostconditionOutcome(
                        postcondition=name,
                        status=VerificationStatus.PASSED,
                    )
                    for name in request.postconditions
                ),
            )

    verifier = EnvironmentVerifier()
    final, result = await loop(EnvironmentExecutor(), verifier).step(state(), active)
    assert isinstance(result, AutomationMacroResult)
    assert final.env_vars == dict.fromkeys(keys, "enabled")
    assert result.state_patch == {f"env:{key}": "enabled" for key in keys}
    assert len(final.history) == key_count + int(later_failure)
    assert result.exit_code == (7 if later_failure else 0)
    assert result.verified is not later_failure
    assert len(result.verifications) == key_count + int(not later_failure)
    assert verifier.calls == len(result.verifications)


def blocking_verifier_readback():
    # Intentionally violates the adapter contract to test late-result rejection.
    time.sleep(0.03)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["blocking", "suppressed_cancellation"])
@pytest.mark.parametrize("scope", ["done", "step"])
async def test_overdue_passing_verifier_cannot_complete_done_or_advance_macro(
    tmp_path, mode, scope
):
    class OverdueVerifier:
        calls = 0
        suppressed_cancellation = False

        async def verify(self, request):
            self.calls += 1
            if mode == "blocking":
                blocking_verifier_readback()
            else:
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    self.suppressed_cancellation = True
                    await asyncio.sleep(0.005)
            return VerificationOutcome(
                request_id=request.id,
                status=VerificationStatus.PASSED,
                checks=tuple(
                    PostconditionOutcome(
                        postcondition=name,
                        status=VerificationStatus.PASSED,
                    )
                    for name in request.postconditions
                ),
            )

    executor = ExternalExecutor(tmp_path)
    verifier = OverdueVerifier()
    with pytest.raises(AutomationRuntimeError, match="verifier_unavailable") as error:
        await loop(
            executor,
            verifier,
            N.DONE if scope == "done" else "recover_port_conflict",
            verification_timeout_seconds=0.001,
        ).step(state(), policy())
    assert verifier.calls == 1
    assert verifier.suppressed_cancellation == (mode == "suppressed_cancellation")
    assert len(executor.actions) == (0 if scope == "done" else 1)
    assert len(error.value.state.history) == len(executor.actions)
    assert error.value.may_have_executed == (scope == "step")


@pytest.mark.parametrize(
    "result_type,key_count",
    [(AutomationActionResult, 17), (AutomationMacroResult, 33)],
)
def test_primitive_and_macro_receipts_keep_separate_bounded_patch_limits(result_type, key_count):
    with pytest.raises(ValidationError):
        result_type(
            action=AutomationAction(name=N.SET_ENVIRONMENT),
            state_patch={f"env:FEATURE_{index}": "enabled" for index in range(key_count)},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_code", [0, 7])
async def test_unexpected_aggregate_validation_failure_retains_state_and_typed_error(
    tmp_path,
    monkeypatch,
    exit_code,
):
    import openclass_core.automation as automation

    def invalid_receipt(**payload):
        # Inject an unexpected receipt-construction defect, not an executor patch.
        payload["state_patch"] = {f"env:KEY_{index}": "enabled" for index in range(33)}
        return AutomationMacroResult(**payload)

    monkeypatch.setattr(automation, "AutomationMacroResult", invalid_receipt)
    executor = ExternalExecutor(tmp_path, exit_code=exit_code)
    with pytest.raises(AutomationRuntimeError, match="invalid_result") as error:
        await loop(executor, ExternalVerifier(tmp_path)).step(state(), policy())
    assert error.value.state.test_port == "8002"
    assert len(error.value.state.history) == (3 if exit_code == 0 else 1)
    assert error.value.state.last_exit_code == exit_code
    assert error.value.action.name == "recover_port_conflict"
    assert error.value.may_have_executed
    assert error.value.step_index == (None if exit_code == 0 else 0)
    assert error.value.__suppress_context__


@pytest.mark.asyncio
@pytest.mark.parametrize("updates", [{"exit_code": None}, {"test_attempted": False}])
async def test_check_exit_code_cannot_inspect_missing_or_unattempted_test(tmp_path, updates):
    from openclass_server.automation_executor import SafeSandboxExecutor

    observed = state(
        failure=FailureState.model_validate(
            state().failure.model_dump() | {"result_inspected": False} | updates
        )
    )
    final, _ = await loop(SafeSandboxExecutor(tmp_path), None, N.CHECK_EXIT_CODE).step(
        observed,
        policy(),
    )
    assert not final.failure.result_inspected
