# Phase 04 — Runs, Traces, Failure Semantics & Audit Truth

Status: **planned, not audited complete**. Sequence: 4/10. Release status: no release or SaaS-readiness claim.

## Outcome and entry gate

Runs, Traces, Failure Semantics & Audit Truth must be a persisted vertical slice that a real business operator can use through the public API, SDK and actual product UI.

**Depends on:** Phase 03 gate evidence accepted; retain every preceding invariant. See README for scoped exception handling.

**Existing ticket mapping:** OC-003, OC-010, OC-016, OC-033, OC-037. Preserve OC identifiers; draft scoped child tickets rather than renumbering the backlog.

Read [README](README.md) and [agent handoff](AGENT-HANDOFF.md) before implementation. Follow repository AGENTS.md and the canonical specification. This document specifies intended behavior; an agent must verify every current-state claim against its chosen commit.

## Audit first

Inspect run persistence, project audit reader/writers, reviews, provider usage and analytics. On the portal branch inspect control-plane forwarding and error mappings.
The challenge reproduced core audit HTTP 400 after cluster events while control audit remained readable; 429 became generic portal 502. Do not rewrite append-only events to hide the incompatibility.

Produce an exists/wired/simulated/broken/missing matrix with file, route, migration and test evidence. Do not spend the phase reimplementing working behavior. Review architectural/API/schema changes using the repository RFC process before landing them.

## Ordered implementation slices

1. Define a versioned event envelope with tenant/project, event ID/sequence, actor identity/type, timestamp, correlation/causation, subject and typed payload. Inventory every writer and reader before changing schema.
2. Add compatible decoding for historical payload variants and additive migrations where required. Preserve original stored bytes; represent an unknown historical schema explicitly and emit a diagnostic rather than failing an entire history page.
3. Persist run lifecycle and provider attempts, including failed/cancelled/incomplete calls. Separate attempted requests from completed decisions and link source/state/spec/ontology/policy/provider identities.
4. Preserve typed errors across API, SDK and control plane: rate limit, auth, unavailable model, timeout, invalid provider output, authorization, execution and verification failures. Expose retry-after when safe; keep upstream content and secrets out of errors.
5. Consolidate usage across decisions, embeddings, discovery, Teacher, replay and actions. Store actual currency/source, missing usage and reconciliation adjustments; costs unavailable are not zero. Avoid counting retries as new source cases.
6. Implement cursor-based scoped history and resumable event consumption where needed. Durable database history is authoritative; request logs and live notifications are not an audit substitute.
7. Deliver a run timeline and audit inspector with linked records and versions. Every displayed span must correspond to a persisted stage; future execution stages appear only when supported.
8. Restrict access to payloads by role, redact routine traces and record privileged configuration/review/export changes. Preserve safe audit metadata under the declared data-retention policy.

Each numbered slice includes domain/service, persistence when required, public API, typed SDK, actual UI, errors/events and meaningful verification. Keep intermediate commits runnable. Work in bounded PRs; do not deliver only backend scaffolding and call the phase complete.

## Contracts, persistence and observable behavior

RunLifecycle, ProviderAttempt, UsageRecord, TraceLink, AuditEnvelope and safe ErrorDescriptor. Reads expose schema version, stable pagination and actual failure state.
Events cover configuration changes, ingestion, decision/supervision, evidence/candidates, evaluation, approval, activation and later execution/verification. Attribution comes from authenticated principal/system service identity; request-provided actor strings grant no authority.

Schema changes use explicit Alembic migrations, including upgrades from existing data. Core owns deterministic rules/ports; providers/adapters cannot write ontology. UI/CLI access public HTTP SDKs. Secrets, raw sensitive payloads and upstream credential-bearing errors stay out of source, fixtures, logs and events.

## Business proof and exit criteria

- Every audit writer used by the real workflow is readable, including legacy and newly generated cluster/discovery records; one incompatible event cannot blank the page.
- A 429 can be inspected as rate limiting through SDK and portal; timeouts/403/malformed output stay distinct and never become UNKNOWN evidence automatically.
- A user reconstructs one successful and one failed run without server logs, including exact versions and attempt chain.
- Hand-computed usage fixtures cover retries, missing prices, mixed currencies, failed calls and discovery/embedding costs; rollups disclose coverage.
- Audit history resists UPDATE/DELETE, survives restart and denies unauthorized/cross-tenant access.
- Pagination/event resume handles equal timestamps, reconnects and retained cursors without skipping records.

The shared pilot is real business issue/support routing with independently reviewed references, authorized external resources and a deliberately withheld concept. Use the retained scikit-learn cohort as a development probe, not a substitute for customer outcomes. Run the phase through the actual product and retain negative findings as well as success evidence.

## Required checks and evidence

- Run meaningful unit/contract tests for the changed rules and failure paths; run PostgreSQL integration checks against a disposable explicitly migrated database.
- Run `make check`, `make test`, `npm run build` and `uv build --all-packages` on the actual target branch. Document the supported frontend/package-manager setup from its development guide; app-specific builds do not silently substitute for required repository gates.
- Add/run public API + SDK + browser E2E for the acceptance behavior and a reload/API/database restart check where relevant. Opt-in live calls use runtime credentials and measured usage; credential-free CI may use clearly marked fixtures.
- Fill [PHASE-EVIDENCE-TEMPLATE](PHASE-EVIDENCE-TEMPLATE.md) with commit, environment, commands, results, IDs/hashes, source/label authorization, coverage and limitations. Do not retain tokens, customer secrets or unnecessary personal data.
- Mark COMPLETE only when all phase criteria and prerequisite gates pass. A pre-existing failed check is recorded and repaired or remains a named blocker; it is not a passing-release claim. Preserve independent quality/business gates even when engineering tests pass.

## Scope limits and risks

Do not erase broken audit records or recalculate historical outcomes in place. A tracing vendor is optional; correctness and scoped durable queries come first.

## Handoff

Provide the reviewed commit/PRs, migrations and rollback instructions, public contract changes, UI routes, persisted proof artifact references, actual check results and remaining blockers. Update phase status in README only with linked evidence; never copy planned/sample figures into measured product metrics.
