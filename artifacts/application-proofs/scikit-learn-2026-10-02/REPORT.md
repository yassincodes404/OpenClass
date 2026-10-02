# Real scikit-learn issue triage: measured local application challenge

Workspace: **Real scikit-learn issue triage**. Source: [actual public scikit-learn issues](https://github.com/scikit-learn/scikit-learn/issues). The frozen 60-case cohort uses real source text, real inference and real embeddings. Additional portal observations without source provenance are excluded from all case metrics; two clustering proposals contain these extra observations and are not source-grounded application evidence. Local sign-in is the existing development admin account.

- [GPT project](http://127.0.0.1:5173/projects/2531a8f4-aca6-46bb-9d87-101039032306)
- [GEMINI project](http://127.0.0.1:5173/projects/4f12358b-a753-4f92-a8c2-d7f4b2a725ef)

## Protocol and independent references

60 distinct actual issues, 15 each with exclusive task labels Bug, Enhancement, Documentation and Build / CI. Known choices are BUG, ENHANCEMENT and DOCUMENTATION; Build / CI is deliberately absent and its reference is UNKNOWN. Both providers see the same source title/body without maintainer labels. Data, timestamps, exact submitted text, SHA-256 hashes, truncations, exclusions and selection rules are retained in `dataset.json`, `protocol.json` and GitHub snapshots. Labels are independent source references, not model-generated truth or full human adjudication. Titles sometimes disclose type tags, so this is a small curated application probe, not a production accuracy estimate. Successful retries do not remove original failures.

## Results

| Provider | Completed source cases | Known accuracy | Held-out UNKNOWN recall | Errors labeled TRUSTED |
|---|---:|---:|---:|---:|
| GPT | 56/60 | 39/45 (86.7%) | 4/11 (36.4%) | 12/51 (23.5%) |
| GEMINI | 38/60 | 29/35 (82.9%) | 2/3 (66.7%) | 7/36 (19.4%) |

Full confusion matrices, per-class F1, UNKNOWN precision, p50/p95 latency, run IDs, distributions, provenance and source links are in `results.json` and per-provider decisions. Providers cannot be ranked on these incomplete, differently covered samples. Across all 15 withheld cases, GPT detected 4 and Gemini detected 2; the displayed recall uses only completed cases. Accuracy denominators use completed independent-source-labeled cases; completion coverage and failed terminal cases are shown separately. One reconciled persisted run per source/model is used for metrics; additional attempts and diagnostic runs remain in the database.

Gateway-reported cost for the instrumented API pipeline: **$0.075827 USD**, across 106 calls with reported cost. Scope: Reported successful API-pipeline choice/cluster-discovery calls, including persisted diagnostic duplicates; excludes embeddings without reported cost, connectivity probes, legacy Teacher/diagnosis calls without persisted cost, and unreported failed-call charges. This is not a complete bill. Missing costs are unavailable, not zero.

## Real disagreements

- GPT: [issue #31808](https://github.com/scikit-learn/scikit-learn/issues/31808) — reference `ENHANCEMENT`, prediction `BUG`, supervision `TRUSTED`.
- GPT: [issue #31536](https://github.com/scikit-learn/scikit-learn/issues/31536) — reference `ENHANCEMENT`, prediction `BUG`, supervision `TRUSTED`.
- GPT: [issue #31315](https://github.com/scikit-learn/scikit-learn/issues/31315) — reference `ENHANCEMENT`, prediction `BUG`, supervision `TRUSTED`.
- GPT: [issue #30689](https://github.com/scikit-learn/scikit-learn/issues/30689) — reference `ENHANCEMENT`, prediction `BUG`, supervision `TRUSTED`.
- GPT: [issue #34880](https://github.com/scikit-learn/scikit-learn/issues/34880) — reference `DOCUMENTATION`, prediction `BUG`, supervision `REVIEW`.
- GPT: [issue #34845](https://github.com/scikit-learn/scikit-learn/issues/34845) — reference `DOCUMENTATION`, prediction `BUG`, supervision `TRUSTED`.
- GPT: [issue #34869](https://github.com/scikit-learn/scikit-learn/issues/34869) — reference `UNKNOWN`, prediction `BUG`, supervision `TRUSTED`.
- GPT: [issue #34723](https://github.com/scikit-learn/scikit-learn/issues/34723) — reference `UNKNOWN`, prediction `ENHANCEMENT`, supervision `TRUSTED`.
- GEMINI: [issue #33842](https://github.com/scikit-learn/scikit-learn/issues/33842) — reference `ENHANCEMENT`, prediction `DOCUMENTATION`, supervision `TRUSTED`.
- GEMINI: [issue #31808](https://github.com/scikit-learn/scikit-learn/issues/31808) — reference `ENHANCEMENT`, prediction `BUG`, supervision `TRUSTED`.
- GEMINI: [issue #31536](https://github.com/scikit-learn/scikit-learn/issues/31536) — reference `ENHANCEMENT`, prediction `BUG`, supervision `TRUSTED`.
- GEMINI: [issue #31315](https://github.com/scikit-learn/scikit-learn/issues/31315) — reference `ENHANCEMENT`, prediction `BUG`, supervision `TRUSTED`.
- GEMINI: [issue #30689](https://github.com/scikit-learn/scikit-learn/issues/30689) — reference `ENHANCEMENT`, prediction `BUG`, supervision `TRUSTED`.
- GEMINI: [issue #30664](https://github.com/scikit-learn/scikit-learn/issues/30664) — reference `ENHANCEMENT`, prediction `BUG`, supervision `TRUSTED`.
- GEMINI: [issue #34869](https://github.com/scikit-learn/scikit-learn/issues/34869) — reference `UNKNOWN`, prediction `BUG`, supervision `TRUSTED`.

Every disagreement is retained. A source label can be imperfect; these are disagreements against the declared independent reference, not invented certainty about the correct route.

## Discovery and learning boundaries

- GPT: 3 real embedding clusters; 3 persisted cluster proposals. Teacher: `existing_choice`.
  - `INSUFFICIENT_EVIDENCE` / `None` from 3 runs; status `candidate`, provider `openai-compatible:openai/gpt-4.1-mini`.
  - `INSUFFICIENT_EVIDENCE` / `None` from 1 runs; status `candidate`, provider `openai-compatible:openai/gpt-4.1-mini`.
  - `INSUFFICIENT_EVIDENCE` / `None` from 1 runs; status `candidate`, provider `openai-compatible:openai/gpt-4.1-mini`.
- GEMINI: 2 real embedding clusters; 2 persisted cluster proposals. Teacher: `unavailable`.
  - `INSUFFICIENT_EVIDENCE` / `None` from 2 runs; status `candidate`, provider `openai-compatible:openai/gpt-4.1-mini`.
  - `INSUFFICIENT_EVIDENCE` / `None` from 1 runs; status `candidate`, provider `openai-compatible:openai/gpt-4.1-mini`.

Teacher and discovery suggestions are inactive proposals, never ground truth. Evaluation/activation guard responses and unchanged service snapshots are saved. Verified replay evaluation, human approval, immutable activation and a verified external task execution are not implemented by this branch. No learned improvement, retention, real-world action success or end-to-end autonomous learning is claimed.

## What this challenged

1. The original Phase 10 clustering and cluster-discovery endpoints hard-coded simulated adapters; bounded existing-port HTTP wiring was required to run this real-only case. The original branch cannot claim these results without that local patch.
2. Real requests exposed gateway HTTP 429s, surfaced by the portal as generic HTTP 502s. Failures were retained, retries paced and persisted results reconciled. Error identity/usage and recovery are insufficient for production operation.
3. The full real ingestion request exceeded the control plane's HTTP body limit (413); eight-item batches succeeded. Batch item limits alone do not describe payload byte limits.
4. Uncalibrated LLM self-assessment can receive TRUSTED status through the current generic margin rule. The trusted-reference-error denominator is reported explicitly.
5. Decision-service instructions are stored, but the executor's choice port carries the observation and bounded ontology, not the full service instructions. This experiment encoded scope in choice definitions too.
6. The UNKNOWN/clustering surface examines only the latest 200 runs. Repeated source events, mixed providers and long-lived projects need explicit cohort/evidence handling; this report reconciles unique source/model records.
7. Provider-config cards are stored references rather than enforced bindings. Explicit per-service model overrides were added and used for this comparison. Embedding/discovery/Teacher telemetry is not fully reflected in portal cost rollups.
8. Jev was actually attempted through Vercel and returned HTTP 403 `no_providers_available`; Gemini and GPT connectivity and decisions were real hosted calls.
9. Core audit reads return HTTP 400 after clustering because stored audit payloads disagree with the core reader schema. Authenticated control-plane audit reads still work; both outcomes are retained.
10. Code inspection shows re-clustering deletes previous clusters and cascades to their proposals, threatening retained review history. This destructive path was not exercised again. Three of the five current clusters contain frozen-cohort sources; two contain additional observations without source provenance.
11. The safe evaluation and activation blocks remain in force. Before/after learned quality and verified outbound action metrics are unavailable.

## Validation and retained artifacts

Focused adapter and Phase 9/10 contract/persistence tests: 28 passed. Python lint/format and provider/server strict typing passed. Portal and control-plane builds/tests passed; Python package builds passed. A freshly migrated disposable PostgreSQL database passed all four persistence tests with explicit mock test fixtures; those fixtures are separate from the real application workspace. The default-provider persistence run failed the unchanged unavailable-Laya assumption. Full `make check` fails on 79 existing Prettier formatting files. Full `make test` yielded 412 passed, 14 skipped, 2 failures in unchanged Laya/supervisor assumptions. Full `npm run build` could not build the separate unused Next.js app because its dependency download/install was incomplete. These qualifications are retained in validation logs; they are not passing-release claims.

The experiment is an isolated local Phase 10 checkout. `provider-wiring.patch`, the added adapter/tests, the credential-free runner and the provider guide preserve the reviewable change. No upstream issues, packages, releases or images were published.
