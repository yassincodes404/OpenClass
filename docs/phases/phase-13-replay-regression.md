# Phase 13 — Replay Evaluation & Regression Gates

- **Depends on:** Phase 12
- **Traceability:** SPEC §§68–74 (baseline/candidate replay, metrics, regression limits); OC-008 (full), OC-033 fail-closed rule

## 1. Goal

Prove a candidate improves quality without regressions: replay the same verified set against baseline and candidate, compare metrics, enforce gates. Until this passes, promotion stays fail-closed.

## 2. Non-goals

- No ontology writes (Phase 14). No auto-promotion on pass.

## 3. Constraints

- Evaluate same immutable dataset against both versions. Compare: known accuracy, macro F1, UNKNOWN precision/recall, coverage, false novelty, duplicate concepts, latency, cost.
- Failed evaluation blocks promotion (hard gate). Empty/undefined metrics explicit, never “passed”.
- Evidence counts/predictions cannot fabricate passing scores (OC-033 correction).

## 4. Tasks

### Engine

1. `POST /projects/:id/evaluations { dataset_id, baseline_version_id, candidate_id }` → runs deterministic replay (no LLM per example beyond provider under test), persists `evaluation_runs` + `evaluation_results`.
2. Metrics: accuracy, macro F1 (hand-checked fixtures), unknown P/R, coverage, false-novelty rate, duplicate-concept rate, p50 latency, est. cost.
3. Gates config: e.g. `min_delta_accuracy ≥ 0`, `no_billing_regression`, `false_novelty ≤ threshold`. `GET .../evaluations/:eid` returns pass/fail per gate + overall.
4. Events: `evaluation.started/completed`.

### Portal

Route `/projects/:id/evaluations/:eid`: baseline vs candidate table, delta chips (green/red), gate checklist, cost/latency comparison, “Ready for human approval” only when all gates pass (still needs Phase 14 human step).

## 5. Data & migrations

`evaluation_runs`, `evaluation_results`; Alembic.

## 6. API

- `POST /api/v1/projects/:id/evaluations`
- `GET /api/v1/projects/:id/evaluations`, `GET .../evaluations/:eid`

## 7. Portal routes

| Route | Expected |
|---|---|
| `/projects/:id/evaluations/:eid` | Cancellation 0%→91% demo; billing no-regression; overall pass/fail |

## 8. Seeder + credentials

`pnpm seed:portal-phase-13`: one passing eval (cancel improves, billing holds) + one failing eval (billing regression → blocked). Owner runs evals.

## 9. Manual browser tests

| # | Action | Expected |
|---|---|---|
| 1 | Open passing eval | All gates green; “ready for human approval” (not auto-promoted) |
| 2 | Open failing eval | Red billing gate; “blocked” banner; promotion button disabled (Phase 14 respects this) |

## 10. Automated tests

Unit: metric math on hand-computed fixtures. Integration: same-dataset-both-versions; failed eval blocks promotion API (409). Regression: billing fixture must not drop.

## 11. Acceptance

- [ ] Central E2E (known→unknown→cluster→candidate→evaluate) reaches pass/fail honestly.
- [ ] No fake passing loop.

## 12. Risks

Flaky provider → pin deterministic mock for eval replay; document live-provider variance separately.
