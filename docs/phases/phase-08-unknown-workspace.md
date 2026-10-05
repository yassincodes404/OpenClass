# Phase 08 — UNKNOWN Workspace

- **Depends on:** Phase 06–07
- **Traceability:** SPEC §§6–17 (unknown pool, novelty features); OC-005 (pre-grouping: storage/triage only)

## 1. Goal

Answer “What is our system failing to understand?” with UNKNOWN volume/trends, filters, and triage — without implying new classes.

## 2. Non-goals

- No embeddings/clustering (Phase 09). No candidates/discovery (Phase 10). No promotion.
- No automatic labeling of unknowns.

## 3. Constraints

- UNKNOWN categories are descriptive only: `truly_novel|ambiguous|out_of_scope|missing_info|schema_problem`. Assigning a category never creates a class.
- Triage never mutates runs/ontology; it only updates evidence status/assignee/notes.
- Sensitive content visible only to workspace members with viewer+ role.

## 4. Tasks

### Engine

1. `GET /api/v1/projects/:id/unknowns?state&category&query&cursor=` + `GET .../unknowns/:uid` (run ref, distribution, score/reasons, recurrence count).
2. Triage: `POST .../unknowns/:uid/triage { category, assignee?, note? }`, `POST .../unknowns/:uid/transition { to: needs_evidence|triaged|dismissed }` with validation.
3. Trends aggregation: `GET .../unknowns/stats?bucket=day&from&to` → volume, rate vs known, top phrases (redacted).

### Control-plane

Proxy + auth; enforce viewer+ read, reviewer+ triage.

### Portal

Route `/projects/:id/unknowns`: KPI cards (volume, UNKNOWN rate, recurring phrases), trend chart (SVG, no heavy chart lib yet), filters (state/category/search/date), table, detail drawer (distribution, reasons, assign, transition buttons). “Not a new-class proposal” hint always visible.

## 5. Data & migrations

`unknown_events` indexes `(project_id, created_at)`, `(project_id, status)`; add `category, assignee, triage_note` if missing via Alembic.

## 6. API

- `GET /api/v1/projects/:id/unknowns`, `GET .../unknowns/:uid`, `GET .../unknowns/stats`
- `POST .../unknowns/:uid/triage`, `POST .../unknowns/:uid/transition`

## 7. Portal routes

| Route | Expected |
|---|---|
| `/projects/:id/unknowns` | KPIs + trend + table; seeded cancellation unknowns visible |
| `/projects/:id/unknowns?category=missing_info` | Filtered list |
| `/projects/:id/unknowns/:uid` (drawer/modal) | Distribution + triage controls |

## 8. Seeder + credentials

`pnpm seed:portal-phase-08`: 30 unknowns (15 cancel variants, 8 account-compromise, 7 ambiguous), 2 assigned to reviewer. Owner/reviewer triage; viewer read-only.

## 9. Manual browser tests

| # | Action | Expected |
|---|---|---|
| 1 | Open unknowns | Volume/rate + recurring “cancel” phrase shown |
| 2 | Filter `likely_novel` + search “cancel” | Only matching rows |
| 3 | Triage one as `missing_info` + assign reviewer | Status updates, audit entry, ontology unchanged |
| 4 | Try to “promote” from here | No such button (correct) |

## 10. Automated tests

Unit: stats bucketing, transition validation. Integration: triage audit, cross-project block, pagination. UI: filters persist in URL.

## 11. Acceptance

- [ ] Trends + triage work; no ontology mutation path exists here.
- [ ] Categories are advisory only.

## 12. Risks

PII in unknown text → redaction + access control + export disabled until Phase 18.
