# Phase 10 — Complete Product Experience & SaaS Operational Platform

Status: **planned, not audited complete**. Sequence: 10/10. Release status: no release or SaaS-readiness claim.

## Outcome and entry gate

Complete Product Experience & SaaS Operational Platform must be a persisted vertical slice that a real business operator can use through the public API, SDK and actual product UI.

**Depends on:** Phase 09 gate evidence accepted; retain every preceding invariant. See README for scoped exception handling.

**Existing ticket mapping:** OC-002, OC-010–014, OC-019, OC-034, OC-037–038; new scoped SaaS tickets required. Preserve OC identifiers; draft scoped child tickets rather than renumbering the backlog.

Read [README](README.md) and [agent handoff](AGENT-HANDOFF.md) before implementation. Follow repository AGENTS.md and the canonical specification. This document specifies intended behavior; an agent must verify every current-state claim against its chosen commit.

## Audit first

Audit the chosen frontend, control plane, engine, deployed network boundary, identity system, usage and all required check/build jobs. Resolve the duplicate Next.js/portal application ownership through a reviewed decision rather than maintaining two incomplete products.
The challenge passed browser checks and focused tests but failed broader checks/build prerequisites. It was a localhost experiment, not a hosted tenant-security or launch proof. The older v0.1 exclusions remain valid for that release; the user's SaaS request adds a later productization scope, not a silent relabeling of Genesis.

Produce an exists/wired/simulated/broken/missing matrix with file, route, migration and test evidence. Do not spend the phase reimplementing working behavior. Review architectural/API/schema changes using the repository RFC process before landing them.

## Ordered implementation slices

1. Select one supported product frontend and canonical service/API ownership. Remove dead navigation or clearly identify unavailable future features. Complete onboarding, loading/error/empty/retry states, accessibility, responsive layout and reconnect behavior across the full lifecycle.
2. Expose project Overview/Data/Decisions/Evolution/Knowledge/Runs/Monitor/Analytics/Audit/Settings plus supported Capabilities/Integrations. Add workspace Projects/Activity/Providers/Usage/Audit/Settings. Chat uses scoped existing tools and deterministic analytics; it must not fabricate metric answers.
3. Harden hosted identity: validated token audience/issuer/expiry, invitations/membership, scoped service keys, minimum owner/operator/reviewer/read-only roles, credential rotation, session revocation and environment separation. Enforce tenancy on DB/file/jobs/events/cache/vector/export paths and privileged support access.
4. Implement encrypted runtime secrets or a selected secret manager with workspace/project/environment grants, safe test/rotation and no returned plaintext. Bound egress, redirects and SSRF for customer-configured endpoints; apply upload limits, rate/concurrency/usage quotas and abuse handling before external access.
5. Build a durable usage ledger and plan entitlements independent of UI. For a paid hosted offering implement billing adapter checkout/portal/webhook verification, event deduplication, lifecycle reconciliation and explicit limits. Store references, not payment data. BYOK versus platform-funded inference and partial cost coverage are transparent; sandbox billing is labeled and live-money operations need separate authorization.
6. Provide monitor dashboards/alerts from persisted traces: completion/failures, UNKNOWN/review, actual fast-path/Teacher calls, verification, p50/p95/p99 sample counts and cost coverage. Version comparisons use the same declared cohorts; counterfactual savings are labeled estimates.
7. Produce reproducible containers/deployment manifests, explicit migration step, readiness/liveness, graceful shutdown, safe upgrades and rollback. Keep engine/private services unreachable from public networks except through authorized ingress; select queues/storage only from observed load and recovery needs.
8. Implement automated backups and prove restore into an isolated environment, including tenant boundaries, immutable version/audit continuity and secret re-binding. Define retention/export/deletion processes, incident response, on-call runbooks, dependency/security scanning and support ownership.
9. Agree pilot SLOs and capacity before testing: proposed 99.9% monthly authorized API availability, RPO ≤24h and RTO ≤4h; benchmark agreed tenant/concurrency/event sizes and provider outage scenarios. These are targets, not achieved promises; report measured results and cost limits.
10. Run a named design-partner business pilot on authorized data using the entire UI flow, at least two tenants and one verified integration. Record human time, routing quality, review workload, retained quality, actual economics and operational failures over a declared period.
11. Close all required clean-install/migration/test/build/security/E2E gates on the reviewed commit. Prepare launch/rollback and support documentation. Deployment/publication is a separate explicit final authorization after evidence is reviewable.

