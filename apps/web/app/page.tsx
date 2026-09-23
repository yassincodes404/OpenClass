"use client";
import { useEffect, useRef, useState, type FormEvent, type MouseEvent } from "react";
import {
  OpenClass,
  type Classifier,
  type ClassificationResult,
  type SupervisorReview,
} from "@openclass/sdk";
const client = new OpenClass("");

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

  return (
    <main>
      <header>
        <a href="/" className="brand">
          <span className="mark">
            O<span>↗</span>
          </span>
          OPENCLASS
        </a>
        <span className="badge">GENESIS / 0.0.1</span>
      </header>
      <section className="intro">
        <p className="eyebrow">THE OPEN-WORLD CLASSIFICATION ENGINE</p>
        <h1>
          Start with what you know.
          <br />
          <span>Discover what you don’t.</span>
        </h1>
        <p className="lede">
          A classifier needs room to say “I don’t know.” Build your known world, observe what falls
          outside it, and keep the evidence.
        </p>
      </section>
      <div className="section-heading">
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
          <p className="hint">Mock provider · deterministic lexical matching · no API key</p>
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
      <footer>
        <span>Local first. Provider independent. Evidence driven.</span>
        <span>Discovery & promotion are on the roadmap.</span>
      </footer>
    </main>
  );
}
