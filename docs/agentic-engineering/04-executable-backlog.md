# 04 — Complete Executable Development Backlog

> **Owner:** Abdelhamid Khaled (`AbdelhamidKhald`)  
> **Scope:** Complete, dependency-ordered backlog (`OC-BG-001` through `OC-BG-038`) covering every P0–P3 defect, security vulnerability, disconnected subsystem, missing capability, and production-readiness requirement across OpenClass.

---

## 1. Master Backlog Overview Table

| ID | Priority | Workstream | Title | Status | Effort | Primary Affected Files |
| :--- | :---: | :--- | :--- | :--- | :---: | :--- |
| **OC-BG-001** | **P0** | WS-14 (CI / Tests) | Fix all 6 current `pytest` failures/errors on Windows & default settings, plus broken PostgreSQL test and `pnpm` CI job | Broken | S | `tests/contract/test_{jev,supervisor}_provider.py`, `tests/integration/test_{reviews,raw_events_postgres}.py`, `tests/unit/test_{decision_executor,automation_reuse}.py`, `.github/workflows/ci.yml`, `.gitattributes` |
| **OC-BG-002** | **P0** | WS-09 / WS-08 (Persistence) | Fix `UnknownTriageStore.append_audit` schema corruption crashing `GET /audit` and `GET /summary` with HTTP 500 | Broken | S | `packages/server/openclass_server/persistence/unknown_triage.py:85-102`, `packages/core/openclass_core/projects.py:78-101`, `persistence/project_repository.py:116-123` |
| **OC-BG-003** | **P0** | WS-11 (Security) | Fix Control-Plane `callerOf(request)` dropping `keyProjectId` (breaking all `oc_...` API keys), enforce granular API key scopes, and require `operator` role for ingestion | Broken | S | `services/control-plane/src/ingestion.controller.ts:26-35`, `services/control-plane/src/ingestion.service.ts:34-61,79,116,235-251`, `decision.controller.ts:58` |
| **OC-BG-004** | **P0** | WS-10 / WS-11 (Security) | Eliminate SSRF and arbitrary env-var exfiltration in `HTTPIntegrationProbe.check`, `EnvironmentSecrets.resolve`, and provider `base_url` | Vulnerable | M | `packages/server/openclass_server/integration_adapters.py:25-37,89-126`, `api/providers.py:15,29-42`, `provider_config.py:71,97,123,194-213` |
| **OC-BG-005** | **P0** | WS-03 / WS-05 (Execution) | Fix custom instruction propagation from `DecisionService`/`DecisionNode` through `DecisionExecutor` to `JevDecisionProvider`, `LayaDecisionProvider`, and `MockDecisionProvider` | Broken | M | `packages/core/openclass_core/decision_executor.py:58-85`, `projects.py:671-672`, `models.py:109-120`, `providers/jev/__init__.py:19-23,102`, `providers/laya/__init__.py:27-31,139` |
| **OC-BG-006** | **P0** | WS-03 / WS-04 (Core Domain) | Fix `DecisionExecutor` tie-breaking bug (favoring known choice over `UNKNOWN`), ephemeral class UUID generation, and `evaluate_predicates` missing-vs-`None` & `bool`-vs-`int` bugs | Broken | S | `packages/core/openclass_core/decision_executor.py:58-80,102-115`, `packages/core/openclass_core/decision.py:217-235` |
| **OC-BG-007** | **P0** | WS-12 / WS-13 (SDK / UI) | Fix broken SDK/API contracts: `ingestBatch` 207 response unwrapping, missing `POST /evidence-cases/{cid}/evidence` route (404), `transition_evidence` `note` vs `rationale`, and missing `POST /candidates/{cid}/reject` route | Broken | M | `packages/sdk-typescript/src/index.ts:573,773,800`, `packages/sdk-python/openclass_sdk/__init__.py:442,466`, `api/evidence.py`, `api/evolution.py`, `apps/web/app/projects/[id]/{data,evolution}/page.tsx` |
| **OC-BG-008** | **P0** | WS-08 / WS-09 (Persistence) | Prevent `ClusterStore.replace_clusters` from cascade-deleting `cluster_candidates` and `candidate_evidence` on re-clustering | Data Loss | S | `packages/server/openclass_server/persistence/cluster_store.py:45-53`, `tables.py:344,361`, `migrations/versions/0016_cluster_candidates.py` |
| **OC-BG-009** | **P0** | WS-05 / WS-07 (Providers) | Fix `provider_config.py` startup crash on empty `base_url`, silent fallback on missing diagnosis key, Jev `real_inference` metadata omission, and Laya `simulated: False` regex fallback | Broken | S | `packages/server/openclass_server/provider_config.py:54-125`, `providers/jev/__init__.py:102-120`, `providers/laya/__init__.py:251,280-287`, `providers/glm/{diagnosis,project_teacher}.py` |
| **OC-BG-010** | **P0** | WS-09 (Persistence) | Implement immutable `DecisionServiceVersion` snapshots (`0017_decision_service_versions.py`), append-only triggers, and version lineage on `DecisionRun` | Missing Invariant | M | `packages/core/openclass_core/projects.py:176-237,470-705`, `persistence/tables.py`, `persistence/project_repository.py:207-290`, `migrations/versions/0017_decision_service_versions.py` |
| **OC-BG-011** | **P1** | WS-08 (Evaluation) | Implement Verified Evaluation Datasets, strict label provenance (`human` / `verified_external`), dataset sealing, and holdout splits (`OC-008` Part 1) | Blocked (409) | L | `packages/core/openclass_core/evaluation.py` (new), `persistence/tables.py`, `migrations/versions/0018_evaluation_datasets_and_runs.py`, `api/evaluation.py` (new) |
| **OC-BG-012** | **P1** | WS-08 (Evaluation) | Implement Deterministic Baseline vs. Candidate Replay Engine with Teacher disabled and regression gates (`OC-008` Part 2) | Blocked (409) | L | `packages/core/openclass_core/{project_evolution,discovery,evaluation}.py`, `api/evolution.py:90-98`, `api/classifiers.py:123-128`, `api/candidates.py` |
| **OC-BG-013** | **P1** | WS-08 (Evolution) | Implement Human Approval Records, Transactional `SELECT ... FOR UPDATE` Promotion (`vN → vN+1`), Evidence Auto-Resolution, and Rollback (`OC-009`) | Blocked (409) | M | `packages/core/openclass_core/{project_evolution,discovery}.py`, `persistence/{repository,project_repository}.py`, `api/{evolution,classifiers,candidates}.py` |
| **OC-BG-014** | **P1** | WS-08 (Evolution) | Unify the 4 fractured candidate pipelines (`Candidate`, `ChoiceCandidate`, `DiscoveryCandidate`, `CandidateEnvelope`) and synchronize `unknown_triage` with `evidence_items` | Duplicated | L | `packages/core/openclass_core/{evolution,project_evolution,candidates,unknown_pool,evidence}.py`, `api/{evolution,candidates,unknowns,evidence}.py` |
| **OC-BG-015** | **P1** | WS-03 (Execution) | Upgrade `DecisionExecutor` to execute multi-node `PolicyGraph` transitions, cycle detection, step budgets (`max_steps`), and durable step traces | Disconnected | L | `packages/core/openclass_core/{decision,decision_executor,projects}.py`, `scripts/jev_contract/runtime.py:89-192` |
| **OC-BG-016** | **P1** | WS-04 (State & Memory) | Implement `StateCompiler` with typed `StateSchema` validation, `RawEvent.metadata` propagation, source provenance, and context token/byte budgets | Missing | M | `packages/core/openclass_core/{decision,decision_executor,projects}.py`, `providers/{jev,laya}/__init__.py` |
| **OC-BG-017** | **P1** | WS-05 (Calibration) | Replace hardcoded provider supervision in `DecisionExecutor._supervise` with data-driven `SupervisionPolicy` and calibrated `OperatingProfile` enforcement | Hardcoded | M | `packages/core/openclass_core/{decision,decision_executor}.py`, `providers/{jev,laya}/profile.py` |
| **OC-BG-018** | **P1** | WS-06 (Capabilities) | Fix `AutomationLoop` macro validation/expansion, port 5-gate macro applicability & independent postcondition verifiers from `scripts/automation_*.py` to `packages/core` | Broken in Core | L | `packages/core/openclass_core/{automation,decision}.py`, `scripts/automation_{applicability,attempts,proof2b_cycle2}.py` |
| **OC-BG-019** | **P1** | WS-06 (Sandbox) | Harden `SafeSandboxExecutor` with subprocess timeouts, output caps, strict env-var allowlisting, port range restrictions, and complete action handlers | Unsafe | M | `packages/server/openclass_server/automation_executor.py:21-105`, `tests/unit/test_automation_executor.py` |
| **OC-BG-020** | **P1** | WS-07 (Teacher/Supervisor) | Wire real LLM `SupervisorProvider` (OpenAI-compatible / Ollama) in `provider_config.py` and add sampled/triggered continuous supervision (`OC-018`, `OC-020`) | Mock-Only | M | `packages/core/openclass_core/supervisor.py`, `providers/glm/openclass_provider_glm/supervisor.py` (new), `packages/server/openclass_server/provider_config.py:54-56` |
| **OC-BG-021** | **P1** | WS-07 (Teacher) | Promote Teacher Protocol v1.1 (`TeacherProposal`, 10-layer `FailureLayer`, `LAYER_OPERATORS`, `apply_candidate`) from `scripts/jev_contract/teacher.py` into server runtime | Script-Only | L | `packages/core/openclass_core/evolution.py`, `providers/glm/openclass_provider_glm/project_teacher.py`, `scripts/jev_contract/teacher.py` |
| **OC-BG-022** | **P1** | WS-08 (Embeddings) | Wire real semantic `EmbeddingProvider` (`OpenAICompatibleEmbedder` + async `SentenceTransformerEmbedder`), cache embeddings in `ClusterStore`, and use `pgvector` on PostgreSQL | Simulated | M | `packages/server/openclass_server/embeddings_local.py:48-65`, `persistence/cluster_store.py:18-37`, `api/clusters.py:35-59` |
| **OC-BG-023** | **P1** | WS-11 (Security) | Authenticate Control-Plane-to-Engine traffic (`X-OpenClass-Internal-Token`), propagate `workspace_id` and `actor` headers, and isolate tenant project lookups | Unauthenticated | M | `packages/server/openclass_server/{security,main}.py`, `services/control-plane/src/engine.ts:274-301`, `docker-compose.yml:37-49` |
| **OC-BG-024** | **P1** | WS-09 / WS-10 (Webhooks & Idempotency) | Fix webhook `409 Conflict` on duplicate content hash across distinct `event_key`s, and fix `IdempotencyStore` request-hash validation, TOCTOU race, and expiry refresh | Buggy | M | `packages/server/openclass_server/persistence/{integration_repository,idempotency}.py`, `api/projects.py:113-198`, `services/control-plane/src/idempotency.service.ts` |
| **OC-BG-025** | **P1** | WS-09 (Transactions) | Wrap multi-step `ProjectService` mutations in atomic Unit-of-Work transactions, add `SELECT ... FOR UPDATE`, and add `UNIQUE(decision_run_id)` on `evidence_items` | Race Condition | M | `packages/server/openclass_server/persistence/{project_repository,repository,tables}.py`, `packages/core/openclass_core/projects.py` |
| **OC-BG-026** | **P1** | WS-09 (Schema Alignment) | Reconcile Engine Alembic vs. Control-Plane SQL migrations (`include_name` filter, control-plane migration runner, scoped slug uniqueness, append-only triggers) | Split-Brain | M | `packages/server/openclass_server/migrations/env.py`, `services/control-plane/migrations/0002..0003.sql`, `services/control-plane/src/project.service.ts` |
| **OC-BG-027** | **P1** | WS-13 (Dual Stack) | Reconcile `apps/portal` + `services/control-plane` vs. `apps/web`: synchronize project creation, replace raw `fetch()` in `apps/portal/src/api.ts` with `@openclass/sdk`, and surface missing tabs | Split-Brain | L | `apps/portal/src/{api.ts,portal.tsx}`, `services/control-plane/src/{project.service.ts,engine.ts}`, `packages/sdk-typescript/src/index.ts` |
| **OC-BG-028** | **P1** | WS-12 (SDK / CLI Parity) | Achieve 100% endpoint parity across Python SDK, TypeScript SDK, and `openclass` CLI for all 50 server routes | Partial | M | `packages/sdk-python/openclass_sdk/__init__.py`, `packages/sdk-typescript/src/index.ts`, `packages/cli/openclass_cli/main.py` |
| **OC-BG-029** | **P1** | WS-14 (Observability) | Fix `record_provider_error` hardcoded `"provider"` rollup bug, include `model` in `uq_provider_usage_day`, and add structured logging + `X-Correlation-ID` propagation | Buggy | S | `packages/server/openclass_server/api/decisions.py:125-132`, `persistence/{project_repository,tables}.py`, `main.py`, `services/control-plane/src/engine.ts` |
| **OC-BG-030** | **P1** | WS-09 (Pagination & Perf) | Replace silent 200-row truncation caps (`unknowns`, `clusters`, `discovery`) and unbounded in-memory table loads (`analytics_runs`, `summary` audit count) with SQL pagination/aggregation | Truncation / OOM | M | `packages/server/openclass_server/api/{unknowns,clusters}.py`, `persistence/project_repository.py:416-421`, `packages/core/openclass_core/{discovery,projects}.py` |
| **OC-BG-031** | **P2** | WS-11 (Security Hardening) | Wire `Settings.redaction_enabled` & `redaction_blocklist`, fix recursive `redact_mapping`, fix `RateLimiter.route_class` HTTP method check & bucket eviction, and add prompt-injection boundaries | Partial | M | `packages/server/openclass_server/{redaction,rate_limit,settings}.py`, `providers/glm/openclass_provider_glm/{__init__,diagnosis}.py` |
| **OC-BG-032** | **P2** | WS-10 (Integrations) | Implement transactional webhook/action outbox with retries, vendor webhook HMAC normalizers (Zendesk, Intercom, Freshdesk), and MCP/Database connectivity probes | Stubbed | L | `packages/server/openclass_server/integration_adapters.py:78-80`, `persistence/tables.py` |
| **OC-BG-033** | **P2** | WS-14 (Full-Stack Tests) | Add real PostgreSQL integration tests for `services/control-plane`, authenticated component tests for `apps/portal`, and live-backend Playwright E2E tests | Mock-Only | M | `services/control-plane/src/*.spec.ts`, `apps/portal/src/portal.test.tsx`, `playwright.config.ts`, `tests/web/*.spec.ts` |
| **OC-BG-034** | **P2** | WS-14 (Benchmarks & Docker) | Make `benchmarks/jev-contract/v1` self-contained without gitignored `build/` paths, add `COPY benchmarks examples` to `Dockerfile`, and add containers for `control-plane`/`portal`/`web` | Broken on Clean Clone | M | `Dockerfile:21-32`, `docker-compose.yml`, `scripts/jev_contract/audit.py`, `scripts/release.py`, `pyproject.toml:42` |
| **OC-BG-035** | **P2** | WS-03 (Durable Runs) | Add durable multi-step run checkpoints (`WAITING_HUMAN`, `PAUSED`, `CANCELLED`), human-in-the-loop step approval, and resume API | Absent | L | `packages/core/openclass_core/{decision_executor,projects}.py`, `persistence/tables.py`, `api/decisions.py` |
| **OC-BG-036** | **P2** | WS-08 (Drift & Monitoring) | Implement post-promotion drift monitoring, confidence/unknown-rate anomaly alerts, and automated rollback triggers (Phase 13) | Absent | M | `packages/core/openclass_core/analytics.py`, `packages/server/openclass_server/api/projects.py` |
| **OC-BG-037** | **P3** | WS-05 (Provider Packaging) | Consolidate or implement standalone `providers/ollama` and `providers/openai-compatible` packages (currently README-only) | Placeholder | S | `providers/ollama/`, `providers/openai-compatible/`, `providers/glm/` |
| **OC-BG-038** | **P3** | WS-12 (Terminal UI) | Implement `packages/tui` terminal inspector using `openclass-sdk` (`OC-013`) | Placeholder | M | `packages/tui/` |

