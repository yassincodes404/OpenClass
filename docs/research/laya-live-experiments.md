# Frozen bilingual Laya live experiments

This is a **new experiment**, not reconstructed historical evidence. The missing
65 historical reports remain **unverified**. Nothing here replaces them or proves
Discovery complete. No measured model results are asserted by this source document.

## Pre-inference task and labels

Three known labels are fixed: BILLING (existing invoices, payments, refunds),
TECHNICAL (application defects/outages), SALES (new purchasing/prices/quotes).
UNKNOWN is permanent: unrelated domains, cancellation/account changes, insufficient
information, or conflicting active intents without priority. Classify the active
request, not negated distractors or quoted instructions. A refund is BILLING even
after cancellation; cancellation alone is UNKNOWN. An observation cannot change
the routing policy.

Every label has this provenance:

> Droid-authored synthetic task labels, not human-expert-reviewed, never model-derived

These labels evaluate adherence to a deliberately bounded policy; they are not
verified expert ground truth or representative samples of real customer traffic.
No provider prediction becomes a label, ontology mutation, or promotion evidence.

`artifacts/laya-live-experiments/dataset/cases.jsonl` contains 120 observations:

| Split       | English | Arabic | Per label per language |
| ----------- | ------: | -----: | ---------------------: |
| development |      24 |     24 |                      6 |
| holdout     |      36 |     36 |                      9 |

Sixty semantic groups each contain an English/Arabic translation pair. Both members
stay in the same split. Cases include known paraphrases, negation, instruction-like
observations, out-of-domain requests, cancellation/account changes, insufficient
information, and conflicting intents. They were independently authored without
model outputs. The dataset is small and synthetic; similar support concepts can
occur in both splits, but translations/near-template instances are not split
across them. Exact NFKC/casefold/whitespace-normalized duplicates are rejected.

`manifest.json` records policy, both predeclared instruction configurations, group
membership, provenance, per-split hashes and canonical dataset hash. Each case has
a canonical hash excluding its own `sha256`. Canonical JSON is sorted-key UTF-8,
non-ASCII preserved, compact separators, nonfinite numbers prohibited.

Frozen hashes:

- dataset: `a98c3697ef2df8c2f5038277bcacab44bfeea8288e0e7409b8a2397424220073`
- development: `ab97ff7483775b59654067e9a0c88c07c94c4e7f02bf11f1bf87eb5dbbf45ab9`
- holdout: `0db536e66c12f57d5c67ea0085f168598143359819e5a0c6a92e5501cdfcbaf5`

The baseline states the domain policy. The only permitted development variant,
`clarified`, additionally explains negation, conflicting intents, and untrusted
observation instructions. It is already frozen, not generated after holdout.

## Runtime/driver boundary

The driver installs and starts official Laya, pins Hugging Face revisions, verifies
weights, instruments actual model forwards, measures loading/resources, and starts
an owned disposable migrated OpenClass instance. Use one loaded checkpoint at a
time. Do not use model download metadata or `real_inference=true` as forward proof.
No inference, package installation, weight download, teacher, or model import
occurs in the dataset/metrics modules or offline tests.

The runner accepts a driver-generated JSON proof with these required fields:

```json
{
  "checkpoint": "official repository identity",
  "revision": "40 lowercase hexadecimal commit characters",
  "weight_files": { "relative weight filename": "64 lowercase hexadecimal SHA256 characters" },
  "model": "exact model string persisted by the OpenClass Laya adapter",
  "device": "actual inspected device",
  "backend": "actual inspected backend",
  "packages": { "distribution": "installed version" },
  "forward_calls": 1,
  "forward_instrumentation": {
    "method": "driver's actual instrumentation and evidence references"
  },
  "cold_start_ms": null,
  "memory": null
}
```

This is a **schema illustration, not execution evidence**. `forward_calls` must
be an actual positive measured count, not a constant copied from this illustration.
`cold_start_ms` is measured checkpoint loading/startup time supplied by the driver,
not inferred from API latency. `memory`, if measured, should state units, method,
sampling interval, process scope and actual RAM/VRAM observations. Missing
measurements remain null. Never include credentials, environment dumps, absolute
cache paths containing private data, or unsanitized provider errors.

The runner structurally validates claims and hashes the exact copied proof file.
It cannot independently establish their truth or attribute experiment forwards to
a prior smoke count. The driver must retain before/after forward counters and
request-correlated instrumentation for each phase, plus weight revision/file
verification and device/parameter inspection. Include the resulting phase evidence
alongside runs; do not alter frozen per-phase proof copies after execution.

