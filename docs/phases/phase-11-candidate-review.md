# Phase 11 — Candidate Lifecycle & Human Review

- **Depends on:** Phase 10
- **Traceability:** SPEC candidate lifecycle, semantic events; OC-007, OC-016 (advisory reviews as evidence)

## 1. Goal

Give humans full control of candidates: collect evidence, reject, request review, decide — with append-only history and no auto-activation.

## 2. Non-goals

- No evaluation scores (Phase 13) or ontology promotion (Phase 14).

## 3. Constraints

- State machine: `discovered → candidate → collecting_evidence → validating → approved → active` (v0.1 may expose `candidate/rejected/active` but storage must allow full enum). Illegal transitions rejected.
- Minimum distinct evidence policy (e.g. ≥5 distinct observations) before review completion.
- Rejection is audited with reason; “approved” from a model has zero authority — only human reviewer action counts (and still needs Phase 13–14 gates for activation).

## 4. Tasks

### Engine

1. `POST .../candidates/:cid/collect` (attach unknown ids, dedup), `POST .../candidates/:cid/request-review`, `POST .../candidates/:cid/review { decision: approve|reject|needs_evidence, rationale }`, `POST .../candidates/:cid/reject { reason }`.
2. Guard: insufficient evidence → 409; illegal transition → 409; reviewer role required (via control-plane).
3. Events: `candidate.updated`, `candidate.rejected`; supervisor `review_completed` can attach as advisory evidence (never auto-approves).

### Portal

`/projects/:id/discoveries/:cid`: timeline (created → evidence → review), evidence manager (add/remove with provenance), review panel (decision radio + rationale textarea, Zod required), reject dialog. Show “No Activate button” explicitly. Insufficient-evidence banner blocks review completion.

## 5. Data & migrations

`candidate_reviews (id, candidate_id, reviewer, decision, rationale, created_at)` append-only; status transitions via events, not in-place rewrites.

## 6. API

- `POST .../candidates/:cid/collect`, `/request-review`, `/review`, `/reject`
- `GET .../candidates/:cid/history` (audit trail)

## 7. Portal routes

| Route | Expected |
|---|---|
| `/projects/:id/discoveries/:cid` | Evidence count, review CTA, history timeline |

## 8. Seeder + credentials

`pnpm seed:portal-phase-11`: candidate with 3 evidences (below threshold) + one with 8 (reviewable). Reviewer can review; viewer cannot.

## 9. Manual browser tests

| # | Action | Expected |
|---|---|---|
| 1 | Try approve 3-evidence candidate | Blocked: “collect more evidence (3/5)” |
| 2 | Add 2 more evidences → approve | Moves to `approved` (still inactive — needs Phase 13–14) |
| 3 | Reject with reason | Status rejected + audit entry; no re-activation path |

## 10. Automated tests

Unit: state machine; duplicate evidence rejected. Integration: illegal transition 409; rejection audited; provider cannot activate.

## 11. Acceptance

- [ ] No automatic activation exists in code or UI.
- [ ] All decisions append-only with actor/rationale.

## 12. Risks

Reviewer fatigue → needs-evidence state + assignment + batch view (Phase 15 aggregates).
