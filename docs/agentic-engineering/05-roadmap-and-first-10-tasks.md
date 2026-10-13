# 05 — Dependency-Ordered Execution Roadmap & First 10 Tasks

> **Owner:** Abdelhamid Khaled (`AbdelhamidKhald`)  
> **Scope:** 8-stage dependency-ordered implementation roadmap, parallelization strategy, and surgical blueprints for the First 10 Highest-Value Implementation Tasks.

---

## 1. Dependency-Ordered 8-Stage Execution Roadmap

```mermaid
flowchart LR
  S0["Stage 0: Baseline & Security Hardening<br/>(OC-BG-001..004, 008, 009)"] --> S1["Stage 1: Canonical Contracts & Versioning<br/>(OC-BG-005..007, 010, 024..026)"]
  S1 --> S2["Stage 2: Core Agentic Execution & State<br/>(OC-BG-015..017, 030, 035)"]
  S2 --> S3["Stage 3: Capability & Verification Runtime<br/>(OC-BG-018, 019, 032)"]
  S1 --> S4["Stage 4: Evidence, Teacher & Supervision<br/>(OC-BG-014, 020..022)"]
  S3 --> S5["Stage 5: Replay Evaluation & Evolution<br/>(OC-BG-011..013, 036)"]
  S4 --> S5
  S1 --> S6["Stage 6: API, SDK, CLI & UI Unification<br/>(OC-BG-023, 027, 028)"]
  S5 --> S7["Stage 7: Production Hardening & Release<br/>(OC-BG-029, 031, 033, 034, 037, 038)"]
  S6 --> S7
```

### Stage-by-Stage Breakdown (Aligned with `docs/implementation-phases/01..10` & `OC-034`..`OC-039`)

