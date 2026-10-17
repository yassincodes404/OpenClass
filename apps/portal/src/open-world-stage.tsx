import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

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

export interface StageProbability {
  label: string;
  value: number;
  display: string;
  isUnknown?: boolean;
}

export interface ScenarioDistribution {
  probabilities: StageProbability[];
  topLabel: string;
  topProbability: number;
  topDisplay: string;
  secondLabel: string;
  secondProbability: number;
  secondDisplay: string;
  unknownProbability: number;
  unknownDisplay: string;
  topMargin: number;
  topMarginDisplay: string;
}

const CANONICAL_CLASS_ORDER = ["billing", "technical", "sales", "UNKNOWN"] as const;

export function deriveScenarioDistribution(
  rawScores: Readonly<Record<string, number>>,
  options?: { isError?: boolean },
): ScenarioDistribution {
  const isError = options?.isError === true;
  const orderedKeys = [
    ...CANONICAL_CLASS_ORDER.filter((key) => key in rawScores),
    ...Object.keys(rawScores).filter(
      (key) => !CANONICAL_CLASS_ORDER.includes(key as (typeof CANONICAL_CLASS_ORDER)[number]),
    ),
  ];

  const probabilities: StageProbability[] = orderedKeys.map((label) => {
    const value = Number((rawScores[label] ?? 0).toFixed(3));
    const isUnknown = label === "UNKNOWN";
    return {
      label,
      value,
      display: isError ? (isUnknown ? "ISOLATED" : "ERR") : value.toFixed(3),
      ...(isUnknown ? { isUnknown: true } : {}),
    };
  });

  const sorted = [...probabilities].sort((a, b) => b.value - a.value);
  const top = sorted[0] ?? { label: "UNKNOWN", value: 0, display: "0.000" };
  const second = sorted[1] ?? { label: "UNKNOWN", value: 0, display: "0.000" };
  const unknownEntry = probabilities.find((item) => item.isUnknown || item.label === "UNKNOWN") ?? {
    label: "UNKNOWN",
    value: 0,
    display: "0.000",
  };

  const topProbability = top.value;
  const secondProbability = second.value;
  const unknownProbability = unknownEntry.value;
  const topMargin = Number((topProbability - secondProbability).toFixed(3));

  return {
    probabilities,
    topLabel: top.label,
    topProbability,
    topDisplay: topProbability.toFixed(3),
    secondLabel: second.label,
    secondProbability,
    secondDisplay: secondProbability.toFixed(3),
    unknownProbability,
    unknownDisplay: unknownProbability.toFixed(3),
    topMargin,
    topMarginDisplay: topMargin.toFixed(3),
  };
}

export const KNOWN_BILLING_DIST = deriveScenarioDistribution({
  billing: 0.9,
  technical: 0.033,
  sales: 0.017,
  UNKNOWN: 0.05,
});

export const UNKNOWN_CANCEL_DIST = deriveScenarioDistribution({
  billing: 0.017,
  technical: 0.017,
  sales: 0.016,
  UNKNOWN: 0.95,
});

export const REVIEW_COMPLIANCE_DIST = deriveScenarioDistribution({
  billing: 0.41,
  technical: 0.27,
  sales: 0.1,
  UNKNOWN: 0.22,
});

export const ERROR_OUTAGE_DIST = deriveScenarioDistribution(
  {
    billing: 0,
    technical: 0,
    sales: 0,
    UNKNOWN: 0,
  },
  { isError: true },
);

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
  probabilities: StageProbability[];
  telemetry: {
    ontologyVersion: string;
    topClass: string;
    unknownProb: string;
    topMarginDisplay: string;
    topProbability: number | null;
    unknownProbability: number;
    topMargin: number;
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
  probabilities: StageProbability[];
  steps: [StageStepSpec, StageStepSpec, StageStepSpec, StageStepSpec, StageStepSpec];
}

/**
 * Four grounded runtime traces modeled directly on OpenClass's actual domain
 * rules (`examples/support-intents/classifier.json`, `novelty.py`,
 * `supervisor.py`, and `project_evolution.py`).
 */