---

## 2. Detailed Executable Backlog Specifications

### OC-BG-001 — Fix All 6 Current `pytest` Failures/Errors, Broken Postgres Test & `pnpm` CI Pipeline
- **Workstream & Subsystem:** WS-14 (`tests/`, `.github/workflows/`, `Makefile`)
- **Priority:** `P0` | **Current Status:** Broken in local Windows runs and GitHub Actions CI
- **Concrete Problem & Evidence:**
  1. `tests/contract/test_jev_provider.py:86` and `tests/contract/test_supervisor_provider.py:72` parametrize `payload` with `"x" * 2_000_000` without `ids=...`. Pytest embeds the 2MB string into `PYTEST_CURRENT_TEST`, causing `ValueError: the environment variable is longer than 32767 characters` on Windows when `anyio` spawns a thread/process.
  2. `tests/integration/test_reviews.py:96` (`test_supervisor_failures_are_safe_and_persist_nothing`) calls `create_app(Settings(database_url=database_url), supervisor_provider=LeakingSupervisor())` without `decision_provider=MockDecisionProvider()`. Because `Settings.decision_provider` defaults to `"laya"` (`settings.py:13`), `/classify` fails before reaching `/reviews`.
  3. `tests/unit/test_decision_executor.py:95` (`test_decision_executor_provenance_recording`) asserts `real_run.execution_mode == "in_process"` on `LayaDecisionProvider(allow_fallback=True)` when `laya` is not installed (`execution_mode` is `"deterministic_test_fallback"`).
  4. `tests/unit/test_automation_reuse.py:142` (`test_frozen_fixture_unchanged`) hashes raw bytes of `scripts/automation_replay_fixture.py`, which fails when Git checks out CRLF (`\r\n`) on Windows.
  5. `tests/unit/test_automation_reuse.py:160` (`test_transfer_fixture_has_real_failure_and_truthful_report`) binds two sockets on `127.0.0.1` without `SO_EXCLUSIVEADDRUSE` on Windows, so the second bind succeeds instead of failing with `"Address already in use"`.
  6. `tests/integration/test_raw_events_postgres.py:59-60` asserts `resp.status_code == 201` and `len(resp.json()) == 2` on `POST /events/batch`, which now returns `207` and `{"items": [...]}` (`api/projects.py:137-198`).
  7. `.github/workflows/ci.yml:56-62` and `.github/workflows/artifacts.yml:20-23` run `npm ci` on a `pnpm` workspace (`apps/web/package.json:12` has `"@openclass/sdk": "workspace:*"`).
