# Takeover completion ledger

Date: 2026-10-15. This is an evidence ledger, not a completion claim.

## Recovered state

- Checkout: `abdelhamid-khaled/fix/checkpoint-revision-cas-and-lease-fencing`.
- HEAD and independently queried remote main: `bfc62161b98efb8ad845c874f29b44b9ba50ce8d`.
- Seven modified files and untracked migration `0028` were preserved. No staged
  changes, reset, cleanup, or recreation of the inherited work occurred.
- Git author configuration and authenticated GitHub identity were verified.
- PR #57 merged at the baseline. Its Python, web, Compose, and security checks
  passed. Main CI run `38722310960` also passed at that baseline.
- No checkpoint PR was open at takeover. PR numbers must be assigned by GitHub.
- Docker CLI exists, but the Linux engine was unavailable at initial inspection.
- Inherited local check:
  `uv run pytest -q tests/integration/test_decision_service_runs.py -m "not postgres and not live"`
  exited 0: **15 passed, 32 warnings**, 29.47 seconds. This is SQLite evidence,
  not PostgreSQL or vector functionality evidence.
- Previous PostgreSQL run recovered from the previous agent's task log:
  `C:\Users\NITRO\.gemini\antigravity\brain\804368c7-9eca-4cd3-a9de-6c53884e445c\.system_generated\tasks\task-2238.log`
  (lines 420–431), exit 1: **2 failed, 1 passed, 1 warning**, 12.36 seconds.
  Both concurrency tests failed from cross-event-loop asyncpg use. A later
  single-event-loop refactor was never successfully rerun against PostgreSQL.
- The `UNAVAILABLE (code 503)` was an agent-service transcript error at
  2026-10-15 11:21:21 UTC, not database output. A separate zero-output task was
  subsequently cancelled; its cause was not proven.
- Confirmed historical fake extension paths,
  `C:\Users\NITRO\scoop\apps\postgresql\current\share\extension\vector.control`
  and `vector--0.1.0.sql`, are now absent, including the physical junction target.
  The temporary `openclass_pg_verify_0028` cluster is also absent. No deletion
  was necessary. The existing PostgreSQL 15 service on port 5432 is preserved.

## Execution order and acceptance

1. Recover interrupted PostgreSQL output and identify any fake extension files.
   Remove only confirmed temporary stubs. Preserve genuine installations.
2. Finish checkpoint revision CAS, transaction-bound claimed snapshots, actual
   paused-node approval validation, renewable leases, authenticated privileged
   recovery, and fencing of superseded writes. Prove both reported schedules
   deterministically against SQLite and separate PostgreSQL repositories.
3. Verify real pgvector and migrations through `0028`. Independently review,
   publish a focused PR, pass required CI, merge, and verify main.
4. Implement the original backlog in dependency order. Read original criteria,
   preserve ticket identities, and record evidence instead of narrowing scope.
5. Implement the landing redesign, inspect desktop/tablet/mobile behavior and
   reduced motion, and capture new screenshots and an interaction recording.
6. Review and deliver focused increments. Keep non-verified requirements open.

## Backlog completion status

All original acceptance criteria remain authoritative in
`04-executable-backlog.md`, reconciled against commit `7158104`.

| Item      | Takeover status | Remaining acceptance / evidence                                       |
| --------- | --------------- | --------------------------------------------------------------------- |
| OC-BG-012 | PARTIAL         | Complete replay, original gates and durable per-example outcomes.     |
| OC-BG-013 | PARTIAL         | Complete transactional promotion, history, and rollback requirements. |
| OC-BG-014 | PARTIAL         | Unify candidate domain, persistence, and lifecycle across tracks.     |
| OC-BG-016 | PARTIAL         | Typed compiler, schemas, persisted snapshots, provenance, budgets.    |
| OC-BG-017 | PARTIAL         | Data-driven supervision and verified calibrated profiles.             |
| OC-BG-018 | PARTIAL         | Runtime applicability gates and independent verifiers.                |
| OC-BG-020 | PARTIAL         | Continuous supervision sampling, triggers, and budgets.               |
| OC-BG-021 | PARTIAL         | Integrate the ten-layer Teacher protocol into runtime paths.          |
| OC-BG-022 | PARTIAL         | Real embeddings, cache identity, and PostgreSQL vector indexing.      |
| OC-BG-024 | PARTIAL         | Control-plane idempotency hashing, expiry, and concurrency.           |
| OC-BG-025 | PARTIAL         | Atomic units of work and evidence uniqueness.                         |
| OC-BG-026 | PARTIAL         | Executed migrations and append-only database protections.             |
| OC-BG-027 | PARTIAL         | Frontend feature parity and consistent project workflows.             |
| OC-BG-029 | PARTIAL         | Provider/model costs and end-to-end correlation.                      |
| OC-BG-030 | PARTIAL         | Complete pagination and SQL aggregation.                              |
| OC-BG-032 | PARTIAL         | Transactional outbound delivery, retries, vendor verification.        |
| OC-BG-033 | PARTIAL         | Real PostgreSQL and live-backend browser tests.                       |
| OC-BG-034 | PARTIAL         | Full-stack Compose and original build/benchmark criteria.             |
| OC-BG-036 | PARTIAL         | Post-promotion cohort monitoring and rollback behavior.               |

## Checkpoint acceptance gates

