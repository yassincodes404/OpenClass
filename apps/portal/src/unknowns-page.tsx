import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { controlFetch } from "./api";
import { useAuth } from "./auth";
import { ProjectShell, type Project } from "./projects";

export type Triage = { status: string; category: string | null; assignee: string | null; note: string | null };
export type UnknownItem = {
  run_id: string;
  content: string;
  unknown_probability: number;
  supervision_reason: string;
  created_at: string;
  recurrence: number;
  triage: Triage;
};
export type UnknownPage = { items: UnknownItem[]; next_cursor: string | null };
export type UnknownStats = {
  total_unknown: number;
  total_runs: number;
  unknown_rate: number;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  top_phrases: string[];
  daily: Array<{ date: string; unknowns: number }>;
};
export type UnknownDetail = UnknownItem & { probabilities: Record<string, number>; raw_event_id: string };

const CATEGORIES = ["truly_novel", "ambiguous", "out_of_scope", "missing_info", "schema_problem"] as const;

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

function TrendChart({ daily }: { daily: Array<{ date: string; unknowns: number }> }) {
  if (daily.length === 0) return <p className="muted">No trend data yet.</p>;
  const max = Math.max(...daily.map((point) => point.unknowns), 1);
  const width = Math.min(daily.length * 44, 560);
  const height = 110;
  const points = daily.map((point, index) => {
    const x = (index / Math.max(daily.length - 1, 1)) * (width - 20) + 10;
    const y = height - 12 - (point.unknowns / max) * (height - 30);
    return { x, y, point };
  });
  return (
    <svg className="trend" viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label="UNKNOWN daily trend">
      <polyline fill="none" stroke="#c4f48a" strokeWidth="2" points={points.map((p) => `${p.x},${p.y}`).join(" ")} />
      {points.map(({ x, y, point }) => (
        <g key={point.date}>
          <circle cx={x} cy={y} r="3.5" fill="#c4f48a" />
          <text x={x} y={height - 1} textAnchor="middle" fontSize="8" fill="#a6b0a6">{point.date.slice(5)}</text>
          <text x={x} y={y - 7} textAnchor="middle" fontSize="8" fill="#eef0e8">{point.unknowns}</text>
        </g>
      ))}
    </svg>
  );
}

