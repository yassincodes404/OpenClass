# Phase 07 — Provider Protocol & Cost Controls

- **Depends on:** Phase 06
- **Traceability:** SPEC §§18–23 (DecisionProvider choice/boolean/score, adapters mock/Jev, discovery OpenAI/Ollama, embeddings sentence-transformers); OC-003 (RFC-0001 full), OC-004 (Jev)

## 1. Goal

Standardize provider integration with capabilities, safe errors, normalization, timeouts/retries, usage/cost capture, and health — while keeping mock clearly simulated.

## 2. Non-goals

- No new decision quality features. No embeddings model training (Phase 09 uses local sentence-transformers only when needed).

## 3. Constraints

- Core defines ports; providers implement them. No provider imports in core/storage.
- No adapter is “implemented” without contract tests + real normalization + error handling + usage capture.
- Secrets env-only; sanitized errors; no vendor-required fields in core.
- Mock stays `simulated: true`, lexical matching documented as demo-only.

## 4. Tasks

### Engine

1. `DecisionProvider` capabilities: `["choice"]` now; stub `boolean|score` for future. Registry with `mock`, `jev`, `laya`, `ollama`, `openai-compatible` (discovery/embedding variants where applicable).
2. Structured errors: `timeout|rate_limit|auth|bad_response|unsupported|unknown` with safe messages; map to HTTP 502 + `provider.error` event.
3. Normalization: coerce provider output to `{ choice|UNKNOWN, probabilities, confidence }`; reject malformed/nonfinite/incomplete (400/502, no run persisted on provider failure).
4. Timeouts (20s default), bounded retries (≤2), backoff; capture `model, latency_ms, tokens, cost_usd, retries`.
5. `GET /api/v1/providers`, `GET /api/v1/providers/status` harden; `POST /api/v1/providers/test { provider, config_ref }` dry-run (no persistence).

### Control-plane

Provider config refs (not raw keys): `POST /control/.../providers { type, endpoint_ref, model, timeout }`; test endpoint; usage rollups.

### Portal

`/projects/:id/providers`: cards per provider (status, model, default badge, simulated badge), config form (endpoint/model/timeout, no raw key display), Test button with safe result, usage table (calls, avg latency, est. cost).

## 5. Data & migrations

`providers`, `provider_usage (id, project_id, provider, model, calls, tokens, cost, latency_ms, errors, date)`; indexes by project/date.

## 6. API

- `GET /api/v1/providers`, `GET /api/v1/providers/status`
- `POST /api/v1/providers/test` → `{ ok, latency_ms, normalized_preview }` or safe error
- `GET /control/.../usage?from&to` → aggregated usage

## 7. Portal routes

| Route                     | Expected                                                                     |
| ------------------------- | ---------------------------------------------------------------------------- |
| `/projects/:id/providers` | Mock shows simulated; Jev shows configured/unconfigured honestly; test works |
| `/projects/:id/runs`      | Each run shows provider/model + simulated badge when mock                    |

## 8. Seeder + credentials

`pnpm seed:portal-phase-07`: sets mock as default (simulated), adds unconfigured Jev entry, seeds usage fixtures. Owner configures; reviewer read-only.

## 9. Manual browser tests

| #   | Action                     | Expected                               |
| --- | -------------------------- | -------------------------------------- |
| 1   | Test mock provider         | Success, labeled simulated             |
| 2   | Test bad endpoint          | Safe error, no secret, event logged    |
| 3   | Classify via each provider | Usage counters increment               |
| 4   | Open status                | Default provider highlighted correctly |

## 10. Automated tests

Shared contract suite: malformed JSON, unknown enums, out-of-range confidence, oversize rationale, timeouts, HTTP failures, secret-bearing upstream errors (must be sanitized). Replayable fixtures; no live keys in CI.

## 11. Acceptance

- [ ] All adapters pass contracts; failures are safe and observable.
- [ ] Usage/cost captured per run.
- [ ] Mock never claims real capability.

## 12. Risks

Cost overruns → per-workspace caps + alerts (Phase 15 consumes this). Vendor drift → contract tests pin shapes.