export const PREDEFINED_SCENARIOS: readonly PresetScenario[] = [
  {
    id: "known_billing",
    badge: "FAST PATH · KNOWN",
    shortTitle: "01 / Known Intent",
    observation: "I was charged twice for my monthly invoice",
    sublabel: `Matches supported class \`${KNOWN_BILLING_DIST.topLabel}\` (${KNOWN_BILLING_DIST.topDisplay}) with ${KNOWN_BILLING_DIST.topMarginDisplay} margin → immediate fast-path commit`,
    accentTone: "known",
    probabilities: KNOWN_BILLING_DIST.probabilities,
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
        probabilities: KNOWN_BILLING_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: `${KNOWN_BILLING_DIST.topLabel} (${KNOWN_BILLING_DIST.topDisplay})`,
          unknownProb: `${KNOWN_BILLING_DIST.unknownDisplay}`,
          topMarginDisplay: `${KNOWN_BILLING_DIST.topMarginDisplay}`,
          topProbability: KNOWN_BILLING_DIST.topProbability,
          unknownProbability: KNOWN_BILLING_DIST.unknownProbability,
          topMargin: KNOWN_BILLING_DIST.topMargin,
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
        traceSnippet: `{"probabilities": {"billing": ${KNOWN_BILLING_DIST.topDisplay}, "technical": 0.033, "sales": 0.017}, "unknown_probability": ${KNOWN_BILLING_DIST.unknownDisplay}}`,
        probabilities: KNOWN_BILLING_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: `${KNOWN_BILLING_DIST.topLabel} (${KNOWN_BILLING_DIST.topDisplay})`,
          unknownProb: `${KNOWN_BILLING_DIST.unknownDisplay} (below 0.450 ceiling)`,
          topMarginDisplay: `${KNOWN_BILLING_DIST.topMarginDisplay} (above 0.200 gate)`,
          topProbability: KNOWN_BILLING_DIST.topProbability,
          unknownProbability: KNOWN_BILLING_DIST.unknownProbability,
          topMargin: KNOWN_BILLING_DIST.topMargin,
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
        narration: `Because unknown_probability (${KNOWN_BILLING_DIST.unknownDisplay}) < 0.450 and top_margin (${KNOWN_BILLING_DIST.topMarginDisplay}) >= 0.200, deterministic core policy marks the decision TRUSTED / KNOWN.`,
        traceSnippet: `{"novelty": {"state": "known", "score": ${KNOWN_BILLING_DIST.unknownDisplay}, "reasons": ["known_class_supported"]}, "top_probability": ${KNOWN_BILLING_DIST.topDisplay}, "top_margin": ${KNOWN_BILLING_DIST.topMarginDisplay}, "supervision": "TRUSTED"}`,
        probabilities: KNOWN_BILLING_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: `${KNOWN_BILLING_DIST.topLabel} (${KNOWN_BILLING_DIST.topDisplay})`,
          unknownProb: `${KNOWN_BILLING_DIST.unknownDisplay}`,
          topMarginDisplay: `${KNOWN_BILLING_DIST.topMarginDisplay} >= 0.200`,
          topProbability: KNOWN_BILLING_DIST.topProbability,
          unknownProbability: KNOWN_BILLING_DIST.unknownProbability,
          topMargin: KNOWN_BILLING_DIST.topMargin,
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
        traceSnippet: `{"run_id": "run_94a1f0", "selected_class": "billing", "top_probability": ${KNOWN_BILLING_DIST.topDisplay}, "top_margin": ${KNOWN_BILLING_DIST.topMarginDisplay}, "ontology_version_id": "v1", "unknown_pool_write": false}`,
        probabilities: KNOWN_BILLING_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: `${KNOWN_BILLING_DIST.topLabel} (${KNOWN_BILLING_DIST.topDisplay})`,
          unknownProb: `${KNOWN_BILLING_DIST.unknownDisplay}`,
          topMarginDisplay: `${KNOWN_BILLING_DIST.topMarginDisplay}`,
          topProbability: KNOWN_BILLING_DIST.topProbability,
          unknownProbability: KNOWN_BILLING_DIST.unknownProbability,
          topMargin: KNOWN_BILLING_DIST.topMargin,
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
        probabilities: KNOWN_BILLING_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (locked)",
          topClass: `${KNOWN_BILLING_DIST.topLabel} (${KNOWN_BILLING_DIST.topDisplay})`,
          unknownProb: `${KNOWN_BILLING_DIST.unknownDisplay}`,
          topMarginDisplay: `${KNOWN_BILLING_DIST.topMarginDisplay}`,
          topProbability: KNOWN_BILLING_DIST.topProbability,
          unknownProbability: KNOWN_BILLING_DIST.unknownProbability,
          topMargin: KNOWN_BILLING_DIST.topMargin,
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
    sublabel: `Unsupported by {billing, technical, sales} → persisted as UNKNOWN (${UNKNOWN_CANCEL_DIST.unknownDisplay}) → clustered → gated candidate`,
    accentTone: "unknown",
    probabilities: UNKNOWN_CANCEL_DIST.probabilities,
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
        probabilities: UNKNOWN_CANCEL_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (billing, technical, sales)",
          topClass: `UNKNOWN (${UNKNOWN_CANCEL_DIST.topDisplay})`,
          unknownProb: `${UNKNOWN_CANCEL_DIST.unknownDisplay}`,
          topMarginDisplay: `${UNKNOWN_CANCEL_DIST.topMarginDisplay}`,
          topProbability: UNKNOWN_CANCEL_DIST.topProbability,
          unknownProbability: UNKNOWN_CANCEL_DIST.unknownProbability,
          topMargin: UNKNOWN_CANCEL_DIST.topMargin,
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
        headline: `DecisionProvider assigns ${UNKNOWN_CANCEL_DIST.unknownDisplay} probability mass to UNKNOWN.`,
        narration: `All known classes score <= ${UNKNOWN_CANCEL_DIST.secondDisplay}. Rather than hallucinating a label, the bounded choice distribution surfaces strong_unknown_probability (${UNKNOWN_CANCEL_DIST.unknownDisplay}).`,
        traceSnippet: `{"selected_class": null, "unknown_probability": ${UNKNOWN_CANCEL_DIST.unknownDisplay}, "novelty": {"state": "likely_novel", "score": ${UNKNOWN_CANCEL_DIST.unknownDisplay}, "reasons": ["strong_unknown_probability"]}}`,
        probabilities: UNKNOWN_CANCEL_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: `UNKNOWN (${UNKNOWN_CANCEL_DIST.topDisplay} · max known ${UNKNOWN_CANCEL_DIST.secondDisplay})`,
          unknownProb: `${UNKNOWN_CANCEL_DIST.unknownDisplay} (exceeds threshold)`,
          topMarginDisplay: `${UNKNOWN_CANCEL_DIST.topMarginDisplay} (known margin 0.000)`,
          topProbability: UNKNOWN_CANCEL_DIST.topProbability,
          unknownProbability: UNKNOWN_CANCEL_DIST.unknownProbability,
          topMargin: UNKNOWN_CANCEL_DIST.topMargin,
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
        traceSnippet: `INSERT INTO evidence_items (trigger_type, status, selected_choice, unknown_probability) VALUES ('semantic_unknown', 'pending', 'UNKNOWN', ${UNKNOWN_CANCEL_DIST.unknownDisplay});`,
        probabilities: UNKNOWN_CANCEL_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (unchanged)",
          topClass: `UNKNOWN (${UNKNOWN_CANCEL_DIST.topDisplay} · selected_class: null)`,
          unknownProb: `${UNKNOWN_CANCEL_DIST.unknownDisplay}`,
          topMarginDisplay: `${UNKNOWN_CANCEL_DIST.topMarginDisplay}`,
          topProbability: UNKNOWN_CANCEL_DIST.topProbability,
          unknownProbability: UNKNOWN_CANCEL_DIST.unknownProbability,
          topMargin: UNKNOWN_CANCEL_DIST.topMargin,
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
        probabilities: UNKNOWN_CANCEL_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (still active)",
          topClass: `UNKNOWN (${UNKNOWN_CANCEL_DIST.topDisplay}); cancellation is an inactive proposal`,
          unknownProb: `${UNKNOWN_CANCEL_DIST.unknownDisplay} (evidence n=3)`,
          topMarginDisplay: `${UNKNOWN_CANCEL_DIST.topMarginDisplay} (original observation)`,
          topProbability: UNKNOWN_CANCEL_DIST.topProbability,
          unknownProbability: UNKNOWN_CANCEL_DIST.unknownProbability,
          topMargin: UNKNOWN_CANCEL_DIST.topMargin,
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
        probabilities: UNKNOWN_CANCEL_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 → v2 gated (OC-008 / OC-009)",
          topClass: `UNKNOWN (${UNKNOWN_CANCEL_DIST.topDisplay}); candidate awaiting verified replay`,
          unknownProb: `${UNKNOWN_CANCEL_DIST.unknownDisplay} (post-change result not yet measured)`,
          topMarginDisplay: `${UNKNOWN_CANCEL_DIST.topMarginDisplay} (requires 0 regressions)`,
          topProbability: UNKNOWN_CANCEL_DIST.topProbability,
          unknownProbability: UNKNOWN_CANCEL_DIST.unknownProbability,
          topMargin: UNKNOWN_CANCEL_DIST.topMargin,
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
    sublabel: `Split distribution (billing ${REVIEW_COMPLIANCE_DIST.topDisplay} vs technical ${REVIEW_COMPLIANCE_DIST.secondDisplay}, margin ${REVIEW_COMPLIANCE_DIST.topMarginDisplay} < 0.200) → advisory Supervisor review`,
    accentTone: "review",
    probabilities: REVIEW_COMPLIANCE_DIST.probabilities,
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
        probabilities: REVIEW_COMPLIANCE_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: `${REVIEW_COMPLIANCE_DIST.topLabel} (${REVIEW_COMPLIANCE_DIST.topDisplay})`,
          unknownProb: `${REVIEW_COMPLIANCE_DIST.unknownDisplay}`,
          topMarginDisplay: `${REVIEW_COMPLIANCE_DIST.topMarginDisplay} (< 0.200 min_margin)`,
          topProbability: REVIEW_COMPLIANCE_DIST.topProbability,
          unknownProbability: REVIEW_COMPLIANCE_DIST.unknownProbability,
          topMargin: REVIEW_COMPLIANCE_DIST.topMargin,
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
        headline: `Top-2 classes collide: billing (${REVIEW_COMPLIANCE_DIST.topDisplay}) vs. technical (${REVIEW_COMPLIANCE_DIST.secondDisplay}).`,
        narration: `The model selects 'billing' (${REVIEW_COMPLIANCE_DIST.topDisplay}), but the top-2 margin against 'technical' (${REVIEW_COMPLIANCE_DIST.secondDisplay}) is only ${REVIEW_COMPLIANCE_DIST.topMarginDisplay}—below the 0.200 minimum safety margin required for autonomous trust.`,
        traceSnippet: `{"probabilities": {"billing": ${REVIEW_COMPLIANCE_DIST.topDisplay}, "technical": ${REVIEW_COMPLIANCE_DIST.secondDisplay}, "sales": 0.100}, "unknown_probability": ${REVIEW_COMPLIANCE_DIST.unknownDisplay}, "top_margin": ${REVIEW_COMPLIANCE_DIST.topMarginDisplay}}`,
        probabilities: REVIEW_COMPLIANCE_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: `${REVIEW_COMPLIANCE_DIST.topLabel} (${REVIEW_COMPLIANCE_DIST.topDisplay})`,
          unknownProb: `${REVIEW_COMPLIANCE_DIST.unknownDisplay}`,
          topMarginDisplay: `${REVIEW_COMPLIANCE_DIST.topMarginDisplay} (< 0.200 min_margin)`,
          topProbability: REVIEW_COMPLIANCE_DIST.topProbability,
          unknownProbability: REVIEW_COMPLIANCE_DIST.unknownProbability,
          topMargin: REVIEW_COMPLIANCE_DIST.topMargin,
          noveltyState: "ambiguous_review",
          outcomeBadge: `LOW MARGIN DETECTED (${REVIEW_COMPLIANCE_DIST.topMarginDisplay})`,
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
        traceSnippet: `{"supervision_outcome": "REVIEW", "supervision_reason": "Margin ${REVIEW_COMPLIANCE_DIST.topMarginDisplay} below safety threshold 0.200", "probabilities": {"billing": ${REVIEW_COMPLIANCE_DIST.topDisplay}, "technical": ${REVIEW_COMPLIANCE_DIST.secondDisplay}, "sales": 0.100}, "unknown_probability": ${REVIEW_COMPLIANCE_DIST.unknownDisplay}, "trigger_type": "low_trust"}`,
        probabilities: REVIEW_COMPLIANCE_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: `${REVIEW_COMPLIANCE_DIST.topLabel} (${REVIEW_COMPLIANCE_DIST.topDisplay} · flagged)`,
          unknownProb: `${REVIEW_COMPLIANCE_DIST.unknownDisplay}`,
          topMarginDisplay: `${REVIEW_COMPLIANCE_DIST.topMarginDisplay} < 0.200`,
          topProbability: REVIEW_COMPLIANCE_DIST.topProbability,
          unknownProbability: REVIEW_COMPLIANCE_DIST.unknownProbability,
          topMargin: REVIEW_COMPLIANCE_DIST.topMargin,
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
        probabilities: REVIEW_COMPLIANCE_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: `${REVIEW_COMPLIANCE_DIST.topLabel} (${REVIEW_COMPLIANCE_DIST.topDisplay} · advisory check)`,
          unknownProb: `${REVIEW_COMPLIANCE_DIST.unknownDisplay}`,
          topMarginDisplay: `${REVIEW_COMPLIANCE_DIST.topMarginDisplay}`,
          topProbability: REVIEW_COMPLIANCE_DIST.topProbability,
          unknownProbability: REVIEW_COMPLIANCE_DIST.unknownProbability,
          topMargin: REVIEW_COMPLIANCE_DIST.topMargin,
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
        probabilities: REVIEW_COMPLIANCE_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (unchanged)",
          topClass: `${REVIEW_COMPLIANCE_DIST.topLabel} (${REVIEW_COMPLIANCE_DIST.topDisplay} · run preserved)`,
          unknownProb: `${REVIEW_COMPLIANCE_DIST.unknownDisplay}`,
          topMarginDisplay: `${REVIEW_COMPLIANCE_DIST.topMarginDisplay}`,
          topProbability: REVIEW_COMPLIANCE_DIST.topProbability,
          unknownProbability: REVIEW_COMPLIANCE_DIST.unknownProbability,
          topMargin: REVIEW_COMPLIANCE_DIST.topMargin,
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
    probabilities: ERROR_OUTAGE_DIST.probabilities,
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
        probabilities: ERROR_OUTAGE_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "awaiting provider…",
          unknownProb: "—",
          topMarginDisplay: "—",
          topProbability: null,
          unknownProbability: ERROR_OUTAGE_DIST.unknownProbability,
          topMargin: ERROR_OUTAGE_DIST.topMargin,
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
        probabilities: ERROR_OUTAGE_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "N/A (ProviderError)",
          unknownProb: "N/A (not scored)",
          topMarginDisplay: "N/A",
          topProbability: null,
          unknownProbability: ERROR_OUTAGE_DIST.unknownProbability,
          topMargin: ERROR_OUTAGE_DIST.topMargin,
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
        probabilities: ERROR_OUTAGE_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "aborted cleanly",
          unknownProb: "0 unknown writes",
          topMarginDisplay: "—",
          topProbability: null,
          unknownProbability: ERROR_OUTAGE_DIST.unknownProbability,
          topMargin: ERROR_OUTAGE_DIST.topMargin,
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
        probabilities: ERROR_OUTAGE_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (immutable)",
          topClass: "none",
          unknownProb: "unpolluted (0 rows)",
          topMarginDisplay: "—",
          topProbability: null,
          unknownProbability: ERROR_OUTAGE_DIST.unknownProbability,
          topMargin: ERROR_OUTAGE_DIST.topMargin,
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
        probabilities: ERROR_OUTAGE_DIST.probabilities,
        telemetry: {
          ontologyVersion: "v1 · 891dc20d (intact)",
          topClass: "retryable via SDK",
          unknownProb: "—",
          topMarginDisplay: "—",
          topProbability: null,
          unknownProbability: ERROR_OUTAGE_DIST.unknownProbability,
          topMargin: ERROR_OUTAGE_DIST.topMargin,
          noveltyState: "provider_error",
          outcomeBadge: "OBSERVABLE & RECOVERABLE",
          authorityRule: "Idempotency keys prevent duplicate ingestion on client retry.",
        },
      },
    ],
  },
] as const;

