import { useCallback, useEffect, useRef, useState } from "react";
import type {
  DecisionService,
  EvaluationDataset,
  OpenClass,
  ReplayEvaluation,
  VerifiedEvaluationExample,
} from "@openclass/sdk";
import "./workflow.css";

type CandidateOption = { id: string; label: string };
const percent = (value: unknown) =>
  typeof value !== "number" || !Number.isFinite(value)
    ? "Unavailable"
    : `${(value * 100).toFixed(1)}%`;

function metricRecord(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

/** Shared replay UI; labels, gates and activation authority belong to the server. */
export function ReplayWorkspace({ client, projectId }: { client: OpenClass; projectId: string }) {
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([]);
  const [services, setServices] = useState<DecisionService[]>([]);
  const [candidates, setCandidates] = useState<CandidateOption[]>([]);
  const [evaluations, setEvaluations] = useState<ReplayEvaluation[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [dataset, setDataset] = useState<EvaluationDataset | null>(null);
  const [result, setResult] = useState<ReplayEvaluation | null>(null);
  const [candidateId, setCandidateId] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [name, setName] = useState("");
  const [sealApproved, setSealApproved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const generation = useRef(0);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [example, setExample] = useState<Omit<VerifiedEvaluationExample, "id">>({
    text: "",
    label: "",
    source: "human",
    annotator: "",
    rationale: "",
    slice_tag: "historical",
    split: "holdout",
  });
  const load = useCallback(async () => {
    const [sets, definitions, discoveries, runs] = await Promise.all([
      client.evalDatasets(projectId),
      client.decisionServices(projectId),
      client.discoveryCandidates(projectId),
      client.evaluations(projectId),
    ]);
    setDatasets(sets);
    setServices(definitions);
    setEvaluations(runs);
    const options: CandidateOption[] = discoveries
      .filter(
        (c) =>
          c.type === "NEW_CLASS" &&
          ["discovered", "candidate", "collecting_evidence", "validating", "approved"].includes(
            c.status,
          ) &&
          typeof c.canonical_name === "string" &&
          c.canonical_name.trim().length > 0,
      )
      .map((c) => ({
        id: c.id,
        // The modern replay endpoint derives its choice key from canonical_name,
        // not an evidence proposal's key/label or a service ID on this inventory.
        label: c.canonical_name!.toUpperCase(),
      }));
    setCandidates([...new Map(options.map((c) => [c.id, c])).values()]);
    setLoaded(true);
  }, [client, projectId]);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void load()
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Replay data unavailable.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      generation.current += 1;
    };
  }, [load]);
  useEffect(() => {
    let cancelled = false;
    setDataset(null);
    setSealApproved(false);
    setDetailLoading(false);
    if (!datasetId) return;
    setDetailLoading(true);
    void client
      .evalDataset({ project: projectId, datasetId })
      .then((value) => {
        if (!cancelled) setDataset(value);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Dataset unavailable.");
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client, projectId, datasetId]);
  async function action(task: () => Promise<void>, success: string) {
    if (inFlight.current) return;
    inFlight.current = true;
    const current = generation.current;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await task();
      if (current !== generation.current) return;
      setMessage(success);
      try {
        await load();
      } catch {
        setError(
          "Action completed, but refresh failed. Refresh the page; do not repeat the mutation blindly.",
        );
      }
    } catch (err) {
      if (current === generation.current)
        setError(
          `${err instanceof Error ? err.message : "Workflow request failed."} No automatic retry was attempted.`,
        );
    } finally {
      inFlight.current = false;
      if (current === generation.current) setBusy(false);
    }
  }
  const canReplay = Boolean(
    dataset?.sealed_at &&
    candidates.some((candidate) => candidate.id === candidateId) &&
    services.some((service) => service.id === serviceId),
  );
  return (
    <section className="panel workflow" aria-label="Replay evaluation workspace">
      <h2>Verified replay evaluations</h2>
      <p>
        Compare baseline and inactive candidate against the same sealed dataset. Predictions are not
        ground truth. Passing gates never activate a proposal without human approval.
      </p>
      <p>
        Supported inventory: inactive NEW_CLASS discovery candidates. Evidence-synthesis proposals
        and ALIAS evaluation await canonical backend integration (OC-BG-012/014); they are not
        offered for this replay.
      </p>
      {loading && <p role="status">Loading replay workflows…</p>}
      {error && (
        <p role="alert" className="field-error">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {!loading && !loaded && <p>Replay data unavailable. Refresh after restoring access.</p>}
      {!loading && loaded && (
        <>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void action(async () => {
                const created = await client.createEvalDataset({
                  project: projectId,
                  name: name.trim(),
                });
                setName("");
                setDatasetId(created.id);
              }, "Dataset created.");
            }}
          >
            <label>
              New dataset name
              <input
                required
                minLength={2}
                maxLength={200}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <button disabled={busy}>Create verified dataset</button>
          </form>
          <label>
            Dataset
            <select
              value={datasetId}
              disabled={busy}
              onChange={(e) => setDatasetId(e.target.value)}
            >
              <option value="">Select a dataset</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} · {d.sealed_at ? "sealed" : "draft"}
                </option>
              ))}
            </select>
          </label>
          {!datasets.length && (
            <p>No datasets yet. Create one and enter independently verified labels.</p>
          )}
          {detailLoading && <p role="status">Loading dataset…</p>}
          {dataset && (
            <section>
              <h3>
                {dataset.name} · {dataset.sealed_at ? "sealed — immutable" : "draft"}
              </h3>
              <p>{dataset.description}</p>
              {dataset.dataset_hash && (
                <p>
                  Sealed identity: <code>{dataset.dataset_hash}</code>
                </p>
              )}
              <div style={{ overflowX: "auto" }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Observation</th>
                      <th>Verified label</th>
                      <th>Source / annotator</th>
                      <th>Split / slice</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dataset.examples?.map((ex) => (
                      <tr key={ex.id}>
                        <td>{ex.text}</td>
                        <td>{ex.label}</td>
                        <td>
                          {ex.source} · {ex.annotator}
                        </td>
                        <td>
                          {ex.split} · {ex.slice_tag}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {dataset.examples?.length === 0 && <p>No verified examples yet.</p>}
              {!dataset.sealed_at && (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void action(async () => {
                      const source_type =
                        example.split === "holdout"
                          ? "verified_holdout"
                          : example.split === "regression"
                            ? "regression_baseline"
                            : "calibration_dev";
                      await client.addVerifiedEvaluationExample({
                        project: projectId,
                        datasetId: dataset.id,
                        example: {
                          ...example,
                          label: example.label.trim().toUpperCase(),
                          source_type,
                        },
                      });
                      setExample((value) => ({ ...value, text: "", label: "", rationale: "" }));
                      setDataset(
                        await client.evalDataset({ project: projectId, datasetId: dataset.id }),
                      );
                    }, "Verified example added.");
                  }}
                >
                  <fieldset disabled={busy}>
                    <legend>Add independently verified example</legend>
                    <label>
                      Observation text
                      <textarea
                        required
                        maxLength={10000}
                        value={example.text}
                        onChange={(e) => setExample((v) => ({ ...v, text: e.target.value }))}
                      />
                    </label>
                    <label>
                      Verified label (or UNKNOWN)
                      <input
                        required
                        maxLength={100}
                        value={example.label}
                        onChange={(e) => setExample((v) => ({ ...v, label: e.target.value }))}
                      />
                    </label>
                    <label>
                      Label source
                      <select
                        value={example.source}
                        onChange={(e) =>
                          setExample((v) => ({ ...v, source: e.target.value as typeof v.source }))
                        }
                      >
                        <option value="human">Human</option>
                        <option value="verified_external">Verified external</option>
                      </select>
                    </label>
                    <label>
                      Annotator / verified source identity
                      <input
                        required
                        minLength={2}
                        maxLength={200}
                        value={example.annotator}
                        onChange={(e) => setExample((v) => ({ ...v, annotator: e.target.value }))}
                      />
                    </label>
                    <label>
                      Label rationale
                      <textarea
                        maxLength={2000}
                        value={example.rationale}
                        onChange={(e) => setExample((v) => ({ ...v, rationale: e.target.value }))}
                      />
                    </label>
                    <label>
                      Dataset split
                      <select
                        value={example.split}
                        onChange={(e) =>
                          setExample((v) => ({ ...v, split: e.target.value as typeof v.split }))
                        }
                      >
                        <option value="holdout">Verified holdout (not discovery evidence)</option>
                        <option value="regression">Regression baseline</option>
                        <option value="calibration">Calibration / development</option>
                      </select>
                    </label>
                    <label>
                      Evaluation slice
                      <select
                        value={example.slice_tag}
                        onChange={(e) =>
                          setExample((v) => ({
                            ...v,
                            slice_tag: e.target.value as typeof v.slice_tag,
                          }))
                        }
                      >
                        {["historical", "recent", "rare", "hard", "unknown", "adversarial"].map(
                          (s) => (
                            <option key={s}>{s}</option>
                          ),
                        )}
                      </select>
                    </label>
                    <button>Add verified example</button>
                  </fieldset>
                </form>
              )}
              {!dataset.sealed_at && (
                <div>
                  <label>
                    <input
                      type="checkbox"
                      checked={sealApproved}
                      disabled={busy}
                      onChange={(e) => setSealApproved(e.target.checked)}
                    />{" "}
                    I reviewed provenance and disjoint splits. Seal this dataset permanently.
                  </label>
                  <button
                    disabled={busy || !sealApproved || !dataset.examples?.length}
                    onClick={() => {
                      void action(async () => {
                        await client.sealEvalDataset({ project: projectId, datasetId: dataset.id });
                        setDataset(
                          await client.evalDataset({ project: projectId, datasetId: dataset.id }),
                        );
                      }, "Dataset sealed; historical examples are immutable.");
                    }}
                  >
                    Seal verified dataset
                  </button>
                </div>
              )}
            </section>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!canReplay || !dataset) return;
              void action(async () => {
                setResult(
                  await client.runEvaluation({
                    project: projectId,
                    datasetId: dataset.id,
                    candidateId,
                    serviceId,
                  }),
                );
              }, "Replay completed. Inspect every gate before human review.");
            }}
          >
            <fieldset disabled={busy}>
              <legend>Run baseline vs candidate replay</legend>
              <label>
                Inactive candidate
                <select
                  required
                  value={candidateId}
                  onChange={(e) => setCandidateId(e.target.value)}
                >
                  <option value="">Select a candidate</option>
                  {candidates.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label} · {c.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Decision service
                <select required value={serviceId} onChange={(e) => setServiceId(e.target.value)}>
                  <option value="">Select a service</option>
                  {services.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
              <button disabled={!canReplay}>Run sealed replay</button>
              {!dataset?.sealed_at && (
                <p>Choose and seal an independently verified dataset first.</p>
              )}
              {!candidates.length && (
                <p>
                  No eligible inactive NEW_CLASS discovery candidates are available. Evidence
                  proposals remain separate and cannot be submitted to modern replay.
                </p>
              )}
            </fieldset>
          </form>
          <h3>Persisted replay history</h3>
          {!evaluations.length && <p>No replay evaluations recorded.</p>}
          <ul>
            {evaluations.map((run) => (
              <li key={run.id}>
                <button
                  disabled={busy}
                  onClick={() => {
                    void action(async () => {
                      setResult(
                        await client.evaluation({ project: projectId, evaluationId: run.id }),
                      );
                    }, "Persisted evaluation loaded.");
                  }}
                >
                  {run.id} · {run.overall_passed === true ? "gates passed" : "blocked"}
                  {run.is_simulated ? " · simulated" : ""}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {result && <ReplayResult result={result} />}
    </section>
  );
}

export function ReplayResult({ result }: { result: ReplayEvaluation }) {
  // Shared history also contains older flat compatibility evaluations.
  // Narrow the actual payload rather than assuming the modern SDK shape.
  const metrics = metricRecord(result.metrics);
  const baseline = metricRecord(metrics?.baseline);
  const candidate = metricRecord(metrics?.candidate);
  const legacy = metrics && ("accuracy_on_knowns" in metrics || "disambiguation_rate" in metrics);
  return (
    <section aria-label="Replay result">
      <h3>
        {!baseline || !candidate
          ? "Historical or incomplete evaluation — comparison unavailable"
          : result.overall_passed === true
            ? "Gates passed — human review still required"
            : "Blocked — evaluation did not pass"}
      </h3>
      <p>
        Evaluation {result.id} · dataset {result.dataset_id} · candidate {result.candidate_id}
      </p>
      {(result.is_simulated === true || metrics?.simulated === true) && (
        <p>Simulated replay — not evidence of real model quality.</p>
      )}
      <p>
        Provider: {result.provider ?? "unavailable"} · model: {result.model ?? "unavailable"}
      </p>
      {legacy && (
        <>
          <p>Legacy metrics — not a baseline/candidate comparison.</p>
          <dl>
            <dt>Accuracy on knowns</dt>
            <dd>{percent(metrics.accuracy_on_knowns)}</dd>
            <dt>Disambiguation rate</dt>
            <dd>{percent(metrics.disambiguation_rate)}</dd>
          </dl>
        </>
      )}
      {metrics ? (
        <table className="table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Baseline</th>
              <th>Candidate</th>
            </tr>
          </thead>
          <tbody>
            {["accuracy", "macro_f1", "coverage", "unknown_precision", "unknown_recall"].map(
              (key) => (
                <tr key={key}>
                  <td>{key.replaceAll("_", " ")}</td>
                  <td>{percent(baseline?.[key])}</td>
                  <td>{percent(candidate?.[key])}</td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      ) : (
        <p>Metric details unavailable.</p>
      )}
      <ul>
        {result.gates?.map((gate) => (
          <li key={gate.gate}>
            {gate.passed === true ? "PASS" : "BLOCKED"} · {gate.gate.replaceAll("_", " ")}
            {gate.reason ? ` — ${gate.reason}` : ""}
            {gate.value !== undefined
              ? ` · measured ${gate.value}, threshold ${gate.threshold ?? "unavailable"}`
              : ""}
          </li>
        ))}
      </ul>
      {!result.gates?.length && (
        <p>Gate details unavailable; do not treat this as promotion approval.</p>
      )}
    </section>
  );
}
