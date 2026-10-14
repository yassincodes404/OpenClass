"use client";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent, type MouseEvent } from "react";
import {
  OpenClass,
  type Classifier,
  type ClassificationResult,
  type SupervisorReview,
} from "@openclass/sdk";

const client = new OpenClass("");

interface LifecycleStageSpec {
  step: string;
  title: string;
  badge: string;
  tone: "known" | "unknown" | "review" | "teacher";
  summary: string;
  contract: string;
  code: string;
}

const LIFECYCLE_STAGES: readonly LifecycleStageSpec[] = [
  {
    step: "01 / OBSERVE",
    title: "Immutable Observation & Version Pinning",
    badge: "PINNED TO SNAPSHOT v1",
    tone: "known",
    summary:
      "Every incoming event is normalized and pinned to the active immutable OntologySnapshot before any model executes. Raw inputs are never overwritten by predictions.",
    contract: "packages/core/openclass_core/models.py :: ClassificationRun",
    code: `POST /api/v1/classifiers/support-intent/classify
{"observation": "Cancel my plan"}`,
  },
  {
    step: "02 / SCORE",
    title: "Bounded Fast-Path Probability Distribution",
    badge: "JEV · LAYA · MOCK",
    tone: "known",
    summary:
      "A fast bounded DecisionProvider scores the active closed class set plus explicit UNKNOWN mass under a strict grammar contract—with zero writable access to the ontology.",
    contract: "packages/core/openclass_core/providers.py :: DecisionProvider",
    code: `{
  "probabilities": {"billing": 0.017, "technical": 0.017, "sales": 0.016},
  "unknown_probability": 0.950
}`,
  },
  {
    step: "03 / POLICY",
    title: "Deterministic Novelty & Supervision Gate",
    badge: "CORE OWNS MECHANICS",
    tone: "unknown",
    summary:
      "Deterministic domain policy evaluates top-2 margin and unknown probability. Supported inputs commit on the fast path; unsupported inputs route to the permanent UNKNOWN pool.",
    contract: "packages/core/openclass_core/novelty.py :: NoveltyDetector",
    code: `{
  "selected_class": null,
  "novelty": {"state": "likely_novel", "score": 0.950}
}`,
  },
  {
    step: "04 / EVIDENCE",
    title: "Permanent Unknown Pool & Embedding Clusters",
    badge: "EVIDENCE ACCUMULATION",
    tone: "unknown",
    summary:
      "A single unknown observation is never treated as proof of a new class. Observations accumulate in the Unknown Pool and cluster by semantic similarity until evidence sufficiency is met.",
    contract: "packages/core/openclass_core/discovery.py :: DiscoveryService",
    code: `Cluster clu_cancel_01 (n = 3 observations)
centroid_similarity: 0.91 · status: ready_for_proposal`,
  },
  {
    step: "05 / REVIEW",
    title: "Advisory Supervisor & Inactive Teacher Proposal",
    badge: "ADVISORY ONLY",
    tone: "teacher",
    summary:
      "Off the critical path, the Supervisor inspects low-confidence runs and the Teacher proposes candidate classes with citations. Neither can mutate the active classification or ontology.",
    contract: "packages/core/openclass_core/supervisor.py :: SupervisorReview",
    code: `CandidateProposal {
  "proposed_name": "cancellation",
  "status": "pending_evaluation",
  "supporting_unknown_ids": ["unk_01", "unk_02", "unk_03"]
}`,
  },
  {
    step: "06 / EVOLVE",
    title: "Replay Evaluation Gate & Human Promotion (vN+1)",
    badge: "FAIL-CLOSED (OC-008/009)",
    tone: "review",
    summary:
      "Before any candidate can activate, it must pass historical replay evaluation without regressing known classes and receive explicit human approval—producing append-only OntologySnapshot v2.",
    contract: "packages/core/openclass_core/evolution.py :: EvolutionEngine",
    code: `OntologySnapshot v2 (parent: v1)
classes: ["billing", "technical", "sales", "cancellation"]`,
  },
];

