# Takeover completion ledger

Date: 2026-10-16. This is an evidence ledger, not a completion claim.

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

| Item      | Takeover status | Remaining acceptance / evidence                                                                         |
| --------- | --------------- | ------------------------------------------------------------------------------------------------------- |
| OC-BG-012 | PARTIAL         | Complete replay, original gates and durable per-example outcomes.                                       |
| OC-BG-013 | PARTIAL         | Complete transactional promotion, history, and rollback requirements.                                   |
| OC-BG-014 | PARTIAL         | Unify candidate domain, persistence, and lifecycle across tracks.                                       |
| OC-BG-016 | PARTIAL         | Typed compiler, schemas, persisted snapshots, provenance, budgets.                                      |
| OC-BG-017 | PARTIAL         | Data-driven supervision and verified calibrated profiles.                                               |
| OC-BG-018 | VERIFIED        | Original scope delivered in PR #59; runtime and independent verification tests pass.                    |
| OC-BG-020 | PARTIAL         | Continuous supervision sampling, triggers, and budgets.                                                 |
| OC-BG-021 | PARTIAL         | Integrate the ten-layer Teacher protocol into runtime paths.                                            |
| OC-BG-022 | PARTIAL         | Real embeddings, cache identity, and PostgreSQL vector indexing.                                        |
| OC-BG-024 | PARTIAL         | Control-plane/engine slices delivered in PR #60/#62; broader webhook identity acceptance remains.       |
| OC-BG-025 | PARTIAL         | Engine UoW/evidence constraints delivered in PR #62; broader original acceptance remains open.          |
| OC-BG-026 | PARTIAL         | Migration/history increments delivered in PR #60/#62; broader upgrade/drift acceptance remains.         |
| OC-BG-027 | PARTIAL         | Frontend feature parity and consistent project workflows.                                               |
| OC-BG-029 | PARTIAL         | Correlation/usage foundation delivered; configured model attribution and caller adoption remain.        |
| OC-BG-030 | PARTIAL         | Engine SQL filtering/rollups delivered in PR #62; discovery/clustering caller adoption remains.         |
| OC-BG-032 | PARTIAL         | Transactional outbound delivery, retries, vendor verification.                                          |
| OC-BG-033 | PARTIAL         | 28 real PostgreSQL contracts and live lifecycle/restart/isolation pass; broader workflow scope remains. |
| OC-BG-034 | PARTIAL         | Full-stack containers delivered in PR #63; original packaging/build/benchmark remainders stay open.     |
| OC-BG-036 | PARTIAL         | Post-promotion cohort monitoring and rollback behavior.                                                 |

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
- [x] Focused PR, green CI, merge, and main verification recorded.

## Guarantees to preserve

UNKNOWN is permanent. Predictions are not verified ground truth. Providers cannot
activate ontology changes. Promotion requires evidence, replay evaluation, and
human review. Ontology snapshots, aliases, and audit history remain append-only.
External side effects are not exactly-once merely because database writes are
fenced. Forced recovery and lease expiry can overlap an already sent remote call.

## Current verification evidence

The following table is historical checkpoint-delivery evidence from 2026-10-15,
not a claim that every command was rerun on the latest main or that its disposable
containers are still running. Later engine/delivery evidence is recorded below.

That run used disposable container `openclass-takeover-pg17-20261015`, bound only
to `127.0.0.1:55434`. Image: `pgvector/pgvector:pg17`, digest
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