- [x] Delayed pre-claim requests cannot replay an older checkpoint.
- [x] Execution uses the atomically claimed snapshot and its actual paused node.
- [x] Default recovery cannot take over a fresh or renewed lease.
- [x] Expired claims recover across restarts; live long calls renew ownership.
- [x] Forced recovery requires trusted authentication, privilege, and rationale.
- [x] Superseded success, failure, release, and lifecycle writes cannot alter state.
- [x] Repeated pauses, cancellation, stale approvals, and request cancellation tested.
- [x] Separate repository instances reproduce schedules on real PostgreSQL.
- [x] Real pgvector version and actual vector operations verified separately.
- [x] Migration upgrade and required repository checks pass.
- [x] Independent review corrections resolved.
- [ ] Focused PR, green CI, merge, and main verification recorded.

## Guarantees to preserve

UNKNOWN is permanent. Predictions are not verified ground truth. Providers cannot
activate ontology changes. Promotion requires evidence, replay evaluation, and
human review. Ontology snapshots, aliases, and audit history remain append-only.
External side effects are not exactly-once merely because database writes are
fenced. Forced recovery and lease expiry can overlap an already sent remote call.

## Current verification evidence

The disposable container `openclass-takeover-pg17-20261015` binds only
`127.0.0.1:55434`. Image: `pgvector/pgvector:pg17`, digest
`sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d`.

| Check                                                                       | Exit / actual result                                                                                                                                                                                                                                                |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `uv run alembic upgrade head` against the disposable database               | 0; queried head is `0028_checkpoint_revision_and_lease_fencing`.                                                                                                                                                                                                    |
| PostgreSQL extension queries                                                | 0; PostgreSQL 17.11, pgvector 0.8.7, `vector` is base type `b`, not domain `d`.                                                                                                                                                                                     |
| Direct vector cosine/arithmetic                                             | 0; orthogonal cosine distance 1; sum `[4,4,4]`.                                                                                                                                                                                                                     |
| `uv run pytest -q tests/integration/test_pgvector_runtime.py`               | First run: 1 failed because asyncpg returns PostgreSQL internal `"char"` as bytes. Assertion query corrected to cast to text. Rerun: 0, **1 passed, 1 warning**, 0.16 seconds. Includes real HNSW index creation and nearest-neighbor ranking in a temporary table. |
| `uv run pytest -q tests/contract/test_python_sdk.py tests/unit/test_cli.py` | 0; **19 passed, 1 warning**, 1.25 seconds.                                                                                                                                                                                                                          |
| `pnpm --filter @openclass/sdk test`                                         | 0; **18 passed, 0 failed, 0 skipped**.                                                                                                                                                                                                                              |
| `uv run mypy -p openclass_sdk -p openclass_cli`                             | 0; 3 source files.                                                                                                                                                                                                                                                  |
| Changed client lint/type/format checks                                      | 0 after Ruff/Prettier formatting corrections.                                                                                                                                                                                                                       |
| `make check`                                                                | 0; Ruff 346 files, mypy 112 source files, workspace TypeScript/format checks; control-plane 86, portal 12, TypeScript SDK 18 tests passed.                                                                                                                          |
| `make test` with the real disposable PostgreSQL URL                         | 0; **645 passed, 7 skipped, 948 warnings**, 230.24 seconds; includes the separate-repository PostgreSQL checkpoint schedules.                                                                                                                                       |
| `uv build --all-packages`                                                   | 0; wheel and source distribution for each of 11 Python workspace packages. No publication.                                                                                                                                                                          |
| `npm run build`                                                             | Initial exit 9: Next.js exhausted local memory with 15 workers. Rerun with `CIRCLE_NODE_TOTAL=3`, `NODE_OPTIONS=--max-old-space-size=1024`, `NEXT_TELEMETRY_DISABLED=1`: exit 0; control-plane, portal, and web built.                                              |
| Isolated Compose startup                                                    | 0; `docker compose --project-name openclass-takeover-checkpoint --env-file .env.example up --build --detach --wait`, database port 55435, server port 17331, provider mock.                                                                                         |
| Packaged readiness/init/classify smoke                                      | All exit 0; migrated API ready, classifier created, cancellation input returns UNKNOWN with explicitly simulated mock provenance.                                                                                                                                   |
| Extra PostgreSQL `uv run alembic check`                                     | Exit 255; pre-existing metadata drift: `cluster_candidates.status` database VARCHAR(30) vs model String(20), and model lacks existing `service_versions(service_id, version_number)` uniqueness. Track under OC-BG-026; do not call this check passed.              |

These vector checks do not prove the application's embedding cache/query path,
or checkpoint concurrency. Those require their own tests.

The seven full-suite skips are five opt-in live provider/closed-loop checks,
one unavailable real Laya in-process engine, and one unavailable historical
local research archive. No PostgreSQL test was skipped in that run.
Warnings are existing Starlette HTTP-client and SQLite datetime/date adapter
deprecations; they are not suppressed.

After both implementation workers returned, the parent independently reran the
checkpoint SQLite/PostgreSQL suites and server/core mypy checks, with exit 0.
Final source lint, formatting and all-workspace mypy also passed.
Independent reviewer `fe212ed0-077c-413d-a3d1-e31a6b5b687c` resolved its four
initial findings and reported no remaining high-confidence checkpoint bugs.
Its separate probes covered forged privilege, both dedicated force scopes and
cancellation-resistant provider fencing.

Limits: tests use simulated providers and controlled schedules. They do not
exercise real socket-level disconnects or prolonged database-lock contention,
and cannot prove exactly-once remote operations. Database-clock expiry assumes
consistent lease TTL configuration across replicas.

## Delivery evidence

Baseline milestone comment:
<https://github.com/yassincodes404/OpenClass/pull/57#issuecomment-6197246031>.

Checkpoint implementation and independent review passed. PR publication,
exact-commit CI, merge and main verification remain pending. No live-stack
browser result or redesign artifact is claimed yet.
