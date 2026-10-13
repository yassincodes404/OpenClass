import { useEffect, useRef, useState } from "react";

/**
 * ============================================================================
 * OPENCLASS PRECISION OBSERVATORY — INTERACTIVE OPEN-WORLD LOOP & ARCHITECTURE
 * ============================================================================
 * Owner: Abdelhamid Khaled (@AbdelhamidKhald)
 *
 * Architectural Purpose:
 * This module implements the code-native interactive product visualization
 * (`OpenWorldLoopStage`) and supporting architectural proof sections for the
 * OpenClass landing experience.
 *
 * Domain Invariants Visualized:
 * 1. Fast-Path Bounded Choice: Known inputs with high confidence and top-2
 *    margin >= threshold route immediately to the active choice (`TRUSTED`).
 * 2. Permanent UNKNOWN: Unfamiliar inputs (`unknown_probability >= threshold`
 *    or unsupported by active classes) persist in the Unknown Pool as
 *    first-class evidence—never forced into a wrong label and never treated
 *    as automatic proof of a new class.
 * 3. Advisory Supervision: Ambiguous / low-margin runs (`top_margin < 0.20`)
 *    trigger `REVIEW` for asynchronous Supervisor inspection. Supervisor
 *    reviews are strictly advisory and never mutate the run or ontology.
 * 4. Operational Fault Separation: Upstream provider failures (HTTP 502 /
 *    timeout / malformed JSON) are quarantined as `ProviderError` before
 *    novelty scoring so outages never pollute semantic discovery evidence.
 * 5. Governed Evolution: Recurring unknown clusters trigger inactive Teacher
 *    proposals that must pass deterministic Replay Evaluation (`OC-008`) and
 *    explicit Human Approval (`OC-009`) to create immutable snapshot `vN+1`.
 *
 * Motion Choreography & Performance Invariants (Emil Kowalski / animate):
 * - All continuous/state transitions use only GPU-composited `transform`,
 *   `opacity`, and SVG `stroke-dashoffset`.
 * - Never animates `width`/`height`/`top`/`left`, never uses `transition: all`,
 *   never starts from `scale(0)`.
 * - Automatically pauses step auto-advance when scrolled out of the viewport
 *   (`IntersectionObserver`), when the browser tab is hidden
 *   (`document.visibilityState`), or when `prefers-reduced-motion: reduce` is
 *   active.
 */

export type PresetId = "known_billing" | "unknown_cancel" | "review_compliance" | "error_timeout";

export type StageStepIndex = 0 | 1 | 2 | 3 | 4;

export interface StageStepSpec {
  index: StageStepIndex;
  code: string;
  label: string;
  activeNodes: string[];
  activeEdges: string[];
  /** Logical SVG coordinate inside the 960x440 viewBox for GPU translate3d() */
  packetCoord: { x: number; y: number };
  headline: string;
  narration: string;
  traceSnippet: string;
  telemetry: {
    ontologyVersion: string;
    topClass: string;
    unknownProb: string;
    topMargin: string;
    noveltyState: "known" | "likely_novel" | "ambiguous_review" | "provider_error";
    outcomeBadge: string;
    authorityRule: string;
  };
}

export interface PresetScenario {
  id: PresetId;
  badge: string;
  shortTitle: string;
  observation: string;
  sublabel: string;
  accentTone: "known" | "unknown" | "review" | "error";
  probabilities: Array<{
    label: string;
    value: number;
    display: string;
    isUnknown?: boolean;
  }>;
  steps: [StageStepSpec, StageStepSpec, StageStepSpec, StageStepSpec, StageStepSpec];
}

/**
 * Four grounded runtime traces modeled directly on OpenClass's actual domain
 * rules (`examples/support-intents/classifier.json`, `novelty.py`,
 * `supervisor.py`, and `project_evolution.py`).
 */