| Stage       | Name                                                                                                     | Entry Criteria                                                                                                                                   | Backlog Items Included                                                                    | Alignment with `docs/implementation-phases/01..10` & Tickets                                                                                    | Parallel Workstreams                                                                                                                                                                                                                                   | Exit Criteria & Verification Gate                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| :---------- | :------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Stage 0** | **Baseline Stabilization, Critical Bug Fixes & Security Emergency Hardening**                            | Current checkout (`abdelhamid-khaled/docs/agentic-harness-audit` with `feat/portal-phase-17` `3ab10ea` & `oc-034-ci-baseline` `ef525ea` merged). | `OC-BG-001`, `OC-BG-002`, `OC-BG-003`, `OC-BG-004`, `OC-BG-008`, `OC-BG-009`              | • `01-verify-ci-baseline.md` (`OC-034`)<br/>• `02-wire-provider-integrations.md` (`OC-035`)                                                     | • **Track A (Python Test & Persistence Fixes):** `OC-BG-001`, `OC-BG-002`, `OC-BG-008` (`0023`), `OC-BG-009`<br/>• **Track B (Security & Control-Plane Fixes):** `OC-BG-003`, `OC-BG-004`                                                              | • `uv run pytest -q` passes with **0 failures, 0 errors** on Windows & Linux (`main.py:237` duplicate `support_router` removed).<br/>• `GET /audit` and `GET /summary` return `200 OK` after unknown triage/clustering/evaluation/alerting (all 10 event types valid).<br/>• `oc_...` API keys authenticate on `IngestionController`.<br/>• SSRF & arbitrary env-var exfiltration blocked in `HTTPIntegrationProbe`.<br/>• Re-clustering preserves `cluster_candidates` (`0023`). |
| **Stage 1** | **Canonical Domain Contracts, Instruction Propagation & Immutable Versioning**                           | Stage 0 green.                                                                                                                                   | `OC-BG-005`, `OC-BG-006`, `OC-BG-007`, `OC-BG-010`, `OC-BG-024`, `OC-BG-025`, `OC-BG-026` | • `03-close-the-learning-loop.md` (`OC-036` versioning & alias foundation)                                                                      | • **Track A (Core & Provider Contracts):** `OC-BG-005`, `OC-BG-006`<br/>• **Track B (DB Versioning & Transactions):** `OC-BG-010` (`0020` + `0024`), `OC-BG-024`, `OC-BG-025`, `OC-BG-026` (`0027`)<br/>• **Track C (SDK/API Alignment):** `OC-BG-007` | • Custom `DecisionService` instructions reach `Jev` and `Laya` prompts.<br/>• `service_versions` (`0020` + `0024`) is append-only with DB triggers and preserves `aliases` in `DecisionChoiceSpec`.<br/>• Tie-breaking selects `UNKNOWN`; `evaluate_predicates` handles missing vs `None` and `bool` vs `int`.<br/>• TS SDK `ingestBatch`, `attachEvidenceToCase`, `transition_evidence`, and `/reject` pass integration tests.                                                   |
| **Stage 2** | **Core Agentic Execution Loop, Multi-Node `PolicyGraph` & `StateCompiler`**                              | Stage 1 green (`0024` migrated).                                                                                                                 | `OC-BG-015`, `OC-BG-016`, `OC-BG-017`, `OC-BG-030`, `OC-BG-035`                           | • `05-harden-fast-path-inference.md` (`OC-038`)<br/>• `06-graduate-multi-step-graphs.md`                                                        | • **Track A (Graph Executor & StateCompiler):** `OC-BG-015`, `OC-BG-016` (`0026`), `OC-BG-035`<br/>• **Track B (Calibration & SQL Pagination):** `OC-BG-017`, `OC-BG-030`                                                                              | • `DecisionExecutor` traverses multi-node `PolicyGraph`s (`max_steps=8`, cycle detection) and persists `DecisionStepTrace`.<br/>• `StateCompiler` compiles `RawEvent.metadata` and enforces field schemas.<br/>• `SupervisionPolicy` replaces hardcoded `"laya"`/`"jev"` branches.                                                                                                                                                                                                |
| **Stage 3** | **Capability Runtime, Macro Expansion, Sandbox Hardening & Independent Verification**                    | Stage 2 green.                                                                                                                                   | `OC-BG-018`, `OC-BG-019`, `OC-BG-032`                                                     | • `08-automate-bounded-actions.md`<br/>• `09-integrate-external-webhooks.md`                                                                    | • **Track A (Core Automation & Verifiers):** `OC-BG-018`<br/>• **Track B (Sandbox & Outbox):** `OC-BG-019`, `OC-BG-032` (`0022`)                                                                                                                       | • `AutomationLoop` validates and expands multi-step macros with 5-gate applicability checks and independent postcondition verifiers.<br/>• `SafeSandboxExecutor` enforces timeouts, output caps, and env allowlists.                                                                                                                                                                                                                                                              |
| **Stage 4** | **Evidence Ledger Unification, Pluggable Embeddings, Teacher v1.1 & Real Supervisor**                    | Stage 1 green (can run in parallel with Stages 2–3).                                                                                             | `OC-BG-014`, `OC-BG-020`, `OC-BG-021`, `OC-BG-022`                                        | • `02-wire-provider-integrations.md` (`OC-035`)<br/>• `03-close-the-learning-loop.md` (`OC-036`)<br/>• `07-attribute-complex-failures.md`       | • **Track A (Embeddings & Unified Candidates):** `OC-BG-014` (`0017`), `OC-BG-022`<br/>• **Track B (Supervisor & Teacher v1.1):** `OC-BG-020`, `OC-BG-021`                                                                                             | • `unknown_triage` and `evidence_items` are synchronized.<br/>• Cluster discovery routes through `ProjectEvolutionService` using configured Teacher.<br/>• Real LLM `SupervisorProvider` and `TeacherProposal` (`apply_candidate`) wired in `provider_config.py`.                                                                                                                                                                                                                 |
| **Stage 5** | **Verified Replay Evaluation, Regression Gates & Controlled Promotion (`OC-008` / `OC-009` / `OC-036`)** | Stages 1, 2, and 4 green.                                                                                                                        | `OC-BG-011`, `OC-BG-012`, `OC-BG-013`, `OC-BG-036`                                        | • `03-close-the-learning-loop.md` (`OC-036`)<br/>• `04-prove-the-learning-loop.md` (`OC-037`)                                                   | • **Track A (Evaluation Datasets & Real Replay Engine):** `OC-BG-011` (`0018` + `0025`), `OC-BG-012` (`0019`)<br/>• **Track B (Transactional Promotion & Drift):** `OC-BG-013` (`0020`), `OC-BG-036` (`0021`)                                          | • Sealed human-verified datasets reject `"prediction"` labels (`0025`).<br/>• `api/evaluations.py:306` replaces hardcoded `MockDecisionProvider()` with real `DecisionExecutor` baseline vs. candidate replay (`simulated=False`) with Teacher disabled.<br/>• Human approval promotes `vN → vN+1` under `SELECT ... FOR UPDATE`, preserves `aliases`, resolves linked evidence, and fixes the `two_weeks_ago` upper-bound bug in `api/operations.py:92-96`.                      |
| **Stage 6** | **API, SDK, CLI & Dual-Frontend Unification**                                                            | Stages 1 and 5 green.                                                                                                                            | `OC-BG-023`, `OC-BG-027`, `OC-BG-028`                                                     | • `09-integrate-external-webhooks.md`<br/>• `10-ship-verified-release.md` (`OC-039`)                                                            | • **Track A (Internal Auth & Tenant Isolation):** `OC-BG-023`<br/>• **Track B (SDK/CLI 100% Parity & Portal/Web Unification):** `OC-BG-027`, `OC-BG-028`                                                                                               | • `apps/portal` uses `@openclass/sdk` (zero raw `fetch`).<br/>• Projects created via SDK/CLI/Web and Portal share a unified registry.<br/>• Python SDK, TS SDK, and CLI cover 100% of server routes (including Phases 11–16 `/evaluations`, `/promotions`, `/alerts`, `/analytics/trends`, `/support`, `/routes`).                                                                                                                                                                |
| **Stage 7** | **Observability, Full-Stack E2E Verification & Release Readiness (`v0.1.0-rc1` / `OC-039`)**             | Stages 3, 5, and 6 green.                                                                                                                        | `OC-BG-029`, `OC-BG-031`, `OC-BG-033`, `OC-BG-034`, `OC-BG-037`, `OC-BG-038`              | • `04-prove-the-learning-loop.md` (`OC-037`)<br/>• `05-harden-fast-path-inference.md` (`OC-038`)<br/>• `10-ship-verified-release.md` (`OC-039`) | • **Track A (Observability & Security Polish):** `OC-BG-029`, `OC-BG-031`<br/>• **Track B (Full-Stack E2E, Docker & Release):** `OC-BG-033`, `OC-BG-034`, `OC-BG-037`, `OC-BG-038`                                                                     | • `make check`, `make test`, PostgreSQL integration suite, Control-Plane Postgres suite, and live-backend Playwright E2E suite pass 100%.<br/>• Second-cycle live application proof (`OC-037`) reduces `scikit-learn` trusted errors below `23.5%` / `19.4%`.<br/>• `docker compose --profile test run test` and `uv build --all-packages` succeed cleanly.                                                                                                                       |