- **Root Cause:** Missing `ids=` on large parametrized strings, missing `.gitattributes` `eol=lf` enforcement, Windows vs POSIX socket flags, and unupdated CI/test assertions after Phase 5 & `pnpm` workspace migration.
- **Target Behavior:** `uv run pytest`, `pnpm test`, and all GitHub Actions jobs (`python`, `postgres`, `web`) pass 100% on Linux, macOS, and Windows.
- **Detailed Implementation Approach:**
  1. Add `ids=["truncated_json", "wrong_type", "oversized_2mb"]` to `@pytest.mark.parametrize` in `test_jev_provider.py:86` and `test_supervisor_provider.py:72`.
  2. Pass `decision_provider=MockDecisionProvider()` in `tests/integration/test_reviews.py:96`.
  3. Normalize `\r\n` to `\n` before hashing in `test_automation_reuse.py:142` and add `.gitattributes` (`* text=auto eol=lf`).
  4. In `scripts/automation_transfer_fixture.py` (or socket binder), set `socket.SO_EXCLUSIVEADDRUSE` on Windows (`sys.platform == "win32"`) instead of `SO_REUSEADDR`.
  5. Update `tests/integration/test_raw_events_postgres.py:59-60` to assert `resp.status_code == 207` and `len(resp.json()["items"]) == 2`, and add `pytestmark = pytest.mark.postgres` to all 6 unmarked `test_*_postgres.py` files.
  6. Update `.github/workflows/ci.yml` and `artifacts.yml` to use `pnpm/action-setup@v4` and `pnpm install --frozen-lockfile`.
- **Dependencies:** None (Stage 0 entry gate).
- **Verification & Acceptance Criteria:** `uv run pytest -q` reports `0 failed, 0 errors`; `pnpm test` and `pnpm build` succeed.
- **Effort / Risk / Blast Radius:** Small (S) | Low risk | Test & CI files only.

---

### OC-BG-002 — Fix `UnknownTriageStore.append_audit` Schema Corruption Breaking `/audit` and `/summary`
- **Workstream & Subsystem:** WS-09 / WS-08 (`packages/server/openclass_server/persistence/unknown_triage.py`, `packages/core/openclass_core/projects.py`)
- **Priority:** `P0` | **Current Status:** Critical Runtime Crash (HTTP 500)
- **Concrete Problem & Evidence:**
  - `SQLProjectRepository.audit_events` (`persistence/project_repository.py:116-123`) deserializes every row in `audit_events` via `ProjectAuditEvent.model_validate(row.payload)`.
  - `UnknownTriageStore.append_audit` (`persistence/unknown_triage.py:85-102`) executes raw SQL `INSERT INTO audit_events` with `payload = json.dumps({"target": target})` and event types `"unknown.triaged"`, `"unknown.transitioned"`, `"cluster.updated"`, and `"candidate.created"`.
  - None of those 4 event types exist in `ProjectAuditEvent.event_type` (`projects.py:78-101`), and `{"target": target}` omits required `ProjectAuditEvent` fields (`id`, `project_id`, `event_type`, `actor`, `created_at`).
- **Root Cause:** `UnknownTriageStore` bypassed `SQLProjectRepository.append_audit_event` and `to_audit_event_row` (`persistence/mappers.py:8-16`).
- **Target Behavior:** All audit writes produce valid `ProjectAuditEvent` envelopes; `GET /api/v1/projects/{id}/audit` and `GET /api/v1/projects/{id}/summary` succeed after unknown triage, clustering, and candidate discovery.
- **Detailed Implementation Approach:**
  1. Add `"unknown.triaged"`, `"unknown.transitioned"`, `"cluster.updated"`, and `"candidate.created"` to `ProjectAuditEvent.event_type` literal in `packages/core/openclass_core/projects.py:78-101`.
  2. Update `UnknownTriageStore.append_audit` (`unknown_triage.py:85-102`) to instantiate `ProjectAuditEvent` and serialize `event.model_dump(mode="json")` into `payload`.
  3. Add fallback normalization in `SQLProjectRepository.audit_events` (`project_repository.py:116-123`) so if a legacy row's `payload` lacks `"id"`, it reconstructs `ProjectAuditEvent` from the row's columns (`row.id`, `row.project_id`, `row.event_type`, `row.actor`, `row.payload`, `row.created_at`).
