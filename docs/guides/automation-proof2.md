# Experimental automation Proof #2

Stage A is a research harness, not a product API. Run from the repository root:

```bash
uv run python scripts/automation_proof2_stage_a.py
```

Supply `OPENCLASS_JEV_API_KEY` and `AI_GATEWAY_API_KEY` through the process environment
from your secret source. The harness uses Jev through Vercel and defaults discovery
to `google/gemini-2.5-flash`; `OPENCLASS_DISCOVERY_MODEL` overrides the model. Calls
are live and billable. Never put credentials into fixtures, reports or commits.

The synthetic project runs a real socket bind test in disposable offline containers.
A blocker holds the default port throughout each replay. The candidate must select
and configure an available permitted port, run the test, and write a report matching
the successful result. The evaluator checks these effects, not one expected sequence.
Both `run_tests` and `rerun_previous` can satisfy the test postcondition. There is no
recovery bypass flag. Only exact registered primitive names are executable.

The candidate's natural-language trigger and success condition are advisory; the
fixed evaluator owns pass/fail. Stage A does not validate learned trigger routing or
generalization. Those require Runs 2/3 with the approved immutable policy and real
Jev decisions, with discovery disabled. The legacy core automation executor remains
experimental and is not the executor used by this dedicated proof harness.

Each invocation creates a new `build/automation-proof2/<UTC timestamp>/` directory.
`store.json` records the run, v1 policy, decision trace, evidence, candidate and replay
result. `report.json` records the outcome; it is not an approval. Provider/executor
failures stop without synthetic blocked evidence. Invalid proposals cannot execute.
Exit 0 means Stage A evaluation passed, 1 failed/rejected, 2 incomplete execution,
and 3 unusable discovery. No command in this harness approves or creates policy v2.

Before approval, inspect the exact candidate, base policy ID, evidence trace and
successful replay/report. After a passing live Stage A, obtain explicit human
approval for that candidate before implementing/performing policy v2 activation.
Do not infer authority from the discovery model's wording.

Offline evaluator tests are in `tests/unit/test_automation_replay.py`. They use local
sockets and verify genuine conflict, ineffective/missing recovery, missing/stale
report, terminal actions and invalid primitives. Passing them is not a learned-macro
proof. Existing artifacts, especially frozen Proof #1, must remain untouched.

## 2026-09-24 continuation results

The repaired evaluator passed independent Docker checks: baseline fails with a real
port conflict; an explicitly scripted recovery passes only with a matching report.
These checks are evaluator validation, not learned-macro evidence.

Live run `20260924T115350Z` reached a genuine blocked state with real Jev, then real
Gemini proposed candidate `2be31e4f-736b-4aa6-b8d1-241c79ff3b7a`:
`choose_available_test_port → set_environment → rerun_previous`.
Tests succeeded during replay, but no report was written, so evaluation failed.
The model's narrower success condition did not override the evaluator.

The next run, `20260924T115459Z`, supplied the full evaluation contract explicitly
but stopped on a Jev provider failure before discovery. Earlier discovery responses
also failed strict JSON validation. All attempts retain separate artifacts. No
candidate passed Stage A, no human approval was requested, and no policy v2 or
Runs 2/3 were produced. The next live attempt should use the current harness and
retain these failure artifacts; never manually add a missing step to an old proposal.

## Bounded infrastructure handling

Jev uses at most three transport attempts per decision, each bounded to 15 seconds,
with 0.25/0.5-second backoff. Received responses (including invalid payloads and
HTTP error statuses) do not trigger transport retries. The adapter's own retry loop
is disabled to avoid multiplying attempts. Exhaustion is `infrastructure_failed`,
never a fabricated automation BLOCKED state.

Discovery may retry malformed, incomplete or schema-invalid output once. The retry
resends the exact same semantic payload and JSON schema; it receives no previous
answer, missing-step hint or expected procedure. Repeated invalid output is
`discovery_unusable`. HTTP/transport failures are `infrastructure_failed`; unsafe
responses are rejected without repair. Every attempt records bounded, allowlisted
status/latency/usage telemetry in `store.json`, with unavailable cost left null.

Candidates retain the exact validated proposal, plus separate `applicability`
(advisory description, explicitly unevaluated) and `procedure` (registered steps).
Stage A evaluates the procedure against the unchanged task contract. A passing
candidate still has status `candidate` and no approval or policy v2.

## First passing Stage A: 20260924T120323Z

The first clean attempt after bounded retries were added passed without using a
retry: five real Jev decisions reached a genuine blocked state, and one real Gemini
call produced candidate `d23d7342-71a7-4db6-876f-51edea836a2f` against base policy
`b28e35ee-7f33-451c-89a0-ee9a43dc86c3`. Its procedure selected/configured an available
port, ran tests, and wrote the required matching report. The original evaluator and
primitive fixture remained byte-identical. Live experimentation stopped immediately.

The complete local review packet is
`build/automation-proof2/20260924T120323Z/review/README.md`, with exact candidate,
blocked trace, replay/postconditions, per-attempt telemetry, validation logs and
SHA-256 manifest. The candidate remains unapproved; applicability, policy v2 and
Runs 2/3 remain pending explicit human approval. Standard validation is green:
142 tests passed, 4 skipped; 20 focused regressions passed; checks and builds passed.

## Authorized v2 and Runs 2/3: 20260924T121515Z

The user explicitly approved the exact candidate for experimental v2 and Runs 2/3
only. `scripts/automation_policy_approval.py` verifies the reviewed artifact hashes,
records human approval, preserves the exact candidate, and exclusively creates v2.
`scripts/automation_proof2_reuse.py` runs real Jev with no discovery adapter; its
sentinel fails any discovery call and its HTTP transport allows only the Jev endpoint.
The original Stage A fixture and all historical evidence remain unchanged.

Policy v2 is `906044f2-1fff-5440-807a-c8420c3e08ee`. Run 2 passed the original task
with Jev-selected macro, verified tests/report, then Jev-selected DONE. Run 3 used a
separate warehouse HTTP-service unittest project, port 3000 and replacement 3001.
Jev reused the macro, tests/report verified, and Jev selected DONE, but the container
emitted `Address in use` rather than the trigger's literal `Address already in use`.
This unintentional fixture wording mismatch fails the clean applicability checkpoint;
it must not be presented as a passing in-trigger Run 3. The raw harness records
`premature_done` for that unmet gate despite successful task completion.

Both runs made six Jev calls and zero discovery calls. No retries or further policy
changes were made. See `build/automation-proof2-reuse/20260924T121515Z/README.md` for
full evidence, approval provenance, hashes, telemetry, and the fixture mismatch.
The agent stopped after these two runs, as authorized. Do not rerun or modify the
candidate automatically. The full three-run proof remains incomplete.

## Frozen conclusion and separate applicability experiment

Runs 2/3 are now frozen in a read-only 56-file evidence set with manifest
`build/automation-proof2-freeze/20260924T121515Z.json`. Neither run was repeated.
The separate [Proof #2B applicability experiment](../research/proof2b-applicability.md)
uses the mismatch as evidence and evaluates inactive applicability proposals without
modifying the approved procedure, historical reports or policy v2.
