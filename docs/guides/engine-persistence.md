# Engine persistence contracts

This increment implements engine foundations from the original OC-BG-024–026,
029 and 030. It does not certify the control plane, clustering/discovery callers,
or all backlog items as complete.

## Transactions

`ProjectRepository.transaction()` is the core unit-of-work port. SQL repositories
on the same engine join one task-local session. Only the outer transaction
commits. Run/checkpoint/usage/evidence/audit writes, feedback and correction
evidence, case creation and all attachments, and accepted batch items roll back
together. Provider execution stays outside the write transaction.

PostgreSQL mutations lock the project before reading mutable project state;
candidate approval locks the classifier and stored candidate. Feedback shares
the checkpoint row lock with lifecycle correction feedback. SQLite uses
`BEGIN IMMEDIATE` because it has no equivalent row locks. Do not share a unit of
work across concurrent tasks. An unsuccessful joined mutation makes its outer
transaction rollback-only even if an intermediate caller catches the failure.

`evidence_items.decision_run_id` is unique for non-null IDs. Multiple human
feedback records remain append-only; they do not manufacture duplicate evidence.
Predictions and corrections do not rewrite the immutable run or ontology.

## Ingestion and HTTP idempotency

`POST /api/v1/projects/{identifier}/events` and `/events/batch` accept
`Idempotency-Key` (up to 200 characters), scoped to the resolved project UUID.
Identity is SHA-256 over canonical JSON containing the HTTP method, canonical
UUID resource path, and submitted JSON body. Object key order is insignificant;
array order, metadata and body content are significant. A slug and UUID for the
same project resolve to the same path identity.

Reservation, ingestion and response storage use one database transaction and a
project lock. Concurrent identical requests return one committed result; changed
bodies or another method/path return `409`. Replays return `200`,
`Idempotency-Replayed: true`, and `deduped: true`. New batches return `207`;
invalid batch entries remain explicit per-item errors. An unexpected failure
rolls back all otherwise accepted entries and the idempotency response.

The TTL defaults to 24 hours (`OPENCLASS_IDEMPOTENCY_TTL_HOURS`). Expired keys can
be reused. An uncommitted crash rolls back the reservation and its writes; a
committed response replays after restart without process-local state.

Webhook receipt identity is `(project_id, integration_id, event_key)` plus the
delivery fingerprint. A changed delivery under an existing key conflicts.
Distinct receipt keys with identical content reference the **same** raw event,
retaining separate receipt/audit records. Original source content, hash and
metadata are not changed to fabricate a second observation.

## Upgrade to 0029

Back up the database and stop writers before `uv run alembic upgrade head`.
Readiness expects `0029_engine_persistence_contracts`.

- The migration checks for repeated non-null evidence run IDs **before any DDL**.
  Duplicates block the upgrade. It never deletes evidence, selects an arbitrary
  winner, detaches run references, or rewrites audit/case history. Preserve the
  backup and obtain an explicitly reviewed reconciliation before retrying.
  There is deliberately no automatic destructive repair command.
- Existing idempotency responses retain their data and have a null request hash.
  Their original requests cannot be recovered reliably from response bodies.
  A live legacy key therefore returns `409` rather than an unverifiable replay;
  use a fresh key or wait for expiry. Expiry reuse writes a proper request hash.
- Usage uniqueness becomes `(project_id, provider, model, usage_date)`. Existing
  counts/costs/tokens and their recorded model are preserved exactly. Earlier
  versions may have mixed models into that row; this migration cannot recover
  a truthful historical split and does not invent one.
- Observations, classification runs, unknown events, decision runs and feedback
  reject SQL UPDATE/DELETE. Existing source, receipts, audit, version and ontology
  protections remain. Historical source/service/run/version references use
  RESTRICT instead of cascading deletion.
- Checkpoint rows remain mutable under the existing 0028 revision/lease fencing
  contract. No checkpoint state or claim is rewritten by this increment.