---

## 2. First 10 Highest-Value Implementation Tasks (Ready for Immediate Execution)

These 10 tasks deliver the highest immediate engineering leverage by eliminating all remaining Windows/Linux test discrepancies, removing the duplicate `support_router` mount, fixing critical security vulnerabilities (`SSRF`, secret exfiltration, broken API key auth), fixing the HTTP 500 audit log crash across all 10 uninscribed event types, restoring instruction propagation, and hardening the newly merged `0017`..`0022` evaluation/promotion/versioning tables with real `DecisionExecutor` replay and alias preservation.

### Task 1: Make Test Suite & CI 100% Green Across Windows, Linux & PostgreSQL (`OC-BG-001` / `OC-034`)

- **Branch:** `abdelhamid-khaled/fix/test-suite-and-ci-parity`
- **Context:** `origin/oc-034-ci-baseline` (`ef525ea`) verified Linux CI (`403 passed, 13 skipped` locally; `413 passed, 3 skipped` with Postgres; `50/50` Playwright specs on run `37051177668`), and `feat/portal-phase-17` (`3ab10ea`) already updated `.github/workflows/ci.yml` to `pnpm`. These edits close the remaining Windows failures, unmarked Postgres/live tests, `.github/workflows/artifacts.yml`, and the duplicate `support_router` in `main.py`.
- **Exact Edits:**
  1. `packages/server/openclass_server/main.py:200,237`: Remove the duplicate `app.include_router(support_router)` at line `237`.
  2. `tests/contract/test_jev_provider.py:86` & `tests/contract/test_supervisor_provider.py:72`: Add `ids=["truncated_json", "wrong_type", "oversized_2mb"]` to `@pytest.mark.parametrize` so 2MB strings are not placed into `PYTEST_CURRENT_TEST`.
  3. `tests/integration/test_reviews.py:96`: Pass `decision_provider=MockDecisionProvider()` to `create_app(...)`.
  4. `tests/unit/test_decision_executor.py:95`: Assert `real_run.execution_mode in {"in_process", "deterministic_test_fallback"}` when `laya` is not installed, or inject a deterministic stub router.
  5. `tests/unit/test_automation_reuse.py:142,160` & `.gitattributes`: Normalize CRLF before SHA-256 comparison, add `.gitattributes` (`* text=auto eol=lf`), and use `socket.SO_EXCLUSIVEADDRUSE` on Windows in `scripts/automation_transfer_fixture.py`.
  6. `tests/integration/test_raw_events_postgres.py:59-60`: Update expected status from `201` to `207` and `len(resp.json()["items"]) == 2`. Add `pytestmark = pytest.mark.postgres` to all 6 unmarked `test_*_postgres.py` files and `pytest.mark.live` to `tests/contract/test_gemini_live.py`.
  7. `.github/workflows/artifacts.yml`: Add `pnpm/action-setup@v4` and replace `npm ci` with `pnpm install --frozen-lockfile`.

