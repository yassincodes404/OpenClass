# Remaining backlog execution plan

Date: 2026-10-15. Scope preserves the original `OC-BG` acceptance criteria at
commit `7158104`. This plan does not certify implementation.

The checkpoint repair and genuine PostgreSQL verification land first.
Work then proceeds through the dependency waves below. Each focused increment
needs failure-path tests, independent review, appropriate API/SDK coverage,
documented events/errors, passing checks, and a recorded PR/merge.

## Acceptance corrections

- `OC-BG-012` requires durable per-example outcomes and all original replay
  gates, not a particular SQL table name. Current evaluation persistence
  contains aggregate metrics, not the claimed `metrics["item_results"]`.
  Restore the original false-novelty ceiling of 0.05, disambiguation threshold
  of 0.80, and separate holdout-regression checks.
- `OC-BG-013` and `025` include active project promotion paths. Track 2 and
  Track 3 currently split activation writes across transactions. Fix these
  safety boundaries before adding activation families.
- `OC-BG-014` includes ALIAS, OUT_OF_DOMAIN, SCHEMA_ISSUE, unified access,
  triage synchronization, and supported non-UNKNOWN evidence. Later patch
  families are additional scope, not substituted acceptance.
- `OC-BG-016` requires typed compiler behavior, provenance and budgets. A
  specifically named compiler class or state-schema SQL table is not required.
  Migration `0028` is already allocated to checkpoint safety.
- `OC-BG-017` requires provider-neutral policy and profile enforcement. An
  automated ECE-fitting subsystem is not a substituted closure requirement.
- `OC-BG-018` needs actual independent verification, not action exit-code success.
- `OC-BG-024` remains open in both Python and the control plane.
- `OC-BG-027` requires feature parity, not retirement of either frontend.
- `OC-BG-029` requires model-sensitive rollups and correlated safe failures.
- `OC-BG-034` includes full-stack containers. Broader benchmark claims require
  separately measured evidence.

## Dependency waves

| Wave                       | Item      | Deliverable and decisive evidence                                                                                                                                                                                   |
| -------------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1                          | OC-BG-026 | Versioned control-plane migration runner, append-only protections including decision runs, safe history references; mixed-schema Alembic check and SQL mutation rejection.                                          |
| 1                          | OC-BG-025 | Shared UoW for run/evidence, feedback/evidence, case attachment and batches; unique run evidence; fault-injected rollback and concurrent mutation tests.                                                            |
| 1                          | OC-BG-024 | Request hashing, body-conflict rejection, expiry reuse, atomic reservation/replay in both runtimes; webhook receipts link identical existing events.                                                                |
| 1, independent             | OC-BG-034 | Reproducible control-plane, portal and web containers with explicit migrations and readiness; clean build and full-stack Compose smoke.                                                                             |
| 2                          | OC-BG-030 | SQL eligibility before pagination, direct evidence lookup, counts/grouping without capped scans; fixtures exceeding 250 eligible runs hidden behind known runs.                                                     |
| 2                          | OC-BG-016 | Integrate strict typed compilation, provenance, budgets, required state/preconditions and metadata transport; missing/false/null/type distinction tests.                                                            |
| 2, after compiler contract | OC-BG-017 | Replace provider-name branches with policies/profiles; provider-neutral distribution fixtures and conservative uncalibrated/high-risk handling.                                                                     |
| 2, independent             | OC-BG-029 | Model-sensitive usage uniqueness/upserts, end-to-end correlation and safe structured failure events; two-model rollup and error tests.                                                                              |
| 2, independent             | OC-BG-022 | Real PostgreSQL cosine query/index path and model/dimension-aware persistent caching; reuse/model-switch/isolation and semantic grouping tests.                                                                     |
| 3                          | OC-BG-014 | Canonical candidate access/lifecycle with compatibility mappings; cluster proposals visible in project candidates, original proposal kinds, non-UNKNOWN evidence and uncapped bidirectional triage synchronization. |
| 3, independent             | OC-BG-018 | Production applicability and verifier contracts, macro/per-step guards and postconditions; misleading exit-code and negative-transfer tests.                                                                        |
| 3                          | OC-BG-020 | Configured post-run low-margin/sampled advisory review outside the synchronous inference path; deterministic sampling and provider-failure evidence.                                                                |
| 4                          | OC-BG-021 | Typed Teacher proposal integration, guard/schema compilation and supported application operators; ADD_CHOICE, REPLACE_PROCEDURE, ADD_STATE_FEATURE and invalid-operator server tests.                               |
| 4                          | OC-BG-012 | Shared replay service/port, NEW_CHOICE/ALIAS and compatibility paths, sealed identity binding, durable item outcomes and all original gates; novelty, known regression, failure and holdout regression fixtures.    |
| 5                          | OC-BG-013 | Explicit approval and one locked activation transaction for evaluation/base/version/pointer/candidate/evidence/audit; stale and concurrent activation rejection, rollback-as-new-version, Teacher-disabled reuse.   |
| 5                          | OC-BG-032 | Transactional outbound intent, bounded retry/reconciliation worker, vendor HMAC normalization, real DB probe and scoped MCP handshake; restart/duplicate/ambiguous-effect/readback evidence.                        |
| 5, UI lane                 | OC-BG-027 | SDK-backed evidence/diagnosis, supported graph editing and evaluation workflow parity; externally created owned projects visible through both entry points.                                                         |
| 6                          | OC-BG-036 | Version/cohort sliding-window UNKNOWN and low-margin monitoring, opt-in rollback-as-new-version; insufficient samples, duplicate triggers and immutable history tests.                                              |
| Continuous, final gate     | OC-BG-033 | Real migrated control-plane PostgreSQL tests, separate live-backend browser project/CI; authenticated lifecycle, cross-workspace denial, restart recovery and both HTTP boundaries.                                 |

## Ownership and integration rules

Keep engine persistence, control-plane platform, decision runtime, automation,
embeddings, integrations, evolution, frontend, and delivery/QA as natural scopes.
Serialize edits to `projects.py`, `tables.py`, shared SDK contracts and migration
head configuration. No two workers own the same file concurrently.

The evolution lane follows candidate unification → Teacher/replay → transactional
promotion → drift. The outbound lane waits for UoW and idempotency. UI parity is
separate from landing redesign. Live PostgreSQL and browser evidence are
continuous gates, not substitutes for domain acceptance.

## Final verification

Run `make check`, `make test`, `npm run build`, and `uv build --all-packages`.
Use disposable migrated PostgreSQL with real pgvector and the live-backend
browser suite. Record exact exits, counts, skips, failures, review corrections,
CI links, merge commits, and post-merge verification. Do not publish packages,
releases, or images merely to validate changes.