## Commands and phase outputs

Run from the worktree root using its runtime-capable Python after driver setup.
The following PowerShell commands do **not** install or start anything:

```powershell
python -m scripts.laya_experiments.runner prepare
$runs = "artifacts/laya-live-experiments/runs"
$proof = "$runs/multilingual-runtime-proof.json"
python -m scripts.laya_experiments.runner development --variant baseline --languages en ar --runtime-proof $proof --output "$runs/ml-development-baseline" --base-url http://127.0.0.1:7331 --owned-local-target
# Inspect DEVELOPMENT metrics/errors and record whether clarification fixes them.
python -m scripts.laya_experiments.runner development --variant clarified --languages en ar --runtime-proof $proof --output "$runs/ml-development-clarified" --base-url http://127.0.0.1:7331 --owned-local-target
python -m scripts.laya_experiments.runner lock --development "$runs/ml-development-baseline" --development "$runs/ml-development-clarified" --lock "$runs/ml-lock.json"
$variant = (Get-Content "$runs/ml-lock.json" -Raw | ConvertFrom-Json).variant
python -m scripts.laya_experiments.runner holdout --variant $variant --languages en ar --runtime-proof $proof --lock "$runs/ml-lock.json" --output "$runs/ml-holdout" --base-url http://127.0.0.1:7331 --owned-local-target
python -m scripts.laya_experiments.runner report --output "$runs/ml-holdout"
python -m scripts.laya_experiments.runner verify --output "$runs/ml-holdout"
```

The driver must stop/unload multilingual before loading English. For the official
English-only checkpoint, repeat with a distinct proof, output names and lock,
using `--languages en` in **every** development/holdout command. Do not interpret
English-only checkpoint results as Arabic capability. Report language/checkpoint
cohorts separately.

Authentication, if required, uses only `LAYA_EXPERIMENT_INTERNAL_TOKEN` from the
process environment, sent as `X-OpenClass-Internal-Token`. It is never a CLI
argument, logged field, or artifact value. No `.env` loading occurs. The runner
requires explicit `--owned-local-target` and a literal loopback HTTP IP with port;
DNS hosts, credentials in URLs, external URLs, redirects, and environment proxies
are rejected/disabled. Only synthetic observations may be sent.

Outputs:

- `prepare`: frozen dataset manifest; existing files are verified, never replaced.
- `development`/`holdout`: exclusive directory containing preregistration,
  runtime proof copy, append-only `examples.jsonl`, metrics and completion manifest.
  Stdout gives path/count/failure count, not predictions. Holdout also copies lock.
- `lock`: new immutable JSON selecting equal-language mean development macro-F1,
  then accuracy, then baseline on ties. Failed/incomplete cohorts cannot be selected.
  Baseline is mandatory; at most one clarified variant is accepted.
- `report`/`verify`: offline hash/cohort/metric checks and per-language summaries.
  Verification explicitly does not independently verify model execution.

Every attempt is claimed exclusively under `runs/cohorts/<identity hash>/`.
Identity binds dataset, checkpoint revision/weight hashes/model and language cohort.
Only one attempt per development variant and one holdout attempt are allowed.
Selection closes development, and copying a lock or changing output directories
does not permit another holdout. A crash/failed attempt leaves its claim and partial
artifacts intact; no automatic retry or tuning is permitted. Report the failure and
seek explicit authorization for a distinct experiment rather than deleting claims.
These are audit gates, not protection against a malicious local file editor.

The holdout phase rejects a missing/mismatched/unregistered lock, changed source
commit or source hashes, changed labels/configuration/splits, different checkpoint,
different language cohort, changed development manifests/results, or a prior attempt.
The lock binds all five data/runner module hashes; finalize source **before**
development. Do not commit/change HEAD between development and holdout. The driver
may restart the same checkpoint, providing a new proof with identical checkpoint
identity; changed forward counters alone do not change identity.

## HTTP persistence contract

Bounded `httpx` is used rather than the SDK because the SDK constructor does not
expose `trust_env=False`. No backend/repository/database imports or `create_all`
are used. All API effects use the public project endpoints:

1. Create a fresh owned experiment project and a fresh service with explicit
   `provider_override=laya` and frozen choices/instructions.
