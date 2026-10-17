import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

const REPOSITORY = "https://github.com/yassincodes404/OpenClass/blob/main/";

export const GROUNDED_PROOFS = [
  {
    id: "support-intents",
    tag: "01 / SUPPORT INTENT ROUTING",
    title: "A request your classes do not cover.",
    artifactPath: "examples/support-intents/classifier.json",
    kind: "Simulated example",
    summary: "Billing, technical, and sales are the starting point. Cancellation stays UNKNOWN.",
    steps: [
      ["Classify", "A supported billing request can select billing."],
      ["Abstain", "An unfamiliar cancellation request remains evidence, not a forced label."],
      ["Review", "A proposal still needs verified evaluation and human approval."],
    ],
    limitation: "The no-key mock checks the mechanism. It is not a model accuracy benchmark.",
  },
  {
    id: "devops-port-macro",
    tag: "02 / DEVOPS RECOVERY MACRO",
    title: "A recovery procedure that must earn reuse.",
    artifactPath: "docs/guides/automation-proof2.md",
    kind: "Frozen research",
    summary: "A bounded port-conflict experiment separates a proposed fix from a verified outcome.",
    steps: [
      ["Safe stop", "The baseline stops at a blocked operation."],
      ["Bounded Macro Synthesis", "A Teacher proposes a sequence of registered primitives."],
      [
        "Independent check",
        "Socket, report, and regression checks decide whether the proposal works.",
      ],
    ],
    limitation:
      "This is a retained research protocol, not evidence of arbitrary autonomous incident recovery.",
  },
  {
    id: "policy-graph-v4",
    tag: "03 / MULTI-LAYER POLICY EVOLUTION",
    title: "Fix the right layer. Keep the history.",
    artifactPath: "docs/architecture/adr-research-phase-complete.md",
    kind: "Frozen research",
    summary: "Retained experiments distinguish changes to choices, procedures, and state.",
    steps: [
      ["Decision space", "Propose a missing choice without changing execution authority."],
      ["Procedure", "Repair a registered procedure without silently rewriting routing."],
      ["State", "Make relevant state explicit, then re-evaluate the candidate."],
    ],
    limitation: "Research results apply to the published fixtures, not every production domain.",
  },
] as const;

export const QUICKSTART_TABS = [
  {
    id: "cli",
    label: "Docker",
    code: `# From a fresh checkout. Uses the simulated mock provider.
git clone https://github.com/yassincodes404/OpenClass.git
cd OpenClass
docker compose --env-file .env.example up --build -d --wait

docker compose exec server openclass init examples/support-intents/classifier.json
docker compose exec server openclass classify "I was charged twice"
docker compose exec server openclass classify "Cancel my plan"
docker compose exec server openclass unknowns --classifier support-intent`,
  },
  {
    id: "ts-sdk",
    label: "TypeScript SDK",
    code: `// Use the workspace SDK with your running local server.
import { OpenClass } from "@openclass/sdk";

const client = new OpenClass("http://localhost:7331");
const run = await client.classify({
  classifier: "support-intent",
  observation: "Cancel my plan",
});
console.log(run.selected_class); // null with the simulated mock

// Trigger an advisory Supervisor review, never an activation.
const review = await client.reviewRun({
  classifier: "support-intent", runId: run.id,
});`,
  },
  {
    id: "py-sdk",
    label: "Python SDK",
    code: `# Use the workspace SDK with your running local server.
from openclass_sdk import OpenClass

with OpenClass("http://localhost:7331") as client:
    run = client.classify(
        classifier="support-intent",
        observation="Cancel my plan",
    )
    print(run["selected_class"])  # None with the simulated mock
    print(client.unknowns("support-intent"))`,
  },
] as const;

const PRINCIPLES = [
  [
    "Unknown stays unknown.",
    "An unfamiliar observation is evidence to investigate, not proof that a new class exists.",
  ],
  [
    "Predictions are not labels.",
    "Only human or verified external labels become evaluation ground truth.",
  ],
  [
    "Models propose. You decide.",
    "Providers suggest inactive candidates. They do not receive writable ontology access.",
  ],
  [
    "Evaluate both versions.",
    "Compare baseline and candidate on the same verified dataset before approving a change.",
  ],
  [
    "Keep every version.",
    "History stays append-only. Rollback creates another version instead of erasing the past.",
  ],
  [
    "Separate errors from novelty.",
    "A provider outage is an operational failure, not a new semantic concept.",
  ],
] as const;

function navigateTabs(
  event: KeyboardEvent<HTMLButtonElement>,
  index: number,
  count: number,
  select: (index: number) => void,
  prefix: string,
) {
  const next =
    event.key === "ArrowRight"
      ? (index + 1) % count
      : event.key === "ArrowLeft"
        ? (index + count - 1) % count
        : event.key === "Home"
          ? 0
          : event.key === "End"
            ? count - 1
            : null;
  if (next === null) return;
  event.preventDefault();
  select(next);
  document.getElementById(`${prefix}-${next}`)?.focus();
}

