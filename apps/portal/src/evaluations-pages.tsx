import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { controlFetch } from "./api";
import { useAuth } from "./auth";
import { ProjectShell, type Project } from "./projects";

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
    queryFn: async (): Promise<Project> => (await controlFetch(`/projects/${projectId}`, token)) as Project,
  });
}

export function EvaluationsPage() {
  const { projectId = "" } = useParams();
  const token = useToken();
  const queryClient = useQueryClient();
  const project = useProjectQuery(projectId);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const datasets = useQuery({
    queryKey: ["datasets", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<Dataset[]> =>
      (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/eval-datasets`, token)) as Dataset[],
  });
  const create = useMutation({
    mutationFn: async () =>
      controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/eval-datasets`, token, {
        method: "POST",
        body: JSON.stringify({ name }),
      }),
    onSuccess: () => {
      setName("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["datasets", projectId] });
    },
    onError: (err: Error) => setError(err.message),
  });
  if (project.isPending) return <main><p className="lede">Loading evaluations…</p></main>;
  if (!project.data) return <main><p className="lede">Project unavailable.</p></main>;
  return (
    <main>
      <ProjectShell project={project.data} active="/evaluations">
        <section className="signal">
          <p className="eyebrow">EVALUATIONS / VERIFIED DATASETS</p>
          <h2>Ground truth with human provenance — the only basis for replay.</h2>
          <p className="muted">Predictions can never become ground truth; datasets are immutable once sealed.</p>
          <div className="panel-head">
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="New dataset name (e.g. support-gold-v1)" />
            <button disabled={name.trim().length < 2 || create.isPending} onClick={() => create.mutate()}>Create dataset</button>
          </div>
          {error && <p className="field-error">{error}</p>}
          {datasets.data?.length === 0 && <p className="muted">No datasets yet.</p>}
          <div className="card-grid">
            {datasets.data?.map((dataset) => (
              <article key={dataset.id} className="project-card">
                <p className="status"><i /> {dataset.size} examples {dataset.sealed_at && <span className="chip locked">sealed</span>}</p>
                <h3>{dataset.name}</h3>
                <p className="muted">
                  slices: {Object.entries(dataset.coverage).filter(([, n]) => n > 0).map(([k, n]) => `${k}×${n}`).join(" · ") || "none"}
                </p>
                <Link to={`/projects/${projectId}/evaluations/datasets/${dataset.id}`}>Open dataset →</Link>
              </article>
            ))}
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
      (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/eval-datasets/${datasetId}`, token)) as DatasetDetail,
  });
  const [form, setForm] = useState({ text: "", label: "BILLING", annotator: "owner@acme.openclass.test", rationale: "" });
  const [message, setMessage] = useState<string | null>(null);
  const addExample = useMutation({
    mutationFn: async () =>
      controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/eval-datasets/${datasetId}/examples`, token, {
        method: "POST",
        body: JSON.stringify({ ...form, source: "human", slice_tag: "recent" }),
      }),
    onSuccess: () => {
      setMessage("Example added");
      setForm({ ...form, text: "" });
      void queryClient.invalidateQueries({ queryKey: ["dataset", projectId, datasetId] });
    },
    onError: (err: Error) => setMessage(err.message),
  });
  const seal = useMutation({
    mutationFn: async () =>
      controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/eval-datasets/${datasetId}/seal`, token, { method: "POST" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["dataset", projectId, datasetId] }),
    onError: (err: Error) => setMessage(err.message),
  });
  if (project.isPending || detail.isPending) return <main><p className="lede">Loading dataset…</p></main>;
  if (!project.data || !detail.data) return <main><p className="lede">Dataset unavailable.</p></main>;
  const sealed = detail.data.sealed_at !== null;
  return (
    <main>
      <ProjectShell project={project.data} active="/evaluations">
        <section className="signal">
          <p className="eyebrow">DATASET / {sealed ? "SEALED — IMMUTABLE" : "DRAFT"} <Link to={`/projects/${projectId}/evaluations`}>← all datasets</Link></p>
          <h2>{detail.data.name}</h2>
          <p className="muted">{detail.data.description} · {detail.data.examples.length} examples · every row carries annotator + source provenance</p>
          <table className="table">
            <thead><tr><th>Text</th><th>Label</th><th>Source</th><th>Annotator</th><th>Slice</th></tr></thead>
            <tbody>
              {detail.data.examples.map((example) => (
                <tr key={example.id}>
                  <td>{example.text.slice(0, 60)}</td>
                  <td><code>{example.label}</code></td>
                  <td><span className="chip">{example.source}</span></td>
                  <td className="muted">{example.annotator}</td>
                  <td><span className="chip">{example.slice_tag}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!sealed ? (
            <div className="panel">
              <div className="panel-head"><h3>Add example (human labels only)</h3></div>
              <textarea className="ingest-area" rows={2} value={form.text} onChange={(event) => setForm({ ...form, text: event.target.value })} placeholder="Observation text" />
              <div className="panel-head">
                <input value={form.label} onChange={(event) => setForm({ ...form, label: event.target.value })} placeholder="LABEL or UNKNOWN" />
                <input value={form.annotator} onChange={(event) => setForm({ ...form, annotator: event.target.value })} placeholder="annotator" />
              </div>
              <div className="panel-head">
                <input value={form.rationale} onChange={(event) => setForm({ ...form, rationale: event.target.value })} placeholder="rationale (why this label)" />
                <button disabled={!form.text.trim() || addExample.isPending} onClick={() => addExample.mutate()}>Add example</button>
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