- The migration removes webhook event-ID uniqueness, allowing multiple receipts
  for one source event. Restoring old uniqueness could require lossy merging.
  Downgrade supports empty affected tables for schema verification only; it
  refuses populated history before DDL and requires a reviewed backup restore.

SQLAlchemy metadata now reflects the already-existing service version uniqueness
and candidate status width (PostgreSQL 30; SQLite's unenforced declaration 20).
No fictitious PostgreSQL DDL is added for metadata-only alignment. Alembic ignores
`control_*` tables. SQLite batch migrations disable FK actions only on their
migration connection, then run `foreign_key_check`. Success or failure settles
the transaction before restoring `foreign_keys=ON`; restoration is verified.
A failed restoration invalidates the physical connection rather than returning
an unenforced handle to a pool. Duplicate-evidence upgrade failures are covered
using a reacquired **same physical** pooled SQLite connection and a rejected
invalid foreign-key write.

## Queries and telemetry

The UNKNOWN listing applies effective run/checkpoint eligibility, triage filters
and text search in SQL **before** pagination. Ordering is descending
`(created_at, id)`; `next_cursor` is the next offset, not a snapshot token.
Use bounded pages; concurrent insertions can shift offsets.

Clustering calls `ProjectService.list_unknown_runs()` with the requested limit;
known runs never consume that limit. Legacy classifier discovery resolves the
requested evidence through the typed `Repository.unknowns_by_ids()` port.
Missing, known-only and other-classifier IDs remain a 409 conflict, even when
other eligible evidence exists. Neither caller scans a capped page.

Checkpoint decision fields are required in the domain **and NOT NULL** in
migration 0026 and the current table mapping. They cannot deliberately clear a
selection or supervision outcome to null. A SQL outer join produces null only
when the checkpoint row is absent; coalescing then retains the immutable run.
With a checkpoint present, explicit values override the run in both SQL
eligibility and the returned overlay. Other nullable checkpoint fields (such as
`next_node_key` and claim metadata) retain their existing clearing semantics.
No schema or lifecycle change is required.

UNKNOWN detail and evidence synchronization use direct IDs, not a 200-row scan.
Detail and listing share the project-scoped recurrence query, so repeated runs
for one source event have the same recurrence count in both responses.
Evidence-to-UNKNOWN synchronization runs only when the persisted evidence status
actually changes. Attaching evidence to a new or existing case changes membership,
not lifecycle state: ready-for-evolution evidence can remain attached to a
resolved or dismissed UNKNOWN without reopening it.
Statistics use SQL count/grouping; phrase extraction streams grouped source text.
Project analytics use SQL counts/grouping and database-ordered nearest-rank
percentiles, without loading all run JSON. Operations measurements use SQL
aggregates and disjoint time windows. No accuracy labels are inferred.

`record_provider_error` atomically increments the supplied provider/model rollup
and appends `decision.provider_failed` with provider, model and latency only.
Raw exception text, submitted content and credentials are excluded. The decision
route supplies the provider's public configured identity when no result exists.
Jev and Laya expose read-only `model` properties and their provider names for this
path, including injected adapters. Successful results retain the validated
upstream-reported model: a configured alias may legitimately resolve to a
different actual name. Only an **omitted** wire model uses the configured model;
explicit null, empty or malformed values still fail validation. Jev's existing
model-format and credential guards also apply to the fallback. Configuration
must not contain the adapter's credential in its model identity. This is
model-sensitive reporting, not a configuration-equality constraint. The caller
tests use synthetic wire responses and establish no inference-quality or cost
benchmark claims; broader cross-service correlation remains outside this change.

### Latency and exact-window declared cost

`GET /api/v1/projects/{identifier}/providers/usage` remains a calendar-day usage
report. `calls` counts recorded successful calls, `errors` counts recorded failed
calls, and `attempts = calls + errors`. Its `avg_latency_ms` is the sum of their
recorded latencies divided by **all attempts**, with `latency_basis: "attempt"`.
Ten milliseconds of success plus twenty milliseconds of failure yields 15 ms;
an error-only 20 ms row yields 20 ms. Zero attempts yields `null`, not a fabricated
zero-ms measurement. This denominator is not a claim about unrecorded internal
provider retries. Operations' `latency_avg_ms` remains the average completed-run
latency; it is a separate metric.

Operations cost uses the exact UTC interval `[since, until)`, **not** a sum of
whole-date cost rollups. It streams only persisted provider metadata for runs
whose immutable timestamps fall inside the interval. Only an explicit finite,
non-negative numeric `provider_metadata.estimated_cost` is a declared estimate.
Missing, null, malformed or boolean values are unknown; explicit numeric zero
is valid. Charges are never inferred from token counts or failed-call status.
Estimates retain their provider-declared units; no billing/currency conversion
or measured-savings claim is made.

`ProviderCostWindow` / `ProjectRunMeasurements` are typed core read models:

- `amount` / the existing operations `cost` or `provider_cost` is numeric only
  when the interval's recorded attempts all have declared costs and no legacy
  attempts on intersecting days lack timestamps.
- `declared_cost` is the timestamp-qualified **known subtotal**, even when a
  complete total is unavailable. It is not silently used as the full cost.
- `timestamped_attempts`, `declared_cost_attempts`, `missing_cost_attempts` and
  `legacy_unlocated_attempts` expose the evidence and missing denominators.
- `status` is `complete`, `partial` (some declared estimates), or `unavailable`
  (no complete total and no declared estimates). Reasons are
  `declared_cost_missing` and/or `legacy_attempt_timestamps_missing`.

Timestamped `decision.provider_failed` events count as attempts with unknown
cost, never free calls. Their audit timestamp and usage date use the same captured
UTC instant. Old rollup-only attempts have no exact timestamp: reconciliation
compares daily success/error counts against persisted runs/error audits for
whole UTC days intersecting the requested interval. Unmatched attempts are
reported as **unlocated**, not assigned to the requested hour or a guessed time.
No old run, audit, timestamp, price, or daily aggregate is backfilled or rewritten;
this correction needs no persistence-schema migration.

`GET .../analytics/summary` exposes `provider_cost_measurement`,
`previous_provider_cost`, and `previous_provider_cost_measurement` alongside the
existing `provider_cost`. The two windows use disjoint timestamp boundaries, even
when the boundary falls halfway through a calendar day.
`POST .../alerts/evaluate` exposes `measurements.cost_window`; cost alerts receive
`null` and do not fire when a full cost is unavailable. A high earlier same-day
cost cannot contaminate a last-hour alert. An entirely empty, fully accounted
interval has a measured cost of zero and zero timestamped attempts.

Discovery and clustering use `SQLRepository.unknowns_by_ids()` through the core
port and `ProjectService.list_unknown_runs()`, respectively. Active project
promotion remains the evolution lane's transaction boundary.

## Validation

Use a disposable migrated PostgreSQL database with real pgvector installed:

```powershell
$env:OPENCLASS_TEST_DATABASE_URL = '<disposable PostgreSQL asyncpg URL>'
uv run pytest -q tests/integration/test_engine_persistence_contracts.py `
  tests/integration/test_idempotency_and_limits.py `
  tests/integration/test_webhooks_api.py tests/integration/test_webhooks_postgres.py `
  tests/integration/test_operations_dashboard.py
```

The focused contracts exercise SQLite and PostgreSQL fault rollback, concurrent
feedback/idempotency, restart replay, immutable history, populated upgrades,
duplicate-evidence upgrade refusal, mixed-schema Alembic checks, model attribution,
251 UNKNOWN runs hidden behind 1,001 newer known runs, pooled SQLite FK cleanup,
HTTP recurrence consistency, attempt latency denominators, exact cost boundaries,
missing/failure charges, and unlocated legacy cost history. PostgreSQL-parametrized
tests are supplied for hosted real-pgvector CI; local connection refusal is not
recorded as passing PostgreSQL evidence.
