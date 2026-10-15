# Control-plane persistence

The control plane owns only `control_*` tables. The engine owns its Alembic
history and domain tables. Apply both migration systems explicitly before
starting services; neither service should create or mutate schemas at startup.

## Explicit migrations

From the repository root, with `CONTROL_PLANE_DATABASE_URL` supplied through
the environment:

```powershell
pnpm --filter @openclass/control-plane migrate
```

The command applies numbered forward SQL files, excluding `.down.sql`, in order.
It locks the current database/schema for the whole transaction, verifies SHA-256
checksums in `control_schema_migrations`, and records successful versions.
Repeated or concurrent invocations are safe. Missing, modified, or out-of-order
applied migrations fail closed; failed DDL and history writes roll back together.
Do not modify an applied file or run historical down scripts against protected
history. Deploy a new reviewed forward migration instead. CLI failure output
contains a fixed error code, never connection strings or raw database errors.

For installations previously migrated manually, `0001`–`0004` run their
idempotent additive statements and acquire checked history; `0005` then upgrades
request receipts and protects audit/history. `0006` adds the audit seek index.
Existing rows are retained. The upgrade removes historical global project-slug constraints and ensures
`UNIQUE (workspace_id, slug)`. Conflicting same-workspace data causes a
transactional migration failure, not silent deduplication.

`control_audit_events` and `control_schema_migrations` reject SQL UPDATE,
DELETE, and TRUNCATE. Audit references prevent workspace deletion through
`ON DELETE RESTRICT`. Table owners/superusers can still change DDL; these are
application-integrity protections, not protection from a malicious administrator.

## Mutation API contract

Authenticated POST/PUT/PATCH/DELETE controller requests run in one local
PostgreSQL transaction. Domain mappings, memberships, audit records and optional
idempotency receipts commit together. Guards execute before the transaction;
the same injected transactional pool routes all services through its connection.
Keep all local writes on that pool; do not open independent clients in mutations.

An optional `Idempotency-Key` must be 1–200 printable characters. Keys are scoped
to a workspace (or authenticated actor for workspace creation). A SHA-256 request
identity includes the HTTP method, complete path/query, canonical JSON body,
authenticated subject, and current role or exact API-key row ID/project/scopes.
Object-key ordering is ignored; array order and absent/null fields remain distinct.

- Same unexpired identity: replay the original HTTP status and JSON response.
- Same key with changed body/path/method/caller/authorization: HTTP **409**,
  without invoking the controller or remote mutation.
- Removed membership or wrong key project/workspace: **404** even on replay.
- Expired key: atomically replace the receipt and execute the new identity once.
- Failed mutation: roll back all local writes and the reservation; retry is allowed.
- Empty/oversized/control-character key: **400**, never silently truncate.
- API-key creation: idempotency headers are rejected with **400**, because
  one-time bearer material must not be stored in response receipts. Trusted
  handler metadata enforces this regardless of route casing.

Concurrent identical requests wait on a transaction-scoped database advisory
lock and replay after the first successful commit. `IDEMPOTENCY_TTL_HOURS`
defaults to 24 and must be positive/finite. Expiry starts at successful completion.
Legacy receipts lacking request identity remain intact and reject reuse with 409
until expiry rather than blindly replaying an unrelated response.

Both API-key guards propagate the non-secret key row ID and required scope.
After acquiring the receipt lock, authorization reloads that exact row, checks
revocation, current scope and workspace/project binding, and holds a shared row
lock through completion. Revoked keys or removed required scopes return **403**,
including requests admitted before waiting. Different keys with identical
project/scopes are different identities and cannot replay each other's receipt.
Neither bearer material nor its hash is used as the request identity.

Successful response bodies can contain observation content; receipts therefore
have the same data sensitivity as the underlying local application records.
Do not put credentials in request bodies. Idempotency keys are identifiers,
not credentials. Expired receipts are replaced on reuse; no automatic destructive
retention cleanup is introduced.

### HTTP boundary and recovery

The control plane forwards a workspace/path-scoped hashed idempotency key to the
engine. Engine endpoints must implement durable request-identity replay for
crash-safe reconciliation. A local SQL transaction cannot roll back an already
successful HTTP call: after a crash or local failure, retry the same key, not a
new key. Project creation intentionally does not blindly archive a successfully
created engine project after a local persistence failure.

This is not a distributed transaction or a new outbox/remote exactly-once
guarantee. Local concurrent requests execute once; remote crash recovery depends
on each engine endpoint's documented receipt contract. Requests without keys
have local atomicity but no retry-deduplication guarantee.

## Correlation, safe errors, events

Incoming `X-Correlation-ID` values matching `[A-Za-z0-9._:-]{1,128}` are echoed;
missing/invalid/multi-value inputs receive a generated UUID. Async request context
forwards the identifier on **every** engine call, including reads and ingestion.
Explicit internal `EngineRequestOptions.correlationId` is also supported.
New audit events persist `correlation_id`; legacy rows retain null.

Existing successful domain events (`workspace.created`, `project.created`,
`member.invited`, `observation.ingested`, etc.) commit with their mutations.
Structured logger events `control.engine_request_failed` and
`control.request_failed` identify a fixed error code, status and correlation ID.
They never include upstream error bodies/messages, request content, URLs,
bearer material or connection strings. Failure logs survive SQL rollback;
failed operations do not fabricate completed audit events. Public failures have
safe status-based messages and `correlation_id`, not raw exceptions.

## Audit pagination API

`GET /control/workspaces/{workspaceId}/audit` retains its SDK-compatible response
shape `{ items, next_cursor }`. Clients must pass `next_cursor` back unchanged;
it is an opaque, versioned base64url cursor, not a timestamp to parse or build.
Ordering and seeking both use `(created_at DESC, id DESC)`, including events
sharing PostgreSQL's transaction timestamp. The cursor encodes the database's
full six-digit microsecond precision and UUID tie-breaker; JavaScript `Date`
millisecond truncation is never used for seek boundaries. Internal cursor
columns are not exposed in audit items.

`limit` defaults to 50 and must be an integer from 1 to 100. Optional `action`
must contain 1–80 characters; cursor strings are bounded to 512 characters.
Malformed, unknown-version, and legacy timestamp-only cursors return typed
HTTP **400** errors. Existing SDKs still exchange strings without changes;
clients holding pre-upgrade timestamp cursors must restart without a cursor.

## Validation

The ordinary suite does not connect to a database:

```powershell
pnpm --filter @openclass/control-plane typecheck
pnpm --filter @openclass/control-plane test
pnpm --filter @openclass/control-plane build
```

For a **disposable PostgreSQL database only**, supply its URL as
`CONTROL_PLANE_TEST_DATABASE_URL`, then run:

```powershell
pnpm --filter @openclass/control-plane test:postgres
```

The command fails rather than silently skipping if the URL is missing. Tests use
unique isolated schemas and drop only those schemas they created. They exercise
real SQL, concurrent migrations, checked upgrades, append-only DML rejection,
rollback, expiry/restart, concurrent receipts, and actual Nest controllers.
Engine responses in these controller tests are explicitly simulated; they are
not live-engine or authenticated-OIDC end-to-end evidence. An unmanaged engine
table is retained alongside control tables; the engine's own mixed-schema
Alembic check and live full-stack browser checks remain separate validation.