- **Data / Migration Changes:** Optional data cleanup in `0017` or runtime mapper fallback in `project_repository.py:116-123`.
- **Verification & Acceptance Criteria:** In `tests/integration/test_unknown_workspace.py` and `test_embeddings_clustering.py`, call `GET /api/v1/projects/{slug}/audit` and `GET /api/v1/projects/{slug}/summary` after triaging and clustering and assert `200 OK` with valid audit entries.
- **Effort / Risk / Blast Radius:** Small (S) | Low risk | Fixes P0 500 crash.

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
- **Priority:** `P0` | **Current Status:** Broken (Instructions silently dropped before inference)
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

### OC-BG-008 — Prevent Re-Clustering from Cascade-Deleting `cluster_candidates` and `candidate_evidence`
- **Workstream & Subsystem:** WS-08 / WS-09 (`persistence/cluster_store.py`, `tables.py`, `migrations/versions/`)
- **Priority:** `P0` | **Current Status:** Destructive Data Loss Bug
- **Concrete Problem & Evidence:**
  - `ClusterStore.replace_clusters` (`packages/server/openclass_server/persistence/cluster_store.py:50-53`) runs `DELETE FROM unknown_clusters WHERE project_id = :project_id`.
  - `cluster_candidates.cluster_id` (`0016_cluster_candidates.py:20-23`, `tables.py:344`) has `ForeignKey("unknown_clusters.id", ondelete="CASCADE")`, and `candidate_evidence.candidate_id` (`tables.py:361`) has `ondelete="CASCADE"`. Re-running clustering wipes out all discovered candidates and evidence links for the project.
- **Detailed Implementation Approach:**
  1. Create migration `0017_preserve_cluster_candidates.py` changing `cluster_candidates.cluster_id` to `nullable=True` with `ondelete="SET NULL"` (and adding `decision_service_id` to `unknown_clusters`).
  2. In `ClusterStore.replace_clusters` (`cluster_store.py:45-55`), only delete `unknown_clusters` rows that are not referenced by an active candidate, or mark prior clusters `status = 'superseded'` while detaching `cluster_id` safely.
- **Verification & Acceptance Criteria:** Integration test in `tests/integration/test_discovery_candidates.py` that discovers a candidate from a cluster, re-runs `POST /unknowns/cluster`, and asserts `GET /discovery-candidates` still returns the candidate and its `candidate_evidence` rows intact.
- **Effort / Risk / Blast Radius:** Small (S) | Low risk | Stops silent candidate deletion.

---

### OC-BG-009 — Fix Provider Configuration, Provenance Metadata & Malformed Response Handling
- **Workstream & Subsystem:** WS-05 / WS-07 (`provider_config.py`, `providers/{jev,laya,glm}`)
- **Priority:** `P0` | **Current Status:** Buggy / Misleading Provenance
- **Concrete Problem & Evidence:**
  1. `provider_config.py:95-99` crashes startup when `OPENCLASS_DISCOVERY_PROVIDER=openai-compatible` and `OPENCLASS_DISCOVERY_BASE_URL` is unset (`base_url=""`).
  2. `provider_config.py:118-119` silently falls back to `RuleBasedDiagnosisProvider` when `OPENCLASS_DIAGNOSIS_API_KEY` is missing.
  3. `JevDecisionProvider` (`providers/jev/openclass_provider_jev/__init__.py:102-120`) omits `"real_inference": True` and `"execution_mode": "api"`, causing `DecisionExecutor` (`L142-146`) to record live Jev runs as `real_inference=False, execution_mode="daemon"`.
  4. `LayaDecisionProvider._local_fallback_choice` (`providers/laya/openclass_provider_laya/__init__.py:251`) sets `"simulated": False` on regex fallback output, and `_normalize_response` (`L280-287`) silently renormalizes uncalibrated numbers instead of rejecting distributions where `abs(total - 1.0) > 0.05`.
  5. `OpenAICompatibleDiagnosisProvider` (`providers/glm/openclass_provider_glm/diagnosis.py:86-93`) silently substitutes `DiagnosisCategory.ANALYTICAL_GAP` on invalid enum values, and `project_teacher.py:121-122` leaks `str(exc)` in `ProviderError`.
- **Detailed Implementation Approach:**
  1. Validate required `base_url` and API key env vars explicitly in `provider_config.py` and raise `ProviderError(kind="configuration")` without silent fallback unless `OPENCLASS_DIAGNOSIS_PROVIDER=mock`.
  2. Set `"real_inference": True`, `"simulated": False`, `"execution_mode": "api"` in `JevDecisionProvider` response metadata (`providers/jev/__init__.py:115`).
  3. Set `"simulated": True` in `LayaDecisionProvider._local_fallback_choice` (`providers/laya/__init__.py:251`) and raise `ProviderError("Laya probability distribution does not sum to 1.0", kind="malformed_response")` in `_normalize_response` when `abs(total - 1.0) > 0.05`.
  4. Raise `ProviderError(kind="malformed_response")` on unknown diagnosis categories in `diagnosis.py:86-93` and sanitize exception messages in `project_teacher.py:121-122`.
- **Verification & Acceptance Criteria:** Unit & contract tests in `tests/unit/test_provider_config.py` and `tests/contract/test_{jev,laya}_provider.py`.
- **Effort / Risk / Blast Radius:** Small (S) | Low risk | Provider adapters & config.

---

### OC-BG-010 — Implement Immutable `DecisionServiceVersion` Snapshots & Run Lineage
- **Workstream & Subsystem:** WS-09 (`packages/core/openclass_core/projects.py`, `persistence/tables.py`, `persistence/project_repository.py`)
- **Priority:** `P0` | **Current Status:** Missing Core Invariant (`AGENTS.md`: *"Ontology snapshots and audit history are append-only"*)
- **Concrete Problem & Evidence:**
  - `DecisionServiceRow` (`persistence/tables.py:133-147`) is overwritten in-place by `SQLProjectRepository.update_decision_service` (`persistence/project_repository.py:230-246`).
  - `DecisionRun` (`projects.py:216-237`) has no `decision_service_version_id` or `service_hash`, making it impossible to know which version of a `DecisionService` produced a historical run after the service is edited or promoted.
  - Furthermore, `ProjectService.create_decision_service` (`projects.py:597-637`) and `update_decision_service` (`L639-679`) emit **no `ProjectAuditEvent`**.
- **Detailed Implementation Approach:**
  1. Add `DecisionServiceVersion` model in `projects.py` (`id`, `project_id`, `decision_service_id`, `version_number`, `parent_version_id`, `service_hash`, `instructions`, `nodes`, `created_by`, `created_at`).
  2. Add `active_version_id: UUID` and `version_number: int = 1` to `DecisionService`, and `decision_service_version_id: UUID` + `service_hash: str` to `DecisionRun`.
  3. Create Alembic migration `0017_decision_service_versions.py` adding table `decision_service_versions` with PostgreSQL & SQLite `BEFORE UPDATE`/`BEFORE DELETE` immutability triggers, backfilling `v1` for existing services, and adding `GET /versions`, `GET /versions/{vid}`, and `POST /rollback` routes.
  4. Emit `decision_service.created`, `decision_service.version_created`, and `decision_service.rolled_back` `ProjectAuditEvent`s.
