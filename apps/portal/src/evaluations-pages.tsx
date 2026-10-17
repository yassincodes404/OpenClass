import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { controlFetch } from "./api";
import { useAuth } from "./auth";
import { ProjectShell, type Project } from "./projects";
import { ReplayWorkspace } from "./replay-workspace";
import { useWorkflowClient } from "./workflow-client";

export type Dataset = {
  id: string;
  name: string;
  description: string;
  sealed_at: string | null;
  size: number;
  coverage: Record<string, number>;
};
export type Example = {
  id: string;
  text: string;
  label: string;
  source: string;
  annotator: string;
  rationale: string;
  slice_tag: string;
};
export type DatasetDetail = Dataset & { examples: Example[] };

function useToken() {
  return useAuth().token() ?? "";
}

function useProjectQuery(projectId: string) {
  const token = useToken();
  return useQuery({
    queryKey: ["project", projectId],
    queryFn: async (): Promise<Project> =>
      (await controlFetch(`/projects/${projectId}`, token)) as Project,
  });
}

export function EvaluationsPage() {
  const { projectId = "" } = useParams();
  const project = useProjectQuery(projectId);
  const client = useWorkflowClient();
  if (project.isError)
    return (
      <main>
        <p role="alert">{project.error.message}</p>
      </main>
    );
  if (!project.data)
    return (
      <main>
        <p role="status">Loading evaluations…</p>
      </main>
    );
  return (
    <main>
      <ProjectShell project={project.data} active="/evaluations">
        <ReplayWorkspace key={projectId} client={client} projectId={projectId} />
      </ProjectShell>
    </main>
  );
}
export type EvaluationSummary = {
  id: string;
  dataset_id: string;
  candidate_id: string;
  overall_passed: boolean;
  created_at: string;
};
export type Gate = {
  gate: string;
  passed: boolean;
  value?: number;
  threshold?: number;
  before?: number;
  after?: number;
  reason?: string;
};
export type EvaluationDetail = {
  id: string;
  dataset_id: string;
  candidate_id: string;
  overall_passed: boolean;
  metrics: {
    examples: number;
    simulated?: boolean;
    baseline: { accuracy: number | null; macro_f1: number | null; coverage: number | null };
    candidate: {
      accuracy: number | null;
      macro_f1: number | null;
      coverage: number | null;
      unknown_precision: number | null;
      unknown_recall: number | null;
    };
  };
  gates: Gate[];
};