export const PRESET_SCENARIOS: readonly PresetScenario[] = [
  {
    id: "known_billing",
    badge: "FAST PATH · KNOWN",
    shortTitle: "01 / Known Intent",
    observation: "I was charged twice for my monthly invoice",
    sublabel: "Matches supported class `billing` with 0.917 margin → immediate fast-path commit",
    accentTone: "known",
    probabilities: [
      { label: "billing", value: 0.9, display: "0.900" },
      { label: "technical", value: 0.033, display: "0.033" },
      { label: "sales", value: 0.017, display: "0.017" },
      { label: "UNKNOWN", value: 0.05, display: "0.050", isUnknown: true },
    ],
    steps: [
      {
        index: 0,
        code: "01 / OBSERVE",
        label: "Observe",
        activeNodes: ["node-ingest"],
        activeEdges: [],
        packetCoord: { x: 96, y: 210 },
        headline: "Ingest raw observation with idempotent provenance.",
        narration:
          "The observation arrives over HTTP SDK or authenticated webhook and is pinned to the active immutable OntologySnapshot v1 (891dc20d).",
        traceSnippet:
          'POST /api/v1/classifiers/support-intent/classify\n{"observation": "I was charged twice for my monthly invoice"}',
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "pending evaluation…",
          unknownProb: "—",
          topMargin: "—",
          noveltyState: "known",
          outcomeBadge: "INGESTED → PINNED TO v1",
          authorityRule: "Raw source event is immutable; predictions never overwrite input.",
        },
      },
      {
        index: 1,
        code: "02 / SCORE",
        label: "Bounded Score",
        activeNodes: ["node-ingest", "node-score"],
        activeEdges: ["edge-ingest-score"],
        packetCoord: { x: 276, y: 210 },
        headline: "Bounded DecisionProvider scores the closed choice set + UNKNOWN.",
        narration:
          "Fast-path provider (Jev / Laya / mock) evaluates {billing, technical, sales, UNKNOWN} under a strict grammar contract without calling a slow reasoning LLM.",
        traceSnippet:
          '{"probabilities": {"billing": 0.950, "technical": 0.033, "sales": 0.017}, "unknown_probability": 0.050}',
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "billing (0.950)",
          unknownProb: "0.050 (below 0.450 ceiling)",
          topMargin: "0.917 (above 0.200 gate)",
          noveltyState: "known",
          outcomeBadge: "SCORED → HIGH CONFIDENCE",
          authorityRule: "Provider returns probabilities only; it has zero writable DB access.",
        },
      },
      {
        index: 2,
        code: "03 / POLICY",
        label: "Novelty Gate",
        activeNodes: ["node-score", "node-policy"],
        activeEdges: ["edge-ingest-score", "edge-score-policy"],
        packetCoord: { x: 456, y: 210 },
        headline: "Deterministic NoveltyDetector & SupervisionPolicy verify margin.",
        narration:
          "Because unknown_probability (0.050) < 0.450 and top_margin (0.917) >= 0.200, deterministic core policy marks the decision TRUSTED / KNOWN.",
        traceSnippet:
          '{"novelty": {"state": "known", "score": 0.05, "reasons": ["known_class_supported"]}, "supervision": "TRUSTED"}',
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "billing (0.950)",
          unknownProb: "0.050",
          topMargin: "0.917 >= 0.200",
          noveltyState: "known",
          outcomeBadge: "GATE PASSED → TRUSTED",
          authorityRule: "Core domain code—not the model—decides whether a run is trusted.",
        },
      },
      {
        index: 3,
        code: "04 / COMMIT",
        label: "Fast Commit",
        activeNodes: ["node-policy", "node-known"],
        activeEdges: ["edge-ingest-score", "edge-score-policy", "edge-policy-known"],
        packetCoord: { x: 686, y: 92 },
        headline: "Route to supported workflow on the synchronous fast path.",
        narration:
          "ClassificationRun is committed atomically with selected_class: 'billing' and ontology_version_id: 'v1'. Zero rows are added to the unknown pool.",
        traceSnippet:
          '{"run_id": "run_94a1f0", "selected_class": "billing", "ontology_version_id": "v1", "unknown_pool_write": false}',
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "billing (0.950)",
          unknownProb: "0.050",
          topMargin: "0.917",
          noveltyState: "known",
          outcomeBadge: "KNOWN → billing",
          authorityRule: "Fast path finishes in <50ms target without Teacher escalation.",
        },
      },
      {
        index: 4,
        code: "05 / AUDIT",
        label: "Immutable Ledger",
        activeNodes: ["node-known", "node-audit"],
        activeEdges: [
          "edge-ingest-score",
          "edge-score-policy",
          "edge-policy-known",
          "edge-known-audit",
        ],
        packetCoord: { x: 864, y: 92 },
        headline: "Append-only run history preserved for future replay.",
        narration:
          "PostgreSQL immutability triggers lock the run record and ontology snapshot v1 so historical decisions remain 100% reproducible.",
        traceSnippet:
          "SELECT id, selected_class, ontology_version_id FROM classification_runs WHERE id = 'run_94a1f0'; -- BEFORE UPDATE/DELETE RAISE ABORT",
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (locked)",
          topClass: "billing (0.950)",
          unknownProb: "0.050",
          topMargin: "0.917",
          noveltyState: "known",
          outcomeBadge: "COMMITTED · APPEND-ONLY",
          authorityRule: "SQL triggers reject UPDATE and DELETE on ontology_versions & runs.",
        },
      },
    ],
  },
  {
    id: "unknown_cancel",
    badge: "DISCOVERY PATH · UNKNOWN",
    shortTitle: "02 / Novel Concept",
    observation: "Cancel my plan",
    sublabel:
      "Unsupported by {billing, technical, sales} → persisted as UNKNOWN → clustered → gated candidate",
    accentTone: "unknown",
    probabilities: [
      { label: "billing", value: 0.017, display: "0.017" },
      { label: "technical", value: 0.017, display: "0.017" },
      { label: "sales", value: 0.016, display: "0.016" },
      { label: "UNKNOWN", value: 0.95, display: "0.950", isUnknown: true },
    ],
    steps: [
      {
        index: 0,
        code: "01 / OBSERVE",
        label: "Observe",
        activeNodes: ["node-ingest"],
        activeEdges: [],
        packetCoord: { x: 96, y: 210 },
        headline: "Unfamiliar request enters Ontology v1 (billing, technical, sales).",
        narration:
          "A closed-world classifier would force 'Cancel my plan' into 'billing' (0.54) and trigger the wrong queue. OpenClass evaluates it against explicit novelty bounds.",
        traceSnippet:
          'POST /api/v1/classifiers/support-intent/classify\n{"observation": "Cancel my plan"}',
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (billing, technical, sales)",
          topClass: "evaluating…",
          unknownProb: "—",
          topMargin: "—",
          noveltyState: "likely_novel",
          outcomeBadge: "OBSERVED → CHECKING COVERAGE",
          authorityRule: "Active ontology v1 contains no 'cancellation' concept yet.",
        },
      },
      {
        index: 1,
        code: "02 / SCORE",
        label: "Abstention Score",
        activeNodes: ["node-ingest", "node-score"],
        activeEdges: ["edge-ingest-score"],
        packetCoord: { x: 276, y: 210 },
        headline: "DecisionProvider assigns 0.950 probability mass to UNKNOWN.",
        narration:
          "All known classes score 0.017. Rather than hallucinating a label, the bounded choice distribution surfaces strong_unknown_probability (0.950).",
        traceSnippet:
          '{"selected_class": null, "unknown_probability": 0.950, "novelty": {"state": "likely_novel", "score": 0.95, "reasons": ["strong_unknown_probability"]}}',
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "none (max known 0.017)",
          unknownProb: "0.950 (exceeds threshold)",
          topMargin: "0.000",
          noveltyState: "likely_novel",
          outcomeBadge: "ABSTAINED → PERMANENT UNKNOWN",
          authorityRule: "UNKNOWN is permanent; a single unknown is not proof of a new class.",
        },
      },
      {
        index: 2,
        code: "03 / EVIDENCE",
        label: "Evidence Pool",
        activeNodes: ["node-score", "node-unknown"],
        activeEdges: ["edge-ingest-score", "edge-score-unknown"],
        packetCoord: { x: 456, y: 296 },
        headline: "Persisted to the Unknown & Evidence Pool for clustering.",
        narration:
          "The run, full probability distribution, and novelty reasons are stored atomically in unknown_events / evidence_items (trigger: SEMANTIC_UNKNOWN).",
        traceSnippet:
          "INSERT INTO evidence_items (trigger_type, status, selected_choice, unknown_probability) VALUES ('semantic_unknown', 'pending', 'UNKNOWN', 0.95);",
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (unchanged)",
          topClass: "UNKNOWN (selected_class: null)",
          unknownProb: "0.950",
          topMargin: "0.000",
          noveltyState: "likely_novel",
          outcomeBadge: "STORED IN EVIDENCE POOL",
          authorityRule: "Saved for discovery. This is not yet a new-class proposal.",
        },
      },
      {
        index: 3,
        code: "04 / TEACHER",
        label: "Cluster & Propose",
        activeNodes: ["node-unknown", "node-cluster"],
        activeEdges: ["edge-ingest-score", "edge-score-unknown", "edge-unknown-cluster"],
        packetCoord: { x: 686, y: 296 },
        headline: "Recurring cluster (n >= 3) triggers an inactive Teacher proposal.",
        narration:
          "Once 3+ similar unknown observations accumulate ('Cancel my plan', 'Stop my subscription', 'End membership'), ChoiceTeacher proposes candidate 'cancellation'.",
        traceSnippet:
          '{"proposal_type": "NEW_CLASS", "canonical_name": "cancellation", "status": "candidate", "base_service_hash": "891dc20d", "evaluation_passed": false}',
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (still active)",
          topClass: "Candidate: cancellation (inactive)",
          unknownProb: "0.950 (evidence n=3)",
          topMargin: "cluster cohesion 0.84",
          noveltyState: "likely_novel",
          outcomeBadge: "CANDIDATE PROPOSED (INACTIVE)",
          authorityRule: "Teacher LLM owns semantic proposal; it cannot activate ontology changes.",
        },
      },
      {
        index: 4,
        code: "05 / GOVERN",
        label: "Replay & Review Gate",
        activeNodes: ["node-cluster", "node-govern"],
        activeEdges: [
          "edge-ingest-score",
          "edge-score-unknown",
          "edge-unknown-cluster",
          "edge-cluster-govern",
        ],
        packetCoord: { x: 864, y: 296 },
        headline: "Gated by Verified Replay Evaluation (OC-008) & Human Approval (OC-009).",
        narration:
          "Candidate 'cancellation' must pass baseline-vs-candidate replay with zero regressions and receive human sign-off before promoting Ontology v2 (0a83f9d9).",
        traceSnippet:
          "POST /api/v1/projects/support/candidates/cand_01/promote\n// Fails closed (HTTP 409 Conflict) until verified replay evaluation & human review pass",
        telemetry: {
          ontologyVersion: "v1 → v2 gated (OC-008 / OC-009)",
          topClass: "cancellation (pending replay)",
          unknownProb: "0.950 → <0.05 post-v2",
          topMargin: "requires 0 regressions",
          noveltyState: "likely_novel",
          outcomeBadge: "HELD AT REPLAY & HUMAN GATE",
          authorityRule: "Predictions never become ground truth; unverified promotion returns 409.",
        },
      },
    ],
  },
  {
    id: "review_compliance",
    badge: "SUPERVISION PATH · REVIEW",
    shortTitle: "03 / Ambiguous Margin",
    observation: "Export compliance packet for EU invoice audit",
    sublabel:
      "Split distribution (billing 0.41 vs technical 0.27, margin 0.14 < 0.20) → advisory Supervisor review",
    accentTone: "review",
    probabilities: [
      { label: "billing", value: 0.41, display: "0.410" },
      { label: "technical", value: 0.27, display: "0.270" },
      { label: "sales", value: 0.1, display: "0.100" },
      { label: "UNKNOWN", value: 0.22, display: "0.220", isUnknown: true },
    ],
    steps: [
      {
        index: 0,
        code: "01 / OBSERVE",
        label: "Observe",
        activeNodes: ["node-ingest"],
        activeEdges: [],
        packetCoord: { x: 96, y: 210 },
        headline: "Cross-domain request enters the decision pipeline.",
        narration:
          "The input touches both invoice records and compliance export tooling, testing boundary overlap between 'billing' and 'technical'.",
        traceSnippet:
          'POST /api/v1/classifiers/support-intent/classify\n{"observation": "Export compliance packet for EU invoice audit"}',
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "evaluating…",
          unknownProb: "—",
          topMargin: "—",
          noveltyState: "ambiguous_review",
          outcomeBadge: "OBSERVED → BOUNDARY TEST",
          authorityRule: "Supervision policy monitors top-2 class margin on every run.",
        },
      },
      {
        index: 1,
        code: "02 / SCORE",
        label: "Split Distribution",
        activeNodes: ["node-ingest", "node-score"],
        activeEdges: ["edge-ingest-score"],
        packetCoord: { x: 276, y: 210 },
        headline: "Top-2 classes collide: billing (0.480) vs. technical (0.340).",
        narration:
          "The model selects 'billing', but the top-2 margin is only 0.140—below the 0.200 minimum safety margin required for autonomous trust.",
        traceSnippet:
          '{"probabilities": {"billing": 0.480, "technical": 0.340, "sales": 0.180}, "unknown_probability": 0.220, "top_margin": 0.140}',
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "billing (0.480)",
          unknownProb: "0.220",
          topMargin: "0.140 (< 0.200 min_margin)",
          noveltyState: "ambiguous_review",
          outcomeBadge: "LOW MARGIN DETECTED (0.140)",
          authorityRule: "Low margin signals boundary ambiguity even when a known class is #1.",
        },
      },
      {
        index: 2,
        code: "03 / POLICY",
        label: "Supervision Gate",
        activeNodes: ["node-score", "node-policy"],
        activeEdges: ["edge-ingest-score", "edge-score-policy"],
        packetCoord: { x: 456, y: 210 },
        headline: "SupervisionPolicy routes the run to REVIEW (LOW_TRUST).",
        narration:
          "Deterministic supervision rules flag low_margin_between_top_classes and emit a LOW_TRUST evidence item for Supervisor inspection.",
        traceSnippet:
          '{"supervision_outcome": "REVIEW", "supervision_reason": "Margin 0.14 below safety threshold 0.20", "trigger_type": "low_trust"}',
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "billing (0.480 · flagged)",
          unknownProb: "0.220",
          topMargin: "0.140 < 0.200",
          noveltyState: "ambiguous_review",
          outcomeBadge: "ROUTED TO SUPERVISOR REVIEW",
          authorityRule: "High or split model probabilities never bypass SupervisionPolicy.",
        },
      },
      {
        index: 3,
        code: "04 / SUPERVISOR",
        label: "Supervisor Audit",
        activeNodes: ["node-policy", "node-supervisor"],
        activeEdges: ["edge-ingest-score", "edge-score-policy", "edge-policy-review"],
        packetCoord: { x: 686, y: 194 },
        headline: "Slow-path Supervisor inspects run against Ontology v1 (OC-016).",
        narration:
          "An independent SupervisorProvider re-examines the input, class definitions, and probabilities, emitting structured finding 'ambiguous_class_boundary'.",
        traceSnippet:
          'POST /api/v1/classifiers/support-intent/runs/run_1/reviews\n{"finding": "possible_misclassification", "recommendation": "clarify_class_boundary"}',
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "billing (advisory check)",
          unknownProb: "0.220",
          topMargin: "0.140",
          noveltyState: "ambiguous_review",
          outcomeBadge: "SUPERVISOR: POSSIBLE BOUNDARY GAP",
          authorityRule: "Supervisor runs off the critical path; it never blocks fast-path SLA.",
        },
      },
      {
        index: 4,
        code: "05 / ADVISORY LOG",
        label: "Append-Only Review",
        activeNodes: ["node-supervisor", "node-review-log"],
        activeEdges: [
          "edge-ingest-score",
          "edge-score-policy",
          "edge-policy-review",
          "edge-review-log",
        ],
        packetCoord: { x: 864, y: 194 },
        headline: "Review stored beside the run; classification is never overwritten.",
        narration:
          "The SupervisorReview record is locked in 0002_supervisor_reviews. Operators can promote the evidence to refine class instructions without silent drift.",
        traceSnippet:
          '{"review_id": "rev_88c", "classification_run_id": "run_1", "advisory_only": true, "mutated_run": false}',
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (unchanged)",
          topClass: "billing (run preserved)",
          unknownProb: "0.220",
          topMargin: "0.140",
          noveltyState: "ambiguous_review",
          outcomeBadge: "ADVISORY FINDING PERSISTED",
          authorityRule: "A Supervisor review never mutates the classification run or ontology.",
        },
      },
    ],
  },
  {
    id: "error_timeout",
    badge: "FAULT ISOLATION · ERROR",
    shortTitle: "04 / Provider Outage",
    observation: "Upstream 502 Bad Gateway / Inference Timeout",
    sublabel:
      "Operational failure separated deterministically from semantic UNKNOWN so outages never corrupt discovery",
    accentTone: "error",
    probabilities: [
      { label: "billing", value: 0, display: "ERR" },
      { label: "technical", value: 0, display: "ERR" },
      { label: "sales", value: 0, display: "ERR" },
      { label: "UNKNOWN", value: 0, display: "ISOLATED", isUnknown: true },
    ],
    steps: [
      {
        index: 0,
        code: "01 / OBSERVE",
        label: "Observe",
        activeNodes: ["node-ingest"],
        activeEdges: [],
        packetCoord: { x: 96, y: 210 },
        headline: "Observation enters pipeline during an upstream model outage.",
        narration:
          "In naive agent harnesses, a failed LLM call or malformed JSON response falls back to 'UNKNOWN', flooding the discovery pool with fake novelty.",
        traceSnippet:
          'POST /api/v1/projects/support/decision-services/router/runs\n{"content": "Refund request #4091"}',
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "awaiting provider…",
          unknownProb: "—",
          topMargin: "—",
          noveltyState: "provider_error",
          outcomeBadge: "DISPATCHING TO PROVIDER",
          authorityRule: "Operational errors and semantic uncertainty are distinct failure layers.",
        },
      },
      {
        index: 1,
        code: "02 / FAULT",
        label: "Provider Fault",
        activeNodes: ["node-ingest", "node-score"],
        activeEdges: ["edge-ingest-score"],
        packetCoord: { x: 276, y: 210 },
        headline: "DecisionProvider raises typed ProviderError (HTTP 502 / Timeout).",
        narration:
          "After bounded retries, the provider adapter raises a sanitized ProviderError(kind='unavailable') with all secrets and internal URLs stripped.",
        traceSnippet:
          'raise ProviderError("Decision provider unavailable after 2 retries", kind="unavailable") # zero API keys in message',
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "N/A (ProviderError)",
          unknownProb: "N/A (not scored)",
          topMargin: "N/A",
          noveltyState: "provider_error",
          outcomeBadge: "FAULT: HTTP 502 / TIMEOUT",
          authorityRule: "No secrets in logs, provider errors, fixtures, or events (AGENTS.md).",
        },
      },
      {
        index: 2,
        code: "03 / BARRIER",
        label: "Fault Barrier",
        activeNodes: ["node-score", "node-error-barrier"],
        activeEdges: ["edge-ingest-score", "edge-score-error"],
        packetCoord: { x: 456, y: 382 },
        headline: "Fault isolation barrier intercepts failure before NoveltyDetector.",
        narration:
          "Execution halts before novelty scoring. The transaction rolls back any partial run state so zero phantom classifications are recorded.",
        traceSnippet:
          "except ProviderError:\n    await repository.record_provider_error(project_id, provider, model, latency_ms)\n    raise # never writes to unknown_events",
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "aborted cleanly",
          unknownProb: "0 unknown writes",
          topMargin: "—",
          noveltyState: "provider_error",
          outcomeBadge: "ISOLATED BEFORE NOVELTY POOL",
          authorityRule: "Infrastructure failure != semantic novelty.",
        },
      },
      {
        index: 3,
        code: "04 / QUARANTINE",
        label: "Zero Pool Pollution",
        activeNodes: ["node-error-barrier", "node-quarantine"],
        activeEdges: ["edge-ingest-score", "edge-score-error", "edge-error-quarantine"],
        packetCoord: { x: 686, y: 382 },
        headline: "Unknown pool & clustering stay 100% uncorrupted.",
        narration:
          "Because nothing is written to unknown_events or evidence_items, a 10-minute model outage never triggers false Teacher candidate proposals.",
        traceSnippet:
          "SELECT COUNT(*) FROM unknown_events WHERE created_at >= :outage_start; -- returns 0",
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "none",
          unknownProb: "unpolluted (0 rows)",
          topMargin: "—",
          noveltyState: "provider_error",
          outcomeBadge: "QUARANTINED · 0 UNKNOWN WRITES",
          authorityRule: "Discovery evidence only admits valid probability distributions.",
        },
      },
      {
        index: 4,
        code: "05 / TELEMETRY",
        label: "Error Telemetry",
        activeNodes: ["node-quarantine", "node-recover"],
        activeEdges: [
          "edge-ingest-score",
          "edge-score-error",
          "edge-error-quarantine",
          "edge-quarantine-recover",
        ],
        packetCoord: { x: 864, y: 382 },
        headline: "Error counter incremented; caller retries safely with Idempotency-Key.",
        narration:
          "provider_usage records the error count and latency, HTTP 502/503 is returned cleanly, and the client can retry with the same Idempotency-Key.",
        traceSnippet:
          'HTTP/1.1 503 Service Unavailable\n{"detail": "Decision provider unavailable"} // Retry-safe with Idempotency-Key',
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (intact)",
          topClass: "retryable via SDK",
          unknownProb: "—",
          topMargin: "—",
          noveltyState: "provider_error",
          outcomeBadge: "OBSERVABLE & RECOVERABLE",
          authorityRule: "Idempotency keys prevent duplicate ingestion on client retry.",
        },
      },
    ],
  },
] as const;

