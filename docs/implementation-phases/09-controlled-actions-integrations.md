# Phase 09 — Controlled Actions, Capabilities, Verifiers & Real Integrations

Status: **planned, not audited complete**. Sequence: 9/10. Release status: no release or SaaS-readiness claim.

## Outcome and entry gate

Controlled Actions, Capabilities, Verifiers & Real Integrations must be a persisted vertical slice that a real business operator can use through the public API, SDK and actual product UI.

**Depends on:** Phase 08 gate evidence accepted; retain every preceding invariant. See README for scoped exception handling.

**Existing ticket mapping:** OC-035, OC-036, OC-037, OC-038. Preserve OC identifiers; draft scoped child tickets rather than renumbering the backlog.

Read [README](README.md) and [agent handoff](AGENT-HANDOFF.md) before implementation. Follow repository AGENTS.md and the canonical specification. This document specifies intended behavior; an agent must verify every current-state claim against its chosen commit.

## Audit first

Inspect automation.py, automation_executor.py, integrations.py, integration_adapters.py, current reachability probes and unsupported connection types. Verify whether execute and independent verify actually exist.
The real issue challenge established decisions, not verified external effects. An HTTP 200, connector card or Teacher claim of success is not an independent postcondition.

Produce an exists/wired/simulated/broken/missing matrix with file, route, migration and test evidence. Do not spend the phase reimplementing working behavior. Review architectural/API/schema changes using the repository RFC process before landing them.

## Ordered implementation slices

1. Define semantic Choice → versioned Transition → policy authorization → capability binding. Start with TERMINATE and one bounded HTTP capability; unsupported transition types remain explicit.
2. Register capability input/output schemas, risk, tenant grants, environment, preconditions, secret references, idempotency strategy and independent verifier. Connectivity/health does not confer execution authority.
3. Persist ExecutionIntent before side effects with source/run/version/binding/approval identities and idempotency key. Reject unauthorized, stale-state, wrong-version and UNKNOWN-triggered actions unless an explicit allowed review/wait transition applies.
4. Implement durable pending/running/succeeded/failed/ambiguous/reconciling states and leases/outbox only as necessary. Cancellation cannot pretend to undo completed effects. Reconcile ambiguous non-idempotent outcomes before retry; never promise exactly-once effects.
5. Execute a real low-risk business workflow, such as applying a reviewed routing label to an existing issue in an explicitly authorized repository or routing a ticket to an approved staging queue. External writes require explicit resource-scoped authorization; prepare payloads/read-only checks before requesting any missing authorization.
6. Independently read destination state with declared verifier version/time/provenance. Distinguish action success, verified postcondition, pending verification and semantic reference label; one does not automatically imply another.
7. Deliver capability/integration setup, test, grant, preview/approve, execution timeline, verification and retry/reconcile controls through public SDK/UI.
8. Reuse the same contracts for a second authorized customer/developer workflow. Add REST/webhook/CSV first; MCP, read-only DB, browser or n8n only when a concrete business workflow requires them. Every new adapter gets permission/SSRF/redirect/schema/secret tests.

Each numbered slice includes domain/service, persistence when required, public API, typed SDK, actual UI, errors/events and meaningful verification. Keep intermediate commits runnable. Work in bounded PRs; do not deliver only backend scaffolding and call the phase complete.

## Contracts, persistence and observable behavior

TransitionVersion, CapabilityManifest, ProjectCapabilityGrant, ExecutionIntent/Attempt/Outcome, VerificationRecord and ReconciliationResult. Core defines rules/ports; adapters own HTTP/MCP/browser transport and credential resolution.
Events: execution.authorized/denied/started/completed/ambiguous, verification.completed/failed and execution.reconciled. Parameter validation and deterministic grants constrain provider output; arbitrary shell, generated SQL and model-created permissions are excluded.

Schema changes use explicit Alembic migrations, including upgrades from existing data. Core owns deterministic rules/ports; providers/adapters cannot write ontology. UI/CLI access public HTTP SDKs. Secrets, raw sensitive payloads and upstream credential-bearing errors stay out of source, fixtures, logs and events.

## Business proof and exit criteria

- An authorized real source produces a bounded real external action and independently observed postcondition; the full lineage survives restart.
- Wrong tenant/environment, revoked grants, prompt injection, malformed arguments and unavailable capabilities are denied before side effects.
- Crash between intent/action/result, duplicate deliveries, timeout after accepted write and verifier failure are exercised with retained evidence; no blind duplicate non-idempotent write occurs.
- No confidence score or UNKNOWN automatically authorizes execution; human approval is required for the pilot risk profile unless independently certified otherwise.
- UI exposes pending/ambiguous/failed verification honestly and can reconcile without hiding history.
- Two workflows use the same Core without domain-specific forks. Shadow/replay cannot emit real side effects.

The shared pilot is real business issue/support routing with independently reviewed references, authorized external resources and a deliberately withheld concept. Use the retained scikit-learn cohort as a development probe, not a substitute for customer outcomes. Run the phase through the actual product and retain negative findings as well as success evidence.

## Required checks and evidence

- Run meaningful unit/contract tests for the changed rules and failure paths; run PostgreSQL integration checks against a disposable explicitly migrated database.
- Run `make check`, `make test`, `npm run build` and `uv build --all-packages` on the actual target branch. Document the supported frontend/package-manager setup from its development guide; app-specific builds do not silently substitute for required repository gates.
- Add/run public API + SDK + browser E2E for the acceptance behavior and a reload/API/database restart check where relevant. Opt-in live calls use runtime credentials and measured usage; credential-free CI may use clearly marked fixtures.
- Fill [PHASE-EVIDENCE-TEMPLATE](PHASE-EVIDENCE-TEMPLATE.md) with commit, environment, commands, results, IDs/hashes, source/label authorization, coverage and limitations. Do not retain tokens, customer secrets or unnecessary personal data.
- Mark COMPLETE only when all phase criteria and prerequisite gates pass. A pre-existing failed check is recorded and repaired or remains a named blocker; it is not a passing-release claim. Preserve independent quality/business gates even when engineering tests pass.

## Scope limits and risks

No universal integration platform, arbitrary browser automation or all transition kinds are required for this gate. Execution-proof planning can start earlier under OC-035, but this numbered phase integrates actions only after the preceding trust/version gates. Do not wait until Phase 9 to discover that the selected external API cannot support verification.

## Handoff

Provide the reviewed commit/PRs, migrations and rollback instructions, public contract changes, UI routes, persisted proof artifact references, actual check results and remaining blockers. Update phase status in README only with linked evidence; never copy planned/sample figures into measured product metrics.