2. For each case, POST `/api/v1/projects/{project}/events` with synthetic metadata.
   GET the returned event, verify content/project/hash, then POST
   `/decision-services/{service}/runs` with that exact `raw_event_id`.
3. GET the returned run. Require exact response/readback equality, matching
   project/service/event/model/instructions, Laya provider, complete finite
   distribution summing to one including UNKNOWN, and no simulated/fallback mode.
4. Read paginated `/evidence`, locate the run's records, GET each item, and verify
   event/service/provider/model/selected label/distribution links. Non-TRUSTED
   outcomes require persisted low-trust/UNKNOWN evidence.

`paused` is valid successful inference with review required. It is not silently
resumed for metrics. Semantic UNKNOWN is a prediction, not a transport error.
Failed HTTP/contract cases preserve safe fixed error codes and null prediction;
server error bodies, tokens, claim tokens and arbitrary provider metadata are not
persisted. Only allowlisted run/evidence fields are retained.

Each result includes case hash, language/checkpoint/split/category, expected label,
prediction, trust, API elapsed time, event/run/evidence readback, error or success,
and per-example hash. Manifest includes source commit/file hashes, package versions,
dataset/split/configuration hashes, actual counts/failures, canonical/file result
hashes, runtime-proof hash, lock hash, optional driver cold start/memory, and the
historical-evidence limitation. Hashes establish integrity, not real inference.

## Metrics and interpretation

Per language/checkpoint/split: count, successful inferences, failures, accuracy on
successful results plus all-attempt accuracy, fixed-four-class macro-F1, complete
confusion matrix, UNKNOWN precision/recall, semantic coverage (non-UNKNOWN among
successful inferences), trusted coverage (TRUSTED among all attempts), trusted
error count/rate, safe failure categories and misclassified case IDs/categories.
An unsupported class contributes zero to fixed-label macro-F1; entirely empty
semantic cohorts return null. Zero UNKNOWN denominator, no trusted samples, and
missing latency return null rather than invented zero values.

Warm API p50/p95 use inclusive/type-7 interpolation at `(n-1)*p`. The first
execution API call in each phase is separately excluded, irrespective of language;
remaining measured successful/failed execution requests enter warm timings.
Elapsed time covers execution POST, not ingest/readback; pre-execution failures
have null latency. Separate cold start/memory come only from actual driver proof.
Zero trusted coverage is legitimate under an uncalibrated profile; no ECE,
calibration, quality threshold, or capability claim is implied.

## Application graph / pause-resume driver proof

The source runner intentionally does not modify graphs or act as a Teacher.
Use a separate driver-owned fresh project and the same instrumented Laya profile
to create a public-HTTP two-node service, retain its service/version/hash, ingest
synthetic state, execute, and read persisted steps/checkpoint/evidence. For a
REVIEW/UNKNOWN pause, inspect `checkpoint_revision`, `current_node_key`, and
`pending_operation`; resume through the public SDK with that expected revision
and node, explicit operator/rationale and a reviewed valid choice, then read back
the resulting checkpoint/run/audit records. Operator approval is not model truth.
If the next node still returns REVIEW, preserve the repeated pause honestly.

Also stop the owned Laya process and execute a separate development-only synthetic
probe: require visible provider/HTTP failure and no new successful simulated run.
Retain failure audit evidence, then restart only under driver ownership. Do not
reuse or consume holdout to test availability.

This demonstrates inference, persistence and operator control only. Full evolution
requires a separately configured real Teacher/discovery provider, independently
verified evidence, replay evaluation and human review. Laya is not that Teacher.

## Offline validation

```powershell
& "D:\Projects 2\OpenClass\.venv\Scripts\python.exe" -m pytest -q tests/unit/test_laya_experiments.py
& "D:\Projects 2\OpenClass\.venv\Scripts\ruff.exe" check scripts/laya_experiments/__init__.py scripts/laya_experiments/dataset.py scripts/laya_experiments/metrics.py scripts/laya_experiments/runner.py scripts/laya_experiments/verify.py tests/unit/test_laya_experiments.py
```

Tests use explicitly SIMULATED HTTP/runtime-proof fixtures, not Laya or Torch.
They cover hand-computed metrics/nulls, group/split/hash leakage, frozen data,
credential-header isolation/redirect rejection, ingestion/run/evidence persistence,
fail-closed provider/malformed-result handling, result hashes and lock/attempt gates.
They do not run or produce holdout predictions.