interface DiagramNodeDef {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  code: string;
  title: string;
  sub: string;
  tone: "neutral" | "known" | "unknown" | "review" | "error";
}

const DIAGRAM_NODES: readonly DiagramNodeDef[] = [
  // Core spine (Cols 1-3)
  {
    id: "node-ingest",
    x: 24,
    y: 172,
    w: 144,
    h: 76,
    code: "01 / INPUT",
    title: "Observe",
    sub: "RawEvent + Schema",
    tone: "neutral",
  },
  {
    id: "node-score",
    x: 204,
    y: 172,
    w: 144,
    h: 76,
    code: "02 / FAST PATH",
    title: "DecisionProvider",
    sub: "Jev · Laya · Mock",
    tone: "neutral",
  },
  {
    id: "node-policy",
    x: 384,
    y: 172,
    w: 144,
    h: 76,
    code: "03 / GUARD",
    title: "Novelty & Policy",
    sub: "Margin & Thresholds",
    tone: "neutral",
  },
  // Row A: Known fast path
  {
    id: "node-known",
    x: 602,
    y: 52,
    w: 168,
    h: 72,
    code: "KNOWN CHOICE",
    title: "Trusted Route",
    sub: "Selected Class (v1)",
    tone: "known",
  },
  {
    id: "node-audit",
    x: 796,
    y: 52,
    w: 140,
    h: 72,
    code: "IMMUTABLE",
    title: "Audit Ledger",
    sub: "Append-Only SQL",
    tone: "known",
  },
  // Row B: Supervisor advisory path
  {
    id: "node-supervisor",
    x: 602,
    y: 156,
    w: 168,
    h: 72,
    code: "OC-016 · SLOW PATH",
    title: "Supervisor Review",
    sub: "Boundary Inspection",
    tone: "review",
  },
  {
    id: "node-review-log",
    x: 796,
    y: 156,
    w: 140,
    h: 72,
    code: "ADVISORY ONLY",
    title: "Review Record",
    sub: "Never Mutates Run",
    tone: "review",
  },
  // Row C: Unknown & Governed Discovery path
  {
    id: "node-unknown",
    x: 384,
    y: 264,
    w: 144,
    h: 72,
    code: "03 / ABSTAIN",
    title: "Unknown Pool",
    sub: "Permanent Evidence",
    tone: "unknown",
  },
  {
    id: "node-cluster",
    x: 602,
    y: 264,
    w: 168,
    h: 72,
    code: "04 / DISCOVERY",
    title: "Cluster & Teacher",
    sub: "Inactive Candidate",
    tone: "unknown",
  },
  {
    id: "node-govern",
    x: 796,
    y: 264,
    w: 140,
    h: 72,
    code: "05 / OC-008 & 009",
    title: "Replay & Human",
    sub: "Gates Ontology v2",
    tone: "unknown",
  },
  // Row D: Operational Fault Quarantine path
  {
    id: "node-error-barrier",
    x: 384,
    y: 352,
    w: 144,
    h: 64,
    code: "03 / BARRIER",
    title: "Fault Isolation",
    sub: "ProviderError Trap",
    tone: "error",
  },
  {
    id: "node-quarantine",
    x: 602,
    y: 352,
    w: 168,
    h: 64,
    code: "04 / QUARANTINE",
    title: "Zero Unknown Write",
    sub: "Protects Evidence",
    tone: "error",
  },
  {
    id: "node-recover",
    x: 796,
    y: 352,
    w: 140,
    h: 64,
    code: "05 / RETRY SAFE",
    title: "Error Telemetry",
    sub: "Idempotent Recovery",
    tone: "error",
  },
] as const;

