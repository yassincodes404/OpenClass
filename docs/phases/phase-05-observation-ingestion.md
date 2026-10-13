# Phase 05 — Observation Ingestion

- **Depends on:** Phase 04
- **Traceability:** SPEC §§6–17 (observation → unknown pool), §§24–27 (observations, classification_runs); OC-010 (ingest, pagination, idempotency)

## 1. Goal

Reliably ingest customer text as observations (single, batch, CSV/JSON) with validation, deduplication, and history — the entry to the UNKNOWN loop.

## 2. Non-goals

- No classification quality changes (Phase 06). No embeddings/clustering (Phase 09).
- No webhook integrations yet (Phase 16 has Zendesk/Intercom; this phase has generic webhook + file import only).

## 3. Constraints

- Text observations only; API uses `classify/observe` naming, not `classify_text` (SPEC).
- Atomic writes: observation + audit + receipt commit together; failures roll back all.
- Idempotency-Key + content hash dedup; concurrent identical deliveries commit once.
- PII redaction from Phase 04 applies before storage/display.

## 4. Tasks

### Engine

1. `POST /api/v1/projects/:id/events` (single), `POST .../events:batch` (up to 500), CSV/JSON import endpoint or CLI helper; fields: `content (1–10000 chars)`, `source_type: text|json|csv|webhook`, `metadata: {}`, `idempotency_key?`.
2. Validation: blank → 400; oversized → 413; bad metadata → 400; dedup: `(project_id, content_hash, source)` + idempotency table.
3. `GET .../events?cursor=` paginated; `GET .../events/:eid` detail with classification history link.
4. Events emitted: `observation.created` (if new event bus) or reuse audit; never emit content when logging disabled.

### Control-plane

Proxy with workspace auth + rate limits; map engine ids to control-plane display; enforce per-workspace quotas (e.g. 10k/month demo cap with clear 402/429 message — no real billing yet).

### Portal

Routes: `/projects/:id/data` (ingest tabs: Text / JSON / CSV, file drop, preview, idempotency key auto-generated, progress), `/projects/:id/observations` (search, source filter, date filter, detail drawer with history). Use React Hook Form + Zod, TanStack Query infinite scroll.

## 5. Data & migrations

Ensure `raw_events (id, project_id, content, content_hash, source_type, metadata jsonb, created_at)` + indexes `(project_id, created_at)`, unique `(project_id, content_hash)` where appropriate; `webhook_receipts` already in `0010` — reuse pattern.

## 6. API

- `POST /api/v1/projects/:id/events` → 201 `{ id, deduped: false }` or 200 `{ id, deduped: true }` on repeat key
- `POST /api/v1/projects/:id/events:batch` → 207 multi-status with per-item ok/error
- `GET /api/v1/projects/:id/events?limit&cursor=` → `{ items, next_cursor }`

## 7. Portal routes

| Route                        | Expected                                                                         |
| ---------------------------- | -------------------------------------------------------------------------------- |
| `/projects/:id/data`         | Paste text → success toast with event id; CSV upload shows parsed count + errors |
| `/projects/:id/observations` | New events appear first; search/filter work; detail shows metadata + timestamps  |

## 8. Seeder + credentials

`pnpm seed:portal-phase-05`: ingests 25 deterministic support texts (billing, refund, delivery, cancel, account_access + 5 unknowns like “Someone changed my account email without permission”). Idempotent via fixed idempotency keys. Login: owner to ingest; reviewer read-only.

## 9. Manual browser tests

| #   | Action                       | Expected                                      |
| --- | ---------------------------- | --------------------------------------------- |
| 1   | Ingest “I was charged twice” | 201, appears in observations                  |
| 2   | Re-send same with same key   | `deduped: true`, count unchanged              |
| 3   | Upload CSV with 1 bad row    | 207, good rows saved, bad row error shown     |
| 4   | Search “refund”              | Only matching observations                    |
| 5   | Open detail                  | Metadata + history visible; no secret leakage |

## 10. Automated tests

Unit: validators, hash, CSV parser. Integration: concurrent identical → 1 row; retry survives restart; cross-project lookup blocked (404). E2E: ingest → list → detail round-trip.

## 11. Acceptance

- [ ] Single/batch/CSV all work with validation and dedup.
- [ ] History paginated and restart-safe.
- [ ] Redaction + auth + rate limits hold.

## 12. Risks

CSV encoding issues → detect UTF-8, report row numbers. Large batches → cap 500, background import job id (pollable) if needed.
