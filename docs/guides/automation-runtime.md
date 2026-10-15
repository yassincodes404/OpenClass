# Automation runtime contracts

The experimental core runtime expands registered macros; it is not a server
activation API or an autonomous policy-promotion service. Historical research
scripts and evidence remain frozen. Examples in the unit suite use explicitly
simulated external state, not measured model capabilities.

## Required API migration

Construct `AutomationLoop(provider, executor, available_capabilities=..., verifier=...)`.
The capability set is the trusted application's available primitive registry, not
model output. It defaults to empty (deny execution). The active policy must also
register every primitive used by a macro. UNKNOWN and unregistered names confer
no authority. Macros cannot shadow primitives, nest macros, or contain DONE/BLOCKED.
The executor's existing sandbox, environment restrictions and fixed-command
mapping remain necessary; these contracts do not authorize arbitrary shell or
generated code.

`AutomationMacro` now requires:

- `applicability_spec: ApplicabilitySpec`;
- one `AutomationStepContract` per action, in the same order;
- nonempty step and final macro `postconditions`.

Legacy macros lacking these fields fail validation, rather than becoming
implicitly trusted. A policy permitting DONE must configure nonempty
`done_postconditions`. DONE without these or without a verifier fails closed.
Read/primitive execution without a verifier is still possible with an explicit
capability registry, but its exit code is **not verified task success**.
Termination is a core operation: DONE must be policy-registered and verified, but
does not require an executor capability entry or execute an adapter action.

These boundaries use strict, revalidated models. Python callers must supply
tuples/enums at typed fields; serialized JSON can use `model_validate_json`.
Test ports are decimal strings in `1024..65535`. State patches are capability-
specific: CHANGE_DIRECTORY may update `cwd`, CHOOSE_AVAILABLE_TEST_PORT may update
`test_port`, and SET_ENVIRONMENT may update only its requested, permitted key/value.
Provider inputs and executor inputs are isolated copies; mutating a dictionary
does not mutate the active policy or the caller's state.

## Five applicability gates

`check_applicability` returns five bounded gate outcomes, all conjunctive:

1. **Schema compatibility:** exact schema ID/version and an aware observation
   timestamp no older than `max_age_seconds` (default 300). Future evidence fails.
2. **Preconditions:** declared attempted/failed/inspected requirements plus
   type-sensitive declarative `StateGuard` predicates.
3. **Failure signature:** escaped, word-bounded literal signals or deterministic
   category normalization. Multiple categories become UNKNOWN and fail closed.
4. **Capabilities:** both declared requirements and every actual macro primitive
   must be available. Omitting a primitive from the spec does not evade this gate.
5. **Safety guards:** closed predicates, never code, regex programs or shell.

`FailureState` is retained separately from the last action's output. Test
primitives create a fresh, uninspected observation. The loop binds CHECK_EXIT_CODE's
read-only executor input to that retained test's exit code, even after intervening
successful primitives. Only a successful check reporting the matching retained
exit code marks it inspected; unrelated output does not. Inspection never refreshes
the observation timestamp or replaces the observed test result.
Adapters supplying initial failure observations own their provenance; provider
decisions and executor patches cannot replace them. The default schema identity
is `automation`, version `1`.

Each macro step rechecks schema freshness, safety guards and its current-state
preconditions, executes only its registered primitive, and independently checks
its postconditions before advancing. A nonzero exit stops expansion as a failed
procedure. A zero exit still requires verification. After all steps, the macro
postconditions are checked again, independently of passing intermediate checks.

Primitive `AutomationActionResult.state_patch` remains limited to 16 entries.
Macro receipts use the compatible subclass `AutomationMacroResult`, whose aggregate
patch permits 32 entries: each permitted patch-producing primitive changes at most
one key, and macros have at most 32 steps. This applies to both successful receipts
and early nonzero-exit receipts. Deserialize aggregate receipts using
`AutomationMacroResult`, not the primitive result schema. Unexpected aggregation
validation failures become typed `invalid_result` errors retaining the complete
current state and attempted macro identity.

`RERUN_PREVIOUS` may only refer to a registered, currently available test primitive.
Non-test history or a revoked capability is rejected before execution. Its result
must identify RERUN_PREVIOUS, while the retained failure observation describes
the underlying test. Returned action identity and arguments must exactly match
the requested action; a result cannot disguise an execution as DONE.

