# Empirical Jev contract: research harness

Research only, on `experiment/jev-characterization`. Existing proof scripts and
artifacts remain unchanged. The successor modules are in `scripts/jev_contract/`.
Read [the ADR](../architecture/jev-empirical-contract-adr.md) for decisions and limits.

## Files and reproduction

- `benchmarks/jev-contract/v1/knowledge.json`: typed `JevKnowledgeBase`; observations
  carry status, identity, date, run, scope, values, evidence paths/hashes/pointers,
  strength, limitations and optional recommendations.
- `profile.json`: empirical profile derived from the registry and measurements.
- `calibration-cases.json` and `calibration-labels.json`: independent cases and private
  evaluator labels; only node plus snapshot may be sent to Jev.
- `teacher-packages.json`: bounded Teacher inputs. `teacher-packets.json` contains
  exactly the messages and schema shared by both models. `teacher-hidden.json` stays
  local to the deterministic evaluator; never send it to a Teacher.
- `frozen-teacher-evidence/`: byte-identical source D/E requests, with normalization
  explicitly identified in the new packages. These are not new live results.
- `protocol.json` and `benchmark-sha256.json`: predeclared protocol and input freeze.
- `build/jev-contract-v1/historical-sha256.json`: baseline inventory of 666 preexisting
  local build files, including earlier failed attempts and frozen proof archives.

The registry references local research evidence, not bundled public ground truth.
A clean checkout without that archive can inspect claims and run offline contract tests,
but cannot verify historical hashes. Missing evidence must never be silently accepted.
The focused integrity test skips explicitly if the local artifact archive is absent.

Regeneration is exclusive-create: choose a new version/output directory for a published
registry. The import and preparation modules never overwrite old artifacts:

```bash
uv run python -m scripts.jev_contract.import_evidence
uv run python -m scripts.jev_contract.prepare_benchmarks
```

Those commands intentionally fail when the v1 outputs already exist. They document
how the initial version was authored; they are not a command to mutate a frozen run.

## Experimental Python API

`compile_state(schema, sensor_facts, raw_evidence, resolved)` validates and copies
facts. `JevDecisionCompiler(profile, events).compile(node, snapshot)` returns a
`CompiledDecision` using the existing shared `ChoiceRequest`. Failures are explicit
`ValueError`/`ProviderCompatibilityError`; no model call is made on compilation failure.

`run_graph(graph, world, profile, identity, call, policy, catalog, store, journal)` is
an async bounded execution API. The injected provider call returns typed `ProviderCall`;
`world` supplies `observe()` and registered `execute(step)`. `EventStore` uses a new
run directory and exclusive event files. Call `freeze()` after completion or failure.
A shared `ProfileJournal` is required so a new process cannot forget stale events.

Decision events include profile ID/version/hash, provider/model, node, DecisionSpec,
full snapshot and its hash, choice-set hash, selected choice/probability, complete
normalized distribution including UNKNOWN, top and second probabilities, their margin,
UNKNOWN probability, latency, usage, retries, infrastructure status and simulation flag.
Infrastructure events have **null semantic fields**, never synthetic UNKNOWN. Latency
includes the enclosing call. Missing cost/tokens remain null. Retry counts must come
from the transport, and failures must be included in the call budget.

Runtime events are `decision.completed`, `provider.failed`, `decision.escalated`,
`macro.verified` and `profile.stale`. No provider error body is persisted. Relevant raw
state is deliberately present in these research traces: use authored/nonsecret inputs
and pass configured secrets to `EventStore` so accidental credential persistence fails.
This is not a general production redaction system.

The neutral state/profile/policy boundaries are typed; strict candidate payload checks
and a catalog-specific closed JSON Schema guard the Teacher. `apply_candidate` returns
an inactive copy with a parent content hash. It cannot activate anything.

## Scoring future authorized live runs

The current prepared protocol authorizes zero new live calls. Credentials alone do
not establish an available research budget. Freeze a new run-specific authorization,
model identities, pricing and source hashes before inference. Preserve both successes
and failures; never retry a candidate to improve its first-response score.

```bash
uv run python -m scripts.jev_contract.calibration results.json new-calibration-report.json
uv run python -m scripts.jev_contract.precision responses.json new-teacher-report.json \
  --models google/gemini-2.5-flash STRONGER_MODEL_ID
```

Calibration results map each frozen case ID to `DecisionTelemetry`. The scorer requires
complete case coverage, matching snapshots/choices, a single profile and nonsimulated
responses. It selects rules solely on calibration data before evaluating holdout.

Teacher results are a list of `TeacherResponse` records, one per model/package,
including infrastructure failures. Each binds to the identical packet hash. Inputs to
one model must never contain the other's output. The deterministic evaluator measures
schema/operator/target/payload correctness, graph invariants, macro fixture execution,
regressions and correct abstentions; it does not claim hidden semantic Jev replay.

Both scorers reject incomplete or mixed runs rather than publishing flattering rates.
Regression denominators include only candidates actually applied/evaluated. Missing
usage/cost is explicitly unreported. Offline invented distributions are marked simulated
and cannot become empirical calibration or model-comparison evidence.

## Validation

```bash
uv run pytest tests/unit/test_jev_contract.py
uv run mypy scripts/jev_contract --follow-imports=silent
make check
make test
npm run build
uv build --all-packages
```

PostgreSQL checks require a newly created disposable database migrated by the test
fixture. No production migration, deployment or release is part of this work.
