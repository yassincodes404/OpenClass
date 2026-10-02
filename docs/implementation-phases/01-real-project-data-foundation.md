# Phase 01 — Real Project, Data & Persistence Foundation

Status: **planned, not audited complete**. Sequence: 1/10. Release status: no release or SaaS-readiness claim.

## Outcome and entry gate

Real Project, Data & Persistence Foundation must be a persisted vertical slice that a real business operator can use through the public API, SDK and actual product UI.

**Depends on:** Phase 0 execution checklist in README and AGENT-HANDOFF; no earlier numbered phase.

**Existing ticket mapping:** OC-001, OC-010, OC-033, OC-034, OC-036. Preserve OC identifiers; draft scoped child tickets rather than renumbering the backlog.

Read [README](README.md) and [agent handoff](AGENT-HANDOFF.md) before implementation. Follow repository AGENTS.md and the canonical specification. This document specifies intended behavior; an agent must verify every current-state claim against its chosen commit.

## Audit first

Trace project CRUD, authenticated ingress, webhook receipts, raw events, normalized state and tenant lookup. Inspect packages/core/openclass_core/projects.py, packages/server/openclass_server/api/projects.py, persistence/project_repository.py, security.py and integration_adapters.py. On the portal branch also trace services/control-plane and apps/portal; do not assume those directories exist on this checkout.
The challenge proved real ingestion but encountered HTTP 413. Existing authentication, idempotency and atomic ingestion are assets to verify and reuse, not reasons to rebuild ingress.

Produce an exists/wired/simulated/broken/missing matrix with file, route, migration and test evidence. Do not spend the phase reimplementing working behavior. Review architectural/API/schema changes using the repository RFC process before landing them.

## Ordered implementation slices

1. Establish the reviewed target commit and reproducible locked installation. Repair CI failures on that branch, including absent provider behavior and frontend package resolution. Record explicit simulated test configuration separately from customer runtime configuration.
2. Define Workspace → Project → SourceConnection → RawEvent → StateSnapshot ownership. Authenticate the browser and API; resolve workspace membership and project permission on every read/write, including the engine behind a control plane. Prevent direct unauthenticated engine access in hosted mode.
3. Migrate only missing persistence. Raw events retain immutable source identity, received/source timestamps, content hash, schema version and provenance. Normalization creates an immutable derived snapshot with transformer version and raw-event reference; corrections create new records.
4. Specify idempotency scope, duplicate receipt behavior and changed-payload conflict. Commit receipt, raw event, derived state and audit atomically; prove concurrent retries and restart recovery.
5. Implement CSV/JSON import and authenticated webhook ingestion through the same source service. Enforce request bytes, item bytes/count, parsing bounds and tenant storage/rate limits. Define partial-batch semantics with per-item receipts and resumable cursors; the SDK batches by bytes as well as count.
6. Build create-project → connect/import → inspect-event → inspect-state screens. Show source health, rejected rows and retry controls. Public typed API/SDK contracts expose actual persisted IDs and pagination.
7. Document remote-data handling and retention. Keep payloads out of routine logs. Define deletion/redaction obligations separately from immutable decision/audit metadata; do not promise indefinite retention of personal data.

Each numbered slice includes domain/service, persistence when required, public API, typed SDK, actual UI, errors/events and meaningful verification. Keep intermediate commits runnable. Work in bounded PRs; do not deliver only backend scaffolding and call the phase complete.

## Contracts, persistence and observable behavior

Workspace, Project, SourceConnection, IngestRequest/Receipt, RawEvent, StateSnapshot and SourceProvenance are typed contracts. Proposed API behaviors: create/list/get projects; register/test a source; ingest events/batches; fetch receipt, event and derived state. Choose compatible route names after auditing existing APIs.
Events include project.created, source.configured, ingestion.accepted/rejected and state.created. Errors distinguish authentication, permission, byte limit, schema rejection, idempotency conflict and unavailable storage. Tenant ownership is server-enforced, never trusted from request JSON.

Schema changes use explicit Alembic migrations, including upgrades from existing data. Core owns deterministic rules/ports; providers/adapters cannot write ontology. UI/CLI access public HTTP SDKs. Secrets, raw sensitive payloads and upstream credential-bearing errors stay out of source, fixtures, logs and events.

## Business proof and exit criteria

- Two unrelated authenticated workspaces cannot enumerate or fetch each other's projects, raw events, states, receipts or files, including guessed IDs and direct engine requests.
- Import the frozen real issue cohort and a separately authorized business export; hashes and source identities match retained inputs after API/database restart.
- Exercise byte-boundary batches, malformed CSV, interrupted upload, duplicate delivery, changed-payload replay and concurrent receipt creation. Accepted rows commit once; rejected rows remain inspectable.
- A fresh migrated PostgreSQL install and an upgrade from existing data both work without create_all or history recreation.
- A user completes the entire import workflow through the actual UI and can inspect immutable source-to-state lineage.

The shared pilot is real business issue/support routing with independently reviewed references, authorized external resources and a deliberately withheld concept. Use the retained scikit-learn cohort as a development probe, not a substitute for customer outcomes. Run the phase through the actual product and retain negative findings as well as success evidence.

## Required checks and evidence

- Run meaningful unit/contract tests for the changed rules and failure paths; run PostgreSQL integration checks against a disposable explicitly migrated database.
- Run `make check`, `make test`, `npm run build` and `uv build --all-packages` on the actual target branch. Document the supported frontend/package-manager setup from its development guide; app-specific builds do not silently substitute for required repository gates.
- Add/run public API + SDK + browser E2E for the acceptance behavior and a reload/API/database restart check where relevant. Opt-in live calls use runtime credentials and measured usage; credential-free CI may use clearly marked fixtures.
- Fill [PHASE-EVIDENCE-TEMPLATE](PHASE-EVIDENCE-TEMPLATE.md) with commit, environment, commands, results, IDs/hashes, source/label authorization, coverage and limitations. Do not retain tokens, customer secrets or unnecessary personal data.
- Mark COMPLETE only when all phase criteria and prerequisite gates pass. A pre-existing failed check is recorded and repaired or remains a named blocker; it is not a passing-release claim. Preserve independent quality/business gates even when engineering tests pass.

## Scope limits and risks

No new queue, object store, vector service or tenant database is mandatory here. Select infrastructure only after measuring limits. This phase does not claim inference quality, learned behavior or paid-service readiness.

## Handoff

Provide the reviewed commit/PRs, migrations and rollback instructions, public contract changes, UI routes, persisted proof artifact references, actual check results and remaining blockers. Update phase status in README only with linked evidence; never copy planned/sample figures into measured product metrics.