export function EvaluationDetailPage() {
  const { projectId = "", evaluationId = "" } = useParams();
  const token = useToken();
  const project = useProjectQuery(projectId);
  const evaluation = useQuery({
    queryKey: ["evaluation", projectId, evaluationId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<EvaluationDetail> =>
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/evaluations/${evaluationId}`,
        token,
      )) as EvaluationDetail,
  });
  if (project.isPending || evaluation.isPending)
    return (
      <main>
        <p className="lede">Loading evaluation…</p>
      </main>
    );
  if (!project.data || !evaluation.data)
    return (
      <main>
        <p className="lede">Evaluation unavailable.</p>
      </main>
    );
  const { metrics, gates, overall_passed: passed } = evaluation.data;
  const pct = (value: number | null | undefined) =>
    value === null || value === undefined ? "—" : `${(value * 100).toFixed(1)}%`;
  return (
    <main>
      <ProjectShell project={project.data} active="/evaluations">
        <section className="signal">
          <p className="eyebrow">
            EVALUATION / REPLAY ·{" "}
            <Link to={`/projects/${projectId}/evaluations`}>← all datasets</Link>
          </p>
          <h2>
            {passed ? "All gates passed — ready for human approval" : "Blocked — failed gates"}
          </h2>
          <p className={passed ? "muted" : "field-error"}>
            {passed
              ? "Ready for promotion review (Phase 14 still requires explicit human approval)."
              : "A failed evaluation blocks promotion. Fix the regression before promoting."}
            {metrics.simulated && <> · mock replay (simulated, deterministic)</>}
          </p>
          <div className="panel">
            <div className="panel-head">
              <h3>Baseline vs candidate</h3>
            </div>
            <div
              className="table-wrap"
              role="region"
              aria-label="Baseline vs candidate metrics"
              tabIndex={0}
            >
              <table className="table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Baseline</th>
                    <th>Candidate</th>
                    <th>Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {(["accuracy", "macro_f1", "coverage"] as const).map((key) => {
                    const before = metrics.baseline[key];
                    const after = metrics.candidate[key];
                    const delta = before !== null && after !== null ? after - before : null;
                    return (
                      <tr key={key}>
                        <td>
                          <div>{key.replaceAll("_", " ")}</div>
                          {before !== null && after !== null && (
                            <div className="replay-metric-bars" aria-hidden="true">
                              <span
                                className="replay-bar baseline"
                                style={{ transform: `scaleX(${Math.max(0.02, before)})` }}
                              />
                              <span
                                className={`replay-bar candidate${after < before ? " regressed" : ""}`}
                                style={{ transform: `scaleX(${Math.max(0.02, after)})` }}
                              />
                            </div>
                          )}
                        </td>
                        <td>{pct(before)}</td>
                        <td>{pct(after)}</td>
                        <td>
                          {delta === null ? (
                            "—"
                          ) : (
                            <span className={delta >= 0 ? "chip locked" : "chip danger"}>
                              {delta >= 0 ? "+" : ""}
                              {(delta * 100).toFixed(1)}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  <tr>
                    <td>unknown precision / recall</td>
                    <td>—</td>
                    <td>
                      {pct(metrics.candidate.unknown_precision)} /{" "}
                      {pct(metrics.candidate.unknown_recall)}
                    </td>
                    <td>—</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="muted">{metrics.examples} sealed examples replayed on both versions.</p>
          </div>
          <div className="panel">
            <div className="panel-head">
              <h3>Gate checklist</h3>
            </div>
            <ul className="timeline">
              {gates.map((gate) => (
                <li key={gate.gate}>
                  {gate.passed ? "✓" : "✕"} {gate.gate.replaceAll("_", " ")}
                  {gate.reason ? ` — ${gate.reason}` : ""}
                  {gate.value !== undefined &&
                    ` — value ${gate.value} vs threshold ${gate.threshold}`}
                  {gate.before !== undefined &&
                    gate.after !== undefined &&
                    ` — ${(gate.before * 100).toFixed(0)}% → ${(gate.after * 100).toFixed(0)}%`}
                </li>
              ))}
            </ul>
          </div>
        </section>
      </ProjectShell>
    </main>
  );
}

export function DatasetPage() {
  const { projectId = "", datasetId = "" } = useParams();
  const token = useToken();
  const queryClient = useQueryClient();
  const project = useProjectQuery(projectId);
  const detail = useQuery({
    queryKey: ["dataset", projectId, datasetId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<DatasetDetail> =>
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/eval-datasets/${datasetId}`,
        token,
      )) as DatasetDetail,
  });
  const [form, setForm] = useState({
    text: "",
    label: "BILLING",
    annotator: "",
    rationale: "",
  });
  const [message, setMessage] = useState<string | null>(null);
  const addExample = useMutation({
    mutationFn: async () =>
      controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/eval-datasets/${datasetId}/examples`,
        token,
        {
          method: "POST",
          body: JSON.stringify({ ...form, source: "human", slice_tag: "recent" }),
        },
      ),
    onSuccess: () => {
      setMessage("Example added");
      setForm({ ...form, text: "" });
      void queryClient.invalidateQueries({ queryKey: ["dataset", projectId, datasetId] });
    },
    onError: (err: Error) => setMessage(err.message),
  });
  const seal = useMutation({
    mutationFn: async () =>
      controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/eval-datasets/${datasetId}/seal`,
        token,
        { method: "POST" },
      ),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["dataset", projectId, datasetId] }),
    onError: (err: Error) => setMessage(err.message),
  });
  if (project.isPending || detail.isPending)
    return (
      <main>
        <p className="lede">Loading dataset…</p>
      </main>
    );
  if (!project.data || !detail.data)
    return (
      <main>
        <p className="lede">Dataset unavailable.</p>
      </main>
    );
  const sealed = detail.data.sealed_at !== null;
  return (
    <main>
      <ProjectShell project={project.data} active="/evaluations">
        <section className="signal">
          <p className="eyebrow">
            DATASET / {sealed ? "SEALED — IMMUTABLE" : "DRAFT"}{" "}
            <Link to={`/projects/${projectId}/evaluations`}>← all datasets</Link>
          </p>
          <h2>{detail.data.name}</h2>
          <p className="muted">
            {detail.data.description} · {detail.data.examples.length} examples · every row carries
            annotator + source provenance
          </p>
          <div className="table-wrap" role="region" aria-label="Dataset examples" tabIndex={0}>
            <table className="table">
              <thead>
                <tr>
                  <th>Text</th>
                  <th>Label</th>
                  <th>Source</th>
                  <th>Annotator</th>
                  <th>Slice</th>
                </tr>
              </thead>
              <tbody>
                {detail.data.examples.map((example) => (
                  <tr key={example.id}>
                    <td>{example.text.slice(0, 60)}</td>
                    <td>
                      <code>{example.label}</code>
                    </td>
                    <td>
                      <span className="chip">{example.source}</span>
                    </td>
                    <td className="muted">{example.annotator}</td>
                    <td>
                      <span className="chip">{example.slice_tag}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!sealed ? (
            <div className="panel">
              <div className="panel-head">
                <h3>Add example (human labels only)</h3>
              </div>
              <textarea
                className="ingest-area"
                rows={2}
                value={form.text}
                onChange={(event) => setForm({ ...form, text: event.target.value })}
                placeholder="Observation text"
              />
              <div className="panel-head">
                <input
                  value={form.label}
                  onChange={(event) => setForm({ ...form, label: event.target.value })}
                  placeholder="LABEL or UNKNOWN"
                />
                <input
                  value={form.annotator}
                  onChange={(event) => setForm({ ...form, annotator: event.target.value })}
                  placeholder="annotator"
                />
              </div>
              <div className="panel-head">
                <input
                  value={form.rationale}
                  onChange={(event) => setForm({ ...form, rationale: event.target.value })}
                  placeholder="rationale (why this label)"
                />
                <button
                  disabled={!form.text.trim() || addExample.isPending}
                  onClick={() => addExample.mutate()}
                >
                  Add example
                </button>
              </div>
              {message && <p className="muted">{message}</p>}
              <div className="modal-actions">
                <button
                  className="ghost danger"
                  onClick={() => {
                    if (window.confirm("Seal this dataset? It becomes immutable.")) seal.mutate();
                  }}
                >
                  Seal dataset (irreversible)
                </button>
              </div>
            </div>
          ) : (
            <p className="field-error">This dataset is sealed — no further edits are possible.</p>
          )}
        </section>
      </ProjectShell>
    </main>
  );
}
