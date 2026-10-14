# 04 — Complete Executable Development Backlog

> **Owner:** Abdelhamid Khaled (`AbdelhamidKhald`)  
> **Scope:** Complete, dependency-ordered backlog (`OC-BG-001` through `OC-BG-038`) covering every P0–P3 defect, security vulnerability, disconnected subsystem, missing capability, and production-readiness requirement across OpenClass.

---

## 1. Master Backlog Overview Table (Post-PR #27–#54 Reconciliation)

| ID            | Priority | Workstream                                      | Title                                                                                                                                                                                                                                                                                                                                                                               | Status                                | Effort | Primary Affected Files                                                                                                                                                                                                 |
| :------------ | :------: | :---------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------ | :----: | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **OC-BG-001** |  **P0**  | WS-14 (`OC-034` / Phase 00)                     | Fix remaining local/Windows `pytest` failures (2MB parametrize IDs, `test_reviews.py:96`, `test_automation_reuse.py` CRLF/`SO_REUSEADDR`), remove duplicate `support_router` in `main.py:237`, and resolve 18 offline CI test failures (PR #29, PR #51)                                                                                                                             | **VERIFIED** (PR #29, PR #51)         |   S    | `tests/contract/test_{jev,supervisor}_provider.py`, `tests/integration/test_reviews.py`, `tests/unit/test_automation_reuse.py`, `packages/server/openclass_server/main.py:200,237`, `.gitattributes`                   |
| **OC-BG-002** |  **P0**  | WS-09 / WS-08 (Impl Phase 04)                   | Fix `UnknownTriageStore.append_audit` schema corruption across all 10 Phase 08–15 event types crashing `GET /audit` and `GET /summary` (`REPORT.md` Finding #9)                                                                                                                                                                                                                     | **VERIFIED** (PR #30)                 |   S    | `packages/server/openclass_server/persistence/unknown_triage.py:86-110`, `packages/core/openclass_core/projects.py:78-101`, `persistence/project_repository.py:116-123`                                                |
| **OC-BG-003** |  **P0**  | WS-11 (Impl Phase 01)                           | Fix Control-Plane `callerOf(request)` dropping `keyProjectId` (breaking all `oc_...` API keys), enforce granular API key scopes, and require `operator` role for ingestion                                                                                                                                                                                                          | **VERIFIED** (PR #31)                 |   S    | `services/control-plane/src/ingestion.controller.ts:26-35`, `services/control-plane/src/ingestion.service.ts:34-61,79,116,235-251`, `decision.controller.ts:58`                                                        |
| **OC-BG-004** |  **P0**  | WS-10 / WS-11 (Impl Phase 01/02)                | Eliminate SSRF and arbitrary env-var exfiltration in `HTTPIntegrationProbe.check`, `EnvironmentSecrets.resolve`, and provider `base_url`                                                                                                                                                                                                                                            | **VERIFIED** (PR #32)                 |   M    | `packages/server/openclass_server/integration_adapters.py:25-37,89-126`, `api/providers.py:15,29-42`, `provider_config.py:71,97,123`                                                                                   |
| **OC-BG-005** |  **P0**  | WS-03 / WS-05 (Impl Phase 02)                   | Fix custom instruction propagation from `DecisionService`/`DecisionNode` through `DecisionExecutor` to `JevDecisionProvider`, `LayaDecisionProvider`, and `MockDecisionProvider` (`REPORT.md` Finding #5)                                                                                                                                                                           | **VERIFIED** (PR #33)                 |   M    | `packages/core/openclass_core/decision_executor.py:58-85`, `projects.py:671-672`, `models.py:109-120`, `providers/jev/__init__.py:19-23,102`, `providers/laya/__init__.py:27-31,139`                                   |
| **OC-BG-006** |  **P0**  | WS-03 / WS-04 (Impl Phase 02/03)                | Fix `DecisionExecutor` tie-breaking bug (favoring known choice over `UNKNOWN`), ephemeral class UUID generation, and `evaluate_predicates` missing-vs-`None` & `bool`-vs-`int` bugs                                                                                                                                                                                                 | **VERIFIED** (PR #34)                 |   S    | `packages/core/openclass_core/decision_executor.py:58-80,102-115`, `packages/core/openclass_core/decision.py:217-235`                                                                                                  |
| **OC-BG-007** |  **P0**  | WS-12 / WS-13 (Impl Phase 06)                   | Fix broken SDK/API contracts: `ingestBatch` 207 response unwrapping, missing `POST /evidence-cases/{cid}/evidence` route (404), `transition_evidence` `note` vs `rationale`, and missing `POST /candidates/{cid}/reject` route                                                                                                                                                      | **VERIFIED** (PR #35)                 |   M    | `packages/sdk-typescript/src/index.ts:573,773,800`, `packages/sdk-python/openclass_sdk/__init__.py:442,466`, `api/evidence.py`, `api/evolution.py`, `apps/web/app/projects/[id]/{data,evolution}/page.tsx`             |
| **OC-BG-008** |  **P0**  | WS-08 / WS-09 (Impl Phase 05)                   | Prevent `ClusterStore.replace_clusters` from cascade-deleting `cluster_candidates`, `candidate_evidence`, and `candidate_reviews` on re-clustering (`0023_preserve_cluster_candidates.py`; `REPORT.md` Finding #10)                                                                                                                                                                 | **VERIFIED** (PR #36)                 |   S    | `packages/server/openclass_server/persistence/cluster_store.py:45-53`, `tables.py:344,361`, `migrations/versions/0023_preserve_cluster_candidates.py`                                                                  |
| **OC-BG-009** |  **P0**  | WS-05 / WS-07 / WS-08 (Impl Phase 02 & 06)      | Fix `provider_config.py` & provenance (`Jev`/`Laya`); activate Track 2 (`/candidates/{cid}/promote`) & Track 3 (`/discovery-candidates/{cid}/promote`) while legacy Track 1 (`POST /classifiers/{slug}/candidates`) remains fail-closed (`409`)                                                                                                                                     | **PARTIAL** (PR #36, PR #38, PR #54)  |   S    | `packages/server/openclass_server/provider_config.py`, `api/{classifiers,evolution,promotions}.py`, `packages/core/openclass_core/evolution.py`                                                                        |
| **OC-BG-010** |  **P0**  | WS-09 (`OC-017` / Impl Phase 02 & 08)           | Complete `DecisionServiceVersion` & alias lineage on top of `0020_service_versions.py` (`0024_decision_run_version_lineage.py`): add `aliases` to `DecisionChoiceSpec`, stop stripping aliases in `promotions.py:148`/`promotion_store.py:160`, and record `decision_service_version_id` on `DecisionRun`                                                                           | **VERIFIED** (PR #37)                 |   M    | `packages/core/openclass_core/projects.py:157-237,470-705`, `api/promotions.py:148-157`, `persistence/promotion_store.py:154-178`, `persistence/tables.py`, `migrations/versions/0024_decision_run_version_lineage.py` |
| **OC-BG-011** |  **P1**  | WS-08 (`OC-008` / Impl Phase 07)                | Extend `0018_evaluation_sets.py` & `evaluation.py` with holdout splits (`source_type`), deterministic `dataset_hash`, `label_source != "prediction"`, and discovery-to-holdout leakage blocking (`0025`; examples in `evaluation_examples` with provenance in `evaluation_examples.example_metadata` JSON column rather than normalized per-example `evaluation_predictions` table) | **PARTIAL** (PR #38, PR #54)          |   M    | `packages/core/openclass_core/evaluation.py:1-84`, `api/evaluations.py:35-265`, `persistence/tables.py`, `migrations/versions/0025_evaluation_holdouts_and_provenance.py`                                              |
| **OC-BG-012** |  **P1**  | WS-08 (`OC-008` / Impl Phase 07)                | Replace hardcoded `MockDecisionProvider()` in `api/evaluations.py:306` with real `DecisionExecutor` replay (Teacher disabled) over `0019_evaluation_runs.py` and wire `ProjectEvolutionService.evaluate` & `DiscoveryService.evaluate`                                                                                                                                              | **VERIFIED** (PR #38, PR #54)         |   L    | `packages/server/openclass_server/api/evaluations.py:266-453`, `packages/core/openclass_core/{evaluation_metrics,project_evolution,discovery}.py`, `api/{evolution,classifiers}.py`                                    |
| **OC-BG-013** |  **P1**  | WS-08 (`OC-009` / Impl Phase 08)                | Harden `api/promotions.py` & `ProjectEvolutionService.promote` over `0017_candidate_reviews` & `0020_service_versions` (`overall_passed`, `zero_regressions`, `holdout_examples >= 1`, `409` collision guard; legacy `Classifier` ontology snapshots in `0001_genesis` remain read-only)                                                                                            | **PARTIAL** (PR #38, PR #54)          |   M    | `packages/server/openclass_server/api/promotions.py:101-269`, `persistence/promotion_store.py`, `packages/core/openclass_core/{promotion,project_evolution,discovery}.py`                                              |
| **OC-BG-014** |  **P1**  | WS-08 (Impl Phase 05 & 06)                      | Unify `GatewayClusterDiscovery` / `ProjectEvolutionService`, synchronize `unknown_triage` with `evidence_items`, and auto-resolve linked cluster `UnknownEventRow`s on promotion (`vN+1`) (no background batch re-ingestion of historical raw events)                                                                                                                               | **PARTIAL** (PR #38, PR #45, PR #54)  |   L    | `packages/core/openclass_core/{evolution,project_evolution,candidates,unknown_pool,evidence}.py`, `api/{evolution,candidates,unknowns,evidence,promotions}.py`                                                         |
| **OC-BG-015** |  **P1**  | WS-03 (`OC-035` / Impl Phase 02)                | Upgrade `DecisionExecutor` to execute multi-node `PolicyGraph` transitions, cycle detection, step budgets (`max_steps`), and durable step traces                                                                                                                                                                                                                                    | **VERIFIED** (PR #42, PR #52)         |   L    | `packages/core/openclass_core/{decision,decision_executor,projects}.py`, `scripts/jev_contract/runtime.py:89-192`                                                                                                      |
| **OC-BG-016** |  **P1**  | WS-04 / WS-05 (`OC-035` / Impl Phase 01–03)     | Implement `GatewayDecisionProvider` probability distributions (`temperature >= 0.5`), token/cost telemetry & `429` retry handling, plus `RawEvent.metadata` compilation (no holdout ECE temperature-fitting pipeline)                                                                                                                                                               | **PARTIAL** (PR #42, PR #45)          |   M    | `providers/glm/openclass_provider_glm/gateway.py`, `packages/core/openclass_core/{decision,decision_executor,projects}.py`                                                                                             |
| **OC-BG-017** |  **P1**  | WS-05 / WS-08 (Impl Phase 03 & 05)              | Implement node-level `SupervisionPolicy` + `GatewayEmbedder` (`text-embedding-3-small`) + SQLite/PostgreSQL `embedding_cache` (`content_hash`) + greedy cosine clustering (HDBSCAN and Silhouette/Davies-Bouldin metrics not implemented)                                                                                                                                           | **PARTIAL** (PR #42, PR #45)          |   M    | `packages/core/openclass_core/{decision,decision_executor}.py`, `providers/glm/openclass_provider_glm/gateway.py`, `packages/server/openclass_server/persistence/cluster_store.py`                                     |
| **OC-BG-018** |  **P1**  | WS-06 (`OC-035` / Impl Phase 09)                | Fix `AutomationLoop` macro validation/expansion, port 5-gate macro applicability & independent postcondition verifiers from `scripts/automation_*.py` to `packages/core`                                                                                                                                                                                                            | **VERIFIED** (PR #43)                 |   L    | `packages/core/openclass_core/{automation,decision}.py`, `scripts/automation_{applicability,attempts,proof2b_cycle2}.py`                                                                                               |
| **OC-BG-019** |  **P1**  | WS-06 (`OC-035` / Impl Phase 09)                | Harden `SafeSandboxExecutor` with subprocess timeouts, output caps, strict env-var allowlisting, port range restrictions, and complete action handlers                                                                                                                                                                                                                              | **VERIFIED** (PR #43)                 |   M    | `packages/server/openclass_server/automation_executor.py:21-105`, `tests/unit/test_automation_executor.py`                                                                                                             |
| **OC-BG-020** |  **P1**  | WS-07 (`OC-018`, `OC-020` / Impl Phase 03 & 06) | Wire real LLM `SupervisorProvider` (OpenAI-compatible / Ollama) in `provider_config.py` and add sampled/triggered continuous supervision                                                                                                                                                                                                                                            | **VERIFIED** (PR #46)                 |   M    | `packages/core/openclass_core/supervisor.py`, `providers/glm/openclass_provider_glm/supervisor.py` (new), `packages/server/openclass_server/provider_config.py:56-58`                                                  |
| **OC-BG-021** |  **P1**  | WS-07 / WS-11 (Impl Phase 06 & 10)              | Promote Teacher Protocol v1.1 (`apply_candidate`) into `openclass_core.evolution` and enforce sliding-window rate limits in `openclass_server/rate_limit.py` and `control-plane/src/rate-limit.service.ts` (per-process memory; no Redis backend)                                                                                                                                   | **PARTIAL** (PR #40, PR #46)          |   L    | `packages/core/openclass_core/evolution.py`, `packages/server/openclass_server/rate_limit.py`, `services/control-plane/src/rate-limit.service.ts`                                                                      |
| **OC-BG-022** |  **P1**  | WS-08 (`OC-005` / Impl Phase 05)                | Merge & harden `GatewayEmbedder` (`provider-wiring.patch`) + async `SentenceTransformerEmbedder`, cache embeddings in `ClusterStore`, and use `pgvector` on PostgreSQL                                                                                                                                                                                                              | **VERIFIED** (PR #45)                 |   M    | `packages/server/openclass_server/embeddings_local.py:48-65`, `persistence/cluster_store.py:18-37`, `api/clusters.py:35-59`, `artifacts/application-proofs/scikit-learn-2026-10-02/provider-wiring.patch`              |
| **OC-BG-023** |  **P1**  | WS-11 (Impl Phase 01 & 10)                      | Authenticate Control-Plane-to-Engine traffic (`X-OpenClass-Internal-Token`), propagate workspace headers, and enforce prompt-injection delimiters & sanitization in `openclass_server/redaction.py`, `providers/glm`, and `providers/jev` (no standalone `openclass_core/prompt_safety.py`)                                                                                         | **PARTIAL** (PR #40, PR #47)          |   M    | `packages/server/openclass_server/{security,redaction,main}.py`, `providers/glm/`, `providers/jev/`, `services/control-plane/src/engine.ts`                                                                            |
| **OC-BG-024** |  **P1**  | WS-09 / WS-10 (`OC-036` / Impl Phase 01)        | Fix webhook `409 Conflict` on duplicate content hash across distinct `event_key`s, and fix `IdempotencyStore` request-hash validation, TOCTOU race, and expiry refresh                                                                                                                                                                                                              | **VERIFIED** (PR #44)                 |   M    | `packages/server/openclass_server/persistence/{integration_repository,idempotency}.py`, `api/projects.py:113-198`, `services/control-plane/src/idempotency.service.ts`                                                 |
| **OC-BG-025** |  **P1**  | WS-09 (Impl Phase 01 & 04)                      | Wrap multi-step `ProjectService` mutations in atomic Unit-of-Work transactions, add `SELECT ... FOR UPDATE`, and add `UNIQUE(decision_run_id)` on `evidence_items`                                                                                                                                                                                                                  | **VERIFIED** (PR #49)                 |   M    | `packages/server/openclass_server/persistence/{project_repository,repository,tables}.py`, `packages/core/openclass_core/projects.py`                                                                                   |
| **OC-BG-026** |  **P1**  | WS-09 (Impl Phase 01)                           | Reconcile Engine Alembic vs. Control-Plane SQL migrations (`include_name` filter, control-plane migration runner, scoped slug uniqueness, append-only triggers)                                                                                                                                                                                                                     | **VERIFIED** (PR #49)                 |   M    | `packages/server/openclass_server/migrations/env.py`, `services/control-plane/migrations/0002..0003.sql`, `services/control-plane/src/project.service.ts`                                                              |
| **OC-BG-027** |  **P1**  | WS-13 (Impl Phase 10)                           | Reconcile `apps/portal` + `services/control-plane` vs. `apps/web`: synchronize project creation (`reconcileEngineProjects`), replace raw `fetch()` in `apps/portal/src/api.ts` with `OpenClassControlClient` (`@openclass/sdk`), and raise Express batch payload byte limit                                                                                                         | **VERIFIED** (PR #44, PR #50, PR #53) |   L    | `apps/portal/src/{api.ts,portal.tsx}`, `services/control-plane/src/{project.service.ts,engine.ts,main.ts}`, `packages/sdk-typescript/src/index.ts`                                                                     |
| **OC-BG-028** |  **P1**  | WS-12 (`OC-010`)                                | Achieve 100% endpoint parity across Python SDK, TypeScript SDK, and `openclass` CLI for all server routes (including Phase 05–16 routes and `OpenClassControlClient`)                                                                                                                                                                                                               | **VERIFIED** (PR #48, PR #53)         |   M    | `packages/sdk-python/openclass_sdk/__init__.py`, `packages/sdk-typescript/src/index.ts`, `packages/cli/openclass_cli/main.py`                                                                                          |
| **OC-BG-029** |  **P1**  | WS-04 / WS-14 (`OC-037` / Impl Phase 02 & 04)   | Fix `record_provider_error` & HTTP `429` telemetry; compile deterministic state facts + prior resolved decisions with `snapshot_hash` via `compile_event_state` in `decision_executor.py` (no separate `0027_state_schemas.py` SQL table)                                                                                                                                           | **PARTIAL** (PR #39, PR #42)          |   S    | `packages/core/openclass_core/decision_executor.py`, `packages/server/openclass_server/api/decisions.py:125-132`, `persistence/{project_repository,tables}.py`                                                         |
| **OC-BG-030** |  **P1**  | WS-06 / WS-09 (Impl Phase 05 & 09)              | Paginate `/unknowns` and `/clusters` queries without 200-row truncation caps; implement `AutomationLoop` and `SafeSandboxExecutor` in `openclass_core/automation.py` without dedicated SQL tables or FastAPI routes                                                                                                                                                                 | **PARTIAL** (PR #39, PR #43)          |   M    | `packages/core/openclass_core/automation.py`, `packages/server/openclass_server/api/{unknowns,clusters,operations}.py`, `persistence/project_repository.py`                                                            |
| **OC-BG-031** |  **P2**  | WS-11 (Impl Phase 10)                           | Wire `Settings.redaction_enabled` & `redaction_blocklist`, fix recursive `redact_mapping`, fix `RateLimiter.route_class` HTTP method check & bucket eviction, and add prompt-injection boundaries                                                                                                                                                                                   | **VERIFIED** (PR #40)                 |   M    | `packages/server/openclass_server/{redaction,rate_limit,settings}.py`, `providers/glm/openclass_provider_glm/{__init__,diagnosis}.py`                                                                                  |
| **OC-BG-032** |  **P2**  | WS-10 (`OC-036` / Impl Phase 09)                | Implement `HTTPIntegrationProbe` (REST, Webhook, MCP JSON-RPC `tools/list`, Provider) with SSRF protection and idempotent `RouteOutcome` evaluation in `api/support.py` (`delivery_mode="simulated"`, without background webhook delivery worker or retry queue)                                                                                                                    | **PARTIAL** (PR #32, PR #49)          |   L    | `packages/core/openclass_core/routing.py`, `packages/server/openclass_server/api/support.py`, `integration_adapters.py:78-80`, `persistence/tables.py`                                                                 |
| **OC-BG-033** |  **P2**  | WS-13 / WS-14 (Impl Phase 01..10)               | Wire `apps/portal` 100% through `@openclass/sdk` (`OpenClassControlClient`), reconcile `control_projects` ↔ `projects`, and expand Portal/Control-Plane/Landing tests (`apps/web` and `apps/portal` both remain active rather than retiring `apps/web`)                                                                                                                             | **PARTIAL** (PR #49, PR #50, PR #53)  |   M    | `apps/portal/src/{api.ts,portal.test.tsx}`, `services/control-plane/src/{project.service.ts,engine.spec.ts}`, `apps/web/tests/landing-consistency.test.mjs`                                                            |
| **OC-BG-034** |  **P2**  | WS-14 (`OC-038`, `OC-039`)                      | Make `benchmarks/jev-contract/v1` self-contained without gitignored `build/` paths, add `COPY benchmarks examples` to `Dockerfile`, and execute closed-loop evolution proof (`tests/e2e/test_closed_loop_evolution.py`)                                                                                                                                                             | **VERIFIED** (PR #41, PR #54)         |   M    | `Dockerfile:21-32`, `docker-compose.yml`, `scripts/jev_contract/audit.py`, `pyproject.toml:42`, `tests/e2e/test_closed_loop_evolution.py`                                                                              |
| **OC-BG-035** |  **P2**  | WS-03 (`OC-035` / Impl Phase 09)                | Add durable multi-step run checkpoints (`decision_run_checkpoints`, `0026_decision_run_checkpoints.py`), `waiting_human` / `paused` / `cancelled` lifecycle, human-in-the-loop step approval, and `/pause`, `/approve`, `/resume`, `/cancel` APIs                                                                                                                                   | **VERIFIED** (PR #49, PR #52)         |   L    | `packages/core/openclass_core/{decision_executor,projects}.py`, `persistence/tables.py`, `migrations/versions/0026_decision_run_checkpoints.py`, `api/decisions.py`                                                    |
| **OC-BG-036** |  **P2**  | WS-08 (`OC-037` / Impl Phase 10)                | Fix `api/operations.py:92-96` `two_weeks_ago` window bug (missing `< week_ago` upper bound), implement persisted `OC-037` application proof reports, and add post-promotion drift triggers                                                                                                                                                                                          | **VERIFIED** (PR #39)                 |   M    | `packages/server/openclass_server/api/operations.py:40-174`, `packages/core/openclass_core/{alerting,analytics}.py`                                                                                                    |
| **OC-BG-037** |  **P3**  | WS-05 (Provider Packaging)                      | Consolidate or implement standalone `providers/ollama` and `providers/openai-compatible` packages (`12/12` workspace packages build cleanly)                                                                                                                                                                                                                                        | **VERIFIED** (PR #50)                 |   S    | `providers/ollama/`, `providers/openai-compatible/`, `providers/glm/`                                                                                                                                                  |
| **OC-BG-038** |  **P3**  | WS-12 (`OC-011` / `OC-013`)                     | Implement `packages/tui` terminal inspector using `openclass-sdk`                                                                                                                                                                                                                                                                                                                   | **VERIFIED** (PR #49)                 |   M    | `packages/tui/`                                                                                                                                                                                                        |

### 1.1 Honest Partial-Scope Reconciliation (`PARTIAL` vs. `VERIFIED`)

Across the 38 backlog items (`OC-BG-001` through `OC-BG-038`), **26 items are `VERIFIED` end-to-end** and **12 items (`OC-BG-009`, `011`, `013`, `014`, `016`, `017`, `021`, `023`, `029`, `030`, `032`, `033`) are `PARTIAL`** with explicit scope boundaries documented below:

| Backlog ID    |   Status    | Shipped & Verified Scope                                                                                                                                                                                                      | Remaining Unimplemented / Partial Scope                                                                                                                                                                                                                                                                              |
| :------------ | :---------: | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **OC-BG-009** | **PARTIAL** | Track 2 (`/api/v1/projects/{id}/candidates/{cid}/promote`) and Track 3 (`/api/v1/projects/{id}/discovery-candidates/{cid}/promote`) are active and gated by sealed evaluation datasets; `Jev`/`Laya` provenance hardened.     | Legacy Track 1 (`POST /api/v1/classifiers/{slug}/candidates`) remains fail-closed (`409`), and `openclass_core.evolution.apply_candidate` is verified in unit tests rather than wired to Track 1 HTTP routes.                                                                                                        |
| **OC-BG-011** | **PARTIAL** | `EvaluationExample` enforces `source_type` (`verified_holdout`, `regression_baseline`, `calibration_dev`), rejects `label_source="prediction"` (`422`), and blocks discovery-to-holdout leakage (`409`).                      | Examples are stored in the `evaluation_examples` SQL table (`0018_evaluation_sets.py`) with provenance fields stored inside the `evaluation_examples.example_metadata` JSON column (`0025_evaluation_holdouts_and_provenance.py`), rather than a separate normalized per-example `evaluation_predictions` SQL table. |
| **OC-BG-013** | **PARTIAL** | `promotions.py` and `project_evolution.py` enforce `overall_passed is True`, `zero_regressions`, `holdout_examples >= 1`, and alias/key collision rejection (`409`) on `DecisionService` versions (`0020`).                   | Legacy `Classifier` ontology snapshots (`0001_genesis`) remain read-only after creation.                                                                                                                                                                                                                             |
| **OC-BG-014** | **PARTIAL** | Promotion creates `ServiceVersionRow` (`vN+1`) and auto-resolves linked cluster `UnknownEventRow`s (`status="resolved"`), and `unknown_triage` syncs with `evidence_items`.                                                   | Promotion does not automatically re-ingest or re-execute historical raw events in a background batch job.                                                                                                                                                                                                            |
| **OC-BG-016** | **PARTIAL** | `GatewayDecisionProvider` (`providers/glm/openclass_provider_glm/gateway.py`) implements bounded JSON-schema probability distributions with temperature scaling (`temperature >= 0.5`), telemetry, and `429` retries.         | LLM logprob/logit extraction is not calibrated against an automated holdout ECE temperature-fitting pipeline.                                                                                                                                                                                                        |
| **OC-BG-017** | **PARTIAL** | `GatewayEmbedder` (`text-embedding-3-small`) + SQLite/PostgreSQL `embedding_cache` (`content_hash`) + greedy cosine clustering are implemented and verified.                                                                  | HDBSCAN and Silhouette/Davies-Bouldin cluster quality metrics are not implemented.                                                                                                                                                                                                                                   |
| **OC-BG-021** | **PARTIAL** | `packages/server/openclass_server/rate_limit.py` and `services/control-plane/src/rate-limit.service.ts` enforce sliding-window rate limits per route class, and `apply_candidate` is in `openclass_core/evolution.py`.        | Rate limiters store sliding windows in per-process memory (`PARTIAL` for multi-worker deployments without Redis).                                                                                                                                                                                                    |
| **OC-BG-023** | **PARTIAL** | Prompt-injection delimiters and instruction sanitization are enforced in `packages/server/openclass_server/redaction.py`, `providers/glm`, and `providers/jev`, plus `X-OpenClass-Internal-Token` engine auth.                | A dedicated core `openclass_core/prompt_safety.py` module is not split out separately.                                                                                                                                                                                                                               |
| **OC-BG-029** | **PARTIAL** | `compile_event_state` in `packages/core/openclass_core/decision_executor.py` compiles bounded deterministic state facts + prior resolved decisions with `snapshot_hash`; provider error/429 telemetry fixed.                  | No separate `0027_state_schemas.py` SQL table exists.                                                                                                                                                                                                                                                                |
| **OC-BG-030** | **PARTIAL** | `AutomationLoop` and `SafeSandboxExecutor` (`packages/core/openclass_core/automation.py`) implement step budgets, oscillation detection, macro synthesis, and sandbox path/env isolation; `/unknowns` paginated.              | `AutomationLoop` and `SafeSandboxExecutor` operate in `openclass_core` without dedicated SQL tables or FastAPI routes.                                                                                                                                                                                               |
| **OC-BG-032** | **PARTIAL** | `HTTPIntegrationProbe` actively probes REST, Webhook, MCP (JSON-RPC `tools/list`), and Provider endpoints with SSRF protection, and `support.py` enforces idempotent `RouteOutcome` evaluation (`delivery_mode="simulated"`). | No background webhook delivery worker or persistent retry queue is implemented.                                                                                                                                                                                                                                      |
| **OC-BG-033** | **PARTIAL** | `apps/portal` is wired 100% through `@openclass/sdk` (`OpenClassControlClient`) and `services/control-plane` reconciles engine-created projects (`control_projects` ↔ `projects`).                                            | `apps/web` (Next.js direct-to-engine workspace) and `apps/portal` (Vite + Control Plane BFF) both remain active rather than retiring `apps/web`.                                                                                                                                                                     |

---

## 2. Detailed Executable Backlog Specifications

### OC-BG-001 — Fix Remaining Local/Windows `pytest` Failures & Duplicate `support_router` Registration (Completing `OC-034`)

- **Workstream & Subsystem:** WS-14 (`tests/`, `packages/server/openclass_server/main.py`, `.gitattributes`)
- **Priority:** `P0` | **Current Status:** CI Repaired on `oc-034-ci-baseline` (`c6545bf`, run `37051177668`); 5 Local Windows `pytest` Failures & Duplicate Router Remain
- **Concrete Problem & Evidence:**
  - _Already resolved by `oc-034-ci-baseline` (`6f61ce0`, `4bd07f9`, `dbb0ab8`, `8fc3507`)_: `pnpm` in `.github/workflows/ci.yml` and `Makefile`, `OPENCLASS_DECISION_PROVIDER=mock` in CI/Compose, `providers/glm/LICENSE`, `test_raw_events_postgres.py:59` (`207`), `test_decision_executor.py` Laya skip guard, and fail-closed `resolve_decision_provider()`.
  - _Remaining defects in the merged working tree_:
    1. `tests/contract/test_jev_provider.py:86` and `tests/contract/test_supervisor_provider.py:72` parametrize `payload` with `"x" * 2_000_000` without `ids=...`. Pytest embeds the 2MB string into `PYTEST_CURRENT_TEST`, causing `ValueError: the environment variable is longer than 32767 characters` on Windows when `anyio` spawns a thread/process.
    2. `tests/integration/test_reviews.py:96` (`test_supervisor_failures_are_safe_and_persist_nothing`) calls `create_app(Settings(database_url=database_url), supervisor_provider=LeakingSupervisor())` without `provider=MockDecisionProvider()`. When `OPENCLASS_DECISION_PROVIDER` is not set in the local shell, `Settings.decision_provider` defaults to `"laya"` (`settings.py:26`), failing before `/reviews` is reached.
    3. `tests/unit/test_automation_reuse.py:142` (`test_frozen_fixture_unchanged`) hashes raw bytes of `scripts/automation_replay_fixture.py`, which fails when Git checks out CRLF (`\r\n`) on Windows.
    4. `tests/unit/test_automation_reuse.py:160` (`test_transfer_fixture_has_real_failure_and_truthful_report`) binds two sockets on `127.0.0.1` without `SO_EXCLUSIVEADDRUSE` on Windows, so the second bind succeeds instead of failing with `"Address already in use"`.
    5. `packages/server/openclass_server/main.py:200,237` calls `app.include_router(support_router(...))` **twice**, registering duplicate route entries for all 5 support endpoints.
- **Target Behavior:** `uv run pytest -q` passes 100% on Windows, macOS, and Linux even without shell env overrides, and `support_router` is mounted exactly once.
- **Detailed Implementation Approach:**
  1. Add `ids=["truncated_json", "wrong_type", "oversized_2mb"]` to `@pytest.mark.parametrize` in `test_jev_provider.py:86` and `test_supervisor_provider.py:72`.
  2. Pass `provider=MockDecisionProvider()` in `tests/integration/test_reviews.py:96`.
  3. Normalize `\r\n` to `\n` before hashing in `test_automation_reuse.py:142` and add `.gitattributes` (`* text=auto eol=lf`).
  4. In `scripts/automation_transfer_fixture.py`, set `socket.SO_EXCLUSIVEADDRUSE` on Windows (`sys.platform == "win32"`) instead of `SO_REUSEADDR`.
  5. Remove the duplicate `app.include_router(support_router(...))` call at `packages/server/openclass_server/main.py:237-244` (keeping the registration at `L200-207` before `integration_router`).
- **Dependencies:** None (Stage 0 entry gate).
- **Verification & Acceptance Criteria:** `uv run pytest -q` reports `0 failed, 0 errors`; OpenAPI route table contains each `/integrations/*` route once.
- **Effort / Risk / Blast Radius:** Small (S) | Low risk | Test files & duplicate router cleanup.

---

### OC-BG-002 — Fix `UnknownTriageStore.append_audit` Schema Corruption Across All 10 Event Types

- **Workstream & Subsystem:** WS-09 / WS-08 (`packages/server/openclass_server/persistence/unknown_triage.py`, `packages/core/openclass_core/projects.py`, `persistence/project_repository.py`)
- **Priority:** `P0` | **Current Status:** Critical Runtime Failure (`scikit-learn-2026-10-02/REPORT.md` Finding #9)
- **Concrete Problem & Evidence:**
  - `SQLProjectRepository.audit_events` (`persistence/project_repository.py:116-123`) deserializes every row in `audit_events` via `ProjectAuditEvent.model_validate(row.payload)`.
  - `UnknownTriageStore.append_audit` (`persistence/unknown_triage.py:86-110`) executes raw SQL `INSERT INTO audit_events` with `payload = json.dumps({"target": target, **(data or {})})` across **10 event types** (`"unknown.triaged"`, `"unknown.transitioned"`, `"cluster.updated"`, `"candidate.created"`, `"candidate.updated"`, `"candidate.rejected"`, `"evaluation.dataset_created"`, `"evaluation.dataset_sealed"`, `"evaluation.completed"`, `"quality.alert"`).
  - None of those 10 event types exist in `ProjectAuditEvent.event_type` (`projects.py:78-101`), and `{"target": target, ...}` omits required `ProjectAuditEvent` fields (`id`, `project_id`, `event_type`, `actor`, `created_at`).
- **Root Cause:** `UnknownTriageStore` bypassed `SQLProjectRepository.append_audit_event` and `to_audit_event_row` (`persistence/mappers.py:8-16`).
- **Target Behavior:** All audit writes produce valid `ProjectAuditEvent` envelopes; `GET /api/v1/projects/{id}/audit` and `GET /api/v1/projects/{id}/summary` succeed after unknown triage, clustering, candidate review, evaluation, and alert evaluation.
- **Detailed Implementation Approach:**
  1. Add all 10 Portal event types (`"unknown.triaged"`, `"unknown.transitioned"`, `"cluster.updated"`, `"candidate.created"`, `"candidate.updated"`, `"candidate.rejected"`, `"evaluation.dataset_created"`, `"evaluation.dataset_sealed"`, `"evaluation.completed"`, `"quality.alert"`) to `ProjectAuditEvent.event_type` literal in `packages/core/openclass_core/projects.py:78-101`.
  2. Update `UnknownTriageStore.append_audit` (`unknown_triage.py:86-110`) to construct a valid `ProjectAuditEvent` (storing `{"target": target, **(data or {})}` inside `event.details`) while keeping `UnknownTriageStore.audit_history` (`L112-140`) compatible with both `payload["details"]` and legacy top-level `payload` keys.
  3. Add fallback normalization in `SQLProjectRepository.audit_events` (`project_repository.py:116-123`) so if an existing row's `payload` lacks `"id"`, it reconstructs `ProjectAuditEvent` from the row's columns (`row.id`, `row.project_id`, `row.event_type`, `row.actor`, `row.payload`, `row.created_at`).
- **Verification & Acceptance Criteria:** Calling `GET /api/v1/projects/{slug}/audit` and `GET /api/v1/projects/{slug}/summary` after triaging, clustering, candidate review, dataset sealing, evaluation, and alert firing returns `200 OK`.
- **Effort / Risk / Blast Radius:** Small (S) | Low risk | Fixes P0 audit crash confirmed in `REPORT.md` Finding #9.

---

### OC-BG-003 — Fix Control-Plane API Key Authorization (`callerOf`), Scope Enforcement & RBAC Roles

- **Workstream & Subsystem:** WS-11 (`services/control-plane/src/`)
- **Priority:** `P0` | **Current Status:** Broken in production HTTP calls
- **Concrete Problem & Evidence:**
  1. `IngestionGuard.canActivate` (`services/control-plane/src/ingestion.service.ts:45-55`) sets `request.keyProjectId = verified.projectId` for `oc_...` API keys.
  2. `callerOf(request)` (`services/control-plane/src/ingestion.controller.ts:26-32`) returns `{ user: request.user, workspaceId: request.workspaceId }` **without `keyProjectId`**.
  3. `IngestionService.authorize` (`ingestion.service.ts:235-248`) sees `caller.keyProjectId === undefined`, skips API key authorization, and calls `this.workspaces.requireRole(workspaceId, caller.user, minimumRole)`, which queries `control_workspace_members` for `user_id = 'apikey:<uuid>'` and fails with `404 Workspace not found`.
  4. `IngestionGuard` (`ingestion.service.ts:49`) requires `"ingest"` scope on all routes, blocking `"read"` keys from `GET /events` and allowing `"ingest"`-only keys to read events.
  5. `DecisionController` (`decision.controller.ts:58`) uses `@UseGuards(KeycloakGuard)`, rejecting API keys with `"classify"` scope.
  6. `IngestionService.ingest` (`L79`) and `ingestBatch` (`L116`) only require `"viewer"` role instead of `"operator"`.
- **Detailed Implementation Approach:**
  1. Update `callerOf(request)` (`ingestion.controller.ts:26-32`) to pass `keyProjectId: request.keyProjectId` and `keyScopes: request.keyScopes`.
  2. In `IngestionGuard`, allow `"read"` or `"ingest"` scope based on HTTP method (`GET` requires `"read"`, `POST` requires `"ingest"`).
  3. Add API-key support (`"classify"` scope) to `DecisionController` guard.
  4. Change minimum role in `IngestionService.ingest` (`L79`) and `ingestBatch` (`L116`) from `"viewer"` to `"operator"`.
- **Verification & Acceptance Criteria:** Controller-level integration tests in `services/control-plane/src/ingestion.spec.ts` invoking `IngestionController` endpoints with `oc_...` API keys (`ingest`, `read`, `classify` scopes) and `viewer` vs `operator` JWTs.
- **Effort / Risk / Blast Radius:** Small (S) | Low risk | Restores API key auth and fixes RBAC escalation.

---

### OC-BG-004 — Eliminate SSRF and Arbitrary Env-Var Exfiltration in Integrations & Provider Config

- **Workstream & Subsystem:** WS-10 / WS-11 (`packages/server/openclass_server/integration_adapters.py`, `api/providers.py`, `provider_config.py`)
- **Priority:** `P0` | **Current Status:** Critical Security Vulnerability
- **Concrete Problem & Evidence:**
  1. `EnvironmentSecrets.resolve(secret_ref)` (`integration_adapters.py:29-35`) resolves **any** uppercase environment variable in `os.environ` (`^[A-Z][A-Z0-9_]{0,199}$`).
  2. `HTTPIntegrationProbe.check` (`integration_adapters.py:89-126`) connects to any `http`/`https` URL and sends `Authorization: Bearer <os.environ[secret_ref]>` (`L106-109`), allowing instant exfiltration of server secrets (`OPENCLASS_JEV_API_KEY`, `AI_GATEWAY_API_KEY`, `OPENCLASS_DATABASE_URL`) to an attacker's server, as well as SSRF against `169.254.169.254` and internal services (`localhost:7331`, `postgres:5432`).
  3. `PUT /api/v1/projects/{identifier}/providers/{provider}` (`api/providers.py:15,29-42`) accepts arbitrary `base_url` and plaintext `api_key`.
- **Detailed Implementation Approach:**
  1. Restrict `EnvironmentSecrets.resolve` (`integration_adapters.py:29-35`) to require prefix `OPENCLASS_INTEGRATION_SECRET_` (and `provider_config.py` `api_key_env` to require `OPENCLASS_PROVIDER_KEY_` or registered provider env vars).
  2. Implement `validate_outbound_url(url: str, allow_loopback: bool = False)` in `packages/server/openclass_server/security.py` that resolves DNS via `socket.getaddrinfo` and rejects loopback (`127.0.0.0/8`, `::1`), RFC1918 private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local (`169.254.0.0/16`, `fe80::/10`), multicast, and internal Docker hostnames, and sets `follow_redirects=False` on `httpx.Client`.
  3. Remove plaintext `api_key` from `ProviderConfigPayload` (`api/providers.py:15`).
- **Verification & Acceptance Criteria:** Unit & integration tests proving that `secret_ref="OPENCLASS_DATABASE_URL"` is rejected with `422`/`400`, and `endpoint="http://169.254.169.254/latest/meta-data/"` or `http://127.0.0.1:7331` is blocked before any socket connection is opened.
- **Effort / Risk / Blast Radius:** Medium (M) | Low risk | Critical security boundary hardening.

---

### OC-BG-005 — Fix Service & Node Instruction Propagation Across `DecisionExecutor` and Providers

- **Workstream & Subsystem:** WS-03 / WS-05 (`decision_executor.py`, `projects.py`, `models.py`, `providers/{jev,laya,mock}`)
- **Priority:** `P0` | **Current Status:** Broken (`scikit-learn-2026-10-02/REPORT.md` Finding #5: Instructions silently dropped before inference)
- **Concrete Problem & Evidence:**
  1. `DecisionExecutor.execute` (`packages/core/openclass_core/decision_executor.py:58-85`) constructs `ChoiceRequest(observation=observation, ontology=ontology)` without passing `service.instructions` or `node.instructions`.
  2. `ChoiceRequest` (`packages/core/openclass_core/models.py:109-120`) has no `instructions: str | None` field.
  3. `JevDecisionProvider` (`providers/jev/openclass_provider_jev/__init__.py:19-23,102`) and `LayaDecisionProvider` (`providers/laya/openclass_provider_laya/__init__.py:27-31,139,193`) send a hardcoded static `INSTRUCTIONS` string.
  4. `ProjectService.update_decision_service` (`packages/core/openclass_core/projects.py:671-672`) updates `service.instructions` when edited in the UI, but **does not update `service.nodes[0].instructions`**, while `DecisionExecutor` (`L164`) snapshots `node.instructions`!
- **Detailed Implementation Approach:**
  1. Add `instructions: str | None = None` to `ChoiceRequest` (`models.py:109-120`).
  2. In `DecisionExecutor.execute` (`decision_executor.py:80-85`), compile effective instructions (`node.instructions or service.instructions`) and pass `instructions=effective_instructions` into `ChoiceRequest` and `DecisionRun.instructions_snapshot`.
  3. In `ProjectService.update_decision_service` (`projects.py:665-678`), synchronize `service.nodes[0].instructions` when `instructions` is updated on a single-node service.
  4. Update `JevDecisionProvider._build_payload` (`providers/jev/__init__.py:102`) and `LayaDecisionProvider` (`providers/laya/__init__.py:139,193`) to include `request.instructions` inside the untrusted/task instruction block while keeping system output-format invariants immutable.
- **Verification & Acceptance Criteria:** Contract & unit tests verifying that updating `DecisionService.instructions` changes the exact prompt payload sent to `JevDecisionProvider` and `LayaDecisionProvider` and matches `DecisionRun.instructions_snapshot`.
- **Effort / Risk / Blast Radius:** Medium (M) | Low risk | Core, providers, and contract tests.

---

### OC-BG-006 — Fix `DecisionExecutor` Tie-Breaking, Ephemeral UUIDs & `evaluate_predicates` Bugs

- **Workstream & Subsystem:** WS-03 / WS-04 (`packages/core/openclass_core/decision_executor.py`, `decision.py`)
- **Priority:** `P0` | **Current Status:** Broken Invariants
- **Concrete Problem & Evidence:**
  1. **Tie-Breaking (`decision_executor.py:102-115`)**: Inserts known choices into `full_probs` before `UNKNOWN_CHOICE_KEY`, so `sorted(full_probs.items(), key=lambda kv: kv[1], reverse=True)` selects a known choice when tied with `UNKNOWN`, violating `decision.py:291-299` (`if unknown_prob >= best_prob: return UNKNOWN_CHOICE`).
  2. **Ephemeral UUIDs (`decision_executor.py:58-80`)**: Generates random `uuid4()` for `OntologyClass.stable_class_id` and `OntologyVersion.id` on every call.
  3. **Predicate Evaluation (`decision.py:226-227`)**: `state.facts.get(predicate.field) == predicate.equals` returns `True` when `predicate.field` is missing and `predicate.equals is None`, and returns `True` when `actual = True` and `predicate.equals = 1` (`bool` is a subclass of `int` in Python).
- **Detailed Implementation Approach:**
  1. In `DecisionExecutor.execute` (`decision_executor.py:110-125`), enforce `if unknown_prob >= top_known_prob: selected_choice = UNKNOWN_CHOICE_KEY` before checking known choices.
  2. Derive deterministic UUIDs (`uuid5(service.id, f"choice:{c.key}")` and `uuid5(service.id, service_hash(service))`) in `DecisionExecutor.execute`.
  3. In `evaluate_predicates` (`decision.py:217-235`), check `if predicate.field not in state.facts: return False` and `if isinstance(actual, bool) != isinstance(predicate.equals, bool): return False`.
- **Verification & Acceptance Criteria:** Unit tests in `tests/unit/test_core_decision.py` and `tests/unit/test_decision_executor.py` covering exact `0.50` / `0.50` ties, deterministic class IDs across runs, missing fields vs `None`, and `True` vs `1`.
- **Effort / Risk / Blast Radius:** Small (S) | Low risk | Core domain only.

---

### OC-BG-007 — Fix SDK, Server & Web Contract Drift (`ingestBatch`, Evidence Case Attach, Transition Rationale, Candidate Reject)

- **Workstream & Subsystem:** WS-12 / WS-13 (`packages/sdk-typescript`, `packages/sdk-python`, `packages/server/openclass_server/api/{evidence,evolution}.py`, `apps/web`)
- **Priority:** `P0` | **Current Status:** Broken in production UI/SDK calls
- **Concrete Problem & Evidence:**
  1. `POST /api/v1/projects/{id}/events/batch` (`api/projects.py:137-198`) returns `207` with `{"items": [{"index": 0, "status": 201, "event": {...}, "deduped": false}]}`. `OpenClass.ingestBatch` in `packages/sdk-typescript/src/index.ts:573-582` returns the raw dict typed as `Promise<RawEvent[]>`, causing `apps/web/app/projects/[id]/data/page.tsx:173,229` to display `"Successfully ingested undefined events."`.
  2. `packages/sdk-python/openclass_sdk/__init__.py:466`, `packages/sdk-typescript/src/index.ts:800`, and `apps/web/app/projects/[id]/evolution/page.tsx:303` call `POST /api/v1/projects/{id}/evidence-cases/{cid}/evidence`, which **does not exist** in `api/evidence.py` (always returns 404).
  3. `transition_evidence` in `sdk-python/__init__.py:442` and `sdk-typescript/src/index.ts:773` sends `{"status": ..., "note": ...}`, whereas `TransitionEvidenceRequest` (`api/schemas.py:240`) expects `{"status": ..., "rationale": ...}`.
  4. `ProjectEvolutionService.reject` (`project_evolution.py:242-257`) is implemented in Core, and called by `sdk-python` (`L515`) and `sdk-typescript` (`L855`), but **has no route in `api/evolution.py`**!
- **Detailed Implementation Approach:**
  1. In `packages/sdk-typescript/src/index.ts:573-582`, unwrap `res.items.map((i) => i.event)` (matching `sdk-python/__init__.py:193-202`) and update `index.test.ts:163-165` and `tests/web/data.spec.ts:98-110`.
  2. Add `POST /api/v1/projects/{identifier}/evidence-cases/{case_id}/evidence` in `packages/server/openclass_server/api/evidence.py` and `ProjectService.attach_evidence_to_case` in `projects.py`.
  3. Accept both `rationale` and `note` (aliased) in `TransitionEvidenceRequest` (`api/schemas.py:240`) and pass `body.note` in `api/evolution.py:105-110`.
  4. Add `POST /api/v1/projects/{identifier}/candidates/{candidate_id}/reject` in `packages/server/openclass_server/api/evolution.py`.
- **Verification & Acceptance Criteria:** Integration tests in `test_evidence_api.py` and `test_candidate_promotion_api.py` exercising all 4 routes through both Python and TypeScript SDK contracts.
- **Effort / Risk / Blast Radius:** Medium (M) | Low risk | Fixes 4 user-facing 404/broken UI paths.

---

### OC-BG-008 — Prevent Re-Clustering from Cascade-Deleting `cluster_candidates`, `candidate_evidence`, and `candidate_reviews`

- **Workstream & Subsystem:** WS-08 / WS-09 (`persistence/cluster_store.py`, `tables.py`, `migrations/versions/`)
- **Priority:** `P0` | **Current Status:** Destructive Data Loss Bug (`scikit-learn-2026-10-02/REPORT.md` Finding #10)
- **Concrete Problem & Evidence:**
  - `ClusterStore.replace_clusters` (`packages/server/openclass_server/persistence/cluster_store.py:50-53`) runs `DELETE FROM unknown_clusters WHERE project_id = :project_id`.
  - `cluster_candidates.cluster_id` (`0016_cluster_candidates.py:20-23`, `tables.py:344`) has `ForeignKey("unknown_clusters.id", ondelete="CASCADE")`, `candidate_evidence.candidate_id` (`tables.py:361`) has `ondelete="CASCADE"`, and `candidate_reviews.candidate_id` (`0017_candidate_reviews.py:20`) has `ondelete="CASCADE"`. Re-running clustering wipes out all discovered candidates, evidence links, and human reviews for the project!
- **Detailed Implementation Approach:**
  1. Create migration `0023_preserve_cluster_candidates.py` (building on `0022_integration_routes.py`) changing `cluster_candidates.cluster_id` to `nullable=True` with `ondelete="SET NULL"` (and adding `decision_service_id` to `unknown_clusters`).
  2. In `ClusterStore.replace_clusters` (`cluster_store.py:45-55`), detach `cluster_id = NULL` on `cluster_candidates` before replacing clusters (or only delete `unknown_clusters` rows not referenced by an active candidate).
- **Verification & Acceptance Criteria:** Integration test in `tests/integration/test_discovery_candidates.py` that discovers and reviews a candidate from a cluster, re-runs `POST /unknowns/cluster`, and asserts `GET /discovery-candidates` and `GET /discovery-candidates/{id}/history` still return the candidate, its `candidate_evidence`, and its `candidate_reviews` intact.
- **Effort / Risk / Blast Radius:** Small (S) | Low risk | Stops silent candidate and review deletion.

---

### OC-BG-009 — Fix Provider Configuration, Provenance Metadata & Malformed Response Handling

- **Workstream & Subsystem:** WS-05 / WS-07 (`provider_config.py`, `providers/{jev,laya,glm}`)
- **Priority:** `P0` | **Current Status:** Buggy / Misleading Provenance
- **Concrete Problem & Evidence:**
  1. `provider_config.py:97-102` crashes startup when `OPENCLASS_DISCOVERY_PROVIDER=openai-compatible` and `OPENCLASS_DISCOVERY_BASE_URL` / `OPENCLASS_GLM_BASE_URL` are unset (`base_url=""`).
  2. `provider_config.py:120-121` silently falls back to `MockDiagnosisProvider` when diagnosis API keys are missing.
  3. `JevDecisionProvider` (`providers/jev/openclass_provider_jev/__init__.py:102-120`) omits `"real_inference": True` and `"execution_mode": "api"`, causing `DecisionExecutor` (`L142-146`) to record live Jev runs as `real_inference=False, execution_mode="daemon"`.
  4. `LayaDecisionProvider._local_fallback_choice` (`providers/laya/openclass_provider_laya/__init__.py:251`) sets `"simulated": False` on regex fallback output, and `_normalize_response` (`L280-287`) silently renormalizes uncalibrated numbers instead of rejecting distributions where `abs(total - 1.0) > 0.05`.
  5. `OpenAICompatibleDiagnosisProvider` (`providers/glm/openclass_provider_glm/diagnosis.py:86-93`) silently substitutes `DiagnosisCategory.ANALYTICAL_GAP` on invalid enum values, and `project_teacher.py:121-122` leaks `str(exc)` in `ProviderError`.
- **Detailed Implementation Approach:**
  1. Validate required `base_url` and API key env vars explicitly in `provider_config.py` and raise `ProviderError(kind="configuration")` without silent fallback unless `OPENCLASS_DISCOVERY_PROVIDER=mock`.
  2. Set `"real_inference": True`, `"simulated": False`, `"execution_mode": "api"` in `JevDecisionProvider` response metadata (`providers/jev/__init__.py:115`).
  3. Set `"simulated": True` in `LayaDecisionProvider._local_fallback_choice` (`providers/laya/__init__.py:251`) and raise `ProviderError("Laya probability distribution does not sum to 1.0", kind="malformed_response")` in `_normalize_response` when `abs(total - 1.0) > 0.05`.
  4. Raise `ProviderError(kind="malformed_response")` on unknown diagnosis categories in `diagnosis.py:86-93` and sanitize exception messages in `project_teacher.py:121-122`.
- **Verification & Acceptance Criteria:** Unit & contract tests in `tests/unit/test_provider_config.py` and `tests/contract/test_{jev,laya}_provider.py`.
- **Effort / Risk / Blast Radius:** Small (S) | Low risk | Provider adapters & config.

---

### OC-BG-010 — Complete Immutable `DecisionServiceVersion` Lineage, Alias Preservation & ORM Alignment (`OC-017` / `0020` + `0024`)

- **Workstream & Subsystem:** WS-09 (`packages/core/openclass_core/projects.py`, `api/promotions.py`, `persistence/promotion_store.py`, `persistence/tables.py`)
- **Priority:** `P0` | **Current Status:** Partially Implemented in `0020_service_versions.py` (Strips Aliases & Lacks Run Version Lineage)
- **Concrete Problem & Evidence:**
  - `feat/portal-phase-17` added migration `0020_service_versions.py` (`service_versions` and `service_ontology_events` with `openclass_immutable` triggers) and `PromotionStore` (`persistence/promotion_store.py:14-200`).
  - **Defect 1 (Alias Stripping)**: Because `DecisionChoiceSpec` (`projects.py:157-168`) has `extra="forbid"` and lacks an `aliases` field, `api/promotions.py:148-149` and `promotion_store.py:159-162` explicitly strip `"aliases"` when writing promoted choices into `decision_services.payload`! As a result, promoted aliases are never passed to `DecisionExecutor` during live inference.
  - **Defect 2 (Missing Run Version Lineage & Unversioned Direct Edits)**: `DecisionRun` (`projects.py:216-237`) still has no `decision_service_version_id` or `service_hash`, and `SQLProjectRepository.update_decision_service` (`project_repository.py:230-246`) mutates `decision_services.payload` in-place without recording a new row in `service_versions`.
  - **Defect 3 (Missing ORM Table Declarations)**: None of the 9 tables added in `0017`..`0022` are declared in `persistence/tables.py`.
- **Detailed Implementation Approach:**
  1. Add `aliases: tuple[str, ...] = ()` to `DecisionChoiceSpec` (`projects.py:157-168`) and pass `aliases=c.aliases` when `DecisionExecutor.execute` (`decision_executor.py:66-74`) constructs `OntologyClass`.
  2. Remove the `k != "aliases"` stripping filter in `api/promotions.py:148` and include `"aliases"` in `promotion_store.py:160` (`if k in ("key", "label", "description", "aliases")`).
  3. Add `active_version_id: UUID | None = None` and `version_number: int = 1` to `DecisionService`, and `decision_service_version_id: UUID | None = None` + `service_hash: str` to `DecisionRun`.
  4. Create Alembic migration `0024_decision_run_version_lineage.py` adding `active_version_id` and `version_number` to `decision_services` and `decision_service_version_id` to `decision_runs`, declare all `0017`..`0024` tables in `persistence/tables.py`, and ensure `ProjectService.create_decision_service` / `update_decision_service` write append-only rows to `service_versions`.
- **Dependencies:** Prerequisite for `OC-BG-012` (Replay Evaluation) and `OC-BG-013` (Candidate Promotion).
- **Verification & Acceptance Criteria:** Integration tests verifying that promoting a candidate with aliases preserves `aliases` on the live `DecisionService`, updating a `DecisionService` increments `service_versions.version_number`, and `DecisionRun` records `decision_service_version_id`.
- **Effort / Risk / Blast Radius:** Medium (M) | Low risk | Builds directly on `0020_service_versions.py`.

---

### OC-BG-011 — Extend Verified Evaluation Datasets (`0018`) with Holdout Splits, Dataset Hash & Metadata (`OC-008` Part 1)

- **Workstream & Subsystem:** WS-08 (`packages/core/openclass_core/evaluation.py`, `api/evaluations.py`, `persistence/tables.py`)
- **Priority:** `P1` | **Current Status:** Partially Implemented in `0018_evaluation_sets.py`
- **Concrete Problem & Evidence:**
  - `feat/portal-phase-17` implemented `0018_evaluation_sets.py` (`evaluation_sets`, `evaluation_examples` with `openclass_immutable` and `openclass_sealed_set_immutable` triggers), `packages/core/openclass_core/evaluation.py`, and `api/evaluations.py:136-265`.
  - However, `EvaluationExample` (`evaluation.py:33-43`) lacks `split: Literal["evaluation", "holdout"] = "evaluation"` and `metadata: dict[str, Any] = {}`, `EvaluationSet` (`L24-31`) lacks a deterministic SHA-256 `dataset_hash` computed on seal, and `EvaluationExample` allows labels from unapproved `cluster_candidates` (`api/evaluations.py:88-102`) but not from Track 2 `project_choice_candidates`.
- **Detailed Implementation Approach:**
  1. Extend `EvaluationExample` and `ExampleDraft` (`evaluation.py:33-72`) with `split: Literal["evaluation", "holdout"] = "evaluation"` and `metadata: dict[str, Any] = Field(default_factory=dict)`, plus `"target_candidate"` in `VALID_SLICES`.
  2. Create Alembic migration `0025_evaluation_holdouts_and_provenance.py` adding `dataset_hash` to `evaluation_sets` and `split` + `metadata` to `evaluation_examples`.
  3. Compute and persist a canonical SHA-256 `dataset_hash` over ordered `(id, text, label, source, slice_tag, split)` in `POST /api/v1/projects/{identifier}/eval-datasets/{dataset_id}/seal` (`api/evaluations.py:209-226`).
- **Dependencies:** `OC-BG-010`.
- **Verification & Acceptance Criteria:** Unit & integration tests proving that `source="prediction"` is rejected with `400`/`422`, sealing records a deterministic SHA-256 `dataset_hash`, and holdout examples are tracked separately from evaluation examples.
- **Effort / Risk / Blast Radius:** Medium (M) | Low risk | Extends `0018_evaluation_sets.py`.

---

### OC-BG-012 — Replace Hardcoded `MockDecisionProvider` in `api/evaluations.py:306` with Real `DecisionExecutor` Replay (`OC-008` Part 2)

- **Workstream & Subsystem:** WS-08 (`packages/server/openclass_server/api/evaluations.py`, `packages/core/openclass_core/{evaluation_metrics,project_evolution,discovery}.py`, `api/{evolution,classifiers}.py`)
- **Priority:** `P1` | **Current Status:** Simulated on Track 3 (`api/evaluations.py:306`); Blocked with HTTP 409 on Tracks 1 & 2
- **Concrete Problem & Evidence:**
  - `feat/portal-phase-17` implemented `0019_evaluation_runs.py` and `POST /api/v1/projects/{identifier}/evaluations` (`api/evaluations.py:266-371`).
  - **Critical Flaw**: `api/evaluations.py:306` hardcodes `provider = MockDecisionProvider()` and sets `"simulated": True` (`L339`), and `_replay` (`L433-452`) calls `MockDecisionProvider.choice()` directly without `DecisionExecutor`, custom service instructions, or the project's configured `DecisionProvider`!
  - Meanwhile, `ProjectEvolutionService.evaluate` (`project_evolution.py:204-206`) and `DiscoveryService.evaluate` (`discovery.py:76-79`) still unconditionally raise `ConflictError("Verified replay evaluation is not implemented")` (HTTP 409).
- **Detailed Implementation Approach:**
  1. Inject `default_decision_provider` (and per-project provider resolution) into `evaluations_router` (`main.py:228-230`, `api/evaluations.py:55-60`).
  2. Replace `_replay` (`api/evaluations.py:306, 433-452`) with `DecisionExecutor(provider).execute(raw_event, service_snapshot)` (with Teacher/discovery disabled, preserving `service.instructions` and `choice.aliases`) across both `baseline_service` and in-memory `candidate_service`.
  3. Record `provider`, `model`, `simulated: provider_is_mock`, `base_service_hash`, per-example `regressions`, and holdout metrics in `evaluation_runs.metrics` (`0019_evaluation_runs.py`).
  4. Wire `ProjectEvolutionService.evaluate` (`project_evolution.py:204-206`) and `DiscoveryService.evaluate` (`discovery.py:76-79`) to the shared replay evaluation engine.
- **Dependencies:** `OC-BG-010`, `OC-BG-011`.
- **Verification & Acceptance Criteria:** End-to-end integration test verifying that `POST /api/v1/projects/{id}/evaluations` executes the configured `DecisionProvider` via `DecisionExecutor`, fails (`overall_passed=False`) when a candidate causes a known-class regression, and passes (`overall_passed=True`) when `UNKNOWN` examples are resolved with zero regressions.
- **Effort / Risk / Blast Radius:** Large (L) | Medium risk | Unlocks real provider-backed `OC-008` replay.

---

### OC-BG-013 — Harden Ontology Promotion (`0020`) with `SELECT ... FOR UPDATE`, Alias Preservation & Evidence Auto-Resolution (`OC-009`)

- **Workstream & Subsystem:** WS-08 (`packages/server/openclass_server/api/promotions.py`, `persistence/promotion_store.py`, `packages/core/openclass_core/{promotion,project_evolution,discovery}.py`)
- **Priority:** `P1` | **Current Status:** Partially Implemented on Track 3 (`api/promotions.py`); Blocked at HTTP 409 on Tracks 1 & 2
- **Concrete Problem & Evidence:**
  - `feat/portal-phase-17` added `0017_candidate_reviews.py`, `0020_service_versions.py`, `promotion.py`, `PromotionStore`, and `POST /api/v1/projects/{identifier}/discovery-candidates/{candidate_id}/promote` (`api/promotions.py:101-174`).
  - However:
    1. `promotions.py:148-157` and `promotion_store.py:160` strip `"aliases"` from `decision_services.payload`.
    2. `promotions.py:102-168` executes 6 separate `sessions.begin()` transactions without `SELECT ... FOR UPDATE`, allowing concurrent promotions to overwrite `decision_services.payload` or race on `version_number`.
    3. Promoting a candidate does not verify that the service's current choices match the baseline evaluated in `evaluation_runs`, nor does it transition linked `unknown_triage` / `evidence_items` rows to `resolved`.
    4. Track 2 `POST /api/v1/projects/{id}/candidates/{cid}/promote` (`project_evolution.py:208-240`) and Track 1 `POST /api/v1/classifiers/{id}/candidates/{cid}/approve` (`discovery.py:69-74`) still raise `ConflictError` (HTTP 409).
- **Detailed Implementation Approach:**
  1. Wrap `PromotionStore.promote` in a single atomic database transaction using `SELECT ... FOR UPDATE` on `decision_services` and `cluster_candidates` / `project_choice_candidates`.
  2. Verify that the active `DecisionService` hash matches the baseline evaluated in `evaluation_runs` (rejecting stale evaluations with `409 Conflict`).
  3. Preserve `aliases` in `decision_services.payload` (via `OC-BG-010`), transition linked `unknown_triage` and `evidence_items` rows to `resolved` / `RESOLVED`, and wire `ProjectEvolutionService.promote` and `DiscoveryService.approve` to the unified promotion store.
- **Dependencies:** `OC-BG-010`, `OC-BG-012`.
- **Verification & Acceptance Criteria:** Concurrent or stale promotions return `409 Conflict`; valid promotion creates immutable `vN+1` with aliases preserved, auto-resolves linked evidence/unknowns, and subsequent Teacher-disabled replay classifies the promoted class and its aliases as `TRUSTED`.
- **Effort / Risk / Blast Radius:** Medium (M) | Medium risk | Completes `OC-009` over `0017` & `0020`.

---

### OC-BG-014 — Unify the 4 Fractured Candidate Pipelines, Merge `GatewayClusterDiscovery` & Synchronize `unknown_triage` with `evidence_items`

- **Workstream & Subsystem:** WS-08 (`evolution.py`, `project_evolution.py`, `candidates.py`, `unknown_pool.py`, `evidence.py`, `api/{candidates,evolution,unknowns,evidence}.py`)
- **Priority:** `P1` | **Current Status:** Duplicated / Split-Brain (`REPORT.md` Finding #1)
- **Concrete Problem & Evidence:**
  - Candidates discovered from clusters via `POST /api/v1/projects/{id}/clusters/{cid}/discover` (`api/candidates.py:120-200`) are written via raw SQL into `cluster_candidates` (`0016`) using a hardcoded `MockClusterDiscoveryProvider` (`api/candidates.py:46`) and never appear in `/api/v1/projects/{id}/candidates` (`project_choice_candidates`, `0007`).
  - Real LLM cluster discovery (`GatewayClusterDiscovery`) was written in `artifacts/application-proofs/scikit-learn-2026-10-02/provider-wiring.patch` (`L14-83`) but remains unmerged.
  - Triaging an unknown in `/unknowns/{run_id}/triage` (`unknown_triage` table, `0014`) does not update `evidence_items` (`0008`), and vice versa.
  - `ProjectEvolutionService.propose` (`project_evolution.py:118`) rejects `READY_FOR_EVOLUTION` evidence items if they originated from `LOW_TRUST` or `HUMAN_CORRECTION` runs (`run.selected_choice != "UNKNOWN"`).
- **Detailed Implementation Approach:**
  1. Merge and harden `GatewayClusterDiscovery` (from `provider-wiring.patch`) into `providers/glm` and wire provider selection in `provider_config.py` and `api/candidates.py:46`.
  2. Bridge `cluster_candidates` (`0016`) and `project_choice_candidates` (`0007`) under a unified candidate repository so candidates created via `/clusters/{cid}/discover` or `/evolution/propose` share the same review (`0017`), evaluation (`0018`–`0019`), and promotion (`0020`) lifecycle.
  3. Relax `project_evolution.py:118` to accept runs linked to `READY_FOR_EVOLUTION` evidence regardless of whether the trigger was `SEMANTIC_UNKNOWN`, `LOW_TRUST`, or `HUMAN_CORRECTION`.
  4. Synchronize `UnknownTriageStore.upsert` with `EvidenceItem` status transitions.
- **Dependencies:** `OC-BG-002`, `OC-BG-008`.
- **Verification & Acceptance Criteria:** Cluster discovery uses the configured provider (`mock`, `glm`, `openai-compatible`), and triaging in `/unknowns` synchronizes with `/evidence`.
- **Effort / Risk / Blast Radius:** Large (L) | Medium risk | Unifies Portal Phase 8–14 with Core Evolution.

---

### OC-BG-015 through OC-BG-038 — Concise Executable Specifications

#### OC-BG-015 (P1, WS-03 — `OC-035` / Impl Phase 02): Multi-Node `PolicyGraph` Execution in `DecisionExecutor`

- **Problem:** `DecisionExecutor.execute` (`decision_executor.py:38-50`) only executes `service.nodes[0]` and ignores `PolicyGraph` (`decision.py:130-330`).
- **Implementation:** Port the multi-hop traversal loop (`max_steps=8`, `visited_nodes` cycle detection, `TransitionTargetKind` dispatch for `NODE`, `CAPABILITY`, `MACRO`, `HUMAN`, `TERMINAL`) from `scripts/jev_contract/runtime.py:89-192` into `DecisionExecutor.execute_graph` in `packages/core/openclass_core/decision_executor.py`. Persist `steps: list[DecisionStepTrace]` in `DecisionRun.payload`.
- **Verification:** Multi-node routing test (root router → specialist node → terminal choice) via `POST /api/v1/projects/{id}/decision-services/{sid}/runs`.

#### OC-BG-016 (P1, WS-04 — `OC-035` / Impl Phase 01 & 02): `StateCompiler`, Persisted `StateSnapshot` (`0026`) & Metadata Context Propagation

- **Problem:** `DecisionExecutor` (`decision_executor.py:58-65`) drops `RawEvent.metadata`, and `state_snapshots` persistence is missing (`phase-0-baseline-and-oc-034.md:43`).
- **Implementation:** Add `StateCompiler.compile(raw_event, prior_steps, schema)` in `packages/core/openclass_core/decision.py` enforcing `StateFieldSpec` types, missing-vs-false semantics, source/freshness provenance, and a configurable max byte/token budget (`4096` chars per field); persist `state_snapshots` (`0026_state_snapshots.py`); pass compiled `state_facts` in `Observation.metadata` and serialize them into `JevDecisionProvider` and `LayaDecisionProvider` prompts.
- **Verification:** Unit & contract tests proving structured metadata facts change node precondition evaluation, persist in `state_snapshots`, and appear in model prompt context.

#### OC-BG-017 (P1, WS-05 — Impl Phase 03): Data-Driven `SupervisionPolicy` & `OperatingProfile` Enforcement

- **Problem:** `DecisionExecutor._supervise` (`decision_executor.py:169-197`) hardcodes `if provider_name == "laya"` and `if provider_name == "jev"`, ignoring `SupervisionPolicy.max_unknown_probability` and `DecisionNode.risk_level` and causing `23.5%` (GPT) and `19.4%` (Gemini) of reference errors in `scikit-learn-2026-10-02/REPORT.md` (Finding #4) to be labeled `TRUSTED`.
- **Implementation:** Replace hardcoded provider name checks in `decision_executor.py:169-197` with `evaluate_supervision(policy, profile, probabilities, unknown_prob, risk_level)` from `decision.py:254-329`, parameterized by each provider's `OperatingProfile` (`calibration_status`, `temperature`, `min_margin`, `max_unknown_probability`, `max_choices`), routing uncalibrated providers through `"REVIEW"`.
- **Verification:** Unit tests verifying that uncalibrated providers or `HIGH` risk nodes require review and `max_unknown_probability` triggers `UNKNOWN`/`REVIEW` across all providers.

#### OC-BG-018 (P1, WS-06 — `OC-035` / Impl Phase 09): `AutomationLoop` Macro Expansion, 5-Gate Applicability & Independent Verifiers

- **Problem:** `AutomationDecision.action` (`automation.py:54`) is typed as `AutomationActionName` enum, rejecting macro names; `AutomationLoop.step()` (`L120-138`) never expands `macro.steps`; `state_patch` (`L132`) injects undeclared fields.
- **Implementation:** Change `AutomationDecision.action` to `str` validated against `set(AutomationActionName) | set(policy.macros.keys())`; expand `macro.steps` sequentially in `AutomationLoop.step()` with per-step precondition/postcondition checks; port the 5-gate applicability checker (`scripts/automation_applicability.py`) and independent postcondition verifier protocol into `packages/core/openclass_core/automation.py`.
- **Verification:** Port `test_automation_applicability.py` and `test_automation_proof2b_cycle2.py` to import directly from `openclass_core.automation` instead of `scripts/`.

#### OC-BG-019 (P1, WS-06 — `OC-035` / Impl Phase 09): Harden `SafeSandboxExecutor` Subprocess & Network Isolation

- **Problem:** `SafeSandboxExecutor` (`packages/server/openclass_server/automation_executor.py:21-105`) runs `subprocess.run` with no timeout, unbounded output, leaky env filter (`if not k.endswith("API_KEY")`), unrestricted port probing, and 4 unimplemented enum actions.
- **Implementation:** Enforce `timeout=30.0` on `subprocess.run`, cap `stdout`/`stderr` at `64 KB`, replace env blacklist with a strict allowlist (`PATH`, `SYSTEMROOT`, `TMP`, `TEMP`, `HOME`, `PYTHONPATH` + explicit `state.env_vars`), restrict `INSPECT_PORT` / `CHOOSE_AVAILABLE_TEST_PORT` to unprivileged ephemeral range `1024..65535`, and implement `SET_ENVIRONMENT`, `RERUN_PREVIOUS`, `DONE`, and `BLOCKED`.
- **Verification:** Unit tests in `tests/unit/test_automation_executor.py` verifying timeout termination, env-var isolation (`OPENCLASS_DATABASE_URL` not leaked), and all 8 action handlers.

#### OC-BG-020 (P1, WS-07 — `OC-018`, `OC-020` / Impl Phase 03 & 06): Real LLM `SupervisorProvider` & Sampled/Triggered Supervision

- **Problem:** `provider_config.py:56-58` only wires `MockSupervisorProvider`.
- **Implementation:** Implement `OpenAICompatibleSupervisorProvider` in `providers/glm/openclass_provider_glm/supervisor.py` (supporting OpenAI/GLM/Ollama endpoints), register `"glm"`, `"openai-compatible"`, and `"ollama"` in `provider_config.py:56`, and add configurable post-run supervision triggers (`review_on_low_margin`, `sample_rate`) in `ProjectService.record_decision_run`.
- **Verification:** Contract tests in `tests/contract/test_supervisor_provider.py` + integration test in `test_reviews.py`.

#### OC-BG-021 (P1, WS-07 — Impl Phase 06): Promote Teacher Protocol v1.1 & 10-Layer `apply_candidate` to Core/Server

- **Problem:** `evolution.py:30-248` defines `FailureLayer`, `TeacherProposal`, and `CandidateEnvelope`, but `apply_candidate` and the v1.1 Teacher prompt builder only exist in `scripts/jev_contract/teacher.py:246-329`.
- **Implementation:** Move `apply_candidate` and deterministic schema/guard compilation from `scripts/jev_contract/teacher.py` into `packages/core/openclass_core/evolution.py`, and upgrade `OpenAICompatibleChoiceTeacher` (`providers/glm/openclass_provider_glm/project_teacher.py`) to support `TeacherProposal` across `DECISION_SPACE`, `PROCEDURE`, and `STATE_REPRESENTATION`.
- **Verification:** Unit & integration tests verifying `ADD_CHOICE`, `REPLACE_PROCEDURE`, and `ADD_STATE_FEATURE` candidate application and hash determinism.

#### OC-BG-022 (P1, WS-08 — `OC-005` / Impl Phase 05): Merge `GatewayEmbedder`, Embedding Cache & `pgvector` Indexing

- **Problem:** `api/clusters.py:35` hardcodes `HashLexicalEmbedder`, recomputes embeddings on every request, and `SentenceTransformerEmbedder.embed` (`embeddings_local.py:63-65`) blocks the async event loop. Real `GatewayEmbedder` exists only in the unmerged `artifacts/application-proofs/scikit-learn-2026-10-02/provider-wiring.patch` (`L85-133`).
- **Implementation:** Merge and harden `GatewayEmbedder` (`OpenAICompatibleEmbedder`), wrap `SentenceTransformerEmbedder._model.encode` in `await asyncio.to_thread(...)`, wire embedder selection in `provider_config.py`, add `ClusterStore.get_embeddings(run_ids, model_version)` cache lookup before calling `embedder.embed`, and add `pgvector` cosine distance query path when running on PostgreSQL.
- **Verification:** Integration tests verifying cache hit (0 redundant `embed()` calls on second cluster run) and semantic synonym clustering.

#### OC-BG-023 (P1, WS-11 — Impl Phase 01): Authenticate Control-Plane-to-Engine Traffic & Tenant Isolation (`0027`)

- **Problem:** `packages/server` is completely unauthenticated (`security.py`) and `services/control-plane/src/engine.ts:274-301` sends no auth or workspace headers (`phase-0-baseline-and-oc-034.md:38,49-51`).
- **Implementation:** Add `InternalAuthMiddleware` in `packages/server/openclass_server/security.py` verifying `X-OpenClass-Internal-Token` (or API key bearer token) via `hmac.compare_digest` and extracting `X-OpenClass-Workspace-Id` and `X-OpenClass-Actor` headers; forward those headers in `services/control-plane/src/engine.ts`; add `workspace_id` column to `projects` (`0027_project_workspace_isolation.py`) and scope all project queries by `workspace_id` when multi-tenant mode is enabled.
- **Verification:** Integration tests verifying unauthenticated requests to `:7331` with `OPENCLASS_AUTH_REQUIRED=true` return `401` and cross-workspace project access returns `404`.

#### OC-BG-024 (P1, WS-09 / WS-10 — `OC-036` / Impl Phase 01): Fix Webhook Content-Hash `409` Bug & Idempotency Store Flaws

- **Problem:** `SQLIntegrationRepository.ingest_webhook` (`integration_repository.py:53-94`) crashes with `409 Conflict` when two different `event_key` webhooks carry identical `content`; `IdempotencyStore` (`idempotency.py:24-61`, `idempotency.service.ts:16-33`) omits request-hash validation, skips storing when `deduped=True` (`api/projects.py:130`), and never updates expired keys (`ON CONFLICT DO NOTHING`).
- **Implementation:** In `ingest_webhook` (`integration_repository.py:72`), check for an existing `RawEventRow` by `(project_id, content_hash)` and link the new `WebhookReceiptRow` to it; add `request_hash` verification to `IdempotencyStore` (raising `409` on payload mismatch); replace `ON CONFLICT DO NOTHING` with `ON CONFLICT (project_id, key) DO UPDATE ... WHERE idempotency_keys.expires_at < EXCLUDED.created_at`; remove `and not deduped` at `api/projects.py:130`.
- **Verification:** Integration tests in `test_webhooks_api.py` and `test_idempotency_and_limits.py`.

#### OC-BG-025 (P1, WS-09 — Impl Phase 01 & 04): Atomic Unit-of-Work Transactions & `SELECT ... FOR UPDATE`

- **Problem:** Multi-step mutations in `ProjectService` (`record_decision_run`, `submit_run_feedback`, `create_evidence_case`, `ingest_events_batch`) commit across separate DB sessions, and `evidence_items.decision_run_id` (`tables.py:226`) lacks a `UNIQUE` constraint.
- **Implementation:** Add a transactional session context manager to `SQLProjectRepository` and `SQLRepository`, use `.with_for_update()` on mutable rows (`CandidateRow`, `ProjectRow`, `DecisionServiceRow`, `ProjectChoiceCandidateRow`), validate `stored.payload` inside `approve_candidate` (`repository.py:311-314`), add `UniqueConstraint("decision_run_id")` on `evidence_items`, and use `create_raw_events` bulk insert in `ingest_events_batch` (`projects.py:552-585`).
- **Verification:** Concurrency integration test submitting parallel feedback and candidate approvals.

#### OC-BG-026 (P1, WS-09 — Impl Phase 01): Reconcile Engine Alembic vs. Control-Plane SQL Migrations & Slug Constraints

- **Problem:** `migrations/env.py:16` has no `include_name` filter for `control_*` tables; `control_projects.slug` is globally unique (`0002_projects.sql:6`) while checked per-workspace (`project.service.ts:253`); `classifiers.slug` is globally unique (`tables.py:33`) while scoped per-project in `control_classifiers` (`0002_projects.sql:18`).
- **Implementation:** Add `include_name` filter in `migrations/env.py` ignoring `control_*` tables; add a migration runner script for `services/control-plane/migrations/`; change `control_projects` unique constraint to `UNIQUE (workspace_id, slug)`; add append-only triggers to `observations`, `classification_runs`, `unknown_events`, `decision_runs`, `run_feedback`, and `control_audit_events` (changing `ON DELETE CASCADE` to `ON DELETE RESTRICT`).
- **Verification:** `alembic check` passes on a database containing both engine and `control_*` tables; two workspaces can create projects with the same slug.

#### OC-BG-027 (P1, WS-13 — Impl Phase 10): Unify Dual Frontend Stack (`apps/portal` + `services/control-plane` vs `apps/web`) & Fix Express Body Limit

- **Problem:** `apps/portal/src/api.ts:10-25` uses raw `fetch()` (violating `AGENTS.md`); projects created in `apps/web`/SDK/CLI do not exist in `control_projects`; `services/control-plane` rejected 60-item batch ingestion with `HTTP 413` due to default Express 100KB body limit (`scikit-learn-2026-10-02/REPORT.md` Finding #3).
- **Implementation:** Refactor `apps/portal/src/api.ts` to use `@openclass/sdk`; configure explicit JSON body limit (`5mb`) in `services/control-plane/src/main.ts`; synchronize project registry between `control-plane` and `server`; unify Portal Track 3 and Web Track 2 views so both workspace entry points share full feature parity.
- **Verification:** E2E test creating a project via SDK/CLI, ingesting a 60-item batch via Control Plane without HTTP 413, and inspecting it in both `apps/portal` and `apps/web`.

#### OC-BG-028 (P1, WS-12 — `OC-010`): 100% API, SDK & CLI Parity Across All Server Endpoints

- **Problem:** Python SDK and TypeScript SDK miss all Phase 05–16 Portal/Engine routes (`/unknowns`, `/clusters`, `/discovery-candidates`, `/eval-datasets`, `/evaluations`, `/ontology`, `/analytics/summary`, `/alerts/*`, `/ops/events*`, `/integrations/{adapters,routes,outcomes}`, `/webhooks/{source}`); CLI covers only 16 routes.
- **Implementation:** Add SDK methods and CLI subcommands (`openclass service *`, `openclass evidence *`, `openclass candidate *`, `openclass cluster *`, `openclass eval *`, `openclass integration *`) for all server endpoints.
- **Verification:** Contract tests in `tests/contract/test_python_sdk.py` and `packages/sdk-typescript/src/index.test.ts` covering every FastAPI route.

#### OC-BG-029 (P1, WS-14 — `OC-037` / Impl Phase 04): Fix Provider Error Rollup, HTTP 429 Propagation, Model Usage Key & Correlation Logging

- **Problem:** `api/decisions.py:129` passes literal `"provider"`, `""`, `0.0` to `record_provider_error`; `main.py:123-125` swallows upstream HTTP `429` rate limits as generic HTTP `502` (`REPORT.md` Finding #2); `uq_provider_usage_day` (`tables.py:300`) omits `model`; embedding/discovery/Teacher costs are omitted from Portal cost rollups (`REPORT.md` Finding #7).
- **Implementation:** Pass actual `provider_name`, `model_name`, and elapsed `latency_ms` in `api/decisions.py:129` and emit `decision.provider_failed` audit event; preserve upstream `rate_limited` (`429`) status/retry metadata in `ProviderError`; include `model` in `uq_provider_usage_day` and record embedding/Teacher usage; add `X-Correlation-ID` middleware in `main.py`.
- **Verification:** Integration test verifying `ProviderError` increments `errors` on the actual provider/model row, surfaces rate-limit identity, and echoes `X-Correlation-ID`.

#### OC-BG-030 (P1, WS-09 — Impl Phase 05): Replace Silent 200-Row Truncation Caps & Unbounded Table Scans

- **Problem:** `api/unknowns.py:43`, `api/clusters.py:38`, and `discovery.py:28` silently slice `limit=200` (`REPORT.md` Finding #6); `analytics_runs` (`project_repository.py:416-421`), `operations._measurements` (`api/operations.py:43-70`), and `summary` audit count (`projects.py:506`) load entire tables into memory.
- **Implementation:** Add SQL `WHERE selected_choice = 'UNKNOWN'` filtering and cursor/offset pagination to `list_decision_runs`, lookup `unknown_events` directly by `id IN (...)` in `discovery.py:28`, and replace in-memory `analytics_runs` and `len(audit_events)` with SQL `COUNT(*)` / `GROUP BY` queries.
- **Verification:** Integration test with `> 250` runs verifying zero truncation and constant-memory SQL aggregation.

#### OC-BG-031 (P2, WS-11 — Impl Phase 10): Wire Redaction Settings, Recursive `redact_mapping`, Rate-Limiter Method Checks & Prompt-Injection Guards

- **Problem:** `Settings.redaction_enabled` & `redaction_blocklist` (`settings.py:19-20`) are unwired; `redact_mapping` (`redaction.py:45-48`) misses dicts inside lists; `RateLimiter.route_class` (`rate_limit.py:44-49`) throttles `GET /events` and `GET /runs`, misses `POST .../webhook`, and leaks memory in `_buckets`; `GLMDiscoveryProvider` and `OpenAICompatibleDiagnosisProvider` lack untrusted-data prompt boundaries.
- **Implementation:** Wire `config.redaction_enabled` and `config.redaction_blocklist` into redaction helpers; recurse into dicts/lists inside lists in `redact_mapping`; check `request.method == "POST"` and `/webhook` in `RateLimiter.route_class` with TTL bucket eviction; add untrusted-data system instructions and per-field truncation (`4000` chars) to `GLMDiscoveryProvider` and `OpenAICompatibleDiagnosisProvider`.
- **Verification:** Unit tests in `test_redaction.py`, `test_rate_limit.py`, and provider contract tests.

#### OC-BG-032 (P2, WS-10 — `OC-036` / Impl Phase 09): Shared Integration Manifests, Transactional Outbox & Verified Outbound Routing

- **Problem:** Phase 16 (`0022_integration_routes.py`, `api/support.py:248-254`) records only simulated DB rows (`"simulated": True`) with no external write-back or postcondition verification, and `HTTPIntegrationProbe.check` (`integration_adapters.py:78-80`) stubs `MCP`, `DATABASE`, and `PROVIDER`.
- **Implementation:** Implement `OC-036` shared integration manifests (`SOURCE`, `QUERY`, `CAPABILITY`, `TRIGGER`, `SINK`), `outbound_deliveries` outbox table with idempotency and retry reconciliation (`OC-035`), vendor HMAC-SHA256 webhook normalizers, and independent destination readback verification.
- **Verification:** Integration tests in `test_support_integrations.py`, `test_integrations_api.py`, and `test_webhooks_api.py`.

#### OC-BG-033 (P2, WS-14 — Impl Phase 01..10): Real PostgreSQL Control-Plane Tests, Portal Component Tests & Live-Backend Playwright Suite

- **Problem:** `services/control-plane/src/*.spec.ts` mocks `pg.Pool` via string prefixes; `apps/portal/src/portal.test.tsx` only tests the login gate; `tests/web/*.spec.ts` mocks 100% of `/api/v1/*` routes.
- **Implementation:** Add PostgreSQL integration test suite for `services/control-plane` applying `migrations/0001..0004.sql`; expand `apps/portal/src/portal.test.tsx` to cover authenticated views; add a live-backend Playwright project in `playwright.config.ts`.
- **Verification:** CI runs both route-mocked unit UI tests and live-backend E2E smoke tests.

#### OC-BG-034 (P2, WS-14 — `OC-038`, `OC-039`): Self-Contained Benchmarks, Complete Docker/Compose Stack & Application Proofs A–D

- **Problem:** `benchmarks/jev-contract/v1/knowledge.json` references gitignored `build/` paths; `Dockerfile:21-26` omits `COPY benchmarks examples`; `pyproject.toml:42` omits `openclass_provider_glm`; `scripts/release.py:14-19` omits `services/control-plane/package.json`.
- **Implementation:** Commit frozen benchmark summary artifacts under `benchmarks/jev-contract/v1/frozen-evidence/`, add `COPY benchmarks benchmarks` and `COPY examples examples` + non-root `USER` to `Dockerfile`, add `openclass_provider_glm` to `pyproject.toml:42`, update `scripts/release.py`, and execute the `OC-038`/`OC-039` application proofs (`Customer Operations`, `Developer Operations`, `Smart Home`, `Robot Simulator`).
- **Verification:** `uv run python -m scripts.jev_contract.audit`, `docker compose --profile test run test`, and `uv run mypy` pass on a clean clone.

#### OC-BG-035 (P2, WS-03 — `OC-035` / Impl Phase 09): Durable Multi-Step Run Checkpoints, Human Step Approval & Resume API

- **Problem:** Multi-step graph/automation runs cannot pause for human approval or resume after process restart.
- **Implementation:** Add `status: Literal["running", "waiting_human", "paused", "completed", "failed", "cancelled"]` and `checkpoint_state` to `DecisionRun`, plus `POST /api/v1/projects/{id}/runs/{run_id}/resume` and `/cancel`.
- **Verification:** Integration test pausing a graph run at a `HUMAN` transition node and resuming it with operator approval.

#### OC-BG-036 (P2, WS-08 — `OC-037` / Impl Phase 10): Fix `operations.py` Window Bug, Persisted Proof Reports & Post-Promotion Drift Triggers

- **Problem:** `api/operations.py:92-96` calls `_measurements(str(project.id), two_weeks_ago)` with `created_at >= :since` and no `< week_ago` upper bound, so `previous_unknown_rate` measures the cumulative 14-day window instead of the prior 7-day window; `OC-037` persisted proof reports and auto-rollback drift triggers are not yet wired.
- **Implementation:** Add `until: datetime | None = None` (`AND created_at < :until`) to `_measurements` in `api/operations.py:40-50` so `previous` measures `[two_weeks_ago, week_ago)`; implement persisted `OC-037` application proof report queries (`decisions`, `quality`, `execution`, `teacher`, `candidates`, `retention`, `cost/latency`, `improvement`); add optional post-promotion drift rollback trigger.
- **Verification:** Unit & integration tests in `test_operations_dashboard.py` verifying disjoint 7-day window comparison (`[now-14d, now-7d)` vs `[now-7d, now)`) and `OC-037` report denominators.

#### OC-BG-037 (P3, WS-05): Consolidate or Implement `providers/ollama` & `providers/openai-compatible`

- **Problem:** `providers/ollama` and `providers/openai-compatible` contain only `README.md` while OpenAI-compatible adapters live inside `providers/glm`.
- **Implementation:** Extract generic OpenAI-compatible and Ollama provider classes into `providers/openai-compatible` and `providers/ollama` (or re-export from `openclass_provider_glm` with proper `pyproject.toml` packages).
- **Verification:** `uv build --all-packages` and contract tests for `ollama` and `openai-compatible`.

#### OC-BG-038 (P3, WS-12): Implement `packages/tui` Terminal Inspector (`OC-013`)

- **Problem:** `packages/tui` contains only `README.md`.
- **Implementation:** Build a Textual/Rich terminal inspector in `packages/tui` using `openclass-sdk` to browse projects, runs, unknown pools, and candidates.
- **Verification:** Unit smoke test rendering TUI views against mock SDK client.
