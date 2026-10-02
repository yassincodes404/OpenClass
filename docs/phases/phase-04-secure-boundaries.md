# Phase 04 — Secure Production Boundaries

- **Depends on:** Phase 03
- **Traceability:** SPEC §§24–27, 39–41 (secrets, redaction, logging, rate limits); OC-003 (RFC-0001, partial: safe errors, redaction, telemetry)

## 1. Goal

Make the system safe for real customer text: secret handling, provider safety, redaction, rate limiting, audit logging, pagination/idempotency foundations. This is the “Secure the Engine” gate before high-volume ingestion.

## 2. Non-goals

- No new product features (no clustering/discovery/eval). Only hardening.
- No SSO/SAML, VPC, or enterprise compliance certifications (Phase 19–20).

## 3. Constraints

- Secrets via env or encrypted store refs; never in DB plaintext, logs, errors, events, or fixtures.
- Provider failures → safe `502` with sanitized `provider.error` event; no stack/secret leakage.
- Request-content logging disabled by default; redaction controls explicit.
- `auto_promote`/`auto_alias` default `false` (already required by SPEC).

## 4. Tasks

### Engine + control-plane

1. Secret refs: `OPENCLASS_*_API_KEY` env; reject credentials in request bodies (`reject_credentials` already in engine — extend to all project routes).
2. Redaction: PII-ish patterns + configurable blocklist; redacted copy for logs/events; original stored per retention policy only.
3. Rate limits: per-key + per-workspace token bucket (e.g. 60/min ingest, 300/min classify), `429 + Retry-After`, headers.
4. Audit log: append-only `audit_events` / control-plane equivalent; actor, action, target, timestamp; cursor pagination.
5. Pagination + idempotency: `?limit/offset/cursor` on lists; `Idempotency-Key` on ingest/create; duplicate key returns original (no dup writes).
6. Timeouts/retries: provider timeout 20s default, max 2 bounded retries, jitter; telemetry (model, latency, tokens, cost, errors, retries).

### Portal

Routes: `/projects/:id/settings` (provider/redaction/retention controls), `/projects/:id/providers` (status, safe error display), `/projects/:id/audit` (filterable log). Show “secrets are never displayed” hints; masked values only.

## 5. Data & migrations

Add if missing: `provider_usage`, `audit_events` indexes, `idempotency_keys (key unique, workspace_id, response_hash, created_at, expires_at)`. Alembic + control-plane SQL.

## 6. API

- `GET /api/v1/providers/status`, `GET /api/v1/providers` (already exist — harden error shape).
- `GET /control/audit?workspace=&cursor=` → `{ items, next_cursor }`
- All lists support `limit ≤ 100`, `cursor`; all mutating ingest routes support `Idempotency-Key`.

## 7. Portal routes

| Route | Expected |
|---|---|
| `/projects/:id/settings` | Redaction toggles persist; secrets fields are write-only |
| `/projects/:id/providers` | Status cards; failure shows safe message, no key |
| `/projects/:id/audit` | Paginated log; filters work |

## 8. Seeder + credentials

`pnpm seed:portal-phase-04`: enables strict redaction on demo project, creates one rate-limit test key, emits one sanitized provider error fixture. Login: owner/admin for settings; reviewer read-only.

## 9. Manual browser tests

| # | Action | Expected |
|---|---|---|
| 1 | Save provider key in settings | Success, value masked, never appears in network response after save |
| 2 | Trigger provider failure (bad endpoint) | Friendly error + `provider.error` event, no secret in payload |
| 3 | Send same ingest twice with same Idempotency-Key | Second returns original id, no duplicate count |
| 4 | Exceed rate limit | 429 + Retry-After; UI shows “slow down” message |
| 5 | Open audit log | New actions appear with actor/timestamp; pagination works |

## 10. Automated tests

Unit: redactor, key hash, rate limiter, idempotency dedup. Integration: secret rejection, 429, pagination cursors, audit append-only (UPDATE/DELETE rejected). Contract: error schema has no `secret|key|token` fields. Security: grep logs/fixtures for secrets fails if found.

## 11. Acceptance

- [ ] No secret in logs/errors/events/fixtures (automated check).
- [ ] Rate limiting + idempotency verified.
- [ ] Audit log complete and paginated.
- [ ] Request logging off by default.

## 12. Risks

Over-redaction breaking debugging → keep `request_id` correlation without content. Rate-limit false positives → per-key tuning + clear 429 UX.