Checkpoint [PR #58](https://github.com/yassincodes404/OpenClass/pull/58)
merged as `91f1b97104ece21787daf597ed44a1b50a00323b`.
[PR CI](https://github.com/yassincodes404/OpenClass/actions/runs/38773727748)
passed Python, web, Compose and security checks. Its actual Python result was
**645 passed, 7 skipped**, 948 warnings, 209.66 seconds.
[Main CI](https://github.com/yassincodes404/OpenClass/actions/runs/38774433446)
also passed. The merged tree matched the reviewed tree exactly; post-merge local
PostgreSQL checkpoint/vector verification passed **49 tests, 1 warning**, 46.11 seconds.

Automation [PR #59](https://github.com/yassincodes404/OpenClass/pull/59)
merged as `b41173e6b2dc2635eb86fb7d7314bb7bacdd4fd1`.
[PR CI](https://github.com/yassincodes404/OpenClass/actions/runs/38785910677)
passed all four checks, including **783 passed, 7 skipped** with genuine
PostgreSQL. [Main CI](https://github.com/yassincodes404/OpenClass/actions/runs/38787559766)
passed. Parent post-merge focused automation verification passed **160 tests**.
Independent review reproduced and resolved failure-provenance, aggregate-patch
and overdue-verifier defects before delivery.

Control-plane [PR #60](https://github.com/yassincodes404/OpenClass/pull/60)
merged as `d8b3051c48439144c4df393cfd57f2591598cf3b`.
All five PR checks passed. The
[genuine PostgreSQL job](https://github.com/yassincodes404/OpenClass/actions/runs/38788850064)
applied six migrations, applied zero on repeat, and passed **23 tests**.
Both [main CI](https://github.com/yassincodes404/OpenClass/actions/runs/38790288768)
and [main PostgreSQL CI](https://github.com/yassincodes404/OpenClass/actions/runs/38790288731)
passed. Parent post-merge control-plane verification passed **109 tests**.
Independent review fixes cover case-insensitive secret routes, API-key caller
identity, authorization revalidation after reservation waits, and tied audit
cursors. This delivery closes control-plane slices, not all of the original
OC-BG-024/026/029/033 criteria.

Landing [PR #61](https://github.com/yassincodes404/OpenClass/pull/61)
merged as `227169358fe321dfed59be89dd47829be6da8781`.
All five PR checks passed, including
[CI](https://github.com/yassincodes404/OpenClass/actions/runs/38796358901)
and [control-plane PostgreSQL](https://github.com/yassincodes404/OpenClass/actions/runs/38796358843).
[Main CI](https://github.com/yassincodes404/OpenClass/actions/runs/38797682622)
also passed. The parent verified that the merged tree exactly matched reviewed
head `cb9e377`, reran the 22 component tests, and verified all four landing gates.
The seven screenshots, genuine recording, source hashes, viewport measurements
and independent review are retained in `artifacts/landing-redesign/`.

Engine foundations [PR #62](https://github.com/yassincodes404/OpenClass/pull/62)
merged as `b99d19776128ff88f94d03da693bb3b602e9d8c6`. The exact reviewed head
`5bd9558def9318ea18c01ff95ddad1ef7c1c3f4b` passed
[PR CI](https://github.com/yassincodes404/OpenClass/actions/runs/38800818959):
**845 passed, 7 optional skips**, using genuine `pgvector/pgvector:pg17`.
The workflow sets the disposable database URL and runs unrestricted
`uv run pytest -q`; quiet output does not enumerate every test.
Both [main CI](https://github.com/yassincodes404/OpenClass/actions/runs/38802459879)
and [main PostgreSQL CI](https://github.com/yassincodes404/OpenClass/actions/runs/38802459825)
passed. Independent review resolved migration/recurrence/latency/cost defects
and verified all four terminal-UNKNOWN attachment combinations, restart survival
and byte-identical immutable run history. This delivers foundations, not the
remaining discovery/clustering callers or all original engine tickets.

Full-stack delivery [PR #63](https://github.com/yassincodes404/OpenClass/pull/63)
merged as `6cd0e9c3b6732d30f28504d70c29dfa2b4fa7eb6`. Its merged tree exactly
matches reviewed head `f6a01639c425a6cdf45882a851498b6ab9c715f5`.
All six checks passed:

- [CI](https://github.com/yassincodes404/OpenClass/actions/runs/38881500309):
  Python **845 passed, 7 optional skips**; containerized suite **845 passed,
  7 optional skips**; quickstart regressions **2 passed**; web and security green.
- [Control-plane PostgreSQL](https://github.com/yassincodes404/OpenClass/actions/runs/38881500301):
  **28 real database contracts passed**, including both project lookup routes
  with control ID, engine ID, slug, missing identifiers and non-member denial.
- Actual live browser: **2 passed in 24.5 seconds**. Real Keycloak, PostgreSQL,
  engine, control plane and both frontend containers start without API route
  mocks. The lifecycle ingests an event, runs a clearly simulated provider,
  restarts database/backends, reads persisted run/event records, restores SSO
  after browser reload and denies another workspace.
- Four genuine screenshots are in that run's
  `live-backend-browser-evidence` artifact. Parent inspected persisted-runs and
  denied-workspace captures and retained a local copy.

Hosted failures were fixed rather than skipped: deterministic applicability
clocks, missing test-image source/protocol fixtures, UUID/text lookup mismatch,
an unhandled idle database connection error, and missing project-route SSO
restoration. Shared pool errors log only a stable event; query failures still
reject. SSO tokens stay in memory and the public landing page does not initiate
the new redirect. The real restart/isolation assertions were not weakened.
Independent correction review found no actionable bugs.

Final local delta checks: **111 control-plane tests**, **25 portal tests**,
types and builds passed. A 256 MB control-plane build heap was insufficient;
the 512 MB retry passed. Earlier fixture/boundary checks passed **19 tests** and
delivery runner checks passed **29 tests**, with one POSIX-only assertion skipped
on Windows. Those local unit checks are not the live-stack proof.

[Main PostgreSQL CI](https://github.com/yassincodes404/OpenClass/actions/runs/38882554834)
passed. [Main CI](https://github.com/yassincodes404/OpenClass/actions/runs/38882554816)
also passed, including another real live-backend run. Original OC-BG-033/034
remain partial beyond this delivery slice. No package, registry image or release
was published.

## Continuing work

- Original `OC-BG-018` is verified through PR #59. The first full local run
  exposed a collection-time freshness-test flake; freezing observation and
  evaluation clocks fixed it. Hosted PostgreSQL subsequently passed without
  database skips.
- Engine and delivery worktrees remain preserved after PR #62/#63. Genuine
  PostgreSQL and full-stack browser evidence is now delivered above. Caller
  adoption and broader original acceptance remain open. The benchmark audit
  reported `historical_files_preserved: 0`; container success does not close the
  original frozen-evidence requirement.
- Landing implementation `05b9eb5d17b68ef40add9c12d986115abec2668f`
  has **22 passing component tests** and independent code/visual approval.
  Fresh actual-browser verification covers **40 scenario/step checks**, five
  viewport captures, readable mobile/tablet cards, exact zero-duration reduced
  motion, and a decodable desktop interaction recording. The
  [artifact manifest](../../artifacts/landing-redesign/README.md) records its
  scope and limits. Focused delivery and main verification are recorded above.
- Original `OC-BG-027` implementation is now isolated in the frontend workflow
  worktree. Both frontends remain; supported evidence/graph/evaluation workflows
  must use SDKs and preserve workspace authorization. Mocked UI checks do not
  close the separate authenticated cross-child integration requirement. The
  frontend worker stopped from model usage exhaustion; partial tracked and new
  files are preserved, uncommitted and unverified. The caller-adoption worker
  also stopped without a result; its worktree is clean, not implemented.
- After safely integrating merged main without overlapping saved landing
  edits, `make check` passed (109 control-plane, 22 portal, 18 SDK tests).
  Explicit offline `make test` passed **725 tests, 7 skipped, 58 deselected**,
  948 warnings, 188.33 seconds. PostgreSQL/live cases were deliberately excluded,
  not passed. Bounded two-worker `npm run build` and all 11 Python package
  builds passed. Initial formatting failure came from an untracked browser
  snapshot; the formatter now excludes generated `.playwright-mcp/` artifacts
  without deleting or staging them.
- Host disk exhaustion interrupted four worker reports; saved source was
  preserved. Storage recovered, but the local Docker engine did not restart
  successfully. New database acceptance must use genuine hosted PostgreSQL CI,
  not silently skipped checks or fake extension files.
- A later disposable Windows PostgreSQL attempt failed under resource pressure;
  retries also failed to start. No test pass is claimed from it and no owned
  disposable server remains. Historical checkpoint checks and current hosted
  results must not be conflated with that failed attempt.
- Coordination reconciliation replaced an invalid manually checked engine gate
  with an executable exact-source hosted oracle and actually released its lease.
  Incorrect future caller-wave timestamps were corrected from native session
  records, preserving the missed prelaunch lease/dispatch ordering as a defect.
  Scheduler completion of failed workers is not acceptance verification.
