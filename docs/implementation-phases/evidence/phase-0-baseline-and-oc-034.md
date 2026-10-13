# Phase 0 — baseline, target branch and OC-034 — evidence record

Copied from [PHASE-EVIDENCE-TEMPLATE](../PHASE-EVIDENCE-TEMPLATE.md). No secrets; no
publication performed.

## Identity and scope

- Phase, status, date and responsible reviewer: Phase 0 (pre-Phase-01 gate) and
  OC-034, **engineering-complete; final gate is the merge of PR #20 into main**,
  2026-10-02, reviewer Yassin Tarek Mohamed (merge approval pending).
- Branch, reviewed commit, worktree and build identity: branch `oc-034-ci-baseline`
  (= `origin/feat/portal-phase-10` at `d539862` + program/docs/OC-034 commits),
  CI-green reviewed commit `c6545bf`, worktree `/home/yassin/Projects/OpenClass`
  (single). Toolchain: pnpm 11.24.0 (pinned via `packageManager`), Node 22 (CI) /
  26 (local), uv 0.11.0, Python 3.12.
- Existing tickets / scoped child tickets / RFC and decision: OC-034 (this gate);
  program adoption commit `f7228d6` (cherry-picked from
  `experiment/jev-characterization` at `c14a954`) added
  `docs/implementation-phases/`, `application-proof-program.md`, OC-034–039.
  Phase 0 decision (required by AGENT-HANDOFF): **target branch = the
  `feat/portal-phase-10` line, merged to main through PR #20**; `apps/web` vs
  `apps/portal` ownership resolution is deferred to Phase 10 as its brief states.
- Prerequisite evidence links and unresolved blockers: none (first gate). The
  retained challenge evidence (`artifacts/application-proofs/scikit-learn-2026-10-02/`,
  produced on `d539862` + the unmerged `provider-wiring.patch`) is referenced but
  **not** part of this gate; the patch remains unapplied, reserved for Phase 02 review.
- Intended public behavior; explicit scope exclusions: green locked CI baseline with
  credential-free python/compose runs. Exclusions: no application ownership decision,
  no live-provider wiring, no migrations, no deployment/publication/release.

## Fresh audit

Phase-01-scope audit matrix on the target branch (drives the Phase 01 entry plan;
status vocabulary per AGENT-HANDOFF):

| Requirement                                                      | Status                                                                                                            | Evidence                                                                                                                                                                                                                                                                                                   | Planned repair (Phase 01)                                                                                                             |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Engine behind control plane is not anonymously writable/readable | **missing**                                                                                                       | `packages/server/openclass_server/main.py` mounts 11 routers with no auth dependency; `security.py` is only secret-scanning; only webhook routes check an integration token (`api/integrations.py:112`); `GET /api/v1/projects` lists all projects unscoped; control-plane `engine.ts` sends no credential | Engine-level service auth + workspace-membership enforcement on every engine route (negative tests: guessed IDs, direct engine calls) |
| Workspace→Project ownership                                      | **wired** (control-plane)                                                                                         | `services/control-plane/migrations/0001_identity.sql`/`0002_projects.sql` (`control_workspaces`, memberships with roles, `control_projects.engine_project_id`); membership checked in project.service `requireRole`                                                                                        | Keep; extend membership checks to engine side                                                                                         |
| SourceConnection as first-class entity                           | **missing** (engine-partial)                                                                                      | Engine `project_integrations` (`0009_integrations.py`) exists; no control-plane proxy, no portal connect screen                                                                                                                                                                                            | Control-plane integrations surface + portal connect/import flow                                                                       |
| Raw event immutability                                           | **wired, incomplete columns**                                                                                     | `0005_raw_events.py` + DB triggers `openclass_immutable` (0010) on UPDATE/DELETE; `0012_raw_event_content_hash.py` adds content hash; code has no update/delete path                                                                                                                                       | Add received/source timestamp split, schema_version, provenance columns via new migration                                             |
| Atomic receipt+event+audit commit                                | **wired webhooks only**                                                                                           | `integration_repository.py:ingest_webhook` commits receipt+event+audit in one transaction; direct `ingest_event`/batch commits per event with **no engine audit row** (`projects.py:520-586`)                                                                                                              | One transaction + audit for direct/batch ingestion                                                                                    |
| StateSnapshot persistence                                        | **missing**                                                                                                       | Only in-memory `compile_state()` (`decision.py:71`); no `state_snapshots` table in 16 engine migrations                                                                                                                                                                                                    | Persist state snapshots with transformer version + raw-event lineage                                                                  |
| CSV/JSON import through one source service                       | **simulated**                                                                                                     | Portal "CSV" splits lines (`ingestion-pages.tsx:63-79`); no parser anywhere; byte limits absent (Express 100KB implicit; uvicorn none); no resumable cursors                                                                                                                                               | Real CSV/JSON parsing, byte limits, partial-batch receipts, cursors                                                                   |
| Ingestion limits + idempotency + per-item receipts               | **wired**                                                                                                         | 413 >10k chars / >500 items; 207 per-item receipts; `0011_idempotency_keys`; control-plane mirrors limits; quota is a simulated demo cap                                                                                                                                                                   | Real tenant storage accounting replaces demo cap                                                                                      |
| Audit trail (engine + control-plane)                             | **wired, disjoint**                                                                                               | Engine `audit_events` (0004, immutable via 0010) written transactionally; control-plane `control_audit_events` separate DB; no linkage; direct ingestion writes no engine audit                                                                                                                            | Unify provenance; engine audit on all ingestion paths                                                                                 |
| Portal screens (create-project → data → inspect)                 | **wired** for project/classify/data/observations; **missing** connect/SourceConnection and state-snapshot lineage | `apps/portal/src/portal.tsx:63-90` route table; `projects.tsx`, `ingestion-pages.tsx`, `decision-pages.tsx`                                                                                                                                                                                                | Add connect/import + state inspection screens in Phase 01                                                                             |

