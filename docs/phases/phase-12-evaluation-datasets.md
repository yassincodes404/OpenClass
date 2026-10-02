# Phase 12 — Verified Evaluation Datasets

- **Depends on:** Phase 11
- **Traceability:** SPEC §§68–74 (evaluate same verified set, historical/recent/rare/hard/unknown/adversarial); OC-008 (partial: datasets only)

## 1. Goal

Create trustworthy ground truth: immutable evaluation datasets with human/verified label provenance — the only basis for later replay.

## 2. Non-goals

- No replay scoring yet (Phase 13). No promotion.

## 3. Constraints

- Ground truth comes only from human or verified external labels. Predictions never become ground truth automatically (enforced in code + UI copy).
- Datasets immutable once sealed; examples versioned; empty/undefined metrics explicit later.
- Must include historical, recent, rare, hard, unknown, adversarial slices.

## 4. Tasks

### Engine

1. `POST /projects/:id/eval-datasets { name, description }`, `POST .../datasets/:did/examples { text, label|UNKNOWN, source: human|verified_external, annotator, rationale? }`, `POST .../datasets/:did/seal` (locks).
2. Validation: label must be existing class or UNKNOWN; duplicate text flagged; `source=prediction` rejected (400 “predictions cannot be ground truth”).
3. `GET .../eval-datasets`, `GET .../datasets/:did` (examples, provenance, sealed flag).

### Portal

Routes: `/projects/:id/evaluations` (dataset cards: size, sealed badge, slice coverage), `/projects/:id/evaluations/datasets/:did` (example table with provenance chips, import via CSV/JSON, seal button with confirmation).

## 5. Data & migrations

`evaluation_sets`, `evaluation_examples (dataset_id, text, label, source, annotator, created_at)`, seal flag; Alembic.

## 6. API

- `POST /api/v1/projects/:id/eval-datasets`, `POST .../datasets/:did/examples`, `POST .../datasets/:did/seal`
- `GET .../eval-datasets`, `GET .../datasets/:did`

## 7. Portal routes

| Route                                     | Expected                                              |
| ----------------------------------------- | ----------------------------------------------------- |
| `/projects/:id/evaluations`               | Seeded dataset with 40 examples, sealed badge         |
| `/projects/:id/evaluations/datasets/:did` | Provenance per row; “prediction” import fails clearly |

## 8. Seeder + credentials

`pnpm seed:portal-phase-12`: dataset `support-gold-v1` (30 known incl. rare/hard + 10 UNKNOWN/adversarial, all `source: human`). Owner seals; reviewer annotates; viewer read-only.

## 9. Manual browser tests

| #   | Action                                | Expected                           |
| --- | ------------------------------------- | ---------------------------------- |
| 1   | Add example with `source: prediction` | 400 with clear message             |
| 2   | Seal dataset → try edit               | Blocked (immutable)                |
| 3   | Import CSV with bad label             | Row-level error, no partial commit |

## 10. Automated tests

Unit: label validation, seal immutability. Integration: sealed dataset rejects writes; provenance required.

## 11. Acceptance

- [ ] No prediction-derived ground truth possible.
- [ ] Slices cover required case types.

## 12. Risks

Label bias → require annotator + rationale fields; document sampling strategy.
