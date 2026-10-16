# Durable outbound integration delivery

Simulation remains the default, including the no-key support demo and legacy
source webhooks. Predictions are not labels; UNKNOWN never authorizes an external
tag or queue assignment. Providers/normalizers have no dispatch or ontology-write
authority.

## Explicit opt-in

1. Apply Alembic migrations through `0030_outbound_deliveries`.
2. Operator sets `OPENCLASS_OUTBOUND_ENABLED=true` in the engine process.
3. Create a `rest_api` integration with a public HTTP(S) `endpoint`, dedicated
   environment `secret_ref` (for example `OPENCLASS_INTEGRATION_SECRET_SINK`), and
   `outbound: {"enabled": true, "receiver_enforces_idempotency": false}`.
4. Create an explicit known-choice `tag` or `assign_queue` rule on that integration.
5. Use the existing `POST .../integrations/routes/evaluate` with the persisted
   `run_id`, `integration_id` and `delivery_mode: "webhook_verified"`.

That legacy mode name means **request durable delivery**, not verified execution.
Default routes and UNKNOWN cannot enqueue; disabled/ineligible configuration fails
closed without an outcome/outbox orphan. The route response's
`routing.delivery_state` is initially `queued`, never a claim that the remote
business effect has happened. Replays and existing `GET .../integrations/outcomes`
expose current state additively. No new public endpoint or SDK method is required.

The JSON HTTP sink contract is `{event_id, run_id, route_id, action, value}`.
It sends dedicated environment-backed bearer authentication, `Idempotency-Key`
(`project UUID:run ID:route ID`) and `X-OpenClass-Request-Hash`. This is a generic
receiver action envelope, **not a native Zendesk/Intercom/Freshdesk action API**.
The receiver must interpret the configured action. Secret values are resolved at
dispatch, not stored in intent, outcomes, audit or history.

## Transaction and history

Routing outcome + immutable outbox intent + append-only audit/history enqueue
commit in one transaction. Project-scoped identity is unique; identical requests
replay, changed identity conflicts. Existing legacy outcomes without a request hash
fail closed on replay instead of gaining new execution authority. No historical
prediction, label, receipt or ontology snapshot is rewritten.

The destination, credential **reference**, action, value, event and receiver
idempotency assertion are bound in an immutable hashed intent. Configuration
edits never retarget queued effects. Before every attempt, deleted, disconnected,
disabled, changed-target/reference/policy or archived-project configuration stops
future attempts. Work with no prior ambiguous call becomes `cancelled`; prior
ambiguity remains `uncertain`. Secret rotation at the same environment reference
is supported. Revocation cannot retract a call already in flight.

Audit uses the existing `integration.updated` envelope to preserve the shared
event/SDK union. Its `payload.delivery_event` names
`integration.routing_simulated`, `integration.delivery_queued`, `_claimed`,
`_sending`, `_sent`, `_uncertain`, `_failed`, `_cancelled`, or
`integration.delivery_reconciled`. Delivery ID, attempt and fixed safe code are
recorded, never response bodies, Authorization/signature values or exception
strings. Reconciliation records only a receipt identifier digest.

## Remote-effect guarantees

- `queued` / `claimed`: the current attempt has not been authorized yet. On a
  retry, an earlier attempt may have applied; `delivery_attempts` and
  `delivery_had_ambiguous_attempt` on outcome history preserve this distinction.
- `sending`: a fenced attempt may have reached the receiver.
- `sent`: HTTP 2xx acceptance, or positive authoritative receipt reconciliation.
  **Neither proves an independently verified business postcondition.**
- `uncertain`: a call may have applied; no safe automatic retry authority remains.
- `failed`: bounded attempts exhausted with no prior ambiguous attempt.
- `cancelled`: configuration no longer authorizes another attempt.

Claims and finishes use DB compare-and-swap with a fresh token and unexpired
lease. Restart recovery requeues expired pre-send claims. Expired sending claims
and ambiguous HTTP failures/timeouts remain uncertain for non-idempotent receivers.
A stale owner cannot acknowledge a later owner's attempt.
An ambiguity bit survives later definitely-unsent retries and configuration
revocation: neither may erase an earlier potentially applied call.

**A DB lease cannot provide exactly-once remote side effects.** Set
`receiver_enforces_idempotency=true` only when the receiver genuinely enforces
stable key + request identity for the entire retry horizon. Only that contract
permits retrying a potentially-sent request, including an expired in-flight call.
Ambiguous exhaustion stays uncertain, even for idempotent receivers.

An injectable `ReceiptReconciler` can perform bounded authoritative readback via
`OutboundDispatcher.reconcile`; positive applied receipts must bind both the
idempotency key and exact request hash. There is no generic invented vendor
readback implementation. Negative absence does not prove that an old call can
never finish, so it neither clears uncertainty nor authorizes a resend.

## Bounded in-process operation

No Redis, queue service or separate worker infrastructure. The opt-in server
lifespan runs an in-process dispatcher; tests/operators can inject a sender and
call its bounded `drain` operation. Defaults and environment bounds:

| Setting (prefix `OPENCLASS_`) | Default | Allowed |
| ----------------------------- | ------- | ------- |
| `OUTBOUND_ENABLED`            | false   | boolean |
| `OUTBOUND_BATCH_SIZE`         | 10      | 1–100   |
| `OUTBOUND_POLL_SECONDS`       | 5       | 0.1–300 |
| `OUTBOUND_MAX_ATTEMPTS`       | 3       | 1–10    |
| `OUTBOUND_TIMEOUT_SECONDS`    | 5       | >0–30   |
| `OUTBOUND_LEASE_SECONDS`      | 60      | 35–600  |

Retry backoff is `min(300, 2 ** attempt)` seconds. Recovery scans at most 100
expired claims/exhausted queues per drain. Lowering the attempt budget cannot
leave previously attempted work stuck queued; it becomes uncertain conservatively.
HTTP connects pin freshly validated public DNS answers,
retain original Host/TLS identity, disable environment proxies and redirects, and
never disable TLS verification. Credentials are dedicated references, not global
provider/application secrets. Shutdown cancellation retains fenced in-flight
claims for conservative recovery; idle DB/client failures cannot kill the app.

## Migration and validation policy

`0030` is additive after `0029_engine_persistence_contracts`: new outbox/history
tables and non-null `{}` configuration defaults, without inference or backfill of
old effects. Routing outcomes/history reject UPDATE/DELETE; outbox identity rejects
rewriting/deletion while fenced lifecycle fields remain mutable.

Downgrade refuses **before DDL** if outbound rows exist or non-default signature/
delivery configuration would be lost. Preserve a reviewed pre-upgrade backup for
populated rollback. Empty-outbox legacy bearer configurations can round-trip
`0029 → 0030 → 0029 → 0030` without rewriting existing rows. No `create_all`.

Offline tests cover atomic rollback, duplicates/conflicts, restart, stale owners,
accepted-then-timeout, explicit reconciliation, attempt limits, cancellation,
SSRF transport pinning, signature failures and honest protocol checks.
`postgres` tests require the existing disposable migrated `postgres_url` fixture,
including genuine concurrent claims and a real database `SELECT 1` probe.
Offline synthetic transports are not evidence of a live vendor capability,
receiver idempotency, business verification or production exactly-once delivery.