const SAMPLE_OBSERVATIONS = [
  {
    label: "Known: Double charge (0.900)",
    value: "I was charged twice",
    tag: "FAST PATH",
  },
  {
    label: "Novel: Cancel plan (0.950)",
    value: "Cancel my plan",
    tag: "UNKNOWN POOL",
  },
  {
    label: "Review: EU audit export (0.410)",
    value: "Export compliance packet for EU invoice audit",
    tag: "SUPERVISION",
  },
] as const;

export default function Home() {
  const [classifiers, setClassifiers] = useState<Classifier[]>([]);
  const [classifier, setClassifier] = useState("");
  const [observation, setObservation] = useState("I was charged twice");
  const [result, setResult] = useState<ClassificationResult | null>(null);
  const [review, setReview] = useState<SupervisorReview | null>(null);
  const [status, setStatus] = useState("Connecting");
  const [error, setError] = useState("");
  const [reviewError, setReviewError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [activeStageIndex, setActiveStageIndex] = useState(0);

  const displayedRun = useRef<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([client.health(), client.classifiers()])
      .then(([, items]) => {
        if (!active) return;
        setStatus("Server ready");
        setClassifiers(items);
        setClassifier(items[0]?.slug ?? "");
      })
      .catch(() => {
        if (active) setStatus("Server unavailable · start the API and refresh");
      });
    return () => {
      active = false;
      displayedRun.current = null;
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || reviewBusy) return;
    displayedRun.current = null;
    setBusy(true);
    setError("");
    setResult(null);
    setReview(null);
    setReviewError("");
    try {
      const next = await client.classify({ classifier, observation });
      displayedRun.current = next.id;
      setResult(next);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Classification failed");
    } finally {
      setBusy(false);
    }
  }

  async function requestReview(event: MouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    if (!result || busy || reviewBusy) return;
    const runId = result.id;
    setReviewBusy(true);
    setReviewError("");
    setReview(null);
    try {
      const next = await client.reviewRun({ classifier, runId });
      if (displayedRun.current === runId && next.classification_run_id === runId) {
        setReview(next);
      }
    } catch (error) {
      if (displayedRun.current === runId) {
        setReviewError(error instanceof Error ? error.message : "Review failed");
      }
    } finally {
      setReviewBusy(false);
    }
  }

  const activeStage = LIFECYCLE_STAGES[activeStageIndex] ?? LIFECYCLE_STAGES[0];

  return (
    <main>
      <div className="web-telemetry-strip" aria-label="Genesis platform invariants">
        <span className="web-strip-pill">GENESIS v0.0.1 · AGPL-3.0</span>
        <span className="web-strip-item">
          <i>●</i> UNKNOWN IS PERMANENT
        </span>
        <span className="web-strip-item">
          <i>●</i> PREDICTIONS ≠ GROUND TRUTH
        </span>
        <span className="web-strip-item">
          <i>●</i> APPEND-ONLY ONTOLOGY SNAPSHOTS
        </span>
      </div>

      <section className="intro web-hero-grid">
        <div className="web-hero-copy">
          <p className="eyebrow">THE OPEN-WORLD CLASSIFICATION ENGINE</p>
          <h1>
            Start with what you know.
            <br />
            <span>Discover what you don’t.</span>
          </h1>
          <p className="lede">
            A classifier needs room to say “I don’t know.” Build your known world, observe what
            falls outside it, and keep the evidence—so proposed classes pass replay evaluation and
            human review before becoming versioned knowledge.
          </p>
          <div className="web-hero-actions">
            <a className="primary-link" href="#live-workspace">
              Try live classifier ↓
            </a>
            <Link className="quiet-link" href="/projects">
              Explore project control plane ↗
            </Link>
            <a className="quiet-link" href="#governed-loop">
              Inspect 6-stage loop ↓
            </a>
          </div>
        </div>

        <aside className="web-contrast-panel" aria-label="Closed-world vs OpenClass comparison">
          <div className="web-contrast-header">
            <span>TRACE COMPARISON</span>
            <code>“Cancel my plan”</code>
          </div>
          <div className="web-contrast-card bad">
            <div className="web-contrast-tag-row">
              <span className="web-chip error">CLOSED-WORLD MODEL</span>
              <code>FORCED GUESS</code>
            </div>
            <strong>Misroutes to known label (0.54)</strong>
            <p>
              Forces an unsupported cancellation request into the closest existing bucket,
              triggering the wrong automation and hiding missing ontology coverage.
            </p>
          </div>
          <div className="web-contrast-card good">
            <div className="web-contrast-tag-row">
              <span className="web-chip known">OPENCLASS ENGINE</span>
              <code>DISCIPLINED ABSTENTION</code>
            </div>
            <strong>Abstains to Unknown Pool (0.95) → Evidence</strong>
            <p>
              Preserves the full probability distribution, clusters recurring unknowns, and gates
              candidate promotion behind replay evaluation and human approval.
            </p>
          </div>
        </aside>
      </section>

      <div id="live-workspace" className="section-heading">
        <h2>Observation workspace</h2>
        <span className="status" role="status">
          {status}
        </span>
      </div>

      <div className="workspace">
        <form onSubmit={submit}>
          <p className="eyebrow">01 / OBSERVE</p>
          <label htmlFor="classifier">Classifier</label>
          <select
            id="classifier"
            value={classifier}
            onChange={(e) => {
              displayedRun.current = null;
              setClassifier(e.target.value);
              setResult(null);
              setReview(null);
              setReviewError("");
            }}
            disabled={busy || reviewBusy || !classifiers.length}
          >
            {!classifiers.length && <option value="">No classifier available</option>}
            {classifiers.map((item) => (
              <option key={item.id} value={item.slug}>
                {item.name}
              </option>
            ))}
          </select>
          {!classifiers.length && (
            <p className="hint">
              Create your first classifier with{" "}
              <code>openclass init examples/support-intents/classifier.json</code>, then refresh.
            </p>
          )}
          <label htmlFor="observation">Observation</label>
          <div className="web-sample-pills" aria-label="Sample observations">
            {SAMPLE_OBSERVATIONS.map((sample) => (
              <button
                key={sample.label}
                type="button"
                aria-pressed={observation === sample.value}
                className={
                  observation === sample.value ? "web-sample-pill active" : "web-sample-pill"
                }
                disabled={busy || reviewBusy}
                onClick={() => setObservation(sample.value)}
              >
                <span>{sample.label}</span>
                <small>{sample.tag}</small>
              </button>
            ))}
          </div>
          <textarea
            id="observation"
            value={observation}
            onChange={(e) => setObservation(e.target.value)}
            maxLength={100000}
            rows={5}
            required
            disabled={busy || reviewBusy}
          />
          <button disabled={busy || reviewBusy || !classifier || !observation.trim()}>
            {busy ? "Classifying…" : "Classify observation ↗"}
          </button>
          <p className="hint">Decision provider configured on the server</p>
        </form>
        <section className="result" aria-live="polite">
          <p className="eyebrow">02 / UNDERSTAND</p>
          {error ? (
            <p role="alert">{error}</p>
          ) : result ? (
            <>
              <span className={`result-state ${result.novelty.state}`}>
                {result.novelty.state.replaceAll("_", " ")}
              </span>
              <h3>{result.selected_class ?? "UNKNOWN"}</h3>
              <p>
                {result.selected_class
                  ? "Represented by the current ontology."
                  : "Saved to the unknown pool for future discovery. This is not yet a new-class proposal."}
              </p>
              <dl>
                <dt>Novelty score</dt>
                <dd>{result.novelty.score.toFixed(2)}</dd>
                <dt>Decision provider</dt>
                <dd>{result.decision.provider}</dd>
              </dl>
              <p className="hint">
                {result.novelty.reasons.map((reason) => reason.replaceAll("_", " ")).join(" · ")}
              </p>
              <div className="review">
                <p className="eyebrow">03 / REVIEW</p>
                <button type="button" onClick={requestReview} disabled={reviewBusy || !result.id}>
                  {reviewBusy ? "Reviewing…" : "Review with Supervisor ↗"}
                </button>
                {reviewError && <p role="alert">{reviewError}</p>}
                {review && review.classification_run_id === result.id && (
                  <div className="review-result">
                    <span className={`finding ${review.result.finding}`}>
                      {review.result.finding.replaceAll("_", " ")}
                    </span>
                    <dl>
                      <dt>Supervisor</dt>
                      <dd>{review.result.provider}</dd>
                      <dt>Confidence</dt>
                      <dd>{review.result.confidence.toFixed(2)}</dd>
                      <dt>Recommendation</dt>
                      <dd>{review.result.recommendation.replaceAll("_", " ")}</dd>
                      {review.result.suspected_class && (
                        <>
                          <dt>Suspected class</dt>
                          <dd>{review.result.suspected_class}</dd>
                        </>
                      )}
                    </dl>
                    <p>{review.result.rationale}</p>
                    <p className="hint">
                      {review.result.provider_metadata.simulated === true
                        ? "Simulated advisory finding"
                        : "Advisory finding"}{" "}
                      · a review never changes the classification
                    </p>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="empty">
              <span>?</span>
              <h3>Room for the unknown.</h3>
              <p>Submit an observation to see its classification and the reasons behind it.</p>
            </div>
          )}
        </section>
      </div>

      {/* Interactive 6-Stage Governed Lifecycle Explorer */}
      <section
        id="governed-loop"
        className="web-lifecycle-section"
        aria-label="Six-stage governed evolution loop"
      >
        <div className="web-lifecycle-header">
          <div>
            <p className="eyebrow">GOVERNED EVOLUTION ARCHITECTURE</p>
            <h2>How uncertainty becomes versioned knowledge—without silent drift.</h2>
          </div>
          <p className="muted">
            Select any stage in the pipeline to inspect its domain boundary and runtime payload.
          </p>
        </div>

        <div className="web-stage-tabs" role="tablist" aria-label="Evolution pipeline stages">
          {LIFECYCLE_STAGES.map((stage, idx) => (
            <button
              key={stage.step}
              type="button"
              role="tab"
              aria-selected={activeStageIndex === idx}
              className={
                activeStageIndex === idx
                  ? `web-stage-tab active ${stage.tone}`
                  : `web-stage-tab ${stage.tone}`
              }
              onClick={() => setActiveStageIndex(idx)}
            >
              <span className="web-stage-code">{stage.step}</span>
              <strong>{stage.title}</strong>
            </button>
          ))}
        </div>

        <div className="web-stage-detail" role="tabpanel">
          <div className="web-stage-narrative">
            <span className={`web-chip ${activeStage.tone}`}>{activeStage.badge}</span>
            <h3>{activeStage.title}</h3>
            <p>{activeStage.summary}</p>
            <div className="web-stage-contract">
              <span>DOMAIN CONTRACT</span>
              <code>{activeStage.contract}</code>
            </div>
          </div>
          <div className="web-stage-codebox">
            <div className="web-stage-codehead">
              <span>RUNTIME ARTIFACT</span>
              <code>JSON / LEDGER TRACE</code>
            </div>
            <pre>
              <code>{activeStage.code}</code>
            </pre>
          </div>
        </div>
      </section>

      {/* Architectural Invariants Grid */}
      <section className="web-invariants-section" aria-label="Core architectural invariants">
        <p className="eyebrow">NON-NEGOTIABLE DOMAIN RULES</p>
        <h2>Engineered for high-consequence open-world systems.</h2>
        <div className="web-invariants-grid">
          <article className="web-invariant-card">
            <span className="web-chip unknown">INVARIANT 01</span>
            <h4>Abstention is permanent first-class data</h4>
            <p>
              Unfamiliar inputs are never squeezed into the closest existing label. They persist in
              the Unknown Pool with full probability distributions and novelty scores.
            </p>
          </article>
          <article className="web-invariant-card">
            <span className="web-chip teacher">INVARIANT 02</span>
            <h4>Teacher owns meaning; Core owns mechanics</h4>
            <p>
              Providers and Teacher models never receive writable ontology access. They emit bounded
              proposals that deterministic core policy validates and records.
            </p>
          </article>
          <article className="web-invariant-card">
            <span className="web-chip review">INVARIANT 03</span>
            <h4>Fail-closed replay &amp; human approval</h4>
            <p>
              Candidate classes remain inactive until historical replay evaluation (`OC-008`) and
              human promotion (`OC-009`) create an append-only OntologySnapshot `vN+1`.
            </p>
          </article>
        </div>
      </section>

      <footer>
        <span>Local first. Provider independent. Evidence driven.</span>
        <span>Discovery &amp; promotion are on the roadmap.</span>
      </footer>
    </main>
  );
}
