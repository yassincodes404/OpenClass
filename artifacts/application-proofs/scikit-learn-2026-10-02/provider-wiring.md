# Real-provider issue triage (local experiment)

The Phase 10 baseline hard-coded lexical simulated embeddings and mock cluster
discovery. This local checkout adds OpenAI-compatible HTTP adapters implementing
the existing choice, embedding and cluster discovery ports. Core and persistence
schemas are unchanged. No migration is needed. This is experimental provider
wiring, not a release or a completed learning loop.

Configure secrets in the process environment only:

```sh
OPENCLASS_DECISION_PROVIDER=openai-compatible
OPENCLASS_DISCOVERY_PROVIDER=openai-compatible
OPENCLASS_EMBEDDING_PROVIDER=openai-compatible
OPENCLASS_DISCOVERY_BASE_URL=https://ai-gateway.vercel.sh/v1
OPENCLASS_DISCOVERY_MODEL=openai/gpt-4.1-mini
OPENCLASS_EMBEDDING_MODEL=openai/text-embedding-3-small
```

Set `OPENCLASS_DISCOVERY_API_KEY` securely outside source. Decision and discovery
use the configured chat model; embeddings support the 1536-dimensional models
`openai/text-embedding-3-small` and `cohere/embed-v4.0`. HTTP failures raise sanitized ProviderError;
invalid distributions, missing vectors and unsafe cluster proposals fail closed.
No deterministic fallback runs for these adapters. Metadata distinguishes real
inference and uncalibrated LLM self-assessment. Scores are not calibration evidence.

An existing decision service may use the explicit overrides
`openai-compatible:openai/gpt-4.1-mini` or
`openai-compatible:google/gemini-2.5-flash`. Unregistered names fail closed.
Choice output budgets are 256 and 768 tokens respectively; cluster proposal
budgets are 1800 tokens. Recorded live transport failures are retained even when
later paced retries complete the same independently labeled source event.

Existing API routes retain their schemas: project events, decision-service runs,
UNKNOWN clustering, cluster discovery and inactive discovery candidates. Cluster
and candidate responses set `simulated: false` for the real configured adapters.
Persisted decision runs retain tokens and gateway-reported cost. Safe provider
completion/error logging exposes model, usage, timing and status without prompts,
upstream error bodies or credentials. Existing cluster/candidate audit events stay
active. Embedding/discovery costs are not yet in portal usage rollups.

External maintainer labels are independent evaluation references, not LLM labels.
Keep source identifiers and exact imported content, truncation and excluded-case
records. Store labels separately from submitted text. Never infer production
accuracy from a small curated public issue cohort.

Real-provider contract tests use HTTP stubs only to test validation boundaries;
the application experiment must use actual hosted inference. Verified evaluation,
human approval, immutable activation and outbound task execution remain absent.
Their absence must be reported; never bypass them to demonstrate improvement.