### Task 2: Fix `UnknownTriageStore.append_audit` HTTP 500 Crash Across All 10 Event Types (`OC-BG-002`)

- **Branch:** `abdelhamid-khaled/fix/audit-event-deserialization`
- **Exact Edits:**
  1. `packages/core/openclass_core/projects.py:78-101`: Add all 10 Portal/triage/evaluation/alerting event types (`"unknown.triaged"`, `"unknown.transitioned"`, `"cluster.updated"`, `"candidate.created"`, `"candidate.updated"`, `"candidate.rejected"`, `"evaluation.dataset_created"`, `"evaluation.dataset_sealed"`, `"evaluation.completed"`, `"quality.alert"`) to `ProjectAuditEvent.event_type`.
  2. `packages/server/openclass_server/persistence/unknown_triage.py:86-110`: Construct a valid `ProjectAuditEvent` and serialize `event.model_dump(mode="json")` into `audit_events.payload`.
  3. `packages/server/openclass_server/persistence/project_repository.py:116-123`: Add defensive fallback in `SQLProjectRepository.audit_events` for any historical row whose `payload` lacks `"id"`.

### Task 3: Fix Control-Plane API Key Authorization (`callerOf`), Scopes & RBAC (`OC-BG-003`)

- **Branch:** `abdelhamid-khaled/fix/control-plane-apikey-auth`
- **Exact Edits:**
  1. `services/control-plane/src/ingestion.controller.ts:26-32`: Include `keyProjectId: request.keyProjectId` and `keyScopes: request.keyScopes` in `callerOf(request)`.
  2. `services/control-plane/src/ingestion.service.ts:45-55, 79, 116`: Check `"read"` scope for `GET` and `"ingest"` scope for `POST`; require `"operator"` minimum role (instead of `"viewer"`) in `ingest` and `ingestBatch`.
  3. `services/control-plane/src/decision.controller.ts:58`: Allow `oc_...` API keys with `"classify"` scope.

