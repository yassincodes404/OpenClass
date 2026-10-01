# ADR: Jev as an empirically measured decision substrate

Status: experimental consolidation, awaiting review. Date: 2026-09-25.
Branch: `experiment/jev-characterization`. This ADR does not authorize production
integration, candidate activation, F/G, a Teacher switch, or new paid inference.

## Decision and implemented boundary

OpenClass owns canonical semantics, state schemas, decisions, choices, macros,
preconditions, safety guards, postconditions, diagnosis, candidate evaluation and
version history. Provider profiles and compilers adapt that knowledge to measured
provider behavior. They do not redefine domain truth.

The successor research harness is `scripts/jev_contract/`. It deliberately leaves
historical proof runners and their frozen artifacts intact. `canonical.py` has no
Jev references or provider choice-count limit. `knowledge.py` owns the evidence
registry and profile history. `jev.py` compiles provider-neutral nodes through the
existing HTTP adapter contract. `runtime.py` records complete decisions and checks
supervision before executing registered macros. `teacher.py` proposes inactive
version copies; there is no activation function or Teacher callback in execution.

This is an experimental Python API, documented in
[the harness guide](../research/jev-contract-harness.md), not a production API.
No migration, server route, package release or main-branch merge is introduced.

## What Jev is empirically good at

Within the authored characterization, flat concrete choices through **32 known
alternatives plus UNKNOWN** had no measured accuracy degradation. Near-synonym
choices, paraphrases, reordered choices, raw/structured/evidence-bearing state
and authored distractors performed strongly. The matched flat routing condition
outperformed its abstract hierarchy condition. Short-run repeat groups were stable.

Port-conflict wording variants were recognized without literal aliases. Proof #2
Run 2 selected the learned macro with Discovery disabled. Run 3 transferred macro
selection and verified macro postconditions, but its overall status was
`premature_done`; successful transfer of an entire workflow was not established.
DecisionGraph A–C also provide bounded routing and macro-execution evidence.

See the generated [operating profile](../research/jev-operating-profile.md) and
`benchmarks/jev-contract/v1/knowledge.json` for the values, denominators, exact run
scopes, hash-addressed sources and limitations behind each observation.

## Weaknesses and unsupported extrapolations

Borderline ambiguous cases included confident false-known decisions. Anaphoric
chains degraded. Abstract intermediate categories sometimes lost useful semantics.
These are measured conditions, not proof that all hierarchies or all deep graphs
fail. Sequential depth and wording are confounded in the characterization.

The characterization had 176 planned cases and 174 accepted responses; the
reported 95.98% describes 167/174, excluding two infrastructure failures. It is
not universal accuracy. Early pilot labels were proposed agent-authored expectations,
not verified ground truth. The registry preserves that distinction.

Above 32 choices, long-term stability, immutable-model-version stability and
complex real-world domains remain uncharacterized. Top probability is not
calibrated correctness. Mean margin association does not establish a threshold,
causation, or superiority to a probability-only baseline. Teacher schema/target
failures and gateway 429/502/503 incidents are not Jev semantic failures.

## Measured facts versus assumptions

Every registry entry is explicitly `OBSERVED`, `INFERRED`, or `UNKNOWN`. Observed
values must match an artifact JSON pointer and SHA-256. Recommendations are
inferences, even when useful. Missing identity, cost and immutable revision remain
unknown. The alias `typesafe-ai/jev` does not establish identical underlying weights
between calls. A historical zero cost field is recorded as reported; it is not a
pricing guarantee.

## Compiling knowledge for Jev

`JevDecisionCompiler` combines a canonical node and complete factual snapshot with
a separately versioned profile. It keeps stable choice IDs, self-contained meanings,
explicit resolved decisions and relevant raw evidence. UNKNOWN is always present
through the shared adapter. The DecisionSpec hash binds the node, compiler version,
profile and state-schema identity. Separate hashes bind the snapshot and choice set.

`max_tested_flat_choices` belongs to the profile and is derived from the recorded
choice-size measurements. Unsupported node sizes fail with a provider-compatibility
error; they are not silently split or asserted safe. Obvious anaphoric forms are
rejected; text lint cannot prove complete semantic independence, so review remains
necessary. A hierarchical edge requires a domain decomposition rationale.

## Semantic decisions versus deterministic code

Jev chooses among supplied semantic alternatives. It never supplies executable
commands, safety authority, hidden capabilities, labels or approval. Macros compose
registered steps with typed argument domains. The whole procedure is checked
against the capability catalog before any step executes; preconditions and safety
guards are deterministic, reality is re-observed, and postconditions are verified.

