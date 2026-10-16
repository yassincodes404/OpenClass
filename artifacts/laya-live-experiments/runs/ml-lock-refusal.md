# Selection lock refusal (2026-10-16)

## Command

```powershell
uv run python -m scripts.laya_experiments.runner lock `
  --development artifacts/laya-live-experiments/runs/ml-development-baseline-r1 `
  --development artifacts/laya-live-experiments/runs/ml-development-clarified `
  --lock artifacts/laya-live-experiments/runs/ml-lock.json
```

## Result

Exit 2, `cannot select configuration from failed development run`.
No lock file was written. The holdout phase was not attempted.

## Cause (measured, not inferred)

Both development variants executed completely (48/48 cases each, real forwards;
daemon forward counter reconciles exactly: 1 warm-up + 96 case executions = 97).
The dominant failure category is `missing_persisted_unknown_or_low_trust_evidence`
(en 24/24, ar 22/24 baseline; en 24/24, ar 23/24 clarified):

- The engine's provider-neutral supervision places every non-UNKNOWN Laya run
  under `REVIEW` ("Laya provider operates under research calibration
  (conservative supervision)"), pausing the run at a `node_supervision_gate`
  pending operation with a persisted checkpoint (`checkpoint_revision: 1`,
  `current_node_key: default`).
- REVIEW-paused runs persist no decision evidence rows. Only UNKNOWN outcomes
  persist evidence (verified directly against the engine: the baseline project
  holds exactly 2 evidence rows, both UNKNOWN).
- The frozen HTTP persistence contract requires persisted low-trust/UNKNOWN
  evidence for every non-TRUSTED outcome, so these cases are contract failures.
- The lock gate (`scripts/laya_experiments/runner.py` `create_lock`) refuses
  selection from any development run with failures, by design.

`trusted_count` is 0 in every cohort; `semantic_coverage` is 0.0 (ar) or null
(en, empty cohort). Per the frozen metrics policy, zero trusted coverage is a
legitimate measurement under an uncalibrated profile; no quality, calibration,
or capability claim is made.

## Consequence

The holdout cohort remains untouched and unopened. Its claim is not consumed.
No retry, reconfiguration, or tuning was performed. The pause/resume and
fail-closed driver proofs proceed separately per the frozen plan.