export function ObservatoryArchitectureSections() {
  const id = useId();
  const [proofIndex, setProofIndex] = useState(0);
  const [codeIndex, setCodeIndex] = useState(0);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "unavailable">("idle");
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const copyGeneration = useRef(0);
  const proof = GROUNDED_PROOFS[proofIndex]!;
  const snippet = QUICKSTART_TABS[codeIndex]!;
  useEffect(
    () => () => {
      copyGeneration.current += 1;
      if (resetTimer.current !== null) clearTimeout(resetTimer.current);
    },
    [],
  );

  function selectCode(index: number) {
    copyGeneration.current += 1;
    if (resetTimer.current !== null) clearTimeout(resetTimer.current);
    setCodeIndex(index);
    setCopyState("idle");
  }

  async function copyCode() {
    const generation = ++copyGeneration.current;
    if (resetTimer.current !== null) clearTimeout(resetTimer.current);
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(snippet.code);
      if (generation !== copyGeneration.current) return;
      setCopyState("copied");
    } catch {
      if (generation !== copyGeneration.current) return;
      setCopyState("unavailable");
    }
    resetTimer.current = setTimeout(() => {
      if (generation === copyGeneration.current) setCopyState("idle");
    }, 2400);
  }

  return (
    <div className="oc-architecture-sections">
      <section className="oc-section-block oc-two-speeds" aria-labelledby={`${id}-paths`}>
        <p className="eyebrow">01 / DUAL-SPEED ARCHITECTURE</p>
        <h2 id={`${id}-paths`}>Decide now. Learn deliberately.</h2>
        <p className="oc-section-sub">
          Two paths, with a clear boundary between prediction and permission.
        </p>
        <div className="oc-path-comparison">
          <article className="oc-path-card is-fast-path">
            <div className="oc-path-card-head">
              <span className="oc-path-label">THE DECISION PATH</span>
              <code className="oc-path-mode">SYNCHRONOUS · READ-ONLY vN</code>
            </div>
            <h3>Use what you already know.</h3>
            <p>
              Score the active choices, check policy, and either return a supported result or
              abstain.
            </p>
            <div className="oc-path-sequence">
              <span>Observe</span>
              <span>Classify</span>
              <span>Check policy</span>
            </div>
          </article>
          <article className="oc-path-card is-slow-path">
            <div className="oc-path-card-head">
              <span className="oc-path-label">THE LEARNING PATH</span>
              <code className="oc-path-mode">ASYNCHRONOUS · HUMAN-GATED vN+1</code>
            </div>
            <h3>Give new knowledge a higher bar.</h3>
            <p>
              Gather evidence, inspect proposals, replay verified examples, and keep a human
              approval gate.
            </p>
            <div className="oc-path-sequence">
              <span>Evidence</span>
              <span>Evaluation</span>
              <span>Approval</span>
            </div>
          </article>
        </div>
        <div className="oc-boundary-strip">
          <span>AUTHORITY BOUNDARY</span>
          <p>
            Fast-path runs can write to the <code>unknown_events</code> evidence pool, but no model
            or supervisor can mutate <code>ontology_versions</code> without verified replay and
            human sign-off.
          </p>
        </div>
      </section>

      <section
        className="oc-section-block oc-principles-section"
        aria-labelledby={`${id}-principles`}
      >
        <div className="oc-principles-lead">
          <p className="eyebrow">02 / DOMAIN INVARIANTS</p>
          <h2 id={`${id}-principles`}>
            Uncertainty is useful. <br />
            Unchecked authority is not.
          </h2>
          <p className="oc-principles-summary">
            OpenClass separates fast classification, slow semantic reasoning, deterministic safety
            policy, and human governance into distinct layers.
          </p>
          <dl className="oc-authority-summary">
            <div>
              <dt>DecisionProvider</dt>
              <dd>Scores active classes + UNKNOWN</dd>
            </div>
            <div>
              <dt>DiscoveryProvider</dt>
              <dd>Proposes inactive candidates only</dd>
            </div>
            <div>
              <dt>Core Domain &amp; Human Gate</dt>
              <dd>Enforces replay &amp; promotes vN+1</dd>
            </div>
          </dl>
        </div>
        <div className="oc-principles-list">
          {PRINCIPLES.map(([title, description], index) => (
            <article key={title}>
              <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
              <div>
                <h3>{title}</h3>
                <p>{description}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="oc-section-block" aria-labelledby={`${id}-proofs`}>
        <p className="eyebrow">03 / VERIFIABLE ARTIFACTS &amp; RETAINED RESEARCH</p>
        <h2 id={`${id}-proofs`}>Follow the evidence, not the claim.</h2>
        <p className="oc-section-sub">
          Examples and retained research, with their sources and limits attached.
        </p>
        <div className="oc-proof-tabs" role="tablist" aria-label="Grounded engineering proofs">
          {GROUNDED_PROOFS.map((item, index) => (
            <button
              key={item.id}
              id={`${id}-proof-${index}`}
              type="button"
              role="tab"
              aria-selected={index === proofIndex}
              aria-controls={`${id}-proof-panel`}
              tabIndex={index === proofIndex ? 0 : -1}
              className={`oc-proof-tab ${index === proofIndex ? "active" : ""}`}
              onClick={() => setProofIndex(index)}
              onKeyDown={(event) =>
                navigateTabs(event, index, GROUNDED_PROOFS.length, setProofIndex, `${id}-proof`)
              }
            >
              <span>{item.tag}</span>
              <strong>{item.title}</strong>
            </button>
          ))}
        </div>
        <div
          className="oc-proof-detail"
          id={`${id}-proof-panel`}
          role="tabpanel"
          aria-labelledby={`${id}-proof-${proofIndex}`}
          tabIndex={0}
        >
          <div className="oc-proof-intro">
            <div className="oc-proof-intro-top">
              <span className="oc-evidence-kind">{proof.kind}</span>
              <code className="oc-proof-artifact-pill">{proof.artifactPath}</code>
            </div>
            <h3>{proof.title}</h3>
            <p>{proof.summary}</p>
          </div>
          <ol className="oc-proof-sequence">
            {proof.steps.map(([phase, detail], stepIdx) => (
              <li key={phase}>
                <span className="oc-proof-step-num" aria-hidden="true">
                  0{stepIdx + 1}
                </span>
                <h4>{phase}</h4>
                <p>{detail}</p>
              </li>
            ))}
          </ol>
          <details className="oc-source-detail">
            <summary>Source and limitations</summary>
            <p>{proof.limitation}</p>
            <a href={`${REPOSITORY}${proof.artifactPath}`}>{proof.artifactPath} ↗</a>
          </details>
        </div>
      </section>

      <section id="quickstart" className="oc-section-block" aria-labelledby={`${id}-quickstart`}>
        <p className="eyebrow">YOUR MACHINE. YOUR PROVIDERS. YOUR EVIDENCE.</p>
        <h2 id={`${id}-quickstart`}>Start locally. No model key needed.</h2>
        <ol className="oc-onboarding-steps">
          <li>
            <strong>Start the stack</strong>
            <p>Compose runs PostgreSQL 17, migrations, and the API on loopback.</p>
          </li>
          <li>
            <strong>Try a known request</strong>
            <p>The mock routes a billing example through the public API.</p>
          </li>
          <li>
            <strong>Keep an unknown</strong>
            <p>Send a cancellation request. Inspect the evidence instead of a forced guess.</p>
          </li>
        </ol>
        <div className="oc-code-console">
          <div className="oc-code-console-bar">
            <div className="oc-code-tabs" role="tablist" aria-label="Quickstart code examples">
              {QUICKSTART_TABS.map((tab, index) => (
                <button
                  key={tab.id}
                  id={`${id}-code-${index}`}
                  type="button"
                  role="tab"
                  aria-selected={index === codeIndex}
                  aria-controls={`${id}-code-panel`}
                  tabIndex={index === codeIndex ? 0 : -1}
                  className={`oc-code-tab ${index === codeIndex ? "active" : ""}`}
                  onClick={() => selectCode(index)}
                  onKeyDown={(event) =>
                    navigateTabs(event, index, QUICKSTART_TABS.length, selectCode, `${id}-code`)
                  }
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <button type="button" className="oc-copy-btn" onClick={() => void copyCode()}>
              {copyState === "copied" ? "Copied" : "Copy snippet"}
            </button>
          </div>
          <pre
            id={`${id}-code-panel`}
            className="oc-code-pre"
            role="tabpanel"
            aria-labelledby={`${id}-code-${codeIndex}`}
            tabIndex={0}
          >
            <code>{snippet.code}</code>
          </pre>
          <p className="oc-copy-status" role="status">
            {copyState === "unavailable"
              ? "Clipboard unavailable. Select the code to copy it."
              : copyState === "copied"
                ? "Snippet copied."
                : ""}
          </p>
        </div>
        <p className="oc-quickstart-note">
          Workspace SDKs are built from this repository; no published package installation is
          assumed. <a href={`${REPOSITORY}docs/guides/development.md`}>Development guide ↗</a>
        </p>
        <details className="oc-source-detail oc-release-detail">
          <summary>Implementation status and release limits</summary>
          <p>
            OpenClass is a Genesis foundation, not a completed Discovery release. Some learning and
            integration paths remain partial or fail closed.
          </p>
          <p>
            The walkthrough is simulated. It does not call a provider, run an evaluation, or
            activate a class.
          </p>
          <a href={`${REPOSITORY}docs/agentic-engineering/07-takeover-completion-ledger.md`}>
            Read the verification ledger ↗
          </a>
        </details>
      </section>
    </div>
  );
}