Prefer few meaningful decisions around substantial verified deterministic work.
The current successor runner executes bounded graph routing through one terminal
choice or verified macro. Accumulating multiple macro cycles is reserved for G
following review, not claimed by this consolidation.

## Escalation and calibration

No numeric execution threshold is selected by this ADR. The default gate escalates
all decisions until a profile-bound rule has held-out evidence and explicit review.
High-risk nodes, UNKNOWN, infrastructure failure and profile mismatches always
escalate. UNKNOWN alone yields insufficient evidence, never an automatic
DECISION_SPACE diagnosis or ADD_CHOICE proposal.

The independent supervision benchmark has 24 calibration cases and 24 held-out
validation cases, covering six strata. Library loans and equipment loans separate
the authored domains. It compares a predeclared probability-only grid with a
margin-plus-UNKNOWN grid, reports coverage/errors and uncertainty intervals, and
selects on calibration only before validation. Validation curves are descriptive;
using them for tuning requires a new holdout. Labels need review. No safety-critical
claim or automatic activation is possible from this small benchmark.

## State and hierarchy

The state compiler copies typed sensor facts and retains raw semantic evidence.
It does not turn substring matches into inferred failure types. Missing observations
are not false or null facts. State hashes include raw evidence and resolved prior
decisions, so identical fact dictionaries with different evidence cannot collide.

Hierarchy is justified by genuine domain decomposition, permissions or independently
meaningful questions, with leaf semantics retained. It is not a default response to
an aesthetically large flat list. Current measurements do not justify automatic
abstraction or arbitrary decomposition above the tested bound.

## Teacher evolution contract

[Teacher Protocol v1.1](teacher-protocol-v1.1.md) provides the exact deterministic
failed layer, graph slice, state schema, evidence-generated Jev manual, candidate
history, permitted typed operators and registered capabilities. Only predeclared
aggregate evaluation feedback can be disclosed.

Procedure repair cannot change routing; semantic repair cannot retarget a working
macro. A layer change requires a new deterministically supported diagnosis, not a
Teacher assertion. Missing capabilities and insufficient evidence are valid answers.
The Teacher never sees hidden evaluation cases or another model's answer, never
activates candidates and cannot remove existing safety guards.

The precision benchmark includes authored cases for every diagnosis layer and frozen
D/E source requests. Strict capability-specific schema generation fixes the known
argument-expressiveness gap before comparison. It measures schema, operator, target,
payload, deterministic evaluation/regression, abstention, tokens, latency and reported
cost. Results will concern this protocol and these packages; a model comparison alone
cannot causally distinguish all protocol and model effects. Semantic Jev replay is a
separate requirement beyond structural and deterministic macro fixtures.

## Drift and re-characterization

Provider, model identifier, reported revision, API behavior, distribution schema and
major-version changes produce append-only `profile.stale` events. Evidence of sustained
runtime drift uses the same mechanism; a drift detector must supply evidence, not an
invented universal threshold. `ProfileJournal` retains staleness across process restarts
and alias reversions. New development is rejected against stale profiles. Old profiles,
policies and trace identities remain available for historical inspection.

Identity changes returned by inference are quarantined outside semantic evidence.
Silent weight changes under an unchanged alias are not automatically observable;
periodic characterization and a separately calibrated drift detector remain necessary.
A new successful characterization creates a new profile version; it does not erase the
old staleness history. Historical reproducibility means retained inputs/configuration
and evidence, not a guarantee of identical future responses from an external alias.

## Generic architecture and Jev optimization

Canonical models, typed state compilation, governance, capability execution, evaluation,
telemetry semantics and append-only history are generic. The empirical choice bound,
concrete formatting recommendations, Jev manual, token adapter mapping and Jev compiler
are provider-specific. Another profile/compiler can target the same canonical policy
without editing its semantic definitions.

## Production decision and review gate

**No evidence yet justifies productionizing the Jev-native DecisionGraph.** The typed
boundaries, failure separation, provenance and deterministic guard design are suitable
for a future reviewed implementation proposal. These experimental modules themselves
are not production components. Calibration, Teacher comparison, broader domains,
model/version drift, governance integration and regression accumulation remain gates.

The historical D/E reports contain at least 16 accepted Teacher calls against a declared
10-call total. Remaining characterization allowance is scoped to that benchmark. A new
live budget must be explicit and recorded before paid use. The supplied credential is
never evidence and must not enter source, logs, fixtures, prompts or manifests.

F/G remain blocked until steps 1–7 are reviewed. F must add a truly missing lower-level
choice while preserving parent routing. G must replay every previous verified case
through several different failure layers, with evaluation and human approval per
version. Stop after G; neither demonstration has been run by this consolidation.