### Task 4: Eliminate SSRF & Arbitrary Env-Var Exfiltration (`OC-BG-004`)

- **Branch:** `abdelhamid-khaled/fix/ssrf-and-secret-isolation`
- **Exact Edits:**
  1. `packages/server/openclass_server/security.py`: Implement `validate_outbound_url(url: str)` blocking loopback, RFC1918 private IPs, link-local (`169.254.0.0/16`), multicast, and internal container hostnames after DNS resolution.
  2. `packages/server/openclass_server/integration_adapters.py:29-35, 89-126`: Restrict `EnvironmentSecrets.resolve` to `OPENCLASS_INTEGRATION_SECRET_*` prefix, call `validate_outbound_url(endpoint)`, and set `follow_redirects=False`.
  3. `packages/server/openclass_server/api/providers.py:15,29-42` & `provider_config.py`: Remove plaintext `api_key` from `ProviderConfigPayload`, restrict `api_key_env` prefix, and validate `base_url` via `validate_outbound_url`.

### Task 5: Propagate `DecisionService` & `DecisionNode` Instructions to Providers (`OC-BG-005`)

- **Branch:** `abdelhamid-khaled/fix/instruction-propagation`
- **Exact Edits:**
  1. `packages/core/openclass_core/models.py:109-120`: Add `instructions: str | None = None` to `ChoiceRequest`.
  2. `packages/core/openclass_core/decision_executor.py:58-85, 164`: Pass `instructions = node.instructions or service.instructions` into `ChoiceRequest` and `DecisionRun.instructions_snapshot`.
  3. `packages/core/openclass_core/projects.py:665-678`: Update `service.nodes[0].instructions` when `service.instructions` is updated on a single-node service.
  4. `providers/jev/openclass_provider_jev/__init__.py:102` & `providers/laya/openclass_provider_laya/__init__.py:139,193`: Include `request.instructions` in the provider request payload.

### Task 6: Fix `DecisionExecutor` Tie-Breaking, Stable UUIDs & `evaluate_predicates` (`OC-BG-006`)

- **Branch:** `abdelhamid-khaled/fix/core-decision-invariants`
- **Exact Edits:**
  1. `packages/core/openclass_core/decision_executor.py:58-80, 102-125`: Select `UNKNOWN` whenever `unknown_prob >= top_known_prob` (fixing tie-breaking); derive deterministic `uuid5` identifiers for `OntologyClass.stable_class_id` and `OntologyVersion.id`.
  2. `packages/core/openclass_core/decision.py:217-235`: Check `if predicate.field not in state.facts: return False` and `if isinstance(actual, bool) != isinstance(predicate.equals, bool): return False` in `evaluate_predicates`.

### Task 7: Fix SDK, Server & Web Contract Drift (`OC-BG-007`)

- **Branch:** `abdelhamid-khaled/fix/sdk-api-contract-alignment`
- **Exact Edits:**
  1. `packages/sdk-typescript/src/index.ts:573-582`: Unwrap `.items.map((i) => i.event)` in `ingestBatch`.
  2. `packages/server/openclass_server/api/evidence.py` & `projects.py`: Add `POST /api/v1/projects/{identifier}/evidence-cases/{case_id}/evidence` and accept `note` as alias for `rationale` in `TransitionEvidenceRequest` (`api/schemas.py:240`).
  3. `packages/server/openclass_server/api/evolution.py`: Add `POST /api/v1/projects/{identifier}/candidates/{candidate_id}/reject` (or unify with `/api/v1/projects/{identifier}/unknowns/candidates/{candidate_id}/reject` from `0017`).

