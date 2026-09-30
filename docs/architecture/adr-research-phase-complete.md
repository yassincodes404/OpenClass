# ADR: Research phase complete — proven facts, boundaries, and the road to OpenClass Core

Status: accepted (research record). Date: 2026-09-25.
Branch: `experiment/jev-characterization`.

This ADR closes the research phase that began with the Jev characterization
benchmark and ended with experimental PolicyGraph v4. It separates **proven
experimental facts** from **unproven production claims**, records the
architectural rule the experiments discovered, and hands off the concept
inventory to build mode. Experimental v4 (`a0043a1e…`) is activated
([v4-activation record](../../build/experiment-g/v4-activation-20260925/v4-activation.json))
with the immutable chain v1 `891dc20d…` → v2 `0a83f9d9…` → v3 `67152f52…` →
v4, approval provenance recorded verbatim, and all historical artifacts
hash-verified at every activation.

## The evolutionary history (all live, all retained)

| Transition | Knowledge layer      | Evolution                                                                           | Retention |
| ---------- | -------------------- | ----------------------------------------------------------------------------------- | --------- |
| v1→v2      | DECISION_SPACE       | TLS certificate failure learned (`ADD_CHOICE`, discovery from live UNKNOWN)         | 1.0       |
| v2→v3      | PROCEDURE            | CA-migration drift repaired (`REPLACE_PROCEDURE`: flush-before-rotate)              | 1.0       |
| v3→v4      | STATE_REPRESENTATION | generation-probe fact represented (`ADD_STATE_FEATURE`, scope derived by OpenClass) | 1.0       |

Each transition: real Jev routing under the frozen research supervision rule,
deterministic layer diagnosis before inference, exactly one Teacher proposal,
OpenClass-attached CandidateEnvelope, deterministic validation, hidden
behavioral replay, human approval before activation. Bad candidates were
stopped by evaluation three times (2B cycle 1; v2.1 `required=true`; F attempt
1's routing) — the gates never passed a defective proposal.

## Proven experimental facts

Within the controlled live system (authored service-operations domain, one
node family, human-authored labels, small samples, research supervision):

1. **Jev routing**: 95.98% across 176 authored cases; no degradation from 2 to
   32 flat choices; robust to paraphrase, ordering, distractors, choice
   similarity, representation style (including opaque IDs), and environment
   wording variants — with no literal aliases.
2. **UNKNOWN-driven knowledge acquisition**: a genuine gap produces UNKNOWN;
   deterministic diagnosis attributes the layer; a Teacher proposal extends
   exactly the deficient structure; previously verified behavior is retained
   (retention 1.0 at every version).
3. **Behavioral repair**: when semantic routing remains correct but a stored
   procedure goes stale, OpenClass attributes PROCEDURE — not a routing
   failure — and repairs only the procedure layer.
4. **Representational evolution under v2.2**: when raw reality contains a fact
   the schema cannot represent, and that omission blocks execution, the
   Teacher names the fact and its source; OpenClass derives machine scope
   (`required=false` from a conditional source) and compiles the schema.
5. **Gate integrity**: every invalid or insufficient candidate across all
   stages was rejected deterministically. No defective proposal ever executed;
   no regression was ever activated.

## The architectural rule (the phase's most valuable finding)

```text
Teacher LLM owns MEANING:
  what concept is missing, what procedure is stale, what state fact matters,
  which semantic target, why — grounded in deterministic evidence.

OpenClass owns MECHANICS:
  ids, hashes, bindings, versions, provenance, source availability,
  schema compilation, capability restrictions, safety, scope derivation,
  evaluation, approval, activation, audit.
```

Every failure traced to a violation of this boundary: v1 packets demanded the
model echo an undisclosed hash; v2.1 let the model decide machine scope
(`required=true` broke probe-less compilation). Both were fixed by _moving the
responsibility_, not by prompting harder. Related rule: **teach through
architecture, not prose** — the empirical Profile measurably helped the
Teacher; the prose Skill added nothing; worked examples hurt.

Provider compatibility facts (adapter-layer, never Teacher knowledge):
`not:{}` constructs silently disable Google schema enforcement; empty enum
values are rejected; null-only branches may be emitted as `{}`; the wire
schema must be bare (single envelope) and every declared property requires
explicit typing.

## Explicit caveats — claims are under corrected protocols

- Some evaluator formulas and one re-observation gate were corrected after
  observing legitimate behavior (F check 7; G cycle 2 gate; stage 2 v1 packet
  defect). Every correction was a deterministic rescore of already-recorded
  traces or a declared protocol amendment before the next run — recorded in
  the run packets, never a silent rerun. Final claims hold **under the
  corrected formulas/protocols**, not the original imperfect harnesses.
- Authored small samples; labels are agent-authored pending human review; no
  statistical significance; one node family (cross-node calibration
  unassessed); one provider endpoint; latency/cost at research scale.
- The v2.1 state proposal's failure mode (schema-convention imitation) is
  recorded as a live-observed Teacher risk; v2.2 removes the authority, and
  the stronger-model question (paywalled tiers unmeasured) remains open.
- UNKNOWN margin thresholds are research-calibrated, not production-calibrated
  (holdout continued only 9 decisions; Wilson upper bound 0.299).

## Unproven production claims (handoff to build mode)

Production reliability; arbitrary-domain generalization; concurrent
multi-project operation; auth/isolation; large global knowledge spaces with
retrieval-compiled local choice sets (designed, not yet measured); cost at
platform scale.

## Concept inventory for OpenClass Core (build mode)

Decision plane: `StateProvider`, `StateSource`, `StateSchema`,
`StateCompiler`, `StateSnapshot`, `DecisionNode`, `Choice`, `DecisionGraph`
(immutable `Version` chain), `DecisionProvider` (Jev adapter),
`SupervisionPolicy`, `CapabilityRegistry`, `Macro`, `Verifier`,
`ResolvedDecision`. Evolution plane: `Evidence`, `FailureDiagnosis`,
`TeacherProvider`, `TeacherProposal` (semantic only), `CandidateEnvelope`,
`EvaluationEnvironment`, `Candidate`, approval + activation records, audit.
Platform: Projects, PostgreSQL authority, API, Python/TS SDKs, extensions.

Boundary invariants carried into Core verbatim: Teacher proposals are semantic
only and never carry identity/scope; identifiers are enum-constrained to the
request's valid universe; infrastructure failures are never semantic
outcomes; UNKNOWN is permanent; approval is human and per-version.

## Research artifacts (frozen, hash-addressed)

`benchmarks/jev/`, `benchmarks/jev-contract/v1/`,
`build/jev-characterization/`, `build/decision-graph-proof/`,
`build/decision-graph-evolution/`, `build/jev-contract-v1/` (including
stage 1–3 live validation), `build/experiment-f/`, `build/experiment-g/`,
`build/automation-proof2*/` and all earlier proofs. Runner sources under
`scripts/` and `scripts/jev_contract/` remain evidence, not runtime authority.