export function UnknownsPage() {
  const { projectId = "" } = useParams();
  const token = useToken();
  const queryClient = useQueryClient();
  const project = useProjectQuery(projectId);
  const [state, setState] = useState("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [queryText, setQueryText] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [triageCategory, setTriageCategory] = useState<string>("missing_info");
  const [assignee, setAssignee] = useState("");

  const stats = useQuery({
    queryKey: ["unknown-stats", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<UnknownStats> =>
      (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/stats`, token)) as UnknownStats,
  });
  const pool = useQuery({
    queryKey: ["unknowns", projectId, state, category, queryText],
    enabled: project.isSuccess,
    queryFn: async (): Promise<UnknownPage> => {
      const params = new URLSearchParams();
      if (state) params.set("state", state);
      if (category) params.set("category", category);
      if (queryText) params.set("q", queryText);
      return (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns?${params}`, token)) as UnknownPage;
    },
  });
  const detail = useQuery({
    queryKey: ["unknown", projectId, selected],
    enabled: selected !== null,
    queryFn: async (): Promise<UnknownDetail> =>
      (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/${selected}`, token)) as UnknownDetail,
  });
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["unknowns", projectId] });
    void queryClient.invalidateQueries({ queryKey: ["unknown-stats", projectId] });
  };
  const triage = useMutation({
    mutationFn: async (runId: string) =>
      controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/${runId}/triage`, token, {
        method: "POST",
        body: JSON.stringify({ category: triageCategory, assignee: assignee || undefined }),
      }),
    onSuccess: invalidate,
  });
  const transition = useMutation({
    mutationFn: async (payload: { runId: string; to: string }) =>
      controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/${payload.runId}/transition`, token, {
        method: "POST",
        body: JSON.stringify({ to: payload.to }),
      }),
    onSuccess: invalidate,
  });

  if (project.isPending) return <main><p className="lede">Loading UNKNOWN workspace…</p></main>;
  if (!project.data) return <main><p className="lede">Project unavailable.</p></main>;

  return (
    <main>
      <ProjectShell project={project.data} active="/unknowns">
        <section className="signal">
          <p className="eyebrow">UNKNOWN / TRIAGE</p>
          <h2>What is the system failing to understand?</h2>
          <p className="muted">Triage is descriptive only — a category is never a new-class proposal, and no promotion path exists here. <Link to={`/projects/${projectId}/unknowns/clusters`}>View clusters →</Link></p>
          <div className="metrics">
            <div><b>{stats.data?.total_unknown ?? "…"}</b><span>UNKNOWN runs</span></div>
            <div><b>{((stats.data?.unknown_rate ?? 0) * 100).toFixed(1)}%</b><span>UNKNOWN rate ({stats.data?.total_runs ?? 0} runs)</span></div>
            <div><b>{stats.data?.top_phrases.slice(0, 3).join(", ") || "—"}</b><span>Recurring phrases (redacted)</span></div>
          </div>
          <div className="panel">
            <div className="panel-head"><h3>Daily trend</h3></div>
            <TrendChart daily={stats.data?.daily ?? []} />
          </div>
          <div className="panel-head">
            <select value={state} onChange={(event) => setState(event.target.value)}>
              <option value="">All states</option>
              <option value="needs_evidence">needs_evidence</option>
              <option value="triaged">triaged</option>
              <option value="dismissed">dismissed</option>
            </select>
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="">All categories</option>
              {CATEGORIES.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
            <input
              placeholder="Search content…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && setQueryText(search.trim())}
            />
          </div>
          {pool.data?.items.length === 0 && <p className="muted">No UNKNOWN runs match.</p>}
          <table className="table">
            <tbody>
              {pool.data?.items.map((item) => (
                <tr key={item.run_id} onClick={() => setSelected(item.run_id)}>
                  <td>{item.content}</td>
                  <td><span className="chip locked">{item.triage.status}</span></td>
                  <td>{item.triage.category && <span className="chip">{item.triage.category}</span>}</td>
                  <td className="muted">×{item.recurrence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </ProjectShell>
      {selected && (
        <div className="modal-backdrop" role="dialog" aria-label="UNKNOWN detail" onClick={() => setSelected(null)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <p className="eyebrow">UNKNOWN / {detail.data?.triage.status ?? "…"}</p>
            <h2>Triage</h2>
            {detail.isPending && <p className="muted">Loading…</p>}
            {detail.data && (
              <>
                <p className="muted">reason: {detail.data.supervision_reason}</p>
                <pre className="detail-pre">{detail.data.content}</pre>
                <label>
                  Category (advisory only)
                  <select value={triageCategory} onChange={(event) => setTriageCategory(event.target.value)}>
                    {CATEGORIES.map((option) => <option key={option} value={option}>{option}</option>)}
                  </select>
                </label>
                <label>
                  Assignee
                  <input value={assignee} onChange={(event) => setAssignee(event.target.value)} placeholder="reviewer@…" />
                </label>
                <div className="modal-actions">
                  <button onClick={() => triage.mutate(selected)}>Save triage</button>
                  {detail.data.triage.status === "needs_evidence" && (
                    <>
                      <button className="ghost" onClick={() => transition.mutate({ runId: selected, to: "triaged" })}>Mark triaged</button>
                      <button className="ghost danger" onClick={() => transition.mutate({ runId: selected, to: "dismissed" })}>Dismiss</button>
                    </>
                  )}
                  {detail.data.triage.status === "triaged" && (
                    <button className="ghost danger" onClick={() => transition.mutate({ runId: selected, to: "dismissed" })}>Dismiss</button>
                  )}
                </div>
              </>
            )}
            <div className="modal-actions">
              <button className="ghost" onClick={() => setSelected(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
