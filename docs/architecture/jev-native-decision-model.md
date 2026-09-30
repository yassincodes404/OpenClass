# RFC: Jev-Native Decision Model (experimental)

Status: draft RFC for the research harness only. This does not change production
architecture (the OC-003–009 reconciliation governs that) and does not authorize
productization. Every design commitment below cites the measured characterization
(`docs/research/jev-characterization-results.md`, profile
`benchmarks/jev/jev-profile-v1.json`) or the Proof #2/#2B record.

## 1. Problem

Proof #2B showed the learned macro's _procedure_ transferring across environments
while its literal applicability trigger failed; Jev routed semantically (p = 1.00)
to a macro whose string gate rejected the same failure. The characterization then
measured what Jev actually is:

- excellent at bounded semantic classification: 95.98% overall; 100% at every
  choice-space size from 2 to 32; 100% across paraphrase, ordering, distractor,
  and environment-wording variants;
- weakened by abstraction (a 4→4 hierarchy measured 87.5% path accuracy against
  100% flat because the group stage lost leaf-level signal);
- weakened by anaphoric context ("the chosen X" → UNKNOWN up to p = 1.00);
- unreliable exactly at the borderline: ambiguous input drew confident wrong
  commits (~0.75) instead of UNKNOWN.

The current automation representation — string triggers attached to macros —
designs around none of this. The hypothesis: represent decision knowledge the way
a bounded semantic router actually consumes it, and put determinism where the
router is weak.

## 2. Separation of concerns

```text
Jev                 = WHICH known semantic choice fits the current state?
DecisionNode        = WHAT alternatives exist, described concretely?
StateCompiler       = WHAT is true right now (including resolved prior decisions)?
Macro               = HOW do we execute a chosen capability (registered steps)?
Safety guards       = ARE we permitted? (deterministic, before execution)
Postconditions      = DID it work? (deterministic, verified after execution)
Teacher LLM         = WHAT knowledge structure appears to be missing?
OpenClass           = evidence, evaluation, governance, versioned policy
```

Jev is never a planner, executor, safety authority, or source of ground truth.

## 3. Objects

```text
PolicyGraphVersion
  id, version_number, parent_version_id, state_schema_id, nodes, macros, created

StateSchemaVersion      typed fields the compiler may emit; versioned, append-only
StateSnapshot           one compiled observation: schema version + field values
                        + raw evidence reference + compiled_at

DecisionNode
  id                    stable node id
  question              what this node decides
  choices[]             bounded semantic alternatives
  unknown_allowed       always true (UNKNOWN is a state, never a class)
  fallback              UNKNOWN → node id | macro | BLOCKED

Choice
  id                    stable id
  semantic_name         name the router sees
  description           one-line semantics (auditability; accuracy-neutral per D)
  target                node id | macro id

Macro
  id, semantic_purpose
  preconditions         deterministic state predicates (typed, not strings)
  safety_guards         permission/capability checks (deterministic)
  procedure[]           registered primitives only; no generated commands
  postconditions        deterministic, independently verified

Transition              the recorded edge: node → choice → outcome
FailureDiagnosis        typed layer attribution (see teacher protocol)
```

## 4. Execution semantics

```text
compile raw environment → StateSnapshot (schema-validated)
loop (bounded depth, cycle-checked):
  current DecisionNode + StateSnapshot → Jev → choice (argmax; UNKNOWN wins ties)
  choice → node | macro | BLOCKED
  macro: preconditions → safety guards → procedure → postconditions
  re-observe reality after every macro; never trust "called == succeeded"
on postcondition FAIL or BLOCKED: stop, diagnose layer, emit evidence
```

Rules the evidence imposes:

1. **Flat beats hierarchy at measured scale.** Nodes route over ≤32 concretely
   described choices. A grouping stage is permitted only if its choices carry
   leaf-level semantics (the measured 4→4 stage-1 loss: J_j2_stage1).
2. **State propagation is the compiler's job.** A downstream node's snapshot must
   contain the resolved prior decision and the facts that motivated it; anaphoric
   references measurably produce UNKNOWN (K_s1_d4, K_s2_d4).
3. **UNKNOWN is always available and is a first-class outcome.** A committed
   choice on borderline input is provisional: record margin and unknown
   probability with every transition for supervision (measured margin separation
   0.889 vs 0.403).
4. **Postcondition failure is never silently retried** and never treated as
   learning evidence; it becomes a FailureDiagnosis for the teacher.
5. **No arbitrary commands.** Procedures compose registered primitives; the
   executor refuses anything else (Proof #2 executor boundary, unchanged).

## 5. Versioning and governance

Policy graphs are append-only versions with parent links, like AutomationPolicy
and ontologies before them. The teacher proposes typed changes against one
version; deterministic evaluation scores candidates on held-out, human-labeled
cases; a human approves activation. A candidate that gains coverage by regressing
verified prior behavior fails evaluation (Proof #2B's rule, retained). Every
policy version records which empirical `JevProfile` it was designed against; a
materially different provider/model requires re-characterization before reuse.

## 6. Non-goals

No production persistence or API in this stage; no free-form planning; no model
authority over labels, safety, or activation; no speculative multi-model routing;
no changes to the frozen Proof #1/#2/#2B artifacts.

## 7. Open questions

- Does margin-based supervision (thresholds on margin/unknown probability) reduce
  borderline false-knowns without suppressing legitimate commits? (Phase 6
  experiments measure a first answer.)
- How much abstract-group signal loss remains when group descriptions are
  enriched with leaf semantics? (Follow-up characterization, not assumed.)
- Cost of re-compiling state after every macro in live settings.
