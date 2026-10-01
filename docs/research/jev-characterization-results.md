# Jev Characterization — Baseline Results

Status: measured baseline; input to the Jev-native decision model RFC. Not a
certified benchmark and not a capability claim about the vendor.

- Benchmark: `benchmarks/jev/manifest.json` (176 authored cases, 14 suites)
- Protocol: `docs/research/jev-characterization.md` (pre-registered; v2 addendum)
- Profile: `benchmarks/jev/jev-profile-v1.json` (generator:
  `scripts/jev_profile.py`)
- Runs: `build/jev-characterization/20260924T140045Z` (run 1, rate-limit
  degraded, 48 accepted) and `build/jev-characterization/20260924T140824Z`
  (run 2, authoritative, 174 accepted of 176 cases; 2 infrastructure failures)
- Budget: 222 of 250 accepted inferences used across both runs (ledger in the
  profile); 94 rate-limited requests were retried successfully in run 2 and
  consumed no budget.

## Headline numbers (run 2)

| Metric                                                 | Value                                                   |
| ------------------------------------------------------ | ------------------------------------------------------- |
| Overall accuracy                                       | 95.98% (167/174)                                        |
| Choice-space size 2 → 32                               | 100% at every size (no degradation measured)            |
| Choice similarity (distinct/adjacent/overlapping)      | 100% / 100% / 100%                                      |
| Choice representation (names/semantic/rich/opaque IDs) | 100% everywhere                                         |
| Input representation (raw/structured/+evidence/+noise) | 100% everywhere                                         |
| Paraphrase disagreement                                | 0 of 5 pairs                                            |
| Order stability                                        | 100% (12/12 groups)                                     |
| Repeatability                                          | identical selections, 0.0 probability spread (15 calls) |
| Flat 16-way vs 4→4 hierarchy                           | 100% vs 87.5% path accuracy                             |
| Bind-conflict wordings (4 variants)                    | 100%; in-set negatives 100%                             |
| Distractor evidence (none/light/heavy)                 | 100% everywhere                                         |
| UNKNOWN precision / recall                             | 0.75 / 0.857                                            |
| False-known / false-UNKNOWN rate                       | 0.143 / 0.025                                           |
| Re-observation step 1 / step 2                         | 100% / 75%                                              |
| Margin, mean when correct vs wrong                     | 0.889 vs 0.403                                          |
| Latency p50 / p95                                      | 0.50 s / 3.75 s                                         |
| Tokens per call (mean)                                 | ≈795 in / ≈89 out                                       |
| Gateway-reported cost                                  | none recorded for these calls                           |

## The seven semantic errors

| Case           | Expected                | Selected      | Top known p | UNKNOWN p |
| -------------- | ----------------------- | ------------- | ----------- | --------- |
| A_ambiguous_01 | UNKNOWN                 | clear_cache   | 0.79        | 0.16      |
| H_borderline_1 | UNKNOWN                 | clear_cache   | 0.73        | 0.23      |
| J_j2_stage1    | compute_actions (group) | UNKNOWN       | 0.36        | 0.64      |
| K_s1_d4        | rollback_deployment     | UNKNOWN       | 0.27        | 0.73      |
| K_s2_d3        | mitigate                | investigate   | 0.52        | 0.31      |
| K_s2_d4        | scale_worker_pool       | UNKNOWN       | 0.00        | 1.00      |
| N_n2_step2     | rollback_deployment     | UNKNOWN (tie) | 0.44        | 0.44      |

They cluster into three mechanisms:

1. **Borderline commitment.** On genuinely ambiguous operations input, Jev
   commits to a plausible class with ~0.75 confidence instead of answering
   UNKNOWN (2 cases). This is the false-known risk: confident, wrong, and not
   flagged by UNKNOWN probability.
2. **Abstraction loses signal.** The only hierarchy stage-1 error is a host-level
   incident ("kernel out of memory, boot the machine") whose concrete wording
   matched no abstract group description; the flat 16-way router classified the
   same observation perfectly. Group-level choices discarded the leaf semantics
   that carry the signal.
3. **Anaphoric context fails.** Stage-4 questions of the form "for the chosen
   response, which concrete action implements it?" produced UNKNOWN (1.00
   UNKNOWN probability on the vaguest wording). Decisions that depend on a prior
   node's answer need that answer restated concretely in the state.

## Findings carried into the decision-model RFC

- Flat routing over ≤32 well-described choices is the measured sweet spot;
  hierarchy is not justified at this scale and its first stage is measurably
  harmful unless group descriptions carry leaf-level semantics.
- Representation budgets can be spent on auditability (semantic names plus
  descriptions), not on accuracy: every tested representation scored 1.0.
- Downstream nodes must receive resolved prior decisions in their state; the
  state compiler owns this, not the router.
- Margin separates correct from wrong decisions far better than raw confidence
  (0.889 vs 0.403 mean margin); supervision should review low-margin and
  high-UNKNOWN-probability decisions, and treat confident borderline commits as
  provisional.
- The router is robust to exactly the things Proof #2B's literal applicability
  gate was not: paraphrase, OS wording variants, and noise. This empirically
  supports moving applicability from literal triggers to semantic routing with
  deterministic guards.

## Limitations

One provider endpoint, one model version, one small authored domain (service
operations), single-run per case except suites F/I/G; no statistical
independence between cases; labels are human judgments, including two debatable
borderline calls (K_s2_d3, N_n2_step2). Depth results measure decision chains
with static per-stage evidence, not a live re-observing executor; the Phase 6
decision-graph experiments are the follow-up evidence.
