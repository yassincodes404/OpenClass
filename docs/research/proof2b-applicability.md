# Proof #2B — Applicability Evolution

Status: experimental applicability discovery/evaluation; no v3 authorization.

## Frozen Proof #2 conclusion

> Exact reuse demonstrated. Cross-instance behavioral transfer observed, but the
> predefined clean generalization checkpoint was not satisfied because the approved
> applicability trigger overfit the original error wording.

Runs 2 and 3 are not rerun or rewritten. Their 56-file evidence set is read-only;
`build/automation-proof2-freeze/20260924T121515Z.json` records every file hash and the
conclusion. The original raw Run 3 status remains `premature_done`. The newer analysis
separates actual task/procedure success from the failed applicability checkpoint.
The historical literal applicability check was a checkpoint after execution, not a
safety guard that prevented execution. This experiment does not retroactively change
that boundary or declare the old checkpoint passed.

## Research question

Can a real discovery provider propose improved applicability knowledge from the
recorded mismatch, and can deterministic evaluation distinguish useful improvements
from overly broad matches? The approved macro's procedure, description and original
trigger remain unchanged in v2. Any proposed replacement is an inactive new candidate.

Discovery sees the frozen policy/candidate, states at macro selection, real Jev
results, executor outcomes and the mismatch. It may return GENERALIZE_TRIGGER,
ADD_FAILURE_ALIAS, ADD_STATE_NORMALIZATION, SPLIT_MACRO, NO_CHANGE or
INSUFFICIENT_EVIDENCE. It is not given an expected implementation, target failure
category, evaluation fixture list, expected labels or failed-answer repair hints.
Only malformed/invalid structured output may be retried once with the identical
request and schema. A valid but failing proposal is retained without tuning or retry.

## Bounded representation and authority

`scripts/automation_applicability.py` defines typed failure state and candidate
applicability specifications. A candidate can propose escaped literal signal
alternatives, or named normalization rules and a required category. Signal matching
is case-insensitive, whitespace tolerant and word bounded. Model-provided regex,
Python, SQL and shell are never evaluated. Conflicting normalization categories
produce UNKNOWN. Normalization retains the observed port rather than inventing it.

Semantic description, deterministic applicability, and task-state requirements are
separate fields. This slice does not execute a macro, alter safety/capability guards,
replace the active state compiler or modify policy. Its matcher is deliberately
small; it is not a universal error classifier. SPLIT_MACRO is recorded but has no
execution/evaluation implementation here. NO_CHANGE and INSUFFICIENT_EVIDENCE are
legitimate non-promotable results.

## Evaluation protocol

The evaluator writes and hashes its cases before inference and does not include them
in the provider request. Twelve cases compare the baseline literal predicate with
the candidate specification:

- The two recorded states, with human-accepted applicability labels.
- Six user-specified synthetic cases: the three port-conflict signals should match;
  connection refused, permission denied and file not found should not.
- Four derived state regressions: successful test, unattempted test, uninspected
  result, and missing exit result must not qualify.

Labels are human-specified or authored regression expectations, never model predictions.
The conformance cases are held out from the request, not a statistically independent
benchmark. Acceptance requires all cases correct and no regression. Results preserve
baseline/candidate decisions, compiled state, sources, exact proposal, telemetry and
candidate/base-policy identity. Passing means offline applicability evaluation only;
it does not mean v3 activation, rerouting success or a corrected historical Run 3.

Future outcome records use distinct task, routing, procedure, postcondition,
applicability and generalization fields. New analytic interpretations of Runs 2/3
live in Proof #2B artifacts with source references; historical files stay frozen.

## Running and stopping

`uv run python scripts/automation_proof2b.py` uses `AI_GATEWAY_API_KEY` from the process
environment and defaults to `google/gemini-2.5-flash` through Vercel. Calls are live.
No credential is included in evidence, source, logs or events. The runner verifies
the freeze before and after, records a new artifact directory, and stops after one
valid proposal and evaluation. It has no policy creation or activation capability.
A passing proposal requires new explicit human approval before any future v3 work.

Cycle 2 (`scripts/automation_proof2b_cycle2.py`) is the single authorized follow-up
round: it verifies the cycle-1 artifacts and that the reused implementation is
byte-identical to what cycle 1 ran, adds the rejected cycle-1 candidate and its
aggregate verdict (counts only; case identities, labels and fixtures stay
undisclosed) to the evidence, and applies the identical acceptance rule. It refuses
to run unless cycle 1 was an inactive rejected proposal, and records
`no_third_round: true`. A valid but failing cycle-2 result is retained as-is.

There is no new public API or database migration: this remains an isolated,
file-backed research harness. Production architecture reconciliation remains the
OC-003–009 plan; this work does not authorize analytics, n8n or platform UI expansion.

## First live result — 20260924T123534Z

Real Gemini proposed candidate `453c624c-ad7b-438b-9018-ddf53b23edbf`, type
GENERALIZE_TRIGGER, with only the literal signal `Address in use` and no normalization
rules. The model claimed this also covered `Address already in use`; deterministic
matching showed otherwise. The candidate fixed the two new-wording cases but regressed
both original-wording cases and missed held-out `EADDRINUSE`: 9/12 correct, the same
count as baseline, with two regressions. Evaluation failed despite model confidence
1.0. This was a phrase substitution, not a demonstrated generalization.

The proposal was not repaired or rerun. It remains inactive; no v3 was created.
The full review packet is `build/automation-proof2b/20260924T123534Z/README.md`.
The frozen Run 2/3 evidence and Proof #1 were verified unchanged. Standard checks,
161 tests (4 skipped), web build and package builds passed.

## Second live result — cycle 2, 20260924T130129Z

With cycle 1's rejected candidate and its aggregate verdict (counts only) in the
evidence, real Gemini returned `ADD_FAILURE_ALIAS` with confidence 1.0: it restored
the original `Address already in use` signal and added a second literal alias, the
verbatim recorded output line `OSError: [Errno 98] Address in use`. Its rationale
cites the prior rejection ("…rejected due to regressions, indicating it was too
broad"), so the evidence feedback demonstrably changed the proposal.

The deterministic result: 10/12 correct with **zero regressions** — strictly better
than baseline (9/12) and cycle 1 (9/12, two regressions) — but the two remaining
misses are the held-out wordings `Address in use` and `EADDRINUSE`. The model
responded to failure feedback by becoming more conservative, not more abstract: it
anchored the new alias to the exact recorded output line instead of proposing the
representable category-mode normalization that would pass. Evaluation refused
promotion again. The candidate is retained inactive; no third round was run.

Recorded conclusion of Proof #2B: evidence-informed applicability evolution improves
monotonically and safely under the deterministic gate, but did not produce the
categorical abstraction the clean generalization checkpoint requires in either
round. Applicability knowledge remains at policy v2; the approved procedure was
never in question. Review packet:
`build/automation-proof2b-cycle2/20260924T130129Z/README.md`. Frozen Run 2/3
evidence, cycle-1 artifacts and the v2 policy were re-verified unchanged after the
run. Standard checks, 168 tests (4 skipped), web build and package builds passed.