Each numbered slice includes domain/service, persistence when required, public API, typed SDK, actual UI, errors/events and meaningful verification. Keep intermediate commits runnable. Work in bounded PRs; do not deliver only backend scaffolding and call the phase complete.

## Contracts, persistence and observable behavior

WorkspaceMembership/Role, ScopedServiceKey, SecretReference, PlanEntitlement, UsageLedgerEntry, BillingEvent/Subscription, Notification and DeploymentHealth need typed contracts plus migrations where applicable. SaaS transport/identity/billing stay outside Core domain inference.
Events: membership.changed, credential.rotated, quota.exceeded, billing.event_processed, backup.completed/restore_verified and security.access_denied. Billing state cannot bypass safety approval or rewrite history.
Create scoped tickets/RFCs for hosted auth, billing, quotas and deployment after reviewing selected implementation. No blanket infrastructure rewrite is authorized by this document.

Schema changes use explicit Alembic migrations, including upgrades from existing data. Core owns deterministic rules/ports; providers/adapters cannot write ontology. UI/CLI access public HTTP SDKs. Secrets, raw sensitive payloads and upstream credential-bearing errors stay out of source, fixtures, logs and events.

## Business proof and exit criteria

- A new business user completes create → ingest → decide → inspect UNKNOWN → propose → evaluate → approve → version → act/verify → measure entirely through supported UI/API.
- Independent tenants and roles pass negative access tests at every public/private boundary, including jobs, reports, live events, exports and guessed IDs.
- Quotas, canceled subscriptions and duplicate/out-of-order billing webhooks produce deterministic recoverable state; financial failures never cause uncontrolled provider spend or erase customer records.
- Restore drill meets declared RPO/RTO with actual evidence; upgrade from existing production-like data preserves history and rolls back safely.
- Capacity/failure tests establish the declared SLO envelope, graceful behavior on provider outages and realistic measured costs; no unlimited-scaling claim.
- A business pilot meets predeclared quality/operational gates or remains a limited human-reviewed pilot. External access/paid launch is blocked by unresolved tenant/security/recovery/release failures.
- All required checks pass on the intended reviewed commit; mocks used in CI are disclosed and do not substitute for the real business pilot.

The shared pilot is real business issue/support routing with independently reviewed references, authorized external resources and a deliberately withheld concept. Use the retained scikit-learn cohort as a development probe, not a substitute for customer outcomes. Run the phase through the actual product and retain negative findings as well as success evidence.

## Required checks and evidence

- Run meaningful unit/contract tests for the changed rules and failure paths; run PostgreSQL integration checks against a disposable explicitly migrated database.
- Run `make check`, `make test`, `npm run build` and `uv build --all-packages` on the actual target branch. Document the supported frontend/package-manager setup from its development guide; app-specific builds do not silently substitute for required repository gates.
- Add/run public API + SDK + browser E2E for the acceptance behavior and a reload/API/database restart check where relevant. Opt-in live calls use runtime credentials and measured usage; credential-free CI may use clearly marked fixtures.
- Fill [PHASE-EVIDENCE-TEMPLATE](PHASE-EVIDENCE-TEMPLATE.md) with commit, environment, commands, results, IDs/hashes, source/label authorization, coverage and limitations. Do not retain tokens, customer secrets or unnecessary personal data.
- Mark COMPLETE only when all phase criteria and prerequisite gates pass. A pre-existing failed check is recorded and repaired or remains a named blocker; it is not a passing-release claim. Preserve independent quality/business gates even when engineering tests pass.

## Scope limits and risks

Marketplace, enterprise SSO, multi-region, robotics, every MCP tool and arbitrary integration builders remain separate expansion phases. Hosted SaaS readiness does require practical tenant isolation, quotas, financial correctness if paid, recovery and support; these cannot be deferred behind a polished dashboard.

## Handoff

Provide the reviewed commit/PRs, migrations and rollback instructions, public contract changes, UI routes, persisted proof artifact references, actual check results and remaining blockers. Update phase status in README only with linked evidence; never copy planned/sample figures into measured product metrics.