export const PRESET_SCENARIOS = PREDEFINED_SCENARIOS;

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
  const stageId = useId();

  // Detect OS/browser reduced-motion preference safely (SSR & JSDOM safe).
  const [reducedMotion, setReducedMotion] = useState<boolean>(() => {
    if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
      return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    }
    return false;
  });

  const [presetId, setPresetId] = useState<PresetId>("unknown_cancel");
  const [stepIndex, setStepIndex] = useState<StageStepIndex>(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [animateStep, setAnimateStep] = useState(false);
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
    const timer = window.setTimeout(() => {
      if (stepIndex === 4) {
        setIsPlaying(false);
      } else {
        setStepIndex((stepIndex + 1) as StageStepIndex);
      }
    }, 2800);
    return () => window.clearTimeout(timer);
  }, [isPlaying, isInView, isDocVisible, reducedMotion, presetId, stepIndex]);

  function selectPreset(nextId: PresetId, animate = false) {
    setPresetId(nextId);
    setStepIndex(0);
    setIsPlaying(false);
    setAnimateStep(animate);
    const chosen = PRESET_SCENARIOS.find((p) => p.id === nextId);
    if (chosen && onSelectObservation && nextId !== "error_timeout") {
      onSelectObservation(chosen.observation);
    }
  }

  function selectStep(index: StageStepIndex, animate = false) {
    setIsPlaying(false);
    setAnimateStep(animate);
    setStepIndex(index);
  }

  function navigateScenarios(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const next =
      event.key === "ArrowRight"
        ? (index + 1) % PRESET_SCENARIOS.length
        : event.key === "ArrowLeft"
          ? (index + PRESET_SCENARIOS.length - 1) % PRESET_SCENARIOS.length
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? PRESET_SCENARIOS.length - 1
              : null;
    if (next === null) return;
    event.preventDefault();
    selectPreset(PRESET_SCENARIOS[next]!.id, false);
    document.getElementById(`${stageId}-scenario-${next}`)?.focus();
  }

  const isAutoplayActive = isPlaying && isInView && isDocVisible && !reducedMotion;
  const activeTargetNodeId = activeStep.activeNodes[activeStep.activeNodes.length - 1];
  const activeTargetNode = DIAGRAM_NODES.find((node) => node.id === activeTargetNodeId);
  const packetSocketX = activeTargetNode
    ? activeTargetNode.x + activeTargetNode.w - 14
    : activeStep.packetCoord.x;
  const packetSocketY = activeTargetNode ? activeTargetNode.y + 18 : activeStep.packetCoord.y;

  return (
    <section
      id="open-world-loop"
      ref={stageRef}
      className={`oc-observatory-stage tone-${activePreset.accentTone}`}
      data-motion={animateStep && !reducedMotion ? "animate" : "instant"}
      data-playing={isAutoplayActive ? "true" : "false"}
      aria-label="Interactive open-world decision and governed discovery architecture"
    >
      {/* Top Instrument Control Bar: Scenario Presets + Playback Toggle */}
      <div className="oc-stage-topbar">
        <div className="oc-stage-title-block">
          <span className="oc-demo-label">SIMULATED WALKTHROUGH · NO PROVIDER CALLS</span>
          <h2>One input. A more considered path.</h2>
          <p>Choose a scenario. Follow the decision, not just the prediction.</p>
        </div>
        <div className="oc-playback-controls">
          <button
            type="button"
            className="oc-play-btn"
            onClick={(event) => {
              setAnimateStep(event.detail > 0);
              if (!isPlaying && stepIndex === 4) setStepIndex(0);
              setIsPlaying((prev) => !prev);
            }}
            aria-pressed={isPlaying}
            disabled={reducedMotion}
            aria-describedby={reducedMotion ? `${stageId}-motion-note` : undefined}
          >
            {isPlaying ? "Pause walkthrough" : "Play walkthrough"}
          </button>
          <span className="oc-stage-clock">
            STEP {stepIndex + 1} / 5 · {activePreset.badge}
          </span>
        </div>
      </div>
      {reducedMotion && (
        <p id={`${stageId}-motion-note`} className="oc-motion-note">
          Reduced motion is on. Choose any step to explore at your own pace.
        </p>
      )}

      {/* Scenario Selector Pills */}
      <div className="oc-preset-bar" role="tablist" aria-label="Decision trace scenarios">
        {PRESET_SCENARIOS.map((preset, index) => {
          const isSelected = preset.id === presetId;
          return (
            <button
              key={preset.id}
              id={`${stageId}-scenario-${index}`}
              type="button"
              role="tab"
              aria-selected={isSelected}
              aria-controls={`${stageId}-scenario-panel`}
              tabIndex={isSelected ? 0 : -1}
              className={`oc-preset-pill tone-${preset.accentTone} ${isSelected ? "active" : ""}`}
              onClick={(event) => selectPreset(preset.id, event.detail > 0)}
              onKeyDown={(event) => navigateScenarios(event, index)}
            >
              <span className="oc-preset-kicker">{preset.shortTitle}</span>
              <strong className="oc-preset-obs">“{preset.observation}”</strong>
              <span className="oc-preset-sub">{preset.badge}</span>
            </button>
          );
        })}
      </div>

      {/* Main Split: Code-Native SVG Architecture Canvas + Live Telemetry Inspector */}
      <div
        className="oc-stage-shell"
        id={`${stageId}-scenario-panel`}
        role="tabpanel"
        aria-labelledby={`${stageId}-scenario-${PRESET_SCENARIOS.indexOf(activePreset)}`}
      >
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

            {/* Top-Left Routing Gate Calibration Schematic (fills void cleanly) */}
            <g className="oc-svg-gate-legend" aria-hidden="true">
              <rect x="16" y="24" width="548" height="108" rx="10" className="oc-gate-legend-box" />
              <text x="30" y="44" className="oc-gate-legend-title">
                DETERMINISTIC ROUTING CALIBRATION · ONTOLOGY SNAPSHOT v1 (891dc20d)
              </text>
              <g
                className={`oc-gate-rule tone-known ${activePreset.accentTone === "known" ? "active" : ""}`}
              >
                <rect x="28" y="54" width="256" height="30" rx="6" />
                <circle cx="42" cy="69" r="3.5" />
                <text x="54" y="73">
                  LANE A · P(unk) &lt; 0.450 ∧ margin ≥ 0.200
                </text>
              </g>
              <g
                className={`oc-gate-rule tone-review ${activePreset.accentTone === "review" ? "active" : ""}`}
              >
                <rect x="296" y="54" width="256" height="30" rx="6" />
                <circle cx="310" cy="69" r="3.5" />
                <text x="322" y="73">
                  LANE B · P(unk) &lt; 0.450 ∧ margin &lt; 0.200
                </text>
              </g>
              <g
                className={`oc-gate-rule tone-unknown ${activePreset.accentTone === "unknown" ? "active" : ""}`}
              >
                <rect x="28" y="92" width="256" height="30" rx="6" />
                <circle cx="42" cy="107" r="3.5" />
                <text x="54" y="111">
                  LANE C · P(unk) ≥ 0.450 (ABSTAIN)
                </text>
              </g>
              <g
                className={`oc-gate-rule tone-error ${activePreset.accentTone === "error" ? "active" : ""}`}
              >
                <rect x="296" y="92" width="256" height="30" rx="6" />
                <circle cx="310" cy="107" r="3.5" />
                <text x="322" y="111">
                  LANE D · ProviderError 502 / Timeout
                </text>
              </g>
            </g>

            {/* Structural Lane Enclosure Bands */}
            <g className="oc-svg-lanes" aria-hidden="true">
              <rect
                x="16"
                y="148"
                width="522"
                height="106"
                rx="10"
                className="oc-lane-band tone-neutral"
              />
              <text x="26" y="164" className="oc-svg-lane-label tone-neutral">
                INGRESS &amp; BOUNDED SCORING SPINE
              </text>
              <rect
                x="592"
                y="24"
                width="354"
                height="108"
                rx="10"
                className={`oc-lane-band tone-known ${activePreset.accentTone === "known" ? "active" : ""}`}
              />
              <rect
                x="592"
                y="136"
                width="354"
                height="100"
                rx="10"
                className={`oc-lane-band tone-review ${activePreset.accentTone === "review" ? "active" : ""}`}
              />
              <rect
                x="376"
                y="240"
                width="570"
                height="98"
                rx="10"
                className={`oc-lane-band tone-unknown ${activePreset.accentTone === "unknown" ? "active" : ""}`}
              />
              <rect
                x="376"
                y="342"
                width="570"
                height="88"
                rx="10"
                className={`oc-lane-band tone-error ${activePreset.accentTone === "error" ? "active" : ""}`}
              />
            </g>

            {/* Lane Labels */}
            <text x="602" y="42" className="oc-svg-lane-label tone-known">
              LANE A · SYNCHRONOUS FAST PATH (TRUSTED KNOWN)
            </text>
            <text x="602" y="150" className="oc-svg-lane-label tone-review">
              LANE B · ASYNCHRONOUS SUPERVISOR AUDIT (OC-016)
            </text>
            <text x="602" y="256" className="oc-svg-lane-label tone-unknown">
              LANE C · PERMANENT UNKNOWN → TEACHER → REPLAY GATE
            </text>
            <text x="602" y="348" className="oc-svg-lane-label tone-error">
              LANE D · FAULT ISOLATION (ZERO UNKNOWN POLLUTION)
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
                  <circle
                    cx={node.x + node.w - 14}
                    cy={node.y + 18}
                    r="4"
                    className="oc-node-socket"
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

            {/* GPU-Composited Travelling Observation Packet (docked in active node socket) */}
            <g
              className={`oc-packet tone-${activePreset.accentTone}`}
              style={{
                transform: `translate3d(${packetSocketX}px, ${packetSocketY}px, 0)`,
              }}
            >
              <circle r="13" className="oc-packet-halo" />
              <circle r="5" className="oc-packet-core" />
            </g>
          </svg>

          <ol className="oc-mobile-loop" aria-label="Mobile decision loop">
            {activePreset.steps.map((step) => (
              <li
                key={step.index}
                className={
                  step.index === stepIndex ? "active" : step.index < stepIndex ? "completed" : ""
                }
              >
                <button
                  type="button"
                  aria-label={`Go to ${step.label}`}
                  aria-current={step.index === stepIndex ? "step" : undefined}
                  onClick={(event) => selectStep(step.index, event.detail > 0)}
                >
                  <span className="oc-mobile-step-number" aria-hidden="true">
                    {step.index + 1}
                  </span>
                  <span className="oc-mobile-step-copy">
                    <strong>{step.label}</strong>
                    <span>{step.headline}</span>
                    {step.index === stepIndex && <small>{step.telemetry.outcomeBadge}</small>}
                  </span>
                  <span className="oc-mobile-step-indicator" aria-hidden="true">
                    {step.index < stepIndex ? "✓" : step.index === stepIndex ? "↳" : ""}
                  </span>
                </button>
              </li>
            ))}
          </ol>

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
                  onClick={(event) => selectStep(step.index, event.detail > 0)}
                >
                  <span className="oc-step-code">{step.code}</span>
                  <span className="oc-step-label">{step.label}</span>
                  <span className="oc-step-progress" aria-hidden="true" />
                </button>
              );
            })}
          </div>
          <div className="oc-step-navigation" aria-label="Walkthrough navigation">
            <button
              type="button"
              disabled={stepIndex === 0}
              onClick={(event) => selectStep((stepIndex - 1) as StageStepIndex, event.detail > 0)}
            >
              Previous
            </button>
            <span aria-live={isPlaying ? "off" : "polite"}>STEP {stepIndex + 1} / 5</span>
            <button
              type="button"
              disabled={stepIndex === 4}
              onClick={(event) => selectStep((stepIndex + 1) as StageStepIndex, event.detail > 0)}
            >
              Next
            </button>
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
            <h3 className="oc-inspector-headline" key={`${presetId}-${stepIndex}`}>
              {activeStep.headline}
            </h3>
            <p className="oc-inspector-narration">{activeStep.narration}</p>

            {/* GPU-Composited Probability Distribution Track (scaleX) */}
            <div className="oc-prob-block">
              <div className="oc-prob-header">
                <span>BOUNDED CHOICE DISTRIBUTION</span>
                <span>
                  {activePreset.id === "error_timeout" ? "∑ P = N/A (FAULT)" : "∑ P = 1.000"}
                </span>
              </div>
              {activeStep.probabilities.map((prob) => (
                <div
                  key={prob.label}
                  className={`oc-prob-row ${prob.isUnknown ? "is-unknown" : ""}`}
                >
                  <code className="oc-prob-label">{prob.label}</code>
                  <div
                    className={`oc-prob-track ${activePreset.id === "error_timeout" ? "is-fault" : ""}`}
                  >
                    <div
                      className={`oc-prob-fill ${prob.isUnknown ? "unknown" : ""}`}
                      style={{
                        transform: `scaleX(${activePreset.id === "error_timeout" ? 0 : Math.max(0.02, prob.value)})`,
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
                <dd>{activeStep.telemetry.topMarginDisplay}</dd>
              </div>
            </dl>

            {/* Wire / SQL Trace Snippet */}
            <details
              className="oc-trace-detail"
              onFocusCapture={() => setIsPlaying(false)}
              onToggle={(event) => {
                if (event.currentTarget.open) setIsPlaying(false);
              }}
            >
              <summary>Inspect the example payload</summary>
              <pre className="oc-trace-pre">
                <code>{activeStep.traceSnippet}</code>
              </pre>
            </details>

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

// Preserve the existing import boundary while architecture content stays separate.
export {
  ObservatoryArchitectureSections,
  GROUNDED_PROOFS,
  QUICKSTART_TABS,
} from "./observatory-sections";
