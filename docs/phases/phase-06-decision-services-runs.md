# Phase 06 — Decision Services & Runs

- **Depends on:** Phase 05
- **Traceability:** SPEC §§6–17 (DecisionProvider, novelty assessment), §57 provider/service steps; OC-003/OC-004 (provider wiring), OC-016 (reviews read runs)

## 1. Goal

Turn observations into governed decisions: configurable decision services with permanent UNKNOWN, persisted runs with probabilities/latency/provider metadata.

## 2. Non-goals

- No embeddings/discovery/eval/promotion. No auto-routing to external systems (Phase 16).

## 3. Constraints

- `UNKNOWN` is permanent and selectable as fallback; it is never a domain choice id `unknown` in ontology (SPEC canonical rule).
- Probabilities include UNKNOWN, finite, sum to 1 within tolerance; distribution keys exactly match inference version.
- Thresholds configurable per service; `auto_promote=false`.
- Every run persists: input ref, service/version, distribution, selected choice or UNKNOWN, novelty score/reasons, provider/model, latency/tokens/cost, timestamps.

## 4. Tasks

### Engine

1. Decision service CRUD: `POST /projects/:id/decision-services { name, instructions, choices[] }`, validate choice keys uppercase, auto-append UNKNOWN fallback (locked).
2. Run: `POST /projects/:id/decision-services/:sid/runs { event_id | content }` → DecisionProvider → novelty → persist run + unknown_event if `likely_novel`.
3. Novelty features: unknown prob, top-2 margin, normalized entropy, recurrence, provider confidence → `known|uncertain|likely_novel` + score + reasons.
4. `GET .../runs?cursor=`, `GET .../runs/:rid` (full distribution, version ids).

### Control-plane

Proxy with auth/quotas; expose service/run summaries without leaking secrets; enforce per-service rate limits.

### Portal

Routes: `/projects/:id/decisions` (service list + create wizard: name/instructions/choices/thresholds), `/projects/:id/decisions/:sid` (detail + test panel), `/projects/:id/runs` (filter by result/choice, detail with probability bars, UNKNOWN highlighted). Probability UI uses honest percentages; mock runs show `simulated` badge.

## 5. Data & migrations

`decision_services`, `decision_runs`, `decision_probabilities`, `unknown_events` (if not yet). Alembic migration with indexes `(service_id, created_at)`.

## 6. API

- `POST /api/v1/projects/:id/decision-services` → 201 service (with UNKNOWN)
- `POST /api/v1/projects/:id/decision-services/:sid/runs` → 200 run `{ selected_choice|UNKNOWN, state, novelty_score, probabilities }`
- `GET .../runs`, `GET .../runs/:rid`

## 7. Portal routes

| Route                          | Expected                                                                                |
| ------------------------------ | --------------------------------------------------------------------------------------- |
| `/projects/:id/decisions`      | Services listed; create works; UNKNOWN shown locked                                     |
| `/projects/:id/decisions/:sid` | Test “I was charged twice” → `billing`; “Cancel my plan” (if not in ontology) → UNKNOWN |
| `/projects/:id/runs`           | Runs with state chips; detail shows distribution + provider + latency                   |

## 8. Seeder + credentials

`pnpm seed:portal-phase-06`: service `support-router` with 5 choices + UNKNOWN; 10 known runs + 5 UNKNOWN runs. Owner creates services; reviewer can run tests but not edit service (403 on edit).

## 9. Manual browser tests

| #   | Action                          | Expected                                                         |
| --- | ------------------------------- | ---------------------------------------------------------------- |
| 1   | Classify known billing text     | `known/billing`, probs sum ~1, latency shown                     |
| 2   | Classify unmatched cancellation | `likely_novel/UNKNOWN`, saved to unknown pool (visible Phase 08) |
| 3   | Open run detail                 | Full distribution, version ids, provider label                   |
| 4   | Try to delete UNKNOWN choice    | Blocked with message                                             |

## 10. Automated tests

Unit: novelty scoring, prob normalization, thresholding. Integration: run persistence atomicity; unknown creation; restart-safe. Contract: SDK matches OpenAPI.

## 11. Acceptance

- [ ] Known routes correctly; unmatched returns UNKNOWN (never forced choice).
- [ ] All runs persisted with required metadata.
- [ ] UNKNOWN cannot be removed.

## 12. Risks

Threshold mis-tuning → expose defaults + per-service override + guidance text.
