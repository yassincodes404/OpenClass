# False start 1: development baseline (2026-10-16)

## What happened

The first `development --variant baseline --languages en ar` attempt aborted with
`http_status_503` before executing any case. Cause: driver setup error. The
experiment engine database (SQLite at `.unlazy/laya-runtime/experiment.db`) had
not been migrated; the engine correctly refuses `create_all` at startup, so the
very first API call (`POST /api/v1/projects`) returned 503 "Database
unavailable". Resolved by running `alembic upgrade head` against the experiment
database and re-probing (200).

## Evidence that zero experiment effects occurred

- Daemon runtime proof `forward_calls` was 1 before the attempt and 1 after
  (the single call is the documented non-dataset warm-up prediction).
- The engine project list was empty after the failure (nothing persisted).
- The attempt output `ml-development-baseline/` contains only
  `preregistration.json` and `runtime-proof.json`; no `examples.jsonl` exists.
- The false-start claim is preserved as
  `development-baseline.started-false-start-1.json` (renamed, not deleted).

## Authorization

The frozen contract prohibits automatic rerun of a claimed phase. The operator
explicitly authorized one retake of `development --variant baseline` with the
false-start claim preserved in the audit trail (session approval, 2026-10-16).

The retake writes to a new exclusive output directory
`ml-development-baseline-r1/`.
