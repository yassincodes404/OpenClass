# Phase 08 — Approval, Immutable Knowledge Versions & Safe Activation

Status: **planned, not audited complete**. Sequence: 8/10. Release status: no release or SaaS-readiness claim.

## Outcome and entry gate

Approval, Immutable Knowledge Versions & Safe Activation must be a persisted vertical slice that a real business operator can use through the public API, SDK and actual product UI.

**Depends on:** Phase 07 gate evidence accepted; retain every preceding invariant. See README for scoped exception handling.

**Existing ticket mapping:** OC-009, OC-013, OC-015, OC-017. Preserve OC identifiers; draft scoped child tickets rather than renumbering the backlog.

Read [README](README.md) and [agent handoff](AGENT-HANDOFF.md) before implementation. Follow repository AGENTS.md and the canonical specification. This document specifies intended behavior; an agent must verify every current-state claim against its chosen commit.

## Audit first

Inspect ontology snapshots, active pointers, immutable constraints, candidate base hashes, approval placeholders and promotion guards. Inventory every writable route/CLI/service, not just the visible Promote button.
The challenge did not demonstrate human-approved immutable activation. Existing immutable ontology snapshots are useful foundation, not proof that all decision/policy/provider configuration is historically versioned.

Produce an exists/wired/simulated/broken/missing matrix with file, route, migration and test evidence. Do not spend the phase reimplementing working behavior. Review architectural/API/schema changes using the repository RFC process before landing them.

## Ordered implementation slices

1. Define immutable KnowledgeVersion manifest referencing ontology/classes/aliases, DecisionSpec, supervision policy and bindings actually supported. Include parent, candidate revisions, evaluation artifacts and content hash.
2. Implement explicit human approval records with authenticated reviewer, scope, decision, reason, evaluation ID/hash, candidate hash and base version. Manual/assisted are initial modes; guarded automatic activation remains deferred OC-015 work.
3. Enforce current complete PASS, independent evidence, canonicalization, permissions and fresh base in one server-side activation transaction. A model saying approved or a UI request flag is not authorization.
4. Create version N+1, append activation event and atomically move the active pointer using compare-and-swap/locking. Concurrent promotions from the same base conflict safely; no partial active state can escape.
5. Bind every decision to a captured manifest for its whole execution. Requests already in flight retain old versions; define action handling when authorization is revoked before execution.
6. Implement version diff, reconstruction and rollback-as-new-version. Rollback retains the failed activation/history and follows an explicit emergency policy with actor/reason and compatibility checks.
7. Add environment-scoped activation pointers for development/staging/production without copying secrets or silently promoting approvals. Production promotion references exact tested artifacts and environment grants.
8. Deliver review/evaluation/version/diff/activate/rollback screens and notifications. Demonstrate real novel cases under v1 and independently checked reuse under v2; measure calls/latency/cost rather than asserting avoided LLM work.

Each numbered slice includes domain/service, persistence when required, public API, typed SDK, actual UI, errors/events and meaningful verification. Keep intermediate commits runnable. Work in bounded PRs; do not deliver only backend scaffolding and call the phase complete.

## Contracts, persistence and observable behavior

KnowledgeVersion, ApprovalRecord, ActivationRecord, EnvironmentBinding and VersionDiff. Candidate lifecycle is server-controlled with explicit legal transitions and append-only history.
Events: candidate.approved, knowledge.version_created, knowledge.activated, knowledge.rollback_created and activation.rejected. APIs require expected base/ETag and an idempotency key; old versions are always readable within tenant permissions.

Schema changes use explicit Alembic migrations, including upgrades from existing data. Core owns deterministic rules/ports; providers/adapters cannot write ontology. UI/CLI access public HTTP SDKs. Secrets, raw sensitive payloads and upstream credential-bearing errors stay out of source, fixtures, logs and events.

## Business proof and exit criteria

- No route, SDK, CLI, background task or chat tool can activate without current evaluation and authorized review.
- Stale base, stale dataset, changed candidate, failed gate and wrong reviewer/project reject atomically without active-pointer/history drift.
- Concurrent and repeated activation requests create one intended version or an explicit conflict, never competing partial versions.
- SQL mutation of snapshots/aliases/history is rejected; rollback creates a new version and old runs reconstruct exact old configuration.
- Real cases previously UNKNOWN are independently evaluated under v2; known-case retention and remaining errors are shown alongside any improvement.
- User completes review → activation → run again → compare → rollback via UI, and all artifacts survive restart.

The shared pilot is real business issue/support routing with independently reviewed references, authorized external resources and a deliberately withheld concept. Use the retained scikit-learn cohort as a development probe, not a substitute for customer outcomes. Run the phase through the actual product and retain negative findings as well as success evidence.

## Required checks and evidence

- Run meaningful unit/contract tests for the changed rules and failure paths; run PostgreSQL integration checks against a disposable explicitly migrated database.
- Run `make check`, `make test`, `npm run build` and `uv build --all-packages` on the actual target branch. Document the supported frontend/package-manager setup from its development guide; app-specific builds do not silently substitute for required repository gates.
- Add/run public API + SDK + browser E2E for the acceptance behavior and a reload/API/database restart check where relevant. Opt-in live calls use runtime credentials and measured usage; credential-free CI may use clearly marked fixtures.
- Fill [PHASE-EVIDENCE-TEMPLATE](PHASE-EVIDENCE-TEMPLATE.md) with commit, environment, commands, results, IDs/hashes, source/label authorization, coverage and limitations. Do not retain tokens, customer secrets or unnecessary personal data.
- Mark COMPLETE only when all phase criteria and prerequisite gates pass. A pre-existing failed check is recorded and repaired or remains a named blocker; it is not a passing-release claim. Preserve independent quality/business gates even when engineering tests pass.

## Scope limits and risks

Do not turn this phase into automatic promotion, model-weight retraining or every environment feature at once. A failed improvement evaluation is a successful safety result but does not close the learned-improvement business proof.

## Handoff

Provide the reviewed commit/PRs, migrations and rollback instructions, public contract changes, UI routes, persisted proof artifact references, actual check results and remaining blockers. Update phase status in README only with linked evidence; never copy planned/sample figures into measured product metrics.
