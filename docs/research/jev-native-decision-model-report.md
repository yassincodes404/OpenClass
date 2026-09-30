# Jev-Native Decision Model — Mission Report

Status: review packet for the characterization + decision-graph mission. Research
only; nothing here is authorized for production. Branch:
`experiment/jev-characterization`. All historical Proof #1/#2/#2B artifacts were
preserved byte-identically (verified by hash).

## WHAT JEV IS EMPIRICALLY GOOD AT

- Bounded semantic classification over concrete, well-described choices:
  95.98% overall across 176 authored cases; 100% at every choice-space size from
  2 to 32; 100% across near-synonym and single-detail-overlapping choice sets;
  100% across names-only, names+descriptions, names+examples, and opaque-ID
  representations; 100% across raw-text, structured, evidence-bearing, and noisy
  inputs; 0 paraphrase disagreement; 100% order stability; deterministic
  repeats (0.0 probability spread).
- Environment-wording robustness: all four bind-conflict wordings ("Address
  already in use", "address in use", "port is already allocated", errno-style)
  classified correctly with no literal aliases — the exact failure that broke
  Proof #2B's literal applicability gate. In graph context (stage B), 7/7
  including the out-of-set control answered UNKNOWN.
- Known-macro execution: stage C routed all three port-conflict scenarios to the
  registered recovery macro, which completed with independently verified
  postconditions (ports 3001/8001/5433), zero discovery calls.

## WHAT JEV IS BAD AT

- Borderline commitment: on genuinely ambiguous input it commits to a plausible
  class at ~0.75 probability instead of answering UNKNOWN (2 cases).
- Abstraction: an abstract group-level stage lost leaf-level signal
  (characterization: 87.5% hierarchy path vs 100% flat; J_j2_stage1).
- Anaphoric context: "for the chosen X" questions produced UNKNOWN up to p=1.00
  (K suite); downstream nodes need resolved prior decisions stated concretely.
- NEW (evolution stage): the teacher model (gemini-2.5-flash, temp 0) shows
  imperfect candidate precision — wrong macro target (D3), invalid dual-target
  choice (E2b), and, before a schema fix, inability to express procedure
  arguments at all. Every defect was caught by deterministic validation or
  evaluation; none reached execution; no regression was activated.

## HOW MANY CHOICES ARE SAFE

At least 32 flat, with no measured degradation (suite B). 32 is the measured
ceiling, not a demonstrated limit.

## WHETHER HIERARCHY HELPS

Not at this scale. Flat 16-way beat a 4→4 hierarchy (100% vs 87.5%) in the
characterization. In graph context with structured state and explicit questions,
the hierarchy also measured 8/8 (stage A) — structured context mitigates the
abstraction loss. Recommendation: flat routing; if grouping is used, group
choices must carry leaf-level semantics.

## HOW RAW VS STRUCTURED STATE AFFECTS IT

No accuracy difference across raw/structured/+evidence/+noise (all 1.0). spend
representation budget on auditability, not accuracy. Structured state plus an
explicit question measured best in the hierarchy context.

## HOW UNKNOWN BEHAVES

UNKNOWN precision 0.75 / recall 0.857; false-known 0.143; false-UNKNOWN 0.025.
Graded responses: obvious and near-known UNKNOWN cases 100%; borderline 66.7%.
Margin separates correct (0.889 mean) from wrong (0.403 mean) far better than
raw confidence. Missing capabilities produced honest UNKNOWN routing (E stage).

## HOW DECISION DEPTH AFFECTS SUCCESS

Chains fail when stage answers are referenced anaphorically (depth 3–4 collapse
in the characterization). With concrete state propagation, graph-context runs
complete multi-stage flows (stage C). Rule: the state compiler injects resolved
prior decisions; routers never rely on pronouns.

## WHAT ROLE JEV SHOULD HAVE

A bounded semantic router over ≤32 concretely described choices, with
margin/UNKNOWN-probability telemetry for supervision — never a planner,
executor, safety authority, or label authority.

## WHAT THE TEACHER SHOULD AND SHOULD NOT MODIFY

Per `docs/architecture/teacher-protocol.md`: typed single-layer operators only;
never procedures to fix routing, never routing to hide execution failures, never
unregistered primitives (MISSING_CAPABILITY is the honest answer — observed
live in E1/E2), never activation authority. Live evidence: the teacher grounded
the correct procedure fix once the schema could express arguments (D3), but its
candidate targeting required two informed rounds and still failed in one
dimension (old-macro targeting; dual-target choice), which the gates rejected.

## WHETHER THE DECISION-GRAPH HYPOTHESIS SURVIVED TESTING

Yes, for everything except one-touch autonomous evolution. Demonstrated live:
state-compilation → semantic routing → registered-macro execution →
re-observation → verified postconditions → typed layer diagnosis → teacher
candidates → deterministic application as a new append-only graph version →
regression suites. Every invalid or insufficient candidate was rejected by
validation or evaluation with full evidence retention. The open gap is teacher
candidate precision on this model tier; a stronger teacher model is the next
experiment (requires a budget/model decision) before Experiments F (nested
evolution) and G (multi-cycle v1→v4) are run live.

## Budgets consumed

- Characterization: 222 of 250 authorized accepted inferences (48 + 174).
- Proof stage A–C: 35 of 40 pre-registered accepted Jev calls; all passed.
- Evolution stage D/E rounds: 7 accepted Jev calls, 4 discovery calls of the 10
  pre-registered (D1 invalid-operator round was a harness disclosure gap;
  D2/D3 and E2 are recorded per-round in build/decision-graph-evolution/*).

## Artifacts

- `benchmarks/jev/manifest.json` — locked 176-case benchmark
- `benchmarks/jev/jev-profile-v1.json` — empirical JevProfile
- `docs/research/jev-characterization.md` + `-results.md`
- `docs/architecture/jev-native-decision-model.md` (RFC)
- `docs/architecture/teacher-protocol.md`
- `scripts/jev_characterization.py`, `scripts/jev_profile.py`,
  `scripts/decision_graph.py`, `scripts/decision_graph_proof.py`,
  `scripts/decision_graph_evolution.py`
- `build/jev-characterization/20260924T{140045,140824}Z/`,
  `build/decision-graph-proof/20260924T144104Z/`,
  `build/decision-graph-evolution/*Z/` — frozen, hashed artifact sets
- Validation: make check, 186 tests passed / 4 skipped, web build, package
  builds — all green at freeze time; secret scans clean everywhere.
