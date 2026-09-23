"use client";
import { useEffect, useState, type FormEvent } from "react";
import { OpenClass, type Classifier, type ClassificationResult } from "@openclass/sdk";
const client = new OpenClass("");

export default function Home() {
  const [classifiers, setClassifiers] = useState<Classifier[]>([]);
  const [classifier, setClassifier] = useState("");
  const [observation, setObservation] = useState("I was charged twice");
  const [result, setResult] = useState<ClassificationResult | null>(null);
  const [status, setStatus] = useState("Connecting");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

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
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(await client.classify({ classifier, observation }));
    } catch (error) {
      setError(error instanceof Error ? error.message : "Classification failed");
    } finally {
      setBusy(false);
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
              setClassifier(e.target.value);
              setResult(null);
            }}
            disabled={busy || !classifiers.length}
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
            disabled={busy}
          />
          <button disabled={busy || !classifier || !observation.trim()}>
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