The load-bearing finding: **the FastAPI engine enforces no authentication on any
route** — exactly the "a secured UI cannot protect an exposed unauthenticated
backend" failure AGENT-HANDOFF warns about. Phase 01 slice 2 exists to fix it.

## Implementation and persistence

- Domain contracts/services and public API/SDK compatibility: no contracts added.
  One behavior repair: `resolve_decision_provider` previously treated **any**
  unknown provider override as laya (fail-open); it now raises for names outside
  `{mock, jev, laya}`, `/api/v1/providers/test` reports unsupported providers, and
  decision runs map a stored bad override to a typed 422 with no side effects.
  This restores the phase-7 contract encoded in
  `test_provider_test_unsupported_provider_is_safe`.
- New/changed migrations: none. Fresh-install and existing-data upgrade verified by
  the Compose migrate path (fresh volume) and by postgres-marked tests running
  `alembic upgrade head` on a disposable database (0001→0016).
- Transaction/ownership/idempotency/concurrency rules: unchanged by this gate.
- Immutable version/audit/source handling: unchanged; immutability triggers verified
  present (0010) during audit.
- Rollback/reconciliation: `docker compose down --volumes` after smoke; no persisted
  external state touched.
- Product UI routes and actual user steps: not exercised for new behavior; existing
  suites (`tests/web`, 50 specs) cover apps/web routes.

## Protocol frozen before live execution

NOT_APPLICABLE: this gate ran the simulated mock provider only; no live provider,
operator authorization, dataset, or budget was used. The retained challenge
artifacts remain frozen separately under `artifacts/application-proofs/`.

## Actual measured results

