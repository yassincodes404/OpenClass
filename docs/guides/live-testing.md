# First real-provider test

The server defaults to deterministic decision and supervisor mocks. Jev is now an
explicitly selectable remote decision provider; the supervisor remains simulated.
Offline contracts validate protocol handling and persistence, not model quality.
See the [adapter configuration](../../providers/jev/README.md) for endpoints,
timeouts, retries and the data disclosed to the provider.

## Configure and check

Keep credentials in environment variables or an ignored local `.env` file. Native
server commands do not load `.env` automatically; `uv run --env-file .env` does.
Set `OPENCLASS_DECISION_PROVIDER=jev`, `OPENCLASS_JEV_API_KEY`, and the matching
`OPENCLASS_JEV_BASE_URL` and `OPENCLASS_JEV_MODEL`. GLM settings are reserved and
inactive. Never include credentials in observations, ontology definitions or labels.

Run offline contracts first:

```bash
uv run pytest tests/contract/test_jev_provider.py tests/unit/test_provider_config.py
```

After explicitly opting into a paid remote call, a smoke test uses a disposable,
Alembic-migrated SQLite database and exercises the HTTP/service/persistence stack:

```bash
OPENCLASS_RUN_LIVE_TESTS=1 uv run --env-file .env python scripts/jev_pilot.py --smoke
```

This makes at most one classification call with retries disabled. It checks stored
history, unchanged ontology and access after app restart. Results and its database
are written to a unique directory under `build/jev-pilot`. A separate opt-in test is
available with `OPENCLASS_RUN_LIVE_TESTS=1 uv run --env-file .env pytest -m live`.
These are real inference calls and must not run in mandatory credential-free CI.

## Bounded pilot

The device dataset in `examples/jev-pilot` contains proposed labels. They are not
verified ground truth. Independently review every label before making a copy of
`labels.proposed.json` with `status: "human_reviewed"` and a nonempty `reviewed_by`
field identifying the reviewer. Pass that file explicitly:

```bash
OPENCLASS_RUN_LIVE_TESTS=1 uv run --env-file .env python scripts/jev_pilot.py --labels /path/to/reviewed-labels.json
```

The runner accepts at most 50 distinct examples, makes one call per example, and
stops on the first failure or after reported cumulative cost reaches $0.10.
This is a post-call stop threshold, not a hard spending cap: a call can cross it,
and missing cost telemetry cannot enforce it. Use an account-side budget where
available. Labels are read locally and never sent to the provider.

For a diagnostic run with the repository's provisional labels, pass
`--allow-proposed-labels`; the report retains their provisional provenance and
must not be treated as benchmark evidence. Pass `--continue-on-failure` when you
need every case attempted despite transient provider errors; failed cases remain
in the report and count in labeled denominators.

Reports contain dataset and label hashes, label provenance, captured ontology,
provider/model, novelty policy, individual predictions, failures, latency percentiles,
reported token/cost totals and labeled diagnostic counts. Missing usage remains
null. Known accuracy includes failed known examples in its denominator. A smoke
run has no accuracy claims; a small pilot is not a general benchmark. Stored reports
and databases include dataset text and require the same care as input data.

Real supervisor testing remains OC-018 work. No prediction or advisory finding
becomes a verified label, and this pilot does not implement ontology learning.
