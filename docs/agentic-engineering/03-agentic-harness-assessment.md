# 03 — Deep Assessment: Agentic Engineering & The OpenClass Agentic Harness

> **Owner:** Abdelhamid Khaled (`AbdelhamidKhald`)  
> **Scope:** Comprehensive technical evaluation of (I) **Agentic Engineering** (how OpenClass is built, tested, and verified) and (II) **OpenClass's Product Agentic Harness** across all 9 architectural dimensions (`6A`–`6I`).

---

## Part I: Agentic Engineering Assessment (How OpenClass Is Developed & Verified)

Agentic Engineering concerns the methodology, repository structure, verification harnesses, and guardrails that allow human and AI engineers to evolve OpenClass without regressions or architectural drift.

### 1.1 Strengths of the Current Engineering Harness

1. **Strict Inward Dependency Enforcement (`tests/unit/test_boundaries.py`)**:
   - AST-level unit tests verify that `openclass_core` never imports `openclass_server`, `openclass_sdk`, `openclass_cli`, or `providers/*`, and that `providers/*` never import `openclass_server`.
2. **Explicit Contract & Adversarial Response Testing (`tests/contract/`)**:
   - Provider adapters (`jev`, `laya`, `glm`, `mock`) are tested against malformed JSON, HTTP 5xx, empty choices, unnormalized probabilities, and secret-redaction checks using deterministic `httpx.MockTransport` harnesses.
3. **Research Proof Discipline (`scripts/jev_contract/`, `scripts/automation_*.py`, `benchmarks/`)**:
   - Complex hypotheses (Jev 2–32 choice scaling, temperature/margin calibration, 10-layer failure attribution, multi-step port-conflict recovery macros, and negative-transfer gate rejection) were empirically proven with hash-verified artifacts before attempting server integration.

### 1.2 Critical Weaknesses in the Current Engineering Harness

1. **Shortcut & Mocked Tests Masking Real Cross-Boundary Breakages**:
   - **SDK/UI Mock Drift**: `packages/sdk-typescript/src/index.test.ts:163-165` and `tests/web/data.spec.ts:98-110` mock `POST /events/batch` returning a bare array `[{...}]` (`200`/`201`), whereas the real FastAPI endpoint (`api/projects.py:137-198`) returns `207 Multi-Status` with `{"items": [...]}`. Because Playwright (`tests/web/*.spec.ts`) stubs 100% of `/api/v1/*` calls with `page.route(...)` and never boots `openclass_server`, the broken batch upload in `apps/web/app/projects/[id]/data/page.tsx:168-173` went undetected.
   - **Fake SQL Pool in Control-Plane Tests**: All 10 NestJS spec files (`services/control-plane/src/*.spec.ts`) match SQL queries using `text.startsWith("INSERT INTO ...")` against an in-memory mock and never apply `services/control-plane/migrations/0001..0004.sql` to PostgreSQL. And `ingestion.service.spec.ts` called `IngestionService` directly with a hand-crafted `caller` object, missing that `IngestionController.callerOf(request)` (`ingestion.controller.ts:26-32`) drops `keyProjectId` and breaks every API key request over HTTP!
   - **Audit Deserialization Blind Spot**: `tests/integration/test_unknown_workspace.py` tests `/unknowns/{id}/triage` and `/unknowns/stats`, but never calls `/audit` or `/summary` afterward—missing that `UnknownTriageStore.append_audit` (`unknown_triage.py:85-102`) corrupts the `audit_events` table and crashes both endpoints with HTTP 500.
2. **Research-to-Production Chasm (`scripts/` vs `packages/core` & `packages/server`)**:
   - 9 of 27 unit test files in `tests/unit/` prepend `scripts/` to `sys.path` and test standalone research scripts (`scripts/jev_contract/*`, `scripts/decision_graph*.py`, `scripts/automation_*.py`) while the production classes in `packages/core/openclass_core/{decision,evolution,automation}.py` remain either unintegrated data models or simplified stubs with regressions.
3. **CI Baseline Repaired on `oc-034-ci-baseline` (`c6545bf`), While Local Windows Caveats Remain**:
   - `oc-034-ci-baseline` (`6f61ce0`, `4bd07f9`, `dbb0ab8`, `8fc3507`) repaired `.github/workflows/ci.yml` and `Makefile` to use `pnpm`, set `OPENCLASS_DECISION_PROVIDER=mock` in CI/Compose, added `providers/glm/LICENSE`, and updated `test_raw_events_postgres.py:59` (`207`), achieving green CI run `37051177668` (`docs/implementation-phases/evidence/phase-0-baseline-and-oc-034.md`).
   - However, local Windows `pytest` runs still hit 2MB parametrized test IDs overflowing `PYTEST_CURRENT_TEST` (`test_jev_provider.py:86`, `test_supervisor_provider.py:72`), CRLF byte hashing (`test_automation_reuse.py:142` — no `.gitattributes`), Windows `SO_REUSEADDR` socket semantics (`test_automation_reuse.py:160`), and `Settings.decision_provider = "laya"` default (`test_reviews.py:96`).