- **Dependencies:** Prerequisite for `OC-BG-012` (Replay Evaluation) and `OC-BG-013` (Candidate Promotion).
- **Verification & Acceptance Criteria:** Integration tests verifying that updating a `DecisionService` creates `version_number = 2`, direct SQL `UPDATE`/`DELETE` on `decision_service_versions` is rejected by DB triggers, and `DecisionRun` records `decision_service_version_id`.
- **Effort / Risk / Blast Radius:** Medium (M) | Medium risk | Core `DecisionService` persistence.

---

### OC-BG-011 — Implement Verified Evaluation Datasets, Label Provenance & Holdouts (`OC-008` Part 1)
- **Workstream & Subsystem:** WS-08 (`packages/core/openclass_core/evaluation.py`, `persistence/tables.py`, `api/evaluation.py`)
- **Priority:** `P1` | **Current Status:** Blocked / Absent
- **Concrete Problem & Evidence:**
  - Zero tables or routes exist for storing human-verified evaluation datasets or holdout splits.
- **Detailed Implementation Approach:**
  1. Create `packages/core/openclass_core/evaluation.py` defining:
     - `LabelSource = Literal["human", "verified_external"]` (Pydantic validator explicitly rejects `"prediction"`, `"model"`, or `"unverified"`).
     - `EvaluationSlice = Literal["historical", "recent", "rare", "hard", "unknown", "target_candidate", "adversarial"]`.
     - `EvaluationSplit = Literal["evaluation", "holdout"]`.
     - `EvaluationExample(id, dataset_id, content, metadata, expected_choice, slice_tag, split, label_source, verified_by, verified_at, rationale)`.
     - `EvaluationDataset(id, project_id, decision_service_id, name, status: Literal["draft", "sealed"], dataset_hash, created_at, sealed_at)`.
  2. Create Alembic migration `0018_evaluation_datasets_and_runs.py` adding `evaluation_datasets`, `evaluation_examples`, `evaluation_runs`, and `candidate_approvals`, with immutability triggers on sealed datasets and `evaluation_runs`.
  3. Expose CRUD + `POST /api/v1/projects/{id}/evaluation-datasets/{did}/seal` in `api/evaluation.py`.
- **Dependencies:** `OC-BG-010`.
- **Verification & Acceptance Criteria:** Unit & integration tests proving that `label_source="prediction"` is rejected with `422`, sealing computes a deterministic SHA-256 `dataset_hash`, and sealed datasets reject mutations.
- **Effort / Risk / Blast Radius:** Large (L) | Low risk | New evaluation persistence layer.

---

### OC-BG-012 — Implement Deterministic Baseline vs. Candidate Replay Engine & Regression Gates (`OC-008` Part 2)
- **Workstream & Subsystem:** WS-08 (`packages/core/openclass_core/{evaluation,project_evolution,discovery}.py`, `api/{evolution,classifiers,candidates}.py`)
- **Priority:** `P1` | **Current Status:** Blocked (Unconditionally raises `ConflictError` / HTTP 409 at `project_evolution.py:206` and `discovery.py:79`)
- **Detailed Implementation Approach:**
  1. Implement `ReplayEvaluationService.evaluate_choice_candidate(project_id, candidate_id, dataset_id, gate_policy, actor)`:
     - Verify `dataset.status == "sealed"` and `service_hash(active_service) == candidate.base_service_hash`.
     - Construct an in-memory candidate `DecisionService` applying `NEW_CHOICE` or `ALIAS` (without persisting it as active).
     - Run `DecisionExecutor.execute` (with Teacher/discovery disabled) across all examples in `dataset` against both `active_service` (baseline) and `candidate_service` (candidate).
     - Compute `accuracy_on_knowns_{before,after}`, `macro_f1_{before,after}`, `unknown_recall_{before,after}`, `false_novelty_rate_{before,after}`, `disambiguation_rate`, `knowledge_retention_rate`, and `regressions: tuple[str, ...]`.
     - Evaluate all 6 deterministic regression gates (`error_count == 0`, `regressions == ()`, `known_accuracy_after >= known_accuracy_before`, `disambiguation_rate >= 0.80`, `false_novelty_rate_after <= 0.05`, `holdout_regressions == ()`).
     - Persist immutable `EvaluationRun` and update `candidate.status = "evaluated"`.
  2. Wire `ProjectEvolutionService.evaluate` (`project_evolution.py:204-206`) and `DiscoveryService.evaluate` (`discovery.py:76-79`) to `ReplayEvaluationService`.
- **Dependencies:** `OC-BG-010`, `OC-BG-011`.
- **Verification & Acceptance Criteria:** End-to-end integration test where a candidate that regresses a known example fails (`passed=False`), and a candidate that resolves `UNKNOWN` examples with zero regressions passes (`passed=True`).
- **Effort / Risk / Blast Radius:** Large (L) | Medium risk | Unlocks `OC-008`.

---

### OC-BG-013 — Implement Human Approval Records, Transactional `vN+1` Promotion, Evidence Auto-Resolution & Rollback (`OC-009`)
- **Workstream & Subsystem:** WS-08 (`packages/core/openclass_core/{project_evolution,discovery}.py`, `persistence/{project_repository,repository}.py`)
- **Priority:** `P1` | **Current Status:** Blocked (HTTP 409 at `project_evolution.py:239` and `discovery.py:74`)
- **Detailed Implementation Approach:**
  1. Require `PromoteCandidateRequest(evaluation_run_id: str, reviewer: str, rationale: str)` on `POST /api/v1/projects/{id}/candidates/{cid}/promote` and `POST /api/v1/classifiers/{id}/candidates/{cid}/approve`.
  2. Inside a single database transaction with `SELECT ... FOR UPDATE` on `DecisionServiceRow` and `ProjectChoiceCandidateRow`:
     - Verify `candidate.status == "evaluated"`, `evaluation_run.candidate_id == candidate.id`, `evaluation_run.passed is True`, and `evaluation_run.base_service_hash == candidate.base_service_hash == service_hash(active_service)`.
     - Persist `CandidateApprovalRow` (`id`, `candidate_id`, `evaluation_run_id`, `reviewer`, `rationale`, `approved_at`).
     - Insert new immutable `DecisionServiceVersionRow` (`version_number = active.version_number + 1`, `parent_version_id = active.active_version_id`).
     - Update `DecisionServiceRow.active_version_id`, set `candidate.status = "promoted"`, transition linked `EvidenceItem`s from `READY_FOR_EVOLUTION` to `RESOLVED`, and append `ProjectAuditEvent` (`choice_candidate.promoted` & `decision_service.version_created`).
- **Dependencies:** `OC-BG-010`, `OC-BG-012`.
- **Verification & Acceptance Criteria:** Promoting without a passing `evaluation_run_id` returns `409`; promoting after concurrent service modification returns `409`; valid promotion creates `vN+1`, resolves linked evidence items, and subsequent Teacher-disabled replay classifies the new choice as `TRUSTED`.
- **Effort / Risk / Blast Radius:** Medium (M) | Medium risk | Unlocks `OC-009`.

---