## Independent verifier port

Implement `AutomationVerifier.verify(VerificationRequest) -> VerificationOutcome`
in a trusted read-back adapter. Register a closed set of postcondition IDs in
that adapter. Examples include checking a real report's contents, independently
observing the external test outcome, and checking filesystem/Git invariants.
Unsupported checks return UNAVAILABLE, never PASSED.

The request contains a fresh ID, policy version ID, step/macro/done scope, action
name, optional step index, workspace location, test port, and 1–16 postcondition
IDs. It deliberately contains **no model rationale, executor output or exit code**.
The adapter must independently observe the relevant external state, enforce its
own workspace/resource isolation, and must not invoke corrective actions. A port
cannot make an untrusted implementation honest: wiring a model/executor that
merely repeats its assertions as the verifier violates this contract.
The loop rejects using the same object for the verifier and executor/provider.
Separate objects alone do not establish independence; read-back implementation
and application resource bindings still require review.

Outcomes contain only the request ID, a bounded status
(`passed`, `failed`, `unavailable`, `error`) and at most 16 named check statuses.
Passing requires a matching request ID and exactly the requested checks, each
passing, with no duplicates. Verification has a configurable monotonic acceptance
deadline in `(0, 60]` seconds (default 10), plus cooperative asyncio cancellation.
The loop rejects overdue outcomes even when a verifier blocks synchronously or
suppresses cancellation and eventually returns PASSED. No automatic retry occurs.

Adapters must use nonblocking, cancellable I/O and propagate cancellation. The
deadline is an acceptance bound, **not a hard-interrupt guarantee**: core cannot
preempt blocking Python or force a non-returning adapter to stop. A late adapter
can delay the caller until it yields or returns, but its result cannot establish
success. Hard wall-clock termination requires caller-owned process isolation,
which this core port does not provide.

DONE is handled by the loop, not by the executor. Only passing independent policy
postconditions produce its zero-exit, `verified=True` result. Executor-supplied
verification claims are discarded. Successful macro results similarly include
every step outcome plus the final macro outcome in `result.verifications`.
Primitive results without independent verification have `verified=False`.

## Errors and observability

`AutomationRuntimeError` is a `ValueError` with an `AutomationErrorCode`, optional
step index, bounded applicability/verification diagnostics and the last retained
state. Codes distinguish unregistered/unavailable actions, applicability and
precondition failures, missing postconditions/verifier, failed/invalid
verification, unsafe reruns, invalid inputs/results, identity mismatch and
provider/executor failure. Adapter exceptions and timeout text are suppressed,
not echoed. Execution/result failures retain the attempted `action` and set
`may_have_executed=True`; failed verification after macro execution does too.

Callers can record codes, policy/request identities, gate/check statuses and step
indices as safe events; no persistence or server/event infrastructure is added
here. Do not log complete states or adapter output: they may contain private
workspace data. After a failure the retained state/history identifies completed
attempts for reconciliation; do not blindly rerun side effects. No rollback,
durable intent, approval authority or automatic promotion is claimed.

## Existing consumer compatibility

Repository inspection found no server route, SDK, UI or historical script
constructing `AutomationLoop` or `AutomationMacro`; the existing loop callers are
the owned unit tests. The historical `scripts/automation_*.py` harnesses use their
own procedure/executor/applicability types and remain unchanged, not silently
redirected to production contracts.

`packages/server/openclass_server/automation_executor.py::SafeSandboxExecutor`
still returns the exact requested action (including RERUN_PREVIOUS), supported
state patches and unverified primitive results. Its direct executor tests remain
valid. Direct `execute(DONE)` still returns an unverified acknowledgement; callers
must use `AutomationLoop` to claim verified completion. Rerunning non-test history
directly is also still possible in that low-level adapter but is rejected by the
loop. This change does not retrofit an authorization boundary into direct calls.

External callers not present in this repository must migrate legacy macro
snapshots, register actual available capabilities, supply independent verifier
bindings and DONE postconditions, and consume `verified`/typed failures rather
than interpreting any primitive zero exit as task success. No out-of-scope caller
edits were required or made.