CI on the reviewed commit `c6545bf` (run 37051177668, PR #20):

| Job      | Outcome      | Notes                                                                                                                                               |
| -------- | ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| python   | pass (2m0s)  | ruff, ruff format, mypy strict, pytest (incl. 9 postgres-marked on service PostgreSQL), `uv build --all-packages`, `release.py` metadata validation |
| web      | pass (3m13s) | pnpm frozen install, prettier, typecheck, vitest, Next build, 50 Playwright specs, pnpm audit --prod                                                |
| compose  | pass (54s)   | migrated pgvector stack, `/health/ready`, credential-free mock classify                                                                             |
| security | pass (18s)   | pip-audit on exported requirements                                                                                                                  |

Failure history (recorded honestly, all on PR #20 before the green run):
run 37048077399 — python failed on 4 environment-dependent tests (they passed only
on a developer machine with a warm laya checkpoint; see repairs below); web failed
on 2 Playwright strict-mode locators. Run 37050004445 — python failed at
`scripts/release.py` (`providers/glm/LICENSE` missing; previously masked because
main's python job died earlier at ruff format). Run 37050413603 — python pass,
web still failing on the strict-mode locator. Run 37051177668 — all green.

Local reproduction (this worktree):

| Check                                                                                   | Outcome                                                                                                                                    |
| --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `make check`                                                                            | pass (after Makefile npm→pnpm alignment)                                                                                                   |
| `make test`                                                                             | 403 passed, 13 skipped                                                                                                                     |
| CI-equivalent env (`OPENCLASS_DECISION_PROVIDER=mock` + disposable migrated PostgreSQL) | 413 passed, 3 skipped (skip: laya in-process guard + live markers)                                                                         |
| `pnpm run format:check` / `typecheck` / `test` / `build`                                | pass (portal, web, control-plane, sdk)                                                                                                     |
| `uv build --all-packages`                                                               | pass                                                                                                                                       |
| `uv run python scripts/release.py`                                                      | pass — "Workspace versions agree: 0.0.1. No publication performed."                                                                        |
| Full Playwright suite (system chromium)                                                 | 50 passed                                                                                                                                  |
| Fresh-volume Compose smoke                                                              | pass — ready → `openclass init` → `openclass classify "Cancel my plan"` returned a `simulated: true` mock decision; `down --volumes` after |

Environment-honesty repairs made so CI is not merely made green: python job runs
`OPENCLASS_DECISION_PROVIDER=mock` (same as compose); the laya provenance test
skips with a stated reason when the in-process engine cannot load; the postgres
restart test asserts the phase-5 batch contract (207 with per-item 201 receipts)
instead of a pre-phase-5 list shape; `providers/status` asserts the configured
default rather than a hardcoded provider name.

## Required checks

| Command/check                             | Target/configuration                                                             | Actual outcome                                                                                            | Log/artifact reference                                  |
| ----------------------------------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| make check                                | local worktree, pnpm 11.24.0                                                     | pass                                                                                                      | this worktree, commit `c6545bf`                         |
| make test                                 | local sqlite + alembic tmp DBs                                                   | 403 passed / 13 skipped                                                                                   | same                                                    |
| npm run build                             | **pnpm run build** (workspace migrated to pnpm)                                  | pass, all four packages                                                                                   | CI web job                                              |
| uv build --all-packages                   | uv 0.11.0                                                                        | pass                                                                                                      | CI python job                                           |
| Migrated disposable PostgreSQL            | pgvector:pg17 @ 127.0.0.1:55432                                                  | 9 postgres-marked tests pass on CI service DB; 4 passed locally                                           | CI python job; local run                                |
| API + SDK + browser E2E                   | 50 Playwright specs against next dev                                             | 50 passed (CI + local)                                                                                    | CI web job run 37051177668                              |
| Reload/API/database restart               | raw-events postgres restart test (fresh app instances over one DB)               | pass                                                                                                      | CI python job                                           |
| Isolation/permission negative checks      | cross-classifier 404s (existing suites)                                          | pass within existing coverage; **engine-level isolation not yet enforceable (no auth)** — Phase 01 repair | `test_reviews.py`, `test_projects_*`                    |
| Phase-specific failure/concurrency checks | webhook duplicate-delivery IntegrityError path; provider failure 502 persistence | pass (existing suites)                                                                                    | `test_integrations_api.py`, `test_provider_protocol.py` |

## Reconstruction proof

- Identities: PR #20 = `yassincodes404/OpenClass` branch `oc-034-ci-baseline`;
  green commit `c6545bf`; program commit `f7228d6`; pre-carry commit `c14a954` on
  `experiment/jev-characterization`.
- Restart procedure: `docker compose down --volumes && OPENCLASS_PORT=7432
OPENCLASS_DB_PORT=55433 OPENCLASS_DECISION_PROVIDER=mock docker compose up
--build -d --wait` then ready/init/classify — reproduced twice (second run after
  discarding the stale host volume that caused a benign 409 on first init).
- Tenant/role boundaries: control-plane membership tests pass; engine-side
  enforcement is absent by audit finding — recorded as the Phase 01 entry blocker,
  not silently exempted.
- Logs/screenshots credential-free: mock provider only; challenge artifacts were
  secret-scanned before commitment (only the documented local
  `owner@acme.openclass.test` fixture appears, already committed in seed scripts).

## Exit review

- OC-034 acceptance: clean locked installs — **PASS** (`pnpm install
--frozen-lockfile` locally and in CI); all CI jobs pass on the reviewed target
  commit including disposable migrated PostgreSQL and Compose — **PASS** on
  `c6545bf` (run 37051177668), with the merge-to-main run as final confirmation;
  no live credentials or publication — **PASS** (mock provider; release.py performs
  validation only).
- Engineering gate versus live quality/business gate: engineering gate only. No
  model-quality, availability, or business claim is made or implied.
- Unsupported/incomplete behavior and operational risk: engine auth absent
  (Phase 01); provider-wiring patch unreviewed (Phase 02); `apps/web` vs
  `apps/portal` duplication unresolved (Phase 10 decision); local
  `OPENCLASS_DB_PORT`/`OPENCLASS_PORT` overrides needed on this host because the
  legacy phase-10 stack still occupies 5432/7331.
- Reviewer decision: merge approval for PR #20 pending (repository owner).
- Next phase prerequisites (Phase 01 entry plan, from the audit matrix):
  1. Engine service authentication + workspace-membership enforcement on every
     route, with negative tests for direct engine access and guessed IDs.
  2. Raw-event provenance columns (received/source timestamps, schema_version,
     source identity) via a new Alembic migration; keep triggers append-only.
  3. Single source service for direct/batch/webhook ingestion: one transaction for
     receipt+event+audit, real CSV/JSON parsing, byte limits, resumable cursors.
  4. Persist StateSnapshot with transformer version and raw-event lineage.
  5. Control-plane integrations proxy + portal connect/import and state-inspection
     screens; then the Phase 01 evidence record.