### OC-BG-014 — Unify the 4 Fractured Candidate Pipelines & Synchronize `unknown_triage` with `evidence_items`
- **Workstream & Subsystem:** WS-08 (`evolution.py`, `project_evolution.py`, `candidates.py`, `unknown_pool.py`, `evidence.py`, `api/{candidates,evolution,unknowns,evidence}.py`)
- **Priority:** `P1` | **Current Status:** Duplicated / Split-Brain
- **Concrete Problem & Evidence:**
  - Candidates discovered from clusters via `POST /api/v1/projects/{id}/clusters/{cid}/discover` (`api/candidates.py:63-143`) are written via raw SQL into `cluster_candidates` (`0016`) using a hardcoded `MockClusterDiscoveryProvider` (`api/candidates.py:30`) and never appear in `/api/v1/projects/{id}/candidates` (`project_choice_candidates`, `0007`).
  - Triaging an unknown in `/unknowns/{run_id}/triage` (`unknown_triage` table, `0014`) does not update `evidence_items` (`0008`), and vice versa.
  - `ProjectEvolutionService.propose` (`project_evolution.py:118`) rejects `READY_FOR_EVOLUTION` evidence items if they originated from `LOW_TRUST` or `HUMAN_CORRECTION` runs (`run.selected_choice != "UNKNOWN"`).
- **Detailed Implementation Approach:**
  1. Expand `ChoiceProposal` / `ProposalKind` (`project_evolution.py:22-44`) to include `ALIAS`, `OUT_OF_DOMAIN`, and `SCHEMA_ISSUE`, plus `aliases: tuple[str, ...] = ()`, `cluster_id: str | None = None`, and `evidence_ids: tuple[str, ...] = ()`.
  2. Route `POST /api/v1/projects/{id}/clusters/{cid}/discover` through `ProjectEvolutionService.propose_from_cluster` using the configured `ChoiceTeacher` (`glm` or `mock`) and persist into the unified candidate store.
  3. Relax `project_evolution.py:118` to accept runs linked to `READY_FOR_EVOLUTION` evidence regardless of whether the trigger was `SEMANTIC_UNKNOWN`, `LOW_TRUST`, or `HUMAN_CORRECTION`.
  4. Synchronize `UnknownTriageStore.set_triage` with `EvidenceService.triage_evidence` / `dismiss_evidence`.
- **Dependencies:** `OC-BG-002`, `OC-BG-008`.
- **Verification & Acceptance Criteria:** Cluster discovery uses the configured provider and creates candidates visible and promotable via `/api/v1/projects/{id}/candidates`; triaging in `/unknowns` updates `/evidence`.
- **Effort / Risk / Blast Radius:** Large (L) | Medium risk | Unifies Portal Phase 7–10 with Core Evolution.

---

### OC-BG-015 through OC-BG-038 — Concise Executable Specifications

#### OC-BG-015 (P1, WS-03): Multi-Node `PolicyGraph` Execution in `DecisionExecutor`
- **Problem:** `DecisionExecutor.execute` (`decision_executor.py:38-50`) only executes `service.nodes[0]` and ignores `PolicyGraph` (`decision.py:130-330`).
- **Implementation:** Port the multi-hop traversal loop (`max_steps=8`, `visited_nodes` cycle detection, `TransitionTargetKind` dispatch for `NODE`, `CAPABILITY`, `MACRO`, `HUMAN`, `TERMINAL`) from `scripts/jev_contract/runtime.py:89-192` into `DecisionExecutor.execute_graph` in `packages/core/openclass_core/decision_executor.py`. Persist `steps: list[DecisionStepTrace]` in `DecisionRun.payload`.
- **Verification:** Multi-node routing test (root router → specialist node → terminal choice) via `POST /api/v1/projects/{id}/decision-services/{sid}/runs`.

#### OC-BG-016 (P1, WS-04): `StateCompiler` & Metadata Context Propagation
- **Problem:** `DecisionExecutor` (`decision_executor.py:58-65`) drops `RawEvent.metadata`, and `DecisionNode` lacks state compilation.
- **Implementation:** Add `StateCompiler.compile(raw_event, prior_steps, schema)` in `packages/core/openclass_core/decision.py` enforcing `StateFieldSpec` types, missing-vs-false semantics, provenance tags, and a configurable max byte/token budget (`4096` chars per field). Pass compiled `state_facts` in `Observation.metadata` and serialize them into `JevDecisionProvider` and `LayaDecisionProvider` prompts.
- **Verification:** Unit & contract tests proving structured metadata facts change node precondition evaluation and model prompt context.

#### OC-BG-017 (P1, WS-05): Data-Driven `SupervisionPolicy` & `OperatingProfile` Enforcement
- **Problem:** `DecisionExecutor._supervise` (`decision_executor.py:169-197`) hardcodes `if provider_name == "laya"` and `if provider_name == "jev"`, ignoring `SupervisionPolicy.max_unknown_probability` and `DecisionNode.risk_level`.
- **Implementation:** Replace hardcoded provider name checks in `decision_executor.py:169-197` with `evaluate_supervision(policy, profile, probabilities, unknown_prob, risk_level)` from `decision.py:254-329`, parameterized by each provider's `OperatingProfile` (`calibration_status`, `temperature`, `min_margin`, `max_unknown_probability`, `max_choices`).
- **Verification:** Unit tests verifying that `HIGH` risk nodes require higher margin or human review and `max_unknown_probability` triggers `UNKNOWN`/`REVIEW` across all providers.

#### OC-BG-018 (P1, WS-06): `AutomationLoop` Macro Expansion, 5-Gate Applicability & Independent Verifiers
- **Problem:** `AutomationDecision.action` (`automation.py:54`) is typed as `AutomationActionName` enum, rejecting macro names; `AutomationLoop.step()` (`L120-138`) never expands `macro.steps`; `state_patch` (`L132`) injects undeclared fields.
- **Implementation:** Change `AutomationDecision.action` to `str` validated against `set(AutomationActionName) | set(policy.macros.keys())`; expand `macro.steps` sequentially in `AutomationLoop.step()` with per-step precondition/postcondition checks; port the 5-gate applicability checker (`scripts/automation_applicability.py`) and independent postcondition verifier protocol into `packages/core/openclass_core/automation.py`.
- **Verification:** Port `test_automation_applicability.py` and `test_automation_proof2b_cycle2.py` to import directly from `openclass_core.automation` instead of `scripts/`.

#### OC-BG-019 (P1, WS-06): Harden `SafeSandboxExecutor` Subprocess & Network Isolation
- **Problem:** `SafeSandboxExecutor` (`packages/server/openclass_server/automation_executor.py:21-105`) runs `subprocess.run` with no timeout, unbounded output, leaky env filter (`if not k.endswith("API_KEY")`), unrestricted port probing, and 4 unimplemented enum actions.
- **Implementation:** Enforce `timeout=30.0` on `subprocess.run`, cap `stdout`/`stderr` at `64 KB`, replace env blacklist with a strict allowlist (`PATH`, `SYSTEMROOT`, `TMP`, `TEMP`, `HOME`, `PYTHONPATH` + explicit `state.env_vars`), restrict `INSPECT_PORT` / `CHOOSE_AVAILABLE_TEST_PORT` to unprivileged ephemeral range `1024..65535`, and implement `SET_ENVIRONMENT`, `RERUN_PREVIOUS`, `DONE`, and `BLOCKED`.
- **Verification:** Unit tests in `tests/unit/test_automation_executor.py` verifying timeout termination, env-var isolation (`OPENCLASS_DATABASE_URL` not leaked), and all 8 action handlers.

#### OC-BG-020 (P1, WS-07): Real LLM `SupervisorProvider` & Sampled/Triggered Supervision (`OC-018`, `OC-020`)
- **Problem:** `provider_config.py:54-56` only wires `MockSupervisorProvider`.
- **Implementation:** Implement `OpenAICompatibleSupervisorProvider` in `providers/glm/openclass_provider_glm/supervisor.py` (supporting OpenAI/GLM/Ollama endpoints), register `"glm"`, `"openai-compatible"`, and `"ollama"` in `provider_config.py:54`, and add configurable post-run supervision triggers (`review_on_low_margin`, `sample_rate`) in `ProjectService.record_decision_run`.
- **Verification:** Contract tests in `tests/contract/test_supervisor_provider.py` + integration test in `test_reviews.py`.

