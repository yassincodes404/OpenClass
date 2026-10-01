# ADR: Jev Contract v1 live validation — supervision calibration, Teacher context ablation, Teacher model comparison

Status: completed research stage; awaiting human review. Date: 2026-09-25.
Branch: `experiment/jev-characterization`. Nothing here authorizes F/G,
candidate activation, a Teacher switch, production integration, or merging.
Frozen inputs (`benchmarks/jev-contract/v1/`, historical proofs) were verified
unchanged; every stage wrote its protocol record before inference and froze
its artifacts after (hash manifests + secret scans clean).

## What was run

- **Stage 1 — Jev supervision calibration** (`build/jev-contract-v1/stage1-calibration/`):
  48 frozen cases through live Jev; 43 accepted semantic inferences of the 120
  authorized (5 lost to sustained rate limiting, recorded as infrastructure
  only). Rule grid of 132 pre-registered supervision rules; selection on the
  calibration split only; holdout scored once.
- **Stage 2 — Teacher context ablation** (`stage2-ablation/` v1 defect record,
  `stage2-ablation-v2/` amended): 6 pre-registered packages × 4 context
  conditions on `gemini-2.5-flash`, temperature 0.
- **Stage 3 — Teacher model comparison** (`stage3-comparison/`): 13 frozen
  packages × 2 models under identical amended packets; 25 successful calls of
  26 authorized.

## Protocol amendment v2 (one field, uniformly applied)

Stage 2 v1 discovered the frozen packets were **defective**: `TeacherCandidate.
base_policy_hash` must equal the graph slice's content hash, but that hash was
never disclosed — the binding was unsatisfiable for any model (all 20 valid
v1 candidates were rejected as stale). The v2 amendment discloses
`base_policy_hash` in every packet, identically for all conditions and both
models. This deviation from the packet freeze is recorded in every v2 protocol
record and preserved the freeze's purpose (no model sees more than another).

## The six authorized questions

### 1. Can Jev supervision safely reduce borderline false-known execution?

Yes, on this dataset, and cheaply. Raw decisions: 95.35% accuracy, one
false-known (committed `identity_check` at top 0.56 / margin 0.12 / UNKNOWN
0.44). Argmax-only supervision would continue it: `trusted_decision_error_rate`
9.1% (calibration) — the error rate among decisions allowed to continue
automatically. **Every thresholded family (top-probability, margin,
UNKNOWN-probability, combined) reached trusted_decision_error_rate 0 on both
the calibration split and the untouched holdout**, at coverage 41.7%/47.4% and
correct-known coverage 1.0/0.9. Bounds: the holdout continued only 9 decisions
(Wilson 95% upper bound 0.299), one node only (cross-node calibration
unassessable), and no probability-calibration claim is made. UNKNOWN selections
always escalate, so false-UNKNOWN errors cost coverage, never trusted
correctness.

### 2. Does the JevProfile materially help a Teacher?

Yes, measurably (small n). Core-contract-only mis-selected operator/target
once (answered INSUFFICIENT_EVIDENCE where evidence explicitly required a
change); with the Profile, operator and target selection were perfect on the
subset (0.83 → 1.00). The Profile is compact (≈1.5k chars), so this is cheap
signal.

### 3. Does the Jev Skill materially help?

No. Skill-over-Profile measured equal on operator/target (1.00) and slightly
worse on payload precision (0.75 vs 0.83, n=4 — within noise). The elaborately
grounded skill document added tokens without demonstrated capability on this
subset. Do not build further on the skill without new evidence.

### 4. Do worked examples help or hurt?

Hurt. The Examples condition measured worst on evaluation (0.60 vs 0.83),
co-occurring with one schema-invalid response and the same id-precision
failure. Longest context, worst precision: consistent with context-dilution
of exact-token copying at this model tier.

### 5. Is Teacher precision mainly a protocol/schema problem or a model-capability problem?

Both, in separated layers — this is the ablation's core yield:

- **Protocol/schema**: the v1 packets made evaluation impossible for every
  model (undisclosed binding hash). Fixed once, deterministically, and all
  conditions immediately measured through to evaluation. After the fix,
  minimality, no-unrelated-changes, capability honesty and profile respect
  were 1.0 for every model — the protocol now transmits and enforces
  structure perfectly.
- **Model capability, residual**: flash's remaining failures are
  reading-precision — it paraphrases exact disclosed tokens (`permission` →
  `permission_denied`) and made one semantic slip (target-kind change in a
  generalization). GLM-4.7's failures are interface-level: 6/13 schema-invalid
  (malformed JSON), yet **7/7 valid-schema outputs passed — including copying
  the exact id flash missed**. So: schema discipline and token-grounding
  precision are different model capabilities, and the current flash Teacher
  lacks the second while the accessible GLM lacks the first.

### 6. Which exact frozen Teacher configuration should F/G use?

`google/gemini-2.5-flash`, temperature 0, **Core + JevProfile context** (the
frozen packet plus amendment v2), with deterministic validation and hidden
evaluation exactly as run here — pending human review of this ADR. Rationale:
it won the comparison (0.75 vs 0.538), the Profile condition was its best
context (operator/target 1.00), the Skill and Examples add cost without
demonstrated benefit, and the accessible GLM tier's schema discipline
(0.538) disqualifies it for now. The paywalled higher tiers (glm-5.3,
gemini-2.5-pro, gpt-5.x, claude) remain unmeasured — switching later requires
a new authorized comparison. The residual flash weakness (exact-token
grounding) is best mitigated in the protocol (deterministic validators already
reject such candidates) rather than by prompt expansion.

## Budgets and integrity ledger

| Stage              | Authorized             | Consumed (successful)      | Lost to infrastructure                                |
| ------------------ | ---------------------- | -------------------------- | ----------------------------------------------------- |
| 1 calibration      | 120 accepted Jev       | 43                         | 5 cases (rate limits)                                 |
| 2 v1 + v2 ablation | 24 + 24 pre-registered | 20 + 21                    | 4 + 3                                                 |
| 3 comparison       | 26 successful          | 25 (12 flash + 13 glm-4.7) | 1 case + 13 paywalled glm-5.3 attempts (0 inferences) |

All retries were byte-identical and bounded per call; infrastructure failures
never became semantic observations; the frozen benchmark and every historical
artifact verify unchanged; credential scans over all new artifacts are clean.

## Stop state

As authorized, execution stops after Stage 3. No F/G, no policy version, no
activation, no Teacher default change, no merge.