interface DiagramEdgeDef {
  id: string;
  d: string;
  tone: "known" | "unknown" | "review" | "error";
}

const DIAGRAM_EDGES: readonly DiagramEdgeDef[] = [
  { id: "edge-ingest-score", d: "M 168 210 L 204 210", tone: "known" },
  { id: "edge-score-policy", d: "M 348 210 L 384 210", tone: "known" },
  {
    id: "edge-policy-known",
    d: "M 528 196 C 564 196, 566 88, 602 88",
    tone: "known",
  },
  { id: "edge-known-audit", d: "M 770 88 L 796 88", tone: "known" },
  {
    id: "edge-policy-review",
    d: "M 528 210 C 564 210, 566 192, 602 192",
    tone: "review",
  },
  { id: "edge-review-log", d: "M 770 192 L 796 192", tone: "review" },
  {
    id: "edge-score-unknown",
    d: "M 348 228 C 366 228, 366 300, 384 300",
    tone: "unknown",
  },
  { id: "edge-unknown-cluster", d: "M 528 300 L 602 300", tone: "unknown" },
  { id: "edge-cluster-govern", d: "M 770 300 L 796 300", tone: "unknown" },
  {
    id: "edge-score-error",
    d: "M 276 248 C 276 384, 340 384, 384 384",
    tone: "error",
  },
  { id: "edge-error-quarantine", d: "M 528 384 L 602 384", tone: "error" },
  { id: "edge-quarantine-recover", d: "M 770 384 L 796 384", tone: "error" },
] as const;

export interface OpenWorldLoopStageProps {
  /**
   * Optional callback invoked when the user clicks "Load into live workspace"
   * on the Next.js workspace surface (`apps/web/app/page.tsx`).
   */
  onSelectObservation?: (observation: string) => void;
}