#### OC-BG-021 (P1, WS-07): Promote Teacher Protocol v1.1 & 10-Layer `apply_candidate` to Core/Server
- **Problem:** `evolution.py:30-248` defines `FailureLayer`, `TeacherProposal`, and `CandidateEnvelope`, but `apply_candidate` and the v1.1 Teacher prompt builder only exist in `scripts/jev_contract/teacher.py:246-329`.
- **Implementation:** Move `apply_candidate` and deterministic schema/guard compilation from `scripts/jev_contract/teacher.py` into `packages/core/openclass_core/evolution.py`, and upgrade `OpenAICompatibleChoiceTeacher` (`providers/glm/openclass_provider_glm/project_teacher.py`) to support `TeacherProposal` across `DECISION_SPACE`, `PROCEDURE`, and `STATE_REPRESENTATION`.
- **Verification:** Unit & integration tests verifying `ADD_CHOICE`, `REPLACE_PROCEDURE`, and `ADD_STATE_FEATURE` candidate application and hash determinism.

#### OC-BG-022 (P1, WS-08): Pluggable Semantic Embeddings, Embedding Cache & `pgvector` Indexing
- **Problem:** `api/clusters.py:35` hardcodes `HashLexicalEmbedder`, recomputes embeddings on every request, and `SentenceTransformerEmbedder.embed` (`embeddings_local.py:63-65`) blocks the async event loop.
- **Implementation:** Wrap `self._model.encode` in `await asyncio.to_thread(...)` in `SentenceTransformerEmbedder`, add `OpenAICompatibleEmbedder`, wire embedder selection in `provider_config.py`, add `ClusterStore.get_embeddings(run_ids, model_version)` cache lookup before calling `embedder.embed`, and add `pgvector` cosine distance query path when running on PostgreSQL.
- **Verification:** Integration tests verifying cache hit (0 redundant `embed()` calls on second cluster run) and semantic synonym clustering.

#### OC-BG-023 (P1, WS-11): Authenticate Control-Plane-to-Engine Traffic & Tenant Isolation
- **Problem:** `packages/server` is completely unauthenticated (`security.py`) and `services/control-plane/src/engine.ts:274-301` sends no auth or workspace headers.
- **Implementation:** Add `InternalAuthMiddleware` in `packages/server/openclass_server/security.py` verifying `X-OpenClass-Internal-Token` (or API key bearer token) via `hmac.compare_digest` and extracting `X-OpenClass-Workspace-Id` and `X-OpenClass-Actor` headers; forward those headers in `services/control-plane/src/engine.ts`; add `workspace_id` column to `projects` (`0019`) and scope all project queries by `workspace_id` when multi-tenant mode is enabled.
- **Verification:** Integration tests verifying unauthenticated requests to `:7331` with `OPENCLASS_AUTH_REQUIRED=true` return `401` and cross-workspace project access returns `404`.

#### OC-BG-024 (P1, WS-09 / WS-10): Fix Webhook Content-Hash `409` Bug & Idempotency Store Flaws
- **Problem:** `SQLIntegrationRepository.ingest_webhook` (`integration_repository.py:53-94`) crashes with `409 Conflict` when two different `event_key` webhooks carry identical `content`; `IdempotencyStore` (`idempotency.py:24-61`, `idempotency.service.ts:16-33`) omits request-hash validation, skips storing when `deduped=True` (`api/projects.py:130`), and never updates expired keys (`ON CONFLICT DO NOTHING`).
- **Implementation:** In `ingest_webhook` (`integration_repository.py:72`), check for an existing `RawEventRow` by `(project_id, content_hash)` and link the new `WebhookReceiptRow` to it; add `request_hash` verification to `IdempotencyStore` (raising `409` on payload mismatch); replace `ON CONFLICT DO NOTHING` with `ON CONFLICT (project_id, key) DO UPDATE ... WHERE idempotency_keys.expires_at < EXCLUDED.created_at`; remove `and not deduped` at `api/projects.py:130`.
- **Verification:** Integration tests in `test_webhooks_api.py` and `test_idempotency_and_limits.py`.

#### OC-BG-025 (P1, WS-09): Atomic Unit-of-Work Transactions & `SELECT ... FOR UPDATE`
- **Problem:** Multi-step mutations in `ProjectService` (`record_decision_run`, `submit_run_feedback`, `create_evidence_case`, `ingest_events_batch`) commit across separate DB sessions, and `evidence_items.decision_run_id` (`tables.py:226`) lacks a `UNIQUE` constraint.
- **Implementation:** Add a transactional session context manager to `SQLProjectRepository` and `SQLRepository`, use `.with_for_update()` on mutable rows (`CandidateRow`, `ProjectRow`, `DecisionServiceRow`, `ProjectChoiceCandidateRow`), validate `stored.payload` inside `approve_candidate` (`repository.py:311-314`), add `UniqueConstraint("decision_run_id")` on `evidence_items`, and use `create_raw_events` bulk insert in `ingest_events_batch` (`projects.py:552-585`).
- **Verification:** Concurrency integration test submitting parallel feedback and candidate approvals.

#### OC-BG-026 (P1, WS-09): Reconcile Engine Alembic vs. Control-Plane SQL Migrations & Slug Constraints
- **Problem:** `migrations/env.py:16` has no `include_name` filter for `control_*` tables; `control_projects.slug` is globally unique (`0002_projects.sql:6`) while checked per-workspace (`project.service.ts:253`); `classifiers.slug` is globally unique (`tables.py:33`) while scoped per-project in `control_classifiers` (`0002_projects.sql:18`).
- **Implementation:** Add `include_name` filter in `migrations/env.py` ignoring `control_*` tables; add a migration runner script for `services/control-plane/migrations/`; change `control_projects` unique constraint to `UNIQUE (workspace_id, slug)`; add append-only triggers to `observations`, `classification_runs`, `unknown_events`, `decision_runs`, `run_feedback`, and `control_audit_events` (changing `ON DELETE CASCADE` to `ON DELETE RESTRICT`).
- **Verification:** `alembic check` passes on a database containing both engine and `control_*` tables; two workspaces can create projects with the same slug.

#### OC-BG-027 (P1, WS-13): Unify Dual Frontend Stack (`apps/portal` + `services/control-plane` vs `apps/web`)
- **Problem:** `apps/portal/src/api.ts:10-25` uses raw `fetch()` (violating `AGENTS.md`); projects created in `apps/web`/SDK/CLI do not exist in `control_projects`; `apps/portal` lacks Decision Services, Evidence Cases, Integrations, and Analytics UIs.
- **Implementation:** Refactor `apps/portal/src/api.ts` to use `@openclass/sdk`; synchronize project registry between `control-plane` and `server`; port Decision Services, Evidence/Diagnosis, Replay Evaluation, Integrations, and Analytics views so both workspace entry points share full feature parity.
- **Verification:** E2E test creating a project via SDK/CLI and inspecting it in both `apps/portal` and `apps/web`.

#### OC-BG-028 (P1, WS-12): 100% API, SDK & CLI Parity Across All 50 Endpoints
- **Problem:** Python SDK misses 15 server routes; TypeScript SDK misses 14 routes; CLI covers only 16 of 50 routes.
- **Implementation:** Add SDK methods and CLI subcommands (`openclass service *`, `openclass evidence *`, `openclass candidate *`, `openclass cluster *`, `openclass integration *`) for all remaining server endpoints.
- **Verification:** Contract tests in `tests/contract/test_python_sdk.py` and `packages/sdk-typescript/src/index.test.ts` covering every FastAPI route.