### 1.3 Empirical Findings from the 60-Issue Live Application Challenge (`artifacts/application-proofs/scikit-learn-2026-10-02/REPORT.md`)

Running 60 real `scikit-learn` GitHub issues (15 `Bug`, 15 `Enhancement`, 15 `Documentation`, and 15 withheld `Build / CI` expected to route to `UNKNOWN`) through the Portal/Engine stack against live hosted models (`openai/gpt-4.1-mini` and `google/gemini-2.5-flash`) independently reproduced and confirmed our architectural audit findings:

| Metric / Dimension             |      `openai/gpt-4.1-mini`       |    `google/gemini-2.5-flash`    | Architectural Root Cause Confirmed                                                                                                                   |
| :----------------------------- | :------------------------------: | :-----------------------------: | :--------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Completed Source Cases**     |       `56 / 60` (`93.3%`)        |       `38 / 60` (`63.3%`)       | Gateway HTTP `429` rate limits were swallowed by `main.py:123-125` as generic HTTP `502` (`REPORT.md` Finding #2).                                   |
| **Known Accuracy (Completed)** |       `39 / 45` (`86.7%`)        |       `29 / 35` (`82.9%`)       | `DecisionExecutor` drops `service.instructions` before building `ChoiceRequest` (`REPORT.md` Finding #5; `OC-BG-005`).                               |
| **Held-Out `UNKNOWN` Recall**  | `4 / 11` (`36.4%`; `4/15` total) | `2 / 3` (`66.7%`; `2/15` total) | Uncalibrated LLM self-reported probabilities over-predict `BUG`/`ENHANCEMENT` on withheld `Build / CI` issues (`REPORT.md` Finding #4; `OC-BG-017`). |
| **Errors Labeled `TRUSTED`**   |     **`12 / 51` (`23.5%`)**      |     **`7 / 36` (`19.4%`)**      | Generic margin rule (`margin >= 0.20`) marks uncalibrated LLM misclassifications as `TRUSTED` (`REPORT.md` Finding #4; `OC-BG-017`).                 |

All **11 challenge findings** in `artifacts/application-proofs/scikit-learn-2026-10-02/REPORT.md:55-68` map directly to our backlog:

1. **Hardcoded Simulated Adapters in Phase 9/10 (`api/clusters.py:35`, `api/candidates.py:46`)**: Required the unmerged `provider-wiring.patch` (`GatewayDecisionProvider`, `GatewayEmbedder`, `GatewayClusterDiscovery`) to run live inference (`OC-BG-014`, `OC-BG-022`).
2. **Gateway HTTP `429` Swallowed as Generic HTTP `502`**: `main.py:123-125` maps all `ProviderError`s to `502`, losing rate-limit retry semantics and error identity (`OC-BG-029`).
3. **HTTP `413` on 60-Item Real Batch Ingestion**: Full 60-issue payload exceeded NestJS/Express default body byte limits despite passing item-count limits (`<= 500`), requiring 8-item batches (`OC-BG-027`).
4. **Uncalibrated LLM Self-Assessment Receiving `TRUSTED` Status (`23.5%` GPT / `19.4%` Gemini trusted error rate)**: Confirms `DecisionExecutor._supervise` (`decision_executor.py:169-197`) needs calibrated `OperatingProfile` and `SupervisionPolicy` gating (`OC-BG-017`).
5. **Service Instructions Dropped Before `ChoiceRequest`**: Confirms `decision_executor.py:58-85` omits `service.instructions` (`OC-BG-005`).
6. **Latest-200 Truncation (`limit=200`) on Unknowns & Clustering**: Confirms `api/unknowns.py:43` and `api/clusters.py:38` silently truncate runs (`OC-BG-030`).
7. **Provider-Config Cards Stored as References Only, Not Enforced Bindings**: `ProjectProviderConfigRow` (`0013`) is never read by `DecisionExecutor`, and embedding/discovery/Teacher costs are omitted from Portal cost rollups (`OC-BG-009`, `OC-BG-029`).
8. **Jev Hosted Availability (`HTTP 403 no_providers_available`)**: Confirms `JevDecisionProvider` requires local/dedicated OpenAI-compatible serving or clean fallback governance.
9. **Core `/audit` Failing After Clustering (`HTTP 400/500`)**: Empirically confirms `UnknownTriageStore.append_audit` (`unknown_triage.py:86-110`) writes payloads incompatible with `ProjectAuditEvent` (`OC-BG-002`).
10. **Destructive Re-Clustering Cascade (`cluster_store.py:50-53`)**: Confirms `DELETE FROM unknown_clusters` cascades to `cluster_candidates` and `candidate_evidence` (`OC-BG-008`).
11. **Evaluation & Activation Safety Blocks**: Track 1/2 remain blocked at `409`, while Track 3 (`feat/portal-phase-17`) hardcodes `MockDecisionProvider` in `api/evaluations.py:306` (`OC-BG-011`..`013`).

---

## Part II: Deep Assessment of the Product's Agentic Harness (Sections 6A–6I)

### 6A. Orchestration and Execution Lifecycle

```mermaid
stateDiagram-v2
  direction LR
  [*] --> Observe: RawEvent / Observation
  Observe --> CompileState: StateCompiler (Typed Facts + Provenance)
  CompileState --> Preconditions: Evaluate Node Predicates
  Preconditions --> FastPathChoice: Predicates Pass
  Preconditions --> BlockedPrecondition: Missing / False Fact
  FastPathChoice --> SupervisionGate: DecisionProvider Distribution
  SupervisionGate --> TransitionDispatch: TRUSTED (Known Choice)
  SupervisionGate --> UnknownSink: UNKNOWN Selected
  SupervisionGate --> ReviewQueue: REVIEW (Low Margin / High Risk)
  TransitionDispatch -->Observe: Transition -> Next DecisionNode (step < max_steps)
  TransitionDispatch --> ExecuteCapability: Transition -> Capability / Macro
  ExecuteCapability --> VerifyPostconditions: Independent Verifier
  VerifyPostconditions --> Completed: Verified Pass
  VerifyPostconditions --> DiagnosisSink: Postcondition Failed
```

#### Current State & Concrete Evidence

- **Two Disconnected Runtime Loops**:
  1. `DecisionExecutor.execute` (`packages/core/openclass_core/decision_executor.py:25-198`): Production executor wired to `POST /api/v1/projects/{id}/decision-services/{sid}/runs` (`api/decisions.py:67-155`). It is strictly **single-node and synchronous**:
     - Always selects `node = service.nodes[0]` (`decision_executor.py:38-50`) unless an explicit `node_id` is passed, and performs **zero graph transitions**.
     - Generates ephemeral `uuid4()` identifiers for `OntologyClass.stable_class_id`, `OntologyVersion.id`, and `Observation.id` on every single invocation (`decision_executor.py:58-80`), destroying cross-run class lineage.
     - Drops `service.instructions` and `node.instructions` when building `ChoiceRequest(observation=..., ontology=...)` (`decision_executor.py:58-85`), even though `DecisionRun.instructions_snapshot` (`L164`) records `node.instructions` as if it were sent to the model.
  2. `PolicyGraph` (`packages/core/openclass_core/decision.py:130-330`) vs `scripts/jev_contract/runtime.py:89-192` and `scripts/decision_graph.py:196-339`:
     - `decision.py` defines `PolicyGraph`, `DecisionNode`, `Transition`, `TransitionTargetKind` (`NODE`, `CAPABILITY`, `MACRO`, `HUMAN`, `TERMINAL`), and `NodeConstraint` (`max_choices: int = 16`).
     - However, `decision.py` has **no graph executor class in `packages/core`**. The actual multi-node loop with cycle detection (`visited_nodes`), step budgets (`max_steps = 8`), and transition dispatch only exists in `scripts/jev_contract/runtime.py:101-192`.
- **Missing Lifecycle States**:
  - There is no durable run state machine (`PENDING`, `RUNNING`, `WAITING_APPROVAL`, `PAUSED`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`). Runs only exist in the database after synchronous completion (`decision_runs` table, `0006`).

#### Target Design

- Promote the multi-hop graph execution loop from `scripts/jev_contract/runtime.py:101-192` into `DecisionExecutor` in `packages/core/openclass_core/decision_executor.py`, unified over versioned `PolicyGraph` / `DecisionServiceVersion` snapshots.
- Persist a step-by-step `DecisionStepTrace` array (`step_index`, `node_id`, `compiled_state_hash`, `probabilities`, `selected_choice`, `margin`, `supervision_outcome`, `transition_target`, `latency_ms`) and support durable `WAITING_HUMAN` / `PAUSED` checkpoints with resume tokens.

---

### 6B. State Compilation, Context, and Memory

#### Current State & Concrete Evidence

- **Predicate Evaluation Bug in Core (`packages/core/openclass_core/decision.py:217-235`)**:
  - `evaluate_predicates` (`decision.py:226-227`) checks:
    ```python
    actual = state.facts.get(predicate.field)
    if actual != predicate.equals:
        return False
    ```
  - **Defect 1 (Missing vs `None`)**: If `predicate.field` is absent from `state.facts` and `predicate.equals` is `None`, `state.facts.get(field)` returns `None == None` (`True`), conflating an unprobed/missing fact with `None`.
  - **Defect 2 (`bool` vs `int` coercion in Python)**: In Python, `True == 1` and `False == 0` evaluate to `True`! Thus a predicate expecting `equals=1` matches `actual=True`.
  - Ironically, `scripts/jev_contract/runtime.py:90-98` fixed both bugs (`if pred.field not in state.facts: return False` and `if isinstance(actual, bool) != isinstance(pred.equals, bool): return False`), but the fix was never ported to `packages/core/openclass_core/decision.py`!
- **Metadata & State Dropped at Runtime (`decision_executor.py:58-65`)**:
  - `RawEvent` (`projects.py:132-146`) stores structured `metadata: dict[str, Any]`, and `POST /runs` (`api/decisions.py:72`) accepts `metadata`. Yet `DecisionExecutor.execute` (`decision_executor.py:58-65`) only passes `content` into `Observation` and providers (`providers/jev/__init__.py:102`, `providers/laya/__init__.py:139`) only read `request.observation.content`, ignoring `observation.metadata` completely.
- **Five-Plane Memory Separation**:
  - Currently, only transient single-step input (`input_snapshot`), raw runs (`decision_runs`), and evidence items (`evidence_items`) are separated. There is no `StateCompiler` service in `packages/core` that compiles raw events + prior node outputs + integration probes into a schema-validated `StateSnapshot` with per-fact provenance (`source`, `observed_at`, `verified: bool`) and token/byte budget enforcement before provider invocation.

#### Target Design

- Fix `evaluate_predicates` in `packages/core/openclass_core/decision.py:217-235` to enforce explicit key presence (`field in state.facts`) and strict type identity (`type(actual) is type(predicate.equals)`).
- Introduce `StateCompiler` in `packages/core/openclass_core/decision.py` that compiles `RawEvent.content`, `RawEvent.metadata`, and prior step outputs against `StateSchema`, enforces field byte/token caps, and serializes structured facts + node instructions into `ChoiceRequest`.

---

### 6C. Decision Execution and Provider Adapters

#### Current State & Concrete Evidence

- **Critical Tie-Breaking Bug Violating `UNKNOWN` Permanence (`packages/core/openclass_core/decision_executor.py:102-115`)**:
  - In `DecisionExecutor.execute`:
    ```python
    full_probs: dict[str, float] = {}
    for c in node.choices:
        full_probs[c.key] = max(0.0, float(raw_probs.get(c.key, 0.0)))
    full_probs[UNKNOWN_CHOICE_KEY] = max(0.0, float(response.unknown_probability))
    ...
    ranked = sorted(full_probs.items(), key=lambda kv: kv[1], reverse=True)
    selected_choice, top_prob = ranked[0]
    ```
  - Because Python's `timsort` is stable and `node.choices` are inserted into `full_probs` **before** `UNKNOWN_CHOICE_KEY`, whenever a known choice and `UNKNOWN` tie for highest probability (e.g., `0.50` vs `0.50`), `ranked[0]` selects the **known choice** instead of `UNKNOWN`!
  - By contrast, `select_choice` in `packages/core/openclass_core/decision.py:291-299` explicitly checks `if unknown_prob >= best_prob or margin < policy.min_margin: return UNKNOWN_CHOICE`.
- **Hardcoded Provider Supervision Logic (`decision_executor.py:169-197`)**:
  - `DecisionExecutor._supervise` branches on literal provider names (`if provider_name == "laya": return "REVIEW", ...` and `if provider_name == "jev": ...`), violating Core provider neutrality (`AGENTS.md`) and ignoring `SupervisionPolicy.max_unknown_probability` and `DecisionNode.risk_level`. In `scikit-learn-2026-10-02/REPORT.md`, this allowed uncalibrated LLM predictions to be marked `TRUSTED` on `23.5%` (GPT) and `19.4%` (Gemini) of reference disagreements.
- **Provider Provenance & Validation Defects**:
  - `JevDecisionProvider` (`providers/jev/openclass_provider_jev/__init__.py:102-120`) does not set `"real_inference": True` or `"execution_mode": "api"` in `provider_metadata`, so `DecisionExecutor` (`L142-146`) records every live Jev inference as `real_inference=False, execution_mode="daemon"`.
  - `LayaDecisionProvider._local_fallback_choice` (`providers/laya/openclass_provider_laya/__init__.py:251`) sets `"simulated": False` on deterministic regex fallback output, violating `AGENTS.md` (_"Keep mock output clearly marked as simulated"_).
  - `LayaDecisionProvider._normalize_response` (`__init__.py:280-287`) silently divides unnormalized numbers by their sum instead of rejecting invalid probability distributions (`abs(total - 1.0) > 0.05`).

---

### 6D. Capabilities, Tools, Macros, and Independent Verification

#### Current State & Concrete Evidence

- **`AutomationLoop` Is Broken on Macros (`packages/core/openclass_core/automation.py:51-58, 120-138`)**:
  - `AutomationDecision.action` (`automation.py:54`) is typed as `AutomationActionName` (a fixed 7-value `StrEnum`: `INSPECT_PORT`, `CHOOSE_AVAILABLE_TEST_PORT`, `SET_ENVIRONMENT`, `RUN_TESTS`, `RERUN_PREVIOUS`, `WRITE_REPORT`, `DONE`, `BLOCKED`).
  - In `AutomationLoop.step()` (`automation.py:120-128`), `policy.choose(state)` returns an `AutomationDecision` **before** `if decision.action in self.policy.macros:` (`L123`) is checked! Any macro name (such as `"recover_port_conflict"`) raises a Pydantic `ValidationError` on `AutomationDecision` construction.
  - Even if constructed, `AutomationLoop.step()` never iterates through `macro.steps`—it passes `decision.action` directly to `self.executor.execute(decision.action, state)` (`L129`).
  - `state = state.model_copy(update=result.state_patch)` (`L132`) bypasses Pydantic validation and injects undeclared attributes (`test_port`) onto `AutomationState`.
- **`SafeSandboxExecutor` Is Unwired and Unsafe (`packages/server/openclass_server/automation_executor.py:21-105`)**:
  - Never imported anywhere in `packages/server/openclass_server/api/*` or `main.py`.
  - Executes `subprocess.run([sys.executable, "-m", "pytest", ...])` (`L65-72`) with **no `timeout=` parameter** (an infinite loop hangs the worker forever) and buffers all `stdout`/`stderr` in memory.
  - Environment filtering (`{k: v for k, v in os.environ.items() if not k.endswith("API_KEY")}`, `L63`) leaks `OPENCLASS_DATABASE_URL`, `AWS_SECRET_ACCESS_KEY`, and webhook tokens to child processes.
  - `INSPECT_PORT` (`L35-48`) allows probing arbitrary localhost TCP ports (`1..65535`).
  - 4 of 8 enum actions (`SET_ENVIRONMENT`, `RERUN_PREVIOUS`, `DONE`, `BLOCKED`) fall through to `raise ValueError(f"Unsupported action: {action}")` (`L104`).
- **Phase 16 Support Routing Is Simulated Only (`packages/core/openclass_core/routing.py`, `api/support.py`)**:
  - `feat/portal-phase-17` added `0022_integration_routes.py` (`integration_routes`, `routing_outcomes`) and `api/support.py:141-255` (`POST /api/v1/projects/{id}/webhooks/{source}`). While `decide_routing` (`routing.py:39-55`) properly enforces `UNKNOWN → escalate`, `source_webhook` only writes a simulated row to `routing_outcomes` (`"simulated": True`) and performs zero external side-effects or independent postcondition verification (`OC-035`/`OC-036`).

---

### 6E. Teacher, Supervisor, and Failure Diagnosis

#### Current State & Concrete Evidence

- **Supervisor Only Wired to Mock (`packages/server/openclass_server/provider_config.py:56-58`)**:
  - `supervisor_provider` only returns `MockSupervisorProvider()`.
- **Startup Crash & Silent Fallback in `provider_config.py:87-129`**:
  - Setting `OPENCLASS_DISCOVERY_PROVIDER=openai-compatible` without `OPENCLASS_DISCOVERY_BASE_URL` or `OPENCLASS_GLM_BASE_URL` passes `base_url=""` to `OpenAICompatibleChoiceTeacher` (`provider_config.py:97-102`), which raises `ValueError("base_url must not be empty")` during `create_app()` startup.
  - Conversely, `project_diagnosis_provider` (`provider_config.py:120-121`) silently falls back to `MockDiagnosisProvider` when API keys are unset, masking misconfiguration.
- **Silent Enum Coercion & Error Leakage in `providers/glm`**:
  - `OpenAICompatibleDiagnosisProvider` (`providers/glm/openclass_provider_glm/diagnosis.py:86-93`) catches `ValueError` on invalid LLM category strings and silently substitutes `DiagnosisCategory.ANALYTICAL_GAP` instead of raising `ProviderError("malformed_response")`.
  - `OpenAICompatibleChoiceTeacher.propose` (`providers/glm/openclass_provider_glm/project_teacher.py:121-122`) catches `Exception as exc` and raises `ProviderError(f"Teacher request failed: {exc}")`, leaking raw `httpx` exception text (including internal URLs/headers).
- **Prompt Injection in Discovery & Diagnosis Prompts**:
  - `GLMDiscoveryProvider.discover` (`providers/glm/openclass_provider_glm/__init__.py:35-58`) and `OpenAICompatibleDiagnosisProvider.diagnose` (`diagnosis.py:53-77`) interpolate raw untrusted `observation` text and user-supplied `instructions` into LLM prompts without untrusted-data boundary instructions or character caps.

---

### 6F. Discovery, Clustering, and Controlled Evolution

#### Current State & Concrete Evidence

- **Four Fractured Candidate & Evolution Pipelines**:
  1. Legacy `DiscoveryService` (`discovery.py:15-94`, `candidates` table `0003`) — slices only the newest 200 unknowns (`L28`); `evaluate` and `approve` raise `ConflictError` (HTTP 409).
  2. Project `ProjectEvolutionService` (`project_evolution.py:101-257`, `project_choice_candidates` table `0007`) — supports only 3 `ProposalKind`s (`new_choice`, `existing_choice`, `insufficient_evidence`); rejects `READY_FOR_EVOLUTION` evidence from `LOW_TRUST` or `HUMAN_CORRECTION` runs (`L118`); `evaluate` and `promote` raise `ConflictError` (HTTP 409); `reject` has **no HTTP route** in `api/evolution.py`!
  3. Portal Cluster Discovery & Promotion (`candidates.py:1-186`, `promotion.py:1-68`, `api/{candidates,promotions}.py`, `0016_cluster_candidates.py`, `0017_candidate_reviews.py`, `0020_service_versions.py`) — `feat/portal-phase-17` added human candidate reviews (`0017`) and versioned promotion (`0020`), **but**:
     - `api/candidates.py:46` still hardcodes `MockClusterDiscoveryProvider()` (real `GatewayClusterDiscovery` remains in the unmerged `provider-wiring.patch`).
     - Re-running `POST /unknowns/cluster` (`cluster_store.py:50-53`) deletes `unknown_clusters`, **cascade-deleting all `cluster_candidates`, `candidate_evidence`, and `candidate_reviews`!**
     - **Alias Stripping Bug (`api/promotions.py:148-157`, `persistence/promotion_store.py:160`)**: Because `DecisionChoiceSpec` (`projects.py:157-168`) has `extra="forbid"` and lacks an `aliases` field, `promotions.py:148` and `promotion_store.py:160` explicitly strip `"aliases"` when writing promoted choices into `decision_services.payload`! Thus promoted aliases exist in `service_versions` snapshots, but are completely absent from live `DecisionExecutor` runs!
  4. Core Graph/Automation Evolution (`evolution.py:1-248`: `FailureLayer`, `TeacherProposal`, `CandidateEnvelope`) — zero tables, zero repositories, zero routes.

---

### 6G. Evaluation, Benchmarking, and Regression Protection

#### Current State & Concrete Evidence

- **Phase 12–13 Replay Engine Hardcodes `MockDecisionProvider` (`packages/server/openclass_server/api/evaluations.py:306, 433-452`)**:
  - `feat/portal-phase-17` added `evaluation.py` (`EvaluationSet`, `EvaluationExample`, `ExampleDraft` rejecting `source="prediction"`), `evaluation_metrics.py` (`accuracy`, `macro_f1`, `unknown_precision_recall`, `coverage`, `false_novelty_rate`, `Gates`), `0018_evaluation_sets.py`, and `0019_evaluation_runs.py`.
  - **Critical Flaw**: `run_evaluation` (`api/evaluations.py:306`) hardcodes `provider = MockDecisionProvider()` and sets `"simulated": True` (`L339`), and `_replay` (`L433-452`) calls `MockDecisionProvider.choice()` directly without `DecisionExecutor` or the service's configured provider! Meanwhile, `ProjectEvolutionService.evaluate` (`project_evolution.py:204-206`) and `DiscoveryService.evaluate` (`discovery.py:76-79`) still raise `ConflictError` (HTTP 409).
- **Unreproducible Benchmark Audit Script (`scripts/jev_contract/audit.py:27,76,80`)**:
  - `benchmarks/jev-contract/v1/knowledge.json` references evidence files inside gitignored `build/...` directories, causing `uv run python -m scripts.jev_contract.audit` to fail with `FileNotFoundError` on any clean clone.

---

### 6H. Reliability, Security, Governance, and Observability

#### Current State & Concrete Evidence

1. **`UnknownTriageStore.append_audit` Permanent 500 Crash Across 10 Event Types (`persistence/unknown_triage.py:86-110`)**:
   - Inserts `{"target": target, **(data or {})}` into `audit_events.payload` with **10 event types** (`unknown.triaged`, `unknown.transitioned`, `cluster.updated`, `candidate.created`, plus 6 new Phase 11–15 types: `candidate.updated`, `candidate.rejected`, `evaluation.dataset_created`, `evaluation.dataset_sealed`, `evaluation.completed`, `quality.alert`) missing from `ProjectAuditEvent.event_type` (`projects.py:78-101`). Subsequent calls to core `GET /api/v1/projects/{id}/audit` or `GET /api/v1/projects/{id}/summary` fail with `ValidationError` (`REPORT.md` Finding #9).
2. **Duplicate `support_router` Registration (`packages/server/openclass_server/main.py:200,237`) & `operations.py` Window Bug (`api/operations.py:92-96`)**:
   - `main.py` calls `app.include_router(support_router(...))` twice (at `L200` and `L237`), duplicating all 5 support integration routes in the FastAPI route table and OpenAPI schema.
   - `api/operations.py:92-96` computes `previous = await _measurements(str(project.id), two_weeks_ago)` where `_measurements` filters `created_at >= :since` with no upper bound (`created_at < :until`), corrupting `previous_unknown_rate` and `unknown_rate_delta`.
3. **Critical SSRF & Arbitrary Env-Var Exfiltration (`integration_adapters.py:25-37, 89-126`)**:
   - `EnvironmentSecrets.resolve` resolves any uppercase env var in `os.environ` (`OPENCLASS_JEV_API_KEY`, `AI_GATEWAY_API_KEY`, etc.), and `HTTPIntegrationProbe.check` sends it as `Authorization: Bearer <secret>` to any user-supplied `endpoint` URL without blocking private IPs, `169.254.169.254`, or external attacker domains.
4. **Unauthenticated Python Engine & Broken Control-Plane API Keys (`ingestion.controller.ts:26-32`)**:
   - `packages/server` has zero authentication on `/api/v1/*` (`phase-0-baseline-and-oc-034.md:38,49-51`).
   - In `services/control-plane/src/ingestion.controller.ts:26-32`, `callerOf(request)` drops `keyProjectId`, causing all `oc_...` API key calls to fail with `404 Workspace not found`.
   - `IngestionService.ingest` (`ingestion.service.ts:79,116`) only checks `"viewer"` role instead of `"operator"`.
5. **Rate Limiter, Idempotency & Webhook Dedup Bugs**:
   - `RateLimiter.route_class` (`rate_limit.py:44-49`) throttles `GET /events` and `GET /runs` against write budgets while leaving `POST .../webhook` unthrottled.
   - `SQLIntegrationRepository.ingest_webhook` (`integration_repository.py:53-94`) crashes with `409 Conflict` when two different `event_key` deliveries share identical message text.
   - `IdempotencyStore` (`idempotency.py:24-61`, `idempotency.service.ts:16-33`) never validates the incoming request body hash and never refreshes expired keys due to `ON CONFLICT DO NOTHING`.

---

### 6I. Product Surface and Developer Experience

#### Current State & Concrete Evidence

- **Dual Incompatible Frontends (`apps/web` vs `apps/portal` + `services/control-plane`)**:
  - `apps/web` (Next.js `:3000`) talks directly to `packages/server` (`:7331`) via `@openclass/sdk`. It implements Decision Services, Playground, Evidence Cases, Teacher Diagnosis, Candidate Proposals, Integrations, and Analytics.
  - `apps/portal` (Vite `:5173`) talks to `services/control-plane` (`:7400`) via raw `fetch()` (`apps/portal/src/api.ts:10-25`, violating `AGENTS.md`). It implements Keycloak Auth, Workspaces, API Keys, Unknown Triage, and Unknown Clusters, but lacks Decision Services, Evidence Cases, Integrations, and Analytics.
  - Projects created via `apps/web`, CLI, or SDKs do not exist in `control_projects` and are invisible in `apps/portal`.
- **Broken SDK & UI Routes**:
  - Both SDKs (`sdk-python/__init__.py:466`, `sdk-typescript/src/index.ts:800`) and `apps/web/app/projects/[id]/evolution/page.tsx:303` call `POST /api/v1/projects/{id}/evidence-cases/{cid}/evidence`, which **does not exist on the server** (404).
  - `transition_evidence` in both SDKs (`sdk-python/__init__.py:442`, `sdk-typescript/src/index.ts:773`) sends `{"status": ..., "note": ...}`, while the server (`api/schemas.py:240`) expects `{"status": ..., "rationale": ...}` (`note` is silently dropped).
  - `ingestBatch` in `@openclass/sdk` (`src/index.ts:573`) returns `{ items: [...] }` typed as `RawEvent[]`, breaking `apps/web/app/projects/[id]/data/page.tsx:173,229`.

---

## Part III: Post-Remediation Harness Reconciliation (`PRs #27`–`#55`)

Following the execution of `OC-BG-001` through `OC-BG-038` under their restored original definitions plus separate tickets `OC-BG-039` through `OC-BG-044` (`OC-040`–`OC-045`) and final verification in **PRs #51, #52, #53, #54, and #55**, the weaknesses identified in Parts I and II have been resolved (`25 VERIFIED`) or explicitly bounded as **`PARTIAL`** (`19 PARTIAL` under original ticket definitions) in [`04-executable-backlog.md`](./04-executable-backlog.md) and [`06-verification-matrix.md`](./06-verification-matrix.md):

1. **Engineering & CI Harness (`OC-BG-001`, `OC-BG-039`, `PR #29`, `PR #51`)**: Restored 100% green GitHub Actions CI (`python`, `web`, `compose`, `security`), fixed `Dockerfile` workspace `COPY` directives (`packages/tui`, `providers/openai-compatible`, `providers/ollama`), widened PostgreSQL `alembic_version.version_num` to `VARCHAR(128)`, deduplicated `support_router`, and resolved all 18 offline Python test failures via ambient `.env` isolation (`585+ passed, 0 failed`).
2. **Orchestration, Durable Checkpoints & Atomic CAS Claiming (`6A`, `OC-BG-015`, `OC-BG-035`, `OC-BG-044`, `PR #42`, `PR #52`, `PR #55`)**: Implemented durable multi-node execution checkpoints (`0026_decision_run_checkpoints.py`), atomic compare-and-swap checkpoint claiming (`0027_workspace_isolation_and_checkpoint_claims.py`) before `DecisionExecutor.resume` with stale-claim crash recovery, supervision pause gates, operator permission checks (`403`), version conflict detection (`409`) + pinned snapshot execution, lifecycle-based cancellation (`run_status == "paused"`), and genuine downstream graph execution.
3. **Product Surface, Workspace Ownership, Control-Plane Reconciliation & SDK Boundary (`6H`–`6I`, `OC-BG-023`, `OC-BG-027`, `OC-BG-028`, `OC-BG-042`, `OC-BG-044`, `PR #47`, `PR #53`, `PR #55`)**: Enforced end-to-end engine & control-plane workspace ownership (`0027`, `POST /api/v1/projects/{id}/claim`), extended `@openclass/sdk` with `OpenClassControlClient` and `ControlApiError`, migrated `apps/portal/src/api.ts` 100% onto `@openclass/sdk` (enforced by `test_portal_uses_sdk_without_raw_fetch`), reconciled `control_projects` with engine `projects`, fixed `deriveScenarioDistribution` (`known_billing = 0.900`, `review_compliance = 0.410 / 0.270`) in `apps/portal/src/open-world-stage.tsx`, fixed `keycloak.init` offline redirect in `apps/portal/src/auth.tsx`, and added `React.lazy` + `manualChunks` (`index.js = 12.08 kB`). Because `apps/web` and `apps/portal` both remain active rather than retiring `apps/web`, `OC-BG-027` is recorded as **`PARTIAL`** under its original scope.
4. **Closed-Loop Discovery, Evaluation & Promotion Proof (`6F`–`6G`, `OC-BG-011`..`014`, `OC-BG-040`, `OC-BG-041`, `PR #38`, `PR #45`, `PR #50`, `PR #54`)**: Enforced strictly disjoint discovery/dev/regression/holdout datasets (`assert_strictly_disjoint_datasets`), server-side discovery-to-holdout leakage rejection (`409`), `label_source="prediction"` rejection (`422`), choice/alias collision rejection (`409`), regressive candidate rejection (`regressions > 0`), and both offline mechanism tests + live Vercel AI Gateway (`OPENCLASS_RUN_LIVE_TESTS=1`) end-to-end closed-loop evolution proofs (`OC-BG-011` and `OC-BG-040` **`VERIFIED`**). Under the restored original scope definitions (`7158104`), partial scope remains honestly documented as **`PARTIAL`** for the 19 items `OC-BG-012`, `OC-BG-013`, `OC-BG-014`, `OC-BG-016`, `OC-BG-017`, `OC-BG-018`, `OC-BG-020`, `OC-BG-021`, `OC-BG-022`, `OC-BG-024`, `OC-BG-025`, `OC-BG-026`, `OC-BG-027`, `OC-BG-029`, `OC-BG-030`, `OC-BG-032`, `OC-BG-033`, `OC-BG-034`, and `OC-BG-036`.