### Task 8: Prevent Re-Clustering Cascade Data Loss (`0023`) & Fix Provider Config/Provenance (`OC-BG-008` + `OC-BG-009` / `OC-035`)

- **Branch:** `abdelhamid-khaled/fix/cluster-cascade-and-provider-provenance`
- **Exact Edits:**
  1. `packages/server/openclass_server/persistence/cluster_store.py:45-53`, `tables.py:344` & migration `0023_preserve_cluster_candidates.py`: Change `cluster_candidates.cluster_id` FK to `ondelete="SET NULL"` (`nullable=True`) so re-clustering never deletes discovered candidates or `candidate_reviews` (`0017`).
  2. `providers/jev/openclass_provider_jev/__init__.py:115`: Add `"real_inference": True, "simulated": False, "execution_mode": "api"`.
  3. `providers/laya/openclass_provider_laya/__init__.py:251,280-287`: Set `"simulated": True` in `_local_fallback_choice` and reject distributions where `abs(total - 1.0) > 0.05`.
  4. `packages/server/openclass_server/provider_config.py:95-125`: Validate required `base_url` and API keys explicitly without crashing on `""` or silently falling back on missing diagnosis key, and reconcile the unmerged `artifacts/application-proofs/scikit-learn-2026-10-02/provider-wiring.patch` cleanly (`OC-035`).

### Task 9: Harden `service_versions` (`0020` + `0024`) with Append-Only Triggers, Alias Preservation & Run Lineage (`OC-BG-010`)

- **Branch:** `abdelhamid-khaled/feat/decision-service-versioning`
- **Exact Edits:**
  1. `packages/core/openclass_core/projects.py:157-168` & `promotion.py`: Add `aliases: tuple[str, ...] = ()` to `DecisionChoiceSpec` and update `persistence/promotion_store.py:160` (`_sync_project_Repository_choices`) and `api/promotions.py:148-157` so promoted aliases are preserved in `decision_services.payload` and `service_versions`.
  2. Create Alembic migration `0024_decision_run_version_lineage.py` adding `decision_service_version_id` and `service_hash` columns to `decision_runs` plus PostgreSQL/SQLite append-only triggers (`BEFORE UPDATE` / `BEFORE DELETE`) on `service_versions` (`0020`).
  3. Record `decision_service_version_id` and `service_hash` on every `DecisionRun` and emit `decision_service.*` `ProjectAuditEvent`s.

### Task 10: Replace Hardcoded `MockDecisionProvider` in `api/evaluations.py` with Real `DecisionExecutor` Replay & Unify Promotion (`OC-BG-011` + `OC-BG-012` + `OC-BG-013` / `OC-036`)

- **Branch:** `abdelhamid-khaled/feat/verified-replay-and-promotion`
- **Exact Edits:**
  1. Create migration `0025_evaluation_holdouts_and_provenance.py` adding `label_source`, `verified_by`, `verified_at`, and `split` (`"replay"` | `"holdout"`) to `evaluation_items` (`0018`) and `is_simulated`, `provider`, and `model` to `evaluation_runs` (`0019`).
  2. `packages/server/openclass_server/api/evaluations.py:306,433-452`: Remove the hardcoded `provider = MockDecisionProvider()` and replace `_replay` with real `DecisionExecutor` execution over the project's configured `DecisionProvider` (with Teacher disabled), persisting per-item `EvaluationPredictionRow`s (`0019`) with honest `is_simulated` provenance.
  3. Unify `ProjectEvolutionService.evaluate` / `promote` (`project_evolution.py:204-240`), `DiscoveryService.evaluate` / `approve` (`discovery.py:69-79`), and `PromotionStore.promote_candidate` (`promotion_store.py:55-96`) under `SELECT ... FOR UPDATE`, requiring a passing `evaluation_run_id`, creating `service_versions` (`0020`) `vN+1`, and resolving linked `EvidenceItem`s.