#### OC-BG-029 (P1, WS-14): Fix Provider Error Rollup, Model Usage Key & Structured Correlation Logging
- **Problem:** `api/decisions.py:129` passes literal `"provider"`, `""`, `0.0` to `record_provider_error`; `uq_provider_usage_day` (`tables.py:300`) omits `model`; no `X-Correlation-ID` middleware or structured logger exists.
- **Implementation:** Pass actual `provider_name`, `model_name`, and elapsed `latency_ms` in `api/decisions.py:129` and emit `decision.provider_failed` audit event; include `model` in `uq_provider_usage_day`; add `X-Correlation-ID` middleware in `main.py` and forward header in `services/control-plane/src/engine.ts`.
- **Verification:** Integration test verifying `ProviderError` increments `errors` on the actual provider/model row and echoes `X-Correlation-ID`.

#### OC-BG-030 (P1, WS-09): Replace Silent 200-Row Truncation Caps & Unbounded Table Scans
- **Problem:** `api/unknowns.py:43`, `api/clusters.py:38`, and `discovery.py:28` silently slice `limit=200`; `analytics_runs` (`project_repository.py:416-421`) and `summary` audit count (`projects.py:506`) load entire tables into memory.
- **Implementation:** Add SQL `WHERE selected_choice = 'UNKNOWN'` filtering and pagination to `list_decision_runs`, lookup `unknown_events` directly by `id IN (...)` in `discovery.py:28`, and replace in-memory `analytics_runs` and `len(audit_events)` with SQL `COUNT(*)` / `GROUP BY` queries.
- **Verification:** Integration test with `> 250` runs verifying zero truncation and constant-memory SQL aggregation.

#### OC-BG-031 (P2, WS-11): Wire Redaction Settings, Recursive `redact_mapping`, Rate-Limiter Method Checks & Prompt-Injection Guards
- **Problem:** `Settings.redaction_enabled` & `redaction_blocklist` (`settings.py:19-20`) are unwired; `redact_mapping` (`redaction.py:45-48`) misses dicts inside lists; `RateLimiter.route_class` (`rate_limit.py:44-49`) throttles `GET /events` and `GET /runs`, misses `POST .../webhook`, and leaks memory in `_buckets`; `GLMDiscoveryProvider` and `OpenAICompatibleDiagnosisProvider` lack untrusted-data prompt boundaries.
- **Implementation:** Wire `config.redaction_enabled` and `config.redaction_blocklist` into redaction helpers; recurse into dicts/lists inside lists in `redact_mapping`; check `request.method == "POST"` and `/webhook` in `RateLimiter.route_class` with TTL bucket eviction; add untrusted-data system instructions and per-field truncation (`4000` chars) to `GLMDiscoveryProvider` and `OpenAICompatibleDiagnosisProvider`.
- **Verification:** Unit tests in `test_redaction.py`, `test_rate_limit.py`, and provider contract tests.

#### OC-BG-032 (P2, WS-10): Transactional Outbox, Vendor Webhook HMAC Normalizers & MCP/Database Probes
- **Problem:** `HTTPIntegrationProbe.check` (`integration_adapters.py:78-80`) stubs `MCP`, `DATABASE`, and `PROVIDER`; no vendor HMAC signature verification (Zendesk, Intercom, Freshdesk) or outbound action outbox exists.
- **Implementation:** Add `outbound_deliveries` outbox table with retry backoff, vendor HMAC-SHA256 webhook adapters (`phase-16`), and MCP JSON-RPC `initialize`/`tools/list` probe + SQLAlchemy `SELECT 1` database probe.
- **Verification:** Integration tests in `test_integrations_api.py` and `test_webhooks_api.py`.

#### OC-BG-033 (P2, WS-14): Real PostgreSQL Control-Plane Tests, Portal Component Tests & Live-Backend Playwright Suite
- **Problem:** `services/control-plane/src/*.spec.ts` mocks `pg.Pool` via string prefixes; `apps/portal/src/portal.test.tsx` only tests the login gate; `tests/web/*.spec.ts` mocks 100% of `/api/v1/*` routes.
- **Implementation:** Add PostgreSQL integration test suite for `services/control-plane` applying `migrations/0001..0004.sql`; expand `apps/portal/src/portal.test.tsx` to cover authenticated views; add a live-backend Playwright project in `playwright.config.ts`.
- **Verification:** CI runs both route-mocked unit UI tests and live-backend E2E smoke tests.

#### OC-BG-034 (P2, WS-14): Self-Contained Benchmarks, Complete Docker/Compose Stack & Release Parity
- **Problem:** `benchmarks/jev-contract/v1/knowledge.json` references gitignored `build/` paths; `Dockerfile:21-26` omits `COPY benchmarks examples`; `pyproject.toml:42` omits `openclass_provider_glm`; `scripts/release.py:14-19` omits `services/control-plane/package.json`.
- **Implementation:** Commit frozen benchmark summary artifacts under `benchmarks/jev-contract/v1/frozen-evidence/`, add `COPY benchmarks benchmarks` and `COPY examples examples` + non-root `USER` to `Dockerfile`, add `openclass_provider_glm` to `pyproject.toml:42`, and update `scripts/release.py`.
- **Verification:** `uv run python -m scripts.jev_contract.audit`, `docker compose --profile test run test`, and `uv run mypy` pass on a clean clone.

#### OC-BG-035 (P2, WS-03): Durable Multi-Step Run Checkpoints, Human Step Approval & Resume API
- **Problem:** Multi-step graph/automation runs cannot pause for human approval or resume after process restart.
- **Implementation:** Add `status: Literal["running", "waiting_human", "paused", "completed", "failed", "cancelled"]` and `checkpoint_state` to `DecisionRun`, plus `POST /api/v1/projects/{id}/runs/{run_id}/resume` and `/cancel`.
- **Verification:** Integration test pausing a graph run at a `HUMAN` transition node and resuming it with operator approval.

#### OC-BG-036 (P2, WS-08): Post-Promotion Drift Monitoring & Automated Rollback Triggers (Phase 13)
- **Problem:** No drift monitoring or post-promotion regression alerting exists after `vN+1` activation.
- **Implementation:** Add sliding-window unknown-rate and low-margin spike detection in `analytics.py` and `GET /api/v1/projects/{id}/decision-services/{sid}/drift`, with optional auto-rollback trigger to parent version `vN`.
- **Verification:** Unit & integration tests simulating a post-promotion unknown-rate spike.

#### OC-BG-037 (P3, WS-05): Consolidate or Implement `providers/ollama` & `providers/openai-compatible`
- **Problem:** `providers/ollama` and `providers/openai-compatible` contain only `README.md` while OpenAI-compatible adapters live inside `providers/glm`.
- **Implementation:** Extract generic OpenAI-compatible and Ollama provider classes into `providers/openai-compatible` and `providers/ollama` (or re-export from `openclass_provider_glm` with proper `pyproject.toml` packages).
- **Verification:** `uv build --all-packages` and contract tests for `ollama` and `openai-compatible`.

#### OC-BG-038 (P3, WS-12): Implement `packages/tui` Terminal Inspector (`OC-013`)
- **Problem:** `packages/tui` contains only `README.md`.
- **Implementation:** Build a Textual/Rich terminal inspector in `packages/tui` using `openclass-sdk` to browse projects, runs, unknown pools, and candidates.
- **Verification:** Unit smoke test rendering TUI views against mock SDK client.
