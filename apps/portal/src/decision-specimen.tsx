import { useState, type CSSProperties } from "react";
import { UNKNOWN_CANCEL_DIST } from "./open-world-stage";

export function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
      <path d="M23.5 12.5A9 9 0 1 0 24 19" />
      <path d="M17.5 7.5h7v7" />
      <path d="m18 15 6.5-6.5" />
      <circle cx="9" cy="20" r="1.5" />
    </svg>
  );
}

const CLOSED_WORLD_FORCED_DIST = [
  { label: "billing", value: 0.542, display: "0.542", isUnknown: false, isForced: true },
  { label: "sales", value: 0.271, display: "0.271", isUnknown: false, isForced: false },
  { label: "technical", value: 0.187, display: "0.187", isUnknown: false, isForced: false },
] as const;

export function DecisionSpecimen() {
  const [mode, setMode] = useState<"open" | "closed">("open");
  const known = UNKNOWN_CANCEL_DIST.probabilities.filter((probability) => !probability.isUnknown);
  const unknown = UNKNOWN_CANCEL_DIST.probabilities.find((probability) => probability.isUnknown);
  const openRows = [...known, ...(unknown ? [unknown] : [])];

  return (
    <aside
      className={`decision-specimen is-${mode}-mode`}
      aria-label="Simulated classification example"
    >
      <div className="specimen-topline">
        <span>DECISION SPECIMEN / 002 · ONTOLOGY v1</span>
        <span className="specimen-simulated">
          <i aria-hidden="true" /> SIMULATED
        </span>
      </div>

      <div className="specimen-observation">
        <div className="specimen-observation-bar">
          <span>OBSERVATION</span>
          <div className="specimen-mode-switch" role="group" aria-label="Classification regime">
            <button
              type="button"
              className={`specimen-mode-btn ${mode === "open" ? "active" : ""}`}
              aria-pressed={mode === "open"}
              onClick={() => setMode("open")}
            >
              Open-world
            </button>
            <button
              type="button"
              className={`specimen-mode-btn ${mode === "closed" ? "active" : ""}`}
              aria-pressed={mode === "closed"}
              onClick={() => setMode("closed")}
            >
              Closed-world guess
            </button>
          </div>
        </div>
        <blockquote id="specimen-observation">“Cancel my plan.”</blockquote>
        <p>
          {mode === "open"
            ? "Three active classes. One open-world fallback."
            : "Closed 3-class softmax has no abstention path—every input is forced into a known label."}
        </p>
      </div>

      <div className="specimen-distribution">
        <div className="specimen-distribution-head">
          <span>
            {mode === "open"
              ? "BOUNDED DISTRIBUTION (+ FALLBACK)"
              : "CLOSED SOFTMAX (FORCED ARGMAX)"}
          </span>
          <span>∑ P = 1.000</span>
        </div>
        <ul aria-label="Simulated classification probabilities">
          {mode === "open"
            ? openRows.map((probability) => (
                <li
                  key={probability.label}
                  className={probability.isUnknown ? "is-unknown" : undefined}
                  style={{ "--specimen-scale": probability.value } as CSSProperties}
                >
                  <div>
                    <code>{probability.isUnknown ? "unknown_fallback" : probability.label}</code>
                    <span>{probability.display}</span>
                  </div>
                  <span className="specimen-track" aria-hidden="true">
                    <span className="specimen-fill" />
                  </span>
                </li>
              ))
            : CLOSED_WORLD_FORCED_DIST.map((probability) => (
                <li
                  key={probability.label}
                  className={probability.isForced ? "is-forced" : undefined}
                  style={{ "--specimen-scale": probability.value } as CSSProperties}
                >
                  <div>
                    <code>{probability.label}</code>
                    <span>{probability.display}</span>
                  </div>
                  <span className="specimen-track" aria-hidden="true">
                    <span className="specimen-fill" />
                  </span>
                </li>
              ))}
        </ul>
      </div>

      <div className="specimen-outcome">
        <span className="specimen-outcome-arrow" aria-hidden="true">
          {mode === "open" ? "↳" : "!"}
        </span>
        <div>
          <span>
            {mode === "open"
              ? "DECISION / ABSTAIN · EVIDENCE PRESERVED"
              : "CLOSED-WORLD FAILURE / FORCED LABEL"}
          </span>
          <strong>{mode === "open" ? "UNKNOWN" : "billing (forced)"}</strong>
          <p>
            {mode === "open"
              ? "Keep the observation as evidence—not a forced label."
              : "Misroutes cancellation into billing instead of recording UNKNOWN evidence."}
          </p>
        </div>
      </div>

      <div className="specimen-contrast-strip" aria-label="Regime comparison">
        <div>
          <span>CLOSED-WORLD SOFTMAX</span>
          <code>billing · 0.542 (wrong queue)</code>
        </div>
        <div>
          <span>OPENCLASS BOUNDED</span>
          <code>Abstain · 0.950 (evidence pool)</code>
        </div>
      </div>

      <p className="specimen-caption">
        Simulated example with a three-class ontology. Unknown does not automatically mean a new
        class.
      </p>
    </aside>
  );
}
