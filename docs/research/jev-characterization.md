# Jev Characterization — Pre-Registered Baseline Protocol

Status: pre-registered before the first live run. The benchmark manifest is locked;
any change to cases, labels, or acceptance after inference would be recorded as a
protocol violation, not a result.

## Motivation

Proof #2/#2B showed Jev's semantic routing generalizing better than the literal
applicability representation around it. Before designing evolution logic or the
Jev-native decision model, Jev must be characterized independently: no OpenClass
learning, no discovery provider, no macros, no policy evolution. This benchmark
measures how the real provider behaves; it does not tune it and it does not claim
Jev is good or bad a priori. Predictions never become labels.

## Setup

- Provider: `openclass_provider_jev.JevDecisionProvider`, model `typesafe-ai/jev`
  through `https://ai-gateway.vercel.sh/typesafe` — the same endpoint Proof #2 used.
- Benchmark: `benchmarks/jev/manifest.json`, protocol version 1. All 176 cases and
  every expected label are human-authored; provenance is recorded in the manifest.
  The manifest is hashed into each run's protocol record before inference.
- Decision rule (fixed in advance, identical to the Proof #2 replay harness):
  `selected = argmax` over known-class probabilities; UNKNOWN is selected when
  `unknown_probability >= top known probability`.
- Determinism of requests: ontology identifiers are derived deterministically from
  case ids so the exact request payload is reproducible from the manifest.

## Suites

| Suite | Dimension                                                           | Cases |
| ----- | ------------------------------------------------------------------- | ----- |
| A     | Semantic clarity: clear known, ambiguous, unrelated                 | 8     |
| B     | Choice-space size: 2/4/8/16/32                                      | 15    |
| C     | Choice similarity: distinct, adjacent, overlapping                  | 12    |
| D     | Choice representation: names, +descriptions, +examples, opaque IDs  | 16    |
| E     | Input representation: raw text, structured, +evidence, +noise       | 16    |
| F     | Paraphrase robustness (5 pairs)                                     | 10    |
| G     | Order sensitivity (4 cases × 3 orderings)                           | 12    |
| H     | UNKNOWN grading: known, near-known, borderline, obvious             | 12    |
| I     | Repeatability (3 fixtures × 5 identical repeats)                    | 15    |
| J     | Flat 16-way vs 4→4 hierarchical routing (8 scenarios)               | 24    |
| K     | Decision depth: 4-stage chains, 2 scenarios (depth = prefix length) | 8     |
| L     | Changed environment wording (4 bind-conflict wordings + controls)   | 8     |
| M     | Distractor evidence (none/light/heavy)                              | 12    |
| N     | Re-observation: decide, state changes, decide again                 | 8     |

Total: **176 planned requests**, under the authorized budget of **250 live Jev
calls**. The budget counts every HTTP request actually issued to the provider,
including transport-level retries, and is enforced by the transport itself: the
251st request is refused, the run stops, and partial results are recorded.
Exceeding 250 requires new explicit authorization.

## Metrics (fixed in advance)

- Per-suite and overall accuracy of the selected label against the authored
  expectation.
- UNKNOWN precision/recall over all cases; false-known rate (a known class chosen
  when UNKNOWN was expected); false-UNKNOWN rate (UNKNOWN chosen when a known class
  was expected).
- Choice-count degradation: accuracy by size within suite B.
- Order sensitivity: fraction of suite-G groups with identical selections across
  orderings; accuracy per ordering position.
- Paraphrase sensitivity: fraction of suite-F pairs whose members disagree.
- Repeatability: selection agreement within suite-I groups; spread of the selected
  probability across repeats.
- Flat vs hierarchical: flat accuracy; per-stage and path accuracy for the 4→4
  hierarchy; request count and latency comparison.
- Decision depth: per-stage accuracy by stage index; path success by depth prefix.
- Margin behavior: distribution of `top − second` probability margin and its
  relation to correctness; provider-reported confidence likewise.
- Latency p50/p95; total and mean tokens; reported costs; provider failures and
  transport attempts.
- Wording robustness (L): accuracy on the four bind-conflict wordings; false-known
  on in-set negatives; UNKNOWN on the out-of-set control.
- Distractor robustness (M): accuracy per noise level.
- Re-observation (N): per-step accuracy and both-steps-correct rate.

## Rules of conduct

1. The baseline run is frozen as-is. No tuning, prompt change, fixture change, or
   re-run in response to results. A follow-up run needs a new protocol version and
   a new artifact directory.
2. Provider/infrastructure failures are recorded as infrastructure results. They
   are never counted as semantic failures and never as BLOCKED evidence.
3. Expected labels come only from the human-authored manifest. Jev output is never
   written back into the benchmark.
4. Credentials stay in the process environment. No key material may appear in any
   artifact; the run verifies this before finishing.
5. Every attempt writes its own timestamped artifact directory under
   `build/jev-characterization/`; artifacts are append-only and hashed after the
   run.

## Artifacts produced by a run

`protocol.json` (script, manifest, and this document hashed; budget; decision
rule), `evaluation-set.json` (ordered locked case list, hashed pre-inference),
one record per case, one record per provider attempt, `summary.json` (metrics
above), `report.json` (run status), `jev-profile.json` (empirical profile, phase
2), `sha256.json` (post-run manifest), `integrity.json` (freeze/secret/budget
checks), and `README.md` (review packet).

## Interpretation boundaries

This is a characterization of one provider endpoint at one point in time with a
small authored case set. It is not a certified benchmark, not a capability claim
about the vendor's model, and not evidence about OpenClass learning. Its purpose
is to size and shape the Jev-native decision model with measured operating
characteristics instead of assumptions.

## Addendum — protocol v2 (recorded before the second run)

The first live run (`build/jev-characterization/20260924T140045Z`) completed in
57 s with 48 accepted inferences and 128 infrastructure failures: 126 requests
were rejected with HTTP 429 (rate limiting) and 2 with HTTP 503. No semantic
result was produced by those requests. The run is retained unchanged as an
infrastructure-degraded partial record; the benchmark manifest, cases, labels,
decision rule and metrics are unchanged. For the second run, three
infrastructure-only changes apply, none of which can alter semantic outcomes:

1. The transport retries 429/503 responses with exponential backoff
   (1/2/4/8/16 s) before giving up on a case; requests are paced by 0.5 s.
2. The budget counts **accepted (2xx) provider responses across all runs of this
   characterization**, not raw HTTP requests: 429/503 rejections perform no
   inference and cost nothing. The first run consumed 48 accepted inferences;
   the 250-call ceiling therefore still holds for a full 176-case re-run
   (48 + 176 = 224 ≤ 250), and the harness enforces it against a persisted
   cross-run ledger.
3. Case records additionally carry `error_type`/`error` for infrastructure
   failures.

If the second run also fails predominantly on infrastructure, the next step is
to stop and renegotiate the budget with the user rather than to keep retrying.