export function OpenWorldLoopStage({ onSelectObservation }: OpenWorldLoopStageProps = {}) {
  const stageRef = useRef<HTMLElement | null>(null);

  // Detect OS/browser reduced-motion preference safely (SSR & JSDOM safe).
  const [reducedMotion, setReducedMotion] = useState<boolean>(() => {
    if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
      return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    }
    return false;
  });

  const [presetId, setPresetId] = useState<PresetId>("unknown_cancel");
  const [stepIndex, setStepIndex] = useState<StageStepIndex>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(() => !reducedMotion);
  const [isInView, setIsInView] = useState<boolean>(true);
  const [isDocVisible, setIsDocVisible] = useState<boolean>(true);

  const activePreset = PRESET_SCENARIOS.find((item) => item.id === presetId) ?? PRESET_SCENARIOS[1];
  const activeStep = activePreset.steps[stepIndex];

  // Subscribe to prefers-reduced-motion changes at runtime.
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handleChange = (event: MediaQueryListEvent) => {
      setReducedMotion(event.matches);
      if (event.matches) {
        setIsPlaying(false);
      }
    };
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", handleChange);
      return () => mq.removeEventListener("change", handleChange);
    }
    return undefined;
  }, []);

  // Pause auto-advance when the stage scrolls out of the viewport.
  useEffect(() => {
    const node = stageRef.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry) {
          setIsInView(entry.isIntersecting);
        }
      },
      { threshold: 0.15 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  // Pause auto-advance when the browser tab is hidden.
  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    const handleVisibility = () => {
      setIsDocVisible(document.visibilityState === "visible");
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, []);

  // Deterministic step progression timer (2800ms per step).
  useEffect(() => {
    if (!isPlaying || !isInView || !isDocVisible || reducedMotion) {
      return;
    }
    const timer = window.setInterval(() => {
      setStepIndex((prev) => ((prev + 1) % 5) as StageStepIndex);
    }, 2800);
    return () => window.clearInterval(timer);
  }, [isPlaying, isInView, isDocVisible, reducedMotion, presetId]);

  function selectPreset(nextId: PresetId) {
    setPresetId(nextId);
    setStepIndex(0);
    const chosen = PRESET_SCENARIOS.find((p) => p.id === nextId);
    if (chosen && onSelectObservation && nextId !== "error_timeout") {
      onSelectObservation(chosen.observation);
    }
  }

  return (
    <section
      id="open-world-loop"
      ref={stageRef}
      className={`oc-observatory-stage tone-${activePreset.accentTone}`}
      aria-label="Interactive open-world decision and governed discovery architecture"
    >
      {/* Top Instrument Control Bar: Scenario Presets + Playback Toggle */}
      <div className="oc-stage-topbar">
        <div className="oc-stage-title-block">
          <p className="eyebrow">INTERACTIVE TELEMETRY OBSERVATORY · GOVERNED DECISION LOOP</p>
          <h2>
            Trace how OpenClass separates confident routing, uncertainty, supervision, and faults.
          </h2>
        </div>
        <div className="oc-playback-controls">
          <button
            type="button"
            className="oc-play-btn"
            onClick={() => setIsPlaying((prev) => !prev)}
            aria-pressed={isPlaying}
          >
            {isPlaying ? "Pause trace ❚❚" : "Auto-trace ▶"}
          </button>
          <span className="oc-stage-clock">
            STEP {stepIndex + 1} / 5 · {activePreset.badge}
          </span>
        </div>
      </div>

      {/* Scenario Selector Pills */}
      <div className="oc-preset-bar" role="tablist" aria-label="Decision trace scenarios">
        {PRESET_SCENARIOS.map((preset) => {
          const isSelected = preset.id === presetId;
          return (
            <button
              key={preset.id}
              type="button"
              role="tab"
              aria-selected={isSelected}
              className={`oc-preset-pill tone-${preset.accentTone} ${isSelected ? "active" : ""}`}
              onClick={() => selectPreset(preset.id)}
            >
              <span className="oc-preset-kicker">{preset.shortTitle}</span>
              <strong className="oc-preset-obs">“{preset.observation}”</strong>
              <span className="oc-preset-sub">{preset.badge}</span>
            </button>
          );
        })}
      </div>

      {/* Main Split: Code-Native SVG Architecture Canvas + Live Telemetry Inspector */}
      <div className="oc-stage-shell">
        <div className="oc-svg-frame">
          <div className="oc-svg-caption-bar">
            <span>
              INPUT OBSERVATION: <code>“{activePreset.observation}”</code>
            </span>
            <span className={`oc-tone-chip tone-${activePreset.accentTone}`}>
              {activeStep.telemetry.outcomeBadge}
            </span>
          </div>

          <svg
            viewBox="0 0 960 440"
            className="oc-loop-svg"
            role="img"
            aria-label={`OpenClass decision pipeline showing ${activePreset.shortTitle} at step ${activeStep.code}`}
          >
            <defs>
              <pattern id="oc-instrument-grid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path
                  d="M 40 0 L 0 0 0 40"
                  fill="none"
                  stroke="rgba(48, 58, 49, 0.35)"
                  strokeWidth="1"
                />
              </pattern>
            </defs>

            {/* Precision Instrument Grid Background */}
            <rect x="0" y="0" width="960" height="440" fill="url(#oc-instrument-grid)" />

            {/* Lane Labels */}
            <text x="604" y="40" className="oc-svg-lane-label tone-known">
              LANE A · SYNCHRONOUS FAST PATH (TRUSTED KNOWN)
            </text>
            <text x="604" y="146" className="oc-svg-lane-label tone-review">
              LANE B · ASYNCHRONOUS SUPERVISOR AUDIT (OC-016)
            </text>
            <text x="604" y="254" className="oc-svg-lane-label tone-unknown">
              LANE C · PERMANENT UNKNOWN → CLUSTERING → TEACHER → REPLAY GATE
            </text>
            <text x="604" y="344" className="oc-svg-lane-label tone-error">
              LANE D · OPERATIONAL FAULT ISOLATION (ZERO UNKNOWN POLLUTION)
            </text>

            {/* Base Inactive Edges */}
            {DIAGRAM_EDGES.map((edge) => (
              <path
                key={`base-${edge.id}`}
                d={edge.d}
                className="oc-edge-base"
                fill="none"
                pathLength={100}
              />
            ))}

            {/* Energized Active Edges (stroke-dashoffset transition) */}
            {DIAGRAM_EDGES.map((edge) => {
              const isEdgeActive = activeStep.activeEdges.includes(edge.id);
              return (
                <path
                  key={`active-${edge.id}`}
                  d={edge.d}
                  className={`oc-edge-active tone-${edge.tone} ${isEdgeActive ? "energized" : ""}`}
                  fill="none"
                  pathLength={100}
                />
              );
            })}

            {/* Pipeline Stage Nodes */}
            {DIAGRAM_NODES.map((node) => {
              const isNodeActive = activeStep.activeNodes.includes(node.id);
              return (
                <g
                  key={node.id}
                  className={`oc-node tone-${node.tone} ${isNodeActive ? "active" : ""}`}
                >
                  <rect
                    x={node.x}
                    y={node.y}
                    width={node.w}
                    height={node.h}
                    rx="8"
                    className="oc-node-box"
                  />
                  <text x={node.x + 12} y={node.y + 20} className="oc-node-code">
                    {node.code}
                  </text>
                  <text x={node.x + 12} y={node.y + 41} className="oc-node-title">
                    {node.title}
                  </text>
                  <text x={node.x + 12} y={node.y + 58} className="oc-node-sub">
                    {node.sub}
                  </text>
                </g>
              );
            })}

            {/* GPU-Composited Travelling Observation Packet */}
            <g
              className={`oc-packet tone-${activePreset.accentTone}`}
              style={{
                transform: `translate3d(${activeStep.packetCoord.x}px, ${activeStep.packetCoord.y}px, 0)`,
              }}
            >
              <circle r="15" className="oc-packet-halo" />
              <circle r="6" className="oc-packet-core" />
            </g>
          </svg>

          {/* 5-Step Interactive Scrubber Bar */}
          <div className="oc-step-scrubber" role="group" aria-label="Pipeline execution steps">
            {activePreset.steps.map((step) => {
              const isCurrent = step.index === stepIndex;
              const isCompleted = step.index < stepIndex;
              return (
                <button
                  key={step.code}
                  type="button"
                  aria-pressed={isCurrent}
                  className={`oc-step-btn ${isCurrent ? "active" : ""} ${
                    isCompleted ? "completed" : ""
                  }`}
                  onClick={() => {
                    setIsPlaying(false);
                    setStepIndex(step.index);
                  }}
                >
                  <span className="oc-step-code">{step.code}</span>
                  <span className="oc-step-label">{step.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right Column: Live Telemetry & Probability Distribution Inspector */}
        <aside className="oc-telemetry-inspector" aria-label="Stage telemetry readout">
          <div className="oc-inspector-card">
            <div className="oc-inspector-header">
              <span className="oc-inspector-step">{activeStep.code}</span>
              <span className={`oc-tone-chip tone-${activePreset.accentTone}`}>
                {activeStep.telemetry.noveltyState.replaceAll("_", " ")}
              </span>
            </div>
            <h3 className="oc-inspector-headline">{activeStep.headline}</h3>
            <p className="oc-inspector-narration">{activeStep.narration}</p>

            {/* GPU-Composited Probability Distribution Track (scaleX) */}
            <div className="oc-prob-block">
              <div className="oc-prob-header">
                <span>BOUNDED CHOICE DISTRIBUTION</span>
                <span>
                  {activePreset.id === "error_timeout" ? "∑ P = N/A (FAULT)" : "∑ P = 1.000"}
                </span>
              </div>
              {activePreset.probabilities.map((prob) => (
                <div
                  key={prob.label}
                  className={`oc-prob-row ${prob.isUnknown ? "is-unknown" : ""}`}
                >
                  <code className="oc-prob-label">{prob.label}</code>
                  <div className="oc-prob-track">
                    <div
                      className={`oc-prob-fill ${prob.isUnknown ? "unknown" : ""}`}
                      style={{
                        transform: `scaleX(${Math.max(0.02, prob.value)})`,
                      }}
                    />
                  </div>
                  <span className="oc-prob-val">{prob.display}</span>
                </div>
              ))}
            </div>

            {/* Key-Value Telemetry Readout */}
            <dl className="oc-telemetry-dl">
              <div>
                <dt>Ontology snapshot</dt>
                <dd>{activeStep.telemetry.ontologyVersion}</dd>
              </div>
              <div>
                <dt>Top candidate</dt>
                <dd>{activeStep.telemetry.topClass}</dd>
              </div>
              <div>
                <dt>Unknown mass</dt>
                <dd>{activeStep.telemetry.unknownProb}</dd>
              </div>
              <div>
                <dt>Top-2 margin</dt>
                <dd>{activeStep.telemetry.topMargin}</dd>
              </div>
            </dl>

            {/* Wire / SQL Trace Snippet */}
            <pre className="oc-trace-pre">
              <code>{activeStep.traceSnippet}</code>
            </pre>

            {/* Enforced Architectural Rule */}
            <div className="oc-authority-callout">
              <span>INVARIANT</span>
              <p>{activeStep.telemetry.authorityRule}</p>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}

/**
 * Grounded Use Cases & Proof Explorer (Section 5 of the Creative Specification).
 * All numbers, hashes, and class names match checked-in repository artifacts:
 * - `examples/support-intents/classifier.json`
 * - `docs/guides/automation-proof2.md` (`b28e35ee` -> `906044f2`)
 * - `docs/architecture/adr-research-phase-complete.md` (`891dc20d` -> `a0043a1e`)
 */
interface GroundedProofSpec {
  id: string;
  tag: string;
  title: string;
  artifactPath: string;
  statusBadge: string;
  summary: string;
  versionChain: string;
  steps: Array<{ phase: string; detail: string; code: string }>;
  outcomeMetric: string;
}

const GROUNDED_PROOFS: readonly GroundedProofSpec[] = [
  {
    id: "support-intents",
    tag: "01 / SUPPORT INTENT ROUTING",
    title: "Customer Support Classification & Missing-Concept Discovery",
    artifactPath: "examples/support-intents/classifier.json",
    statusBadge: "SHIPPED IN GENESIS v0.0.1",
    summary:
      "Starts with a 3-class ontology (billing, technical, sales). Confident knowns resolve on the fast path; unfamiliar cancellation requests persist in the unknown pool without corrupting billing queues.",
    versionChain:
      "Ontology v1 (billing, technical, sales) → Unknown Pool → Candidate: cancellation",
    steps: [
      {
        phase: "Fast Path (Known)",
        detail:
          "“I was charged twice” matches billing with low novelty (0.05) and routes immediately.",
        code: 'selected_class: "billing" · novelty.state: "known"',
      },
      {
        phase: "Disciplined Abstention (UNKNOWN)",
        detail:
          "“Cancel my plan” scores 0.95 unknown probability and is stored in unknown_events instead of guessing.",
        code: 'selected_class: null · reasons: ["strong_unknown_probability"]',
      },
      {
        phase: "Advisory Supervision (OC-016)",
        detail:
          "Supervisor reviews persisted runs off the critical path and flags boundary overlap without mutating the run.",
        code: 'finding: "possible_missing_class" · recommendation: "collect_more_evidence"',
      },
    ],
    outcomeMetric: "Zero forced guesses on out-of-ontology intents · Append-only SQL history",
  },
  {
    id: "devops-port-macro",
    tag: "02 / DEVOPS RECOVERY MACRO",
    title: "Port-Conflict Recovery & Negative-Transfer Gate (Proof #2 & #2B)",
    artifactPath: "docs/guides/automation-proof2.md",
    statusBadge: "FROZEN RESEARCH PROOF",
    summary:
      "When a container test runner hits 'Address already in use', five real Jev decisions halt safely at BLOCKED. One Teacher call proposes a 4-step recovery macro verified by real socket bind and report checks.",
    versionChain: "Policy v1 (b28e35ee…) → Candidate (d23d7342…) → Approved Policy v2 (906044f2…)",
    steps: [
      {
        phase: "Safe Blocked Halt",
        detail:
          "Baseline policy encounters a live port conflict in disposable containers and halts without destructive retries.",
        code: "status: BLOCKED · failure_signature: Address already in use",
      },
      {
        phase: "Bounded Macro Synthesis",
        detail:
          "Teacher composes only registered primitives: choose_available_test_port → set_environment → run_tests → write_report.",
        code: "macro: recover_port_conflict (4 verified primitives)",
      },
      {
        phase: "Replay Gate Rejects Regression (Proof #2B)",
        detail:
          "When an over-broad trigger regressed 2 baseline cases (9/12 pass despite LLM confidence 1.0), the deterministic gate blocked promotion.",
        code: "Run 2 reuse: 6 Jev calls · 0 Teacher calls · 100% postcondition verified",
      },
    ],
    outcomeMetric:
      "6 Jev fast-path calls & 0 Teacher calls after promotion · Regressing candidate rejected",
  },
  {
    id: "policy-graph-v4",
    tag: "03 / MULTI-LAYER POLICY EVOLUTION",
    title: "Three-Layer PolicyGraph Evolution (Decision Space, Procedure, State)",
    artifactPath: "docs/architecture/adr-research-phase-complete.md",
    statusBadge: "HASH-VERIFIED v1 → v4 CHAIN",
    summary:
      "Separates semantic Choice ('what was decided') from Transition ('what happens next': CAPABILITY, HUMAN, LLM, WORKFLOW) and attributes failures across 10 architectural layers.",
    versionChain: "v1 (891dc20d) → v2 (0a83f9d9) → v3 (67152f52) → v4 (a0043a1e)",
    steps: [
      {
        phase: "v1 → v2 (DECISION_SPACE)",
        detail:
          "Learns ADD_CHOICE for TLS certificate failure from recurring UNKNOWN observations.",
        code: "operator: add_choice · retention: 1.00",
      },
      {
        phase: "v2 → v3 (PROCEDURE)",
        detail:
          "Repairs CA-migration script drift (flush-before-rotate) without altering routing choices.",
        code: "operator: replace_procedure · retention: 1.00",
      },
      {
        phase: "v3 → v4 (STATE_REPRESENTATION)",
        detail:
          "Adds conditional generation-probe state feature with machine scope compiled deterministically by OpenClass.",
        code: "operator: add_state_feature · required: false (compiler-enforced)",
      },
    ],
    outcomeMetric:
      "95.98% Jev accuracy across 176 characterization cases (2–32 flat choices) · 1.0 retention across v1→v4",
  },
] as const;

const QUICKSTART_TABS = [
  {
    id: "cli",
    label: "CLI & Docker Compose",
    lang: "bash",
    code: `git clone https://github.com/yassincodes404/OpenClass.git
cd OpenClass
OPENCLASS_DECISION_PROVIDER=mock docker compose up --build -d --wait
curl http://localhost:7331/health/ready

# Initialize Ontology v1 (billing, technical, sales)
docker compose exec server openclass init examples/support-intents/classifier.json

# 1. Confident known observation -> routes to "billing"
docker compose exec server openclass classify "I was charged twice"

# 2. Unfamiliar observation -> persisted as permanent UNKNOWN evidence
docker compose exec server openclass classify "Cancel my plan"
docker compose exec server openclass unknowns --classifier support-intent`,
  },
  {
    id: "ts-sdk",
    label: "TypeScript SDK (@openclass/sdk)",
    lang: "typescript",
    code: `import { OpenClass } from "@openclass/sdk";

const client = new OpenClass("http://localhost:7331");

// Evaluate an observation against the active immutable ontology
const run = await client.classify({
  classifier: "support-intent",
  observation: "Cancel my plan",
});

console.log(run.selected_class); // null (persisted to Unknown Pool)
console.log(run.novelty);        // { state: "likely_novel", score: 0.95, reasons: [...] }

// Trigger an advisory Supervisor review (never mutates the run or ontology)
const review = await client.reviewRun({
  classifier: "support-intent",
  runId: run.id,
});
console.log(review.result.finding, review.result.recommendation);`,
  },
  {
    id: "py-sdk",
    label: "Python SDK (openclass-sdk)",
    lang: "python",
    code: `from openclass_sdk import OpenClass

with OpenClass("http://localhost:7331") as client:
    result = client.classify(
        classifier="support-intent",
        observation="I was charged twice",
    )
    print(result["selected_class"])      # "billing"
    print(result["novelty"]["state"])    # "known"

    # Inspect persisted UNKNOWN evidence pool for discovery clustering
    unknown_pool = client.unknowns("support-intent")
    print(f"Captured {len(unknown_pool)} unknown observations.")`,
  },
] as const;

export function ObservatoryArchitectureSections() {
  const [selectedProofId, setSelectedProofId] = useState<string>("support-intents");
  const [selectedCodeTab, setSelectedCodeTab] = useState<string>("cli");
  const [copiedTab, setCopiedTab] = useState<string | null>(null);

  const activeProof =
    GROUNDED_PROOFS.find((item) => item.id === selectedProofId) ?? GROUNDED_PROOFS[0];
  const activeSnippet =
    QUICKSTART_TABS.find((item) => item.id === selectedCodeTab) ?? QUICKSTART_TABS[0];

  async function handleCopyCode() {
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard) {
        await navigator.clipboard.writeText(activeSnippet.code);
      }
      setCopiedTab(activeSnippet.id);
      window.setTimeout(() => setCopiedTab(null), 1800);
    } catch {
      setCopiedTab(activeSnippet.id);
      window.setTimeout(() => setCopiedTab(null), 1800);
    }
  }

  return (
    <div className="oc-architecture-sections">
      {/* SECTION 3: Fast Path vs. Slow Path Architecture */}
      <section className="oc-section-block" aria-labelledby="oc-fast-slow-heading">
        <div className="oc-section-head">
          <p className="eyebrow">LATENCY & AUTHORITY HIERARCHY</p>
          <h2 id="oc-fast-slow-heading">Keep frontier LLMs off your critical path.</h2>
          <p className="oc-section-sub">
            Calling a general-purpose reasoning model on every request breaks latency budgets,
            inflates token spend, and invites silent drift. OpenClass separates{" "}
            <strong>bounded synchronous decisions</strong> from{" "}
            <strong>asynchronous supervisory intelligence</strong>.
          </p>
        </div>

        <div className="oc-dual-lane-grid">
          <article className="oc-lane-card tone-known">
            <div className="oc-lane-head">
              <span className="oc-tone-chip tone-known">FAST PATH · SYNCHRONOUS RUNTIME</span>
              <code>EVERY REQUEST · BOUNDED SLA</code>
            </div>
            <h3>Bounded DecisionProvider + Deterministic Policy</h3>
            <p>
              Evaluates a version-pinned choice space (<code>v1</code>) plus <code>UNKNOWN</code>.
              In research characterization (<code>benchmarks/jev/</code>), Jev routed{" "}
              <strong>95.98% across 176 authored cases</strong> from 2 to 32 flat choices with zero
              literal aliases.
            </p>
            <div className="oc-lane-flow">
              <span>StateSnapshot</span>
              <i>→</i>
              <span>Bounded Provider (Jev / Laya)</span>
              <i>→</i>
              <span>Margin & Novelty Gate</span>
              <i>→</i>
              <span>Trusted Action or UNKNOWN</span>
            </div>
          </article>

          <article className="oc-lane-card tone-review">
            <div className="oc-lane-head">
              <span className="oc-tone-chip tone-review">
                SLOW PATH · ASYNCHRONOUS SUPERVISION & TEACHER
              </span>
              <code>SAMPLED / TRIGGERED BY EVIDENCE</code>
            </div>
            <h3>Supervisor Audits & Teacher Proposals Off the Critical Path</h3>
            <p>
              Stronger reasoning models inspect persisted runs, low-margin decisions, and recurring{" "}
              <code>UNKNOWN</code> clusters to emit strictly typed, inactive candidates—called{" "}
              <strong>once per concept gap</strong>, never once per user request.
            </p>
            <div className="oc-lane-flow">
              <span>Unknown Cluster (n ≥ 3)</span>
              <i>→</i>
              <span>Teacher Proposal</span>
              <i>→</i>
              <span>Replay Gate (OC-008)</span>
              <i>→</i>
              <span>Human Approval → vN+1</span>
            </div>
          </article>
        </div>

        {/* Teacher Owns Meaning vs. OpenClass Owns Mechanics Contract */}
        <div className="oc-authority-matrix">
          <div className="oc-authority-col">
            <p className="eyebrow">TEACHER & SUPERVISOR LLMs OWN MEANING</p>
            <ul>
              <li>
                Identify what semantic concept is missing from a recurring <code>UNKNOWN</code>{" "}
                cluster.
              </li>
              <li>
                Diagnose whether a failure stems from <code>DECISION_SPACE</code>,{" "}
                <code>PROCEDURE</code>, or <code>STATE_REPRESENTATION</code>.
              </li>
              <li>
                Propose canonical labels, descriptions, aliases, and grounded rationales from stored
                evidence.
              </li>
            </ul>
          </div>
          <div className="oc-authority-col">
            <p className="eyebrow">OPENCLASS CORE OWNS MECHANICS & AUTHORITY</p>
            <ul>
              <li>
                Assign stable UUIDs, SHA-256 version hashes, and deterministic schema/guard
                compilation.
              </li>
              <li>
                Enforce novelty thresholds, margin math, capability allowlists, and{" "}
                <code>ProviderError</code> fault isolation.
              </li>
              <li>
                Gate activation on human-verified replay evaluation (<code>OC-008</code>), human
                review (<code>OC-009</code>), and SQL immutability triggers.
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* SECTION 4: Six-Stage Governed Evolution Invariants */}
      <section className="oc-section-block" aria-labelledby="oc-invariants-heading">
        <div className="oc-section-head">
          <p className="eyebrow">EPISTEMIC SAFETY & DOMAIN INVARIANTS</p>
          <h2 id="oc-invariants-heading">
            Six stages from anomaly to versioned knowledge. Zero silent self-modification.
          </h2>
          <p className="oc-section-sub">
            Every governance boundary in OpenClass is enforced in <code>packages/core</code> and
            PostgreSQL migrations—never left to prompt instructions.
          </p>
        </div>

        <div className="oc-pillars-grid">
          <article className="oc-pillar-card">
            <span className="oc-pillar-tag">INVARIANT 01 · NOVELTY POLICY</span>
            <h3>Persistent UNKNOWN Is Permanent</h3>
            <p>
              An <code>UNKNOWN</code> observation is never automatic proof of a new class. OpenClass
              stores the full probability distribution (<code>∑ P = 1.0</code>), top-2 margin, and
              novelty reasons without guessing.
            </p>
          </article>

          <article className="oc-pillar-card">
            <span className="oc-pillar-tag">INVARIANT 02 · FAULT SEPARATION</span>
            <h3>Layer-Specific Failure Diagnosis</h3>
            <p>
              An upstream HTTP 502 is quarantined as a <code>ProviderError</code>, never stored as
              semantic <code>UNKNOWN</code> evidence. A script failure attributes{" "}
              <code>PROCEDURE</code>, not routing choices.
            </p>
          </article>

          <article className="oc-pillar-card">
            <span className="oc-pillar-tag">INVARIANT 03 · ZERO WRITABLE MODEL ACCESS</span>
            <h3>Canonicalized Teacher Proposals</h3>
            <p>
              Discovery providers emit structured outcomes (<code>NEW_CLASS</code>,{" "}
              <code>ALIAS</code>, <code>EXISTING_CLASS</code>, <code>INSUFFICIENT_EVIDENCE</code>)
              checked against existing names and versioned aliases.
            </p>
          </article>

          <article className="oc-pillar-card">
            <span className="oc-pillar-tag">INVARIANT 04 · PREDICTIONS ≠ GROUND TRUTH</span>
            <h3>Independent Replay Evaluation (OC-008)</h3>
            <p>
              Model confidence (<code>1.00</code>) and evidence counts never fabricate passing
              evaluation scores. Baseline <code>vN</code> and candidate <code>vN+1</code> must
              replay against human-verified datasets.
            </p>
          </article>

          <article className="oc-pillar-card">
            <span className="oc-pillar-tag">INVARIANT 05 · ADVISORY SUPERVISION</span>
            <h3>Explicit Human & Supervisor Authority (OC-016)</h3>
            <p>
              A <code>SupervisorProvider</code> can flag <code>possible_misclassification</code> on
              a confident run. That finding is stored append-only beside the run and never rewrites
              history.
            </p>
          </article>

          <article className="oc-pillar-card">
            <span className="oc-pillar-tag">INVARIANT 06 · SQL-ENFORCED IMMUTABILITY</span>
            <h3>Append-Only Ontology Snapshots (OC-009)</h3>
            <p>
              Database triggers reject <code>UPDATE</code> and <code>DELETE</code> on{" "}
              <code>ontology_versions</code>, <code>ontology_events</code>,{" "}
              <code>supervisor_reviews</code>, and <code>webhook_receipts</code>.
            </p>
          </article>
        </div>
      </section>

      {/* SECTION 5: Grounded Repository Use Cases */}
      <section className="oc-section-block" aria-labelledby="oc-proofs-heading">
        <div className="oc-section-head">
          <p className="eyebrow">GROUNDED SCENARIOS · CHECKED-IN REPOSITORY ARTIFACTS</p>
          <h2 id="oc-proofs-heading">
            One adaptive decision kernel. Three concrete engineering proofs.
          </h2>
        </div>

        <div className="oc-proof-tabs" role="tablist" aria-label="Grounded engineering proofs">
          {GROUNDED_PROOFS.map((proof) => (
            <button
              key={proof.id}
              type="button"
              role="tab"
              aria-selected={proof.id === selectedProofId}
              className={`oc-proof-tab ${proof.id === selectedProofId ? "active" : ""}`}
              onClick={() => setSelectedProofId(proof.id)}
            >
              <span>{proof.tag}</span>
              <strong>{proof.title}</strong>
            </button>
          ))}
        </div>

        <div className="oc-proof-detail" role="tabpanel" key={activeProof.id}>
          <div className="oc-proof-meta">
            <div>
              <span className="oc-tone-chip tone-known">{activeProof.statusBadge}</span>
              <h3>{activeProof.title}</h3>
              <p>{activeProof.summary}</p>
            </div>
            <div className="oc-proof-hashes">
              <span>SOURCE ARTIFACT</span>
              <code>{activeProof.artifactPath}</code>
              <span>VERSION LINEAGE</span>
              <code>{activeProof.versionChain}</code>
            </div>
          </div>

          <div className="oc-proof-steps-grid">
            {activeProof.steps.map((step) => (
              <div key={step.phase} className="oc-proof-step-card">
                <span className="oc-step-phase">{step.phase}</span>
                <p>{step.detail}</p>
                <code>{step.code}</code>
              </div>
            ))}
          </div>

          <div className="oc-proof-footer">
            <span>VERIFIED OUTCOME</span>
            <strong>{activeProof.outcomeMetric}</strong>
          </div>
        </div>
      </section>

      {/* SECTION 6: Honest Implementation Status Matrix */}
      <section className="oc-section-block" aria-labelledby="oc-status-matrix-heading">
        <div className="oc-section-head">
          <p className="eyebrow">RADICAL ENGINEERING TRANSPARENCY · implementation-status.md</p>
          <h2 id="oc-status-matrix-heading">
            What ships in Genesis v0.0.1 today—and what fails closed until verified.
          </h2>
          <p className="oc-section-sub">
            OpenClass refuses to fake passing evaluations from prediction counts or disguise mock
            fixtures as live inference.
          </p>
        </div>

        <div className="oc-status-table-wrap">
          <table className="oc-status-table">
            <thead>
              <tr>
                <th>Subsystem</th>
                <th>Current Status</th>
                <th>Verified Behavior in Local Tree (v0.0.1)</th>
                <th>Gate Before v0.1.0 Discovery Release</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <strong>Classification & Novelty Kernel</strong>
                </td>
                <td>
                  <span className="oc-tone-chip tone-known">SHIPPED · v0.0.1</span>
                </td>
                <td>
                  Typed <code>DecisionProvider</code> port (<code>Laya</code>, <code>Jev</code>,{" "}
                  <code>mock</code>), configurable novelty thresholds, persistent{" "}
                  <code>UNKNOWN</code> pool, append-only ontology snapshots.
                </td>
                <td>
                  Wider-domain calibration & live provider benchmarks (<code>OC-003</code>,{" "}
                  <code>OC-004</code>).
                </td>
              </tr>
              <tr>
                <td>
                  <strong>Supervisor Run Reviews</strong>
                </td>
                <td>
                  <span className="oc-tone-chip tone-known">SHIPPED · OC-016</span>
                </td>
                <td>
                  Manual-trigger advisory <code>SupervisorProvider</code>, structured findings (
                  <code>possible_misclassification</code>, <code>possible_missing_class</code>),
                  immutable <code>0002_supervisor_reviews</code> table.
                </td>
                <td>
                  Live OpenAI-compatible / Ollama supervisor adapters (<code>OC-018</code>) &
                  sampling policy (<code>OC-020</code>).
                </td>
              </tr>
              <tr>
                <td>
                  <strong>Projects, Ingestion & Webhooks</strong>
                </td>
                <td>
                  <span className="oc-tone-chip tone-known">SHIPPED · OC-033</span>
                </td>
                <td>
                  Project-scoped CRUD, batch ingestion, token-authenticated webhooks with{" "}
                  <code>event_key</code> deduplication and immutable{" "}
                  <code>0010_webhook_receipts</code>.
                </td>
                <td>Unified workspace tenancy boundary & vendor-signed webhook normalizers.</td>
              </tr>
              <tr>
                <td>
                  <strong>Candidate Review &amp; Sealed Evaluation Datasets</strong>
                </td>
                <td>
                  <span className="oc-tone-chip tone-known">SHIPPED · PHASES 11–12</span>
                </td>
                <td>
                  State-machine candidate review (<code>≥ 5</code> distinct evidence runs required),
                  human-verified <code>0018_evaluation_sets</code> rejecting{" "}
                  <code>source=&quot;prediction&quot;</code>, irreversible dataset sealing.
                </td>
                <td>
                  Pluggable semantic embeddings (<code>OC-005</code>) &amp; unified candidate
                  revisions across legacy/project tracks.
                </td>
              </tr>
              <tr>
                <td>
                  <strong>Replay Evaluation &amp; Guarded Promotion</strong>
                </td>
                <td>
                  <span className="oc-tone-chip tone-review">SHIPPED · SIMULATED REPLAY</span>
                </td>
                <td>
                  Baseline vs. candidate regression gates (<code>0019_evaluation_runs</code>),
                  append-only <code>0020_service_versions</code> with diff/rollback, while
                  unverified <code>/candidates</code> routes fail closed (<code>409 Conflict</code>
                  ).
                </td>
                <td>
                  Live provider replay (<code>OC-008</code>) &amp; unified Core <code>vN+1</code>{" "}
                  activation (<code>OC-009</code>).
                </td>
              </tr>
              <tr>
                <td>
                  <strong>Live Operations &amp; Safe Support Routing</strong>
                </td>
                <td>
                  <span className="oc-tone-chip tone-known">SHIPPED · PHASES 15–16</span>
                </td>
                <td>
                  Quality KPIs, threshold alert rules (<code>0021_alert_rules</code>),
                  cursor-resumable SSE stream, and deterministic support routing (
                  <code>UNKNOWN → escalate</code> to human triage).
                </td>
                <td>
                  External destination state verification (<code>OC-035</code>, <code>OC-038</code>
                  ).
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* SECTION 7: Developer Quickstart & SDK Switcher */}
      <section id="quickstart" className="oc-section-block" aria-labelledby="oc-quickstart-heading">
        <div className="oc-section-head">
          <p className="eyebrow">LOCAL-FIRST EXECUTION · LOOPBACK BY DEFAULT</p>
          <h2 id="oc-quickstart-heading">Up in four commands. Inspectable over HTTP.</h2>
          <p className="oc-section-sub">
            Compose starts PostgreSQL 16 with <code>pgvector</code>, runs Alembic migrations (
            <code>upgrade head</code>), and binds the FastAPI server to <code>127.0.0.1:7331</code>.
          </p>
        </div>

        <div className="oc-code-console">
          <div className="oc-code-console-bar">
            <div className="oc-code-tabs" role="tablist" aria-label="Quickstart code examples">
              {QUICKSTART_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={tab.id === selectedCodeTab}
                  className={`oc-code-tab ${tab.id === selectedCodeTab ? "active" : ""}`}
                  onClick={() => setSelectedCodeTab(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <button type="button" className="oc-copy-btn" onClick={() => void handleCopyCode()}>
              {copiedTab === activeSnippet.id ? "Copied · ✓" : "Copy snippet"}
            </button>
          </div>
          <pre className="oc-code-pre" role="tabpanel">
            <code>{activeSnippet.code}</code>
          </pre>
        </div>

        <div className="oc-dependency-law">
          <span>INWARD DEPENDENCY LAW</span>
          <code>
            UI & CLI → Public HTTP SDKs → FastAPI Server → Core Domain Ports ← Isolated Providers
            (Jev / Laya / Mock)
          </code>
        </div>
      </section>
    </div>
  );
}
