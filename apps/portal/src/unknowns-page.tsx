import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { controlFetch } from "./api";
import { useAuth } from "./auth";
import { Dialog } from "./dialog";
import { ProjectShell, type Project } from "./projects";

export type Triage = {
  status: string;
  category: string | null;
  assignee: string | null;
  note: string | null;
};
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
export type UnknownDetail = UnknownItem & {
  probabilities: Record<string, number>;
  raw_event_id: string;
};

const CATEGORIES = [
  "truly_novel",
  "ambiguous",
  "out_of_scope",
  "missing_info",
  "schema_problem",
] as const;

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

function TrendChart({ daily }: { daily: Array<{ date: string; unknowns: number }> }) {
  if (daily.length === 0) return <p className="muted">No trend data yet.</p>;
  const max = Math.max(...daily.map((point) => point.unknowns), 1);
  const width = 1120;
  const height = 192;
  const padX = 48;
  const padRight = 36;
  const padTop = 30;
  const padBottom = 34;
  const plotW = width - padX - padRight;
  const plotH = height - padTop - padBottom;
  const points = daily.map((point, index) => {
    const x =
      daily.length === 1
        ? padX + plotW / 2
        : padX + (index / Math.max(daily.length - 1, 1)) * plotW;
    const y = padTop + plotH - (point.unknowns / max) * plotH;
    return { x, y, point };
  });
  const areaPath =
    points.length > 1
      ? `M ${points[0]!.x},${padTop + plotH} ` +
        points.map((p) => `L ${p.x},${p.y}`).join(" ") +
        ` L ${points[points.length - 1]!.x},${padTop + plotH} Z`
      : "";
  const midTick = Math.round(max / 2);

  return (
    <svg
      className="trend"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="UNKNOWN daily trend"
    >
      <defs>
        <linearGradient id="oc-unknown-area-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#f2c879" stopOpacity="0.22" />
          <stop offset="100%" stopColor="#f2c879" stopOpacity="0.0" />
        </linearGradient>
      </defs>
      {[
        { label: max, y: padTop },
        { label: midTick, y: padTop + plotH / 2 },
        { label: 0, y: padTop + plotH },
      ].map((tick, idx) => (
        <g key={idx} aria-hidden="true">
          <line
            x1={padX}
            y1={tick.y}
            x2={width - padRight}
            y2={tick.y}
            stroke="rgba(168, 180, 170, 0.16)"
            strokeDasharray={idx === 2 ? undefined : "3 4"}
          />
          <text
            x={padX - 10}
            y={tick.y + 3}
            textAnchor="end"
            fontSize="9"
            fill="#76857a"
            fontFamily="var(--font-mono)"
          >
            {tick.label}
          </text>
        </g>
      ))}
      {areaPath && <path d={areaPath} fill="url(#oc-unknown-area-grad)" />}
      <polyline
        fill="none"
        stroke="#f2c879"
        strokeWidth="2.25"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points.map((p) => `${p.x},${p.y}`).join(" ")}
      />
      {points.map(({ x, y, point }) => (
        <g key={point.date}>
          <line
            x1={x}
            y1={padTop}
            x2={x}
            y2={padTop + plotH}
            stroke="rgba(242, 200, 121, 0.1)"
            strokeDasharray="2 3"
            aria-hidden="true"
          />
          <circle cx={x} cy={y} r="7" fill="rgba(242, 200, 121, 0.16)" />
          <circle cx={x} cy={y} r="3.5" fill="#0e1512" stroke="#f2c879" strokeWidth="2" />
          <text
            x={x}
            y={height - 8}
            textAnchor="middle"
            fontSize="10"
            fill="#a8b4aa"
            fontFamily="var(--font-mono)"
          >
            {point.date.slice(5)}
          </text>
          <rect
            x={x - 13}
            y={y - 22}
            width="26"
            height="14"
            rx="4"
            fill="#151e19"
            stroke="rgba(242, 200, 121, 0.36)"
            aria-hidden="true"
          />
          <text
            x={x}
            y={y - 12}
            textAnchor="middle"
            fontSize="9.5"
            fontWeight="700"
            fill="#f2c879"
            fontFamily="var(--font-mono)"
          >
            {point.unknowns}
          </text>
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
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/stats`,
        token,
      )) as UnknownStats,
  });
  const pool = useQuery({
    queryKey: ["unknowns", projectId, state, category, queryText],
    enabled: project.isSuccess,
    queryFn: async (): Promise<UnknownPage> => {
      const params = new URLSearchParams();
      if (state) params.set("state", state);
      if (category) params.set("category", category);
      if (queryText) params.set("q", queryText);
      return (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns?${params}`,
        token,
      )) as UnknownPage;
    },
  });
  const detail = useQuery({
    queryKey: ["unknown", projectId, selected],
    enabled: selected !== null,
    queryFn: async (): Promise<UnknownDetail> =>
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/${selected}`,
        token,
      )) as UnknownDetail,
  });
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["unknowns", projectId] });
    void queryClient.invalidateQueries({ queryKey: ["unknown-stats", projectId] });
  };
  const triage = useMutation({
    mutationFn: async (runId: string) =>
      controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/${runId}/triage`,
        token,
        {
          method: "POST",
          body: JSON.stringify({ category: triageCategory, assignee: assignee || undefined }),
        },
      ),
    onSuccess: invalidate,
  });
  const transition = useMutation({
    mutationFn: async (payload: { runId: string; to: string }) =>
      controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/${payload.runId}/transition`,
        token,
        {
          method: "POST",
          body: JSON.stringify({ to: payload.to }),
        },
      ),
    onSuccess: invalidate,
  });

  if (project.isPending)
    return (
      <main>
        <p className="lede">Loading UNKNOWN workspace…</p>
      </main>
    );
  if (!project.data)
    return (
      <main>
        <p className="lede">Project unavailable.</p>
      </main>
    );

  return (
    <main>
      <ProjectShell project={project.data} active="/unknowns">
        <section className="signal">
          <p className="eyebrow">UNKNOWN / TRIAGE</p>
          <h2>What is the system failing to understand?</h2>
          <p className="muted">
            Triage is descriptive only — a category is never a new-class proposal, and no promotion
            path exists here.{" "}
            <Link to={`/projects/${projectId}/unknowns/clusters`}>View clusters →</Link>
          </p>
          <div className="metrics">
            <div>
              <b>{stats.data?.total_unknown ?? "…"}</b>
              <span>UNKNOWN runs</span>
            </div>
            <div>
              <b>{((stats.data?.unknown_rate ?? 0) * 100).toFixed(1)}%</b>
              <span>UNKNOWN rate ({stats.data?.total_runs ?? 0} runs)</span>
            </div>
            <div>
              <b className="metric-text">{stats.data?.top_phrases.slice(0, 3).join(", ") || "—"}</b>
              <span>Recurring phrases (redacted)</span>
            </div>
          </div>
          <div className="panel">
            <div className="panel-head">
              <h3>Daily trend</h3>
              <span className="chip locked">UNKNOWN evidence pool</span>
            </div>
            <TrendChart daily={stats.data?.daily ?? []} />
          </div>
          <div className="panel-head filter-toolbar">
            <select
              aria-label="Filter by triage state"
              value={state}
              onChange={(event) => setState(event.target.value)}
            >
              <option value="">All states</option>
              <option value="needs_evidence">needs_evidence</option>
              <option value="triaged">triaged</option>
              <option value="dismissed">dismissed</option>
            </select>
            <select
              aria-label="Filter by advisory category"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option value="">All categories</option>
              {CATEGORIES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <input
              aria-label="Search UNKNOWN observations"
              placeholder="Search content…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && setQueryText(search.trim())}
            />
          </div>
          {pool.data?.items.length === 0 && <p className="muted">No UNKNOWN runs match.</p>}
          <div className="table-wrap" role="region" aria-label="UNKNOWN runs" tabIndex={0}>
            <table className="table">
              <thead>
                <tr>
                  <th>Observation</th>
                  <th>State</th>
                  <th>Category</th>
                  <th>Occurrences</th>
                </tr>
              </thead>
              <tbody>
                {pool.data?.items.map((item) => (
                  <tr
                    key={item.run_id}
                    className={
                      selected === item.run_id ? "interactive-row selected" : "interactive-row"
                    }
                    tabIndex={0}
                    aria-label={`Open UNKNOWN detail: ${item.content}`}
                    onClick={() => setSelected(item.run_id)}
                    onKeyDown={(event) => {
                      if (event.target !== event.currentTarget) return;
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelected(item.run_id);
                      }
                    }}
                  >
                    <td>{item.content}</td>
                    <td>
                      <span className="chip locked">{item.triage.status}</span>
                    </td>
                    <td>
                      {item.triage.category && <span className="chip">{item.triage.category}</span>}
                    </td>
                    <td className="muted">×{item.recurrence}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </ProjectShell>
      {selected && (
        <Dialog label="UNKNOWN detail" onClose={() => setSelected(null)}>
          <p className="eyebrow">UNKNOWN / {detail.data?.triage.status ?? "…"}</p>
          <h2>Triage</h2>
          {detail.isPending && <p className="muted">Loading…</p>}
          {detail.data && (
            <>
              <p className="muted">reason: {detail.data.supervision_reason}</p>
              <pre className="detail-pre">{detail.data.content}</pre>
              {detail.data.probabilities && Object.keys(detail.data.probabilities).length > 0 && (
                <div className="prob-panel" aria-label="Bounded probability readout">
                  {Object.entries(detail.data.probabilities)
                    .sort(([keyA, valA], [keyB, valB]) => {
                      if (keyA === "UNKNOWN") return -1;
                      if (keyB === "UNKNOWN") return 1;
                      return valB - valA;
                    })
                    .map(([choice, prob]) => (
                      <div key={choice} className="prob-row">
                        <code>{choice}</code>
                        <div className="prob-track">
                          <div
                            className={`prob-fill${choice === "UNKNOWN" ? " unknown" : ""}`}
                            style={{ transform: `scaleX(${Math.max(0.02, prob)})` }}
                          />
                        </div>
                        <span>{(prob * 100).toFixed(1)}%</span>
                      </div>
                    ))}
                </div>
              )}
              <label>
                Category (advisory only)
                <select
                  value={triageCategory}
                  onChange={(event) => setTriageCategory(event.target.value)}
                >
                  {CATEGORIES.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Assignee
                <input
                  value={assignee}
                  onChange={(event) => setAssignee(event.target.value)}
                  placeholder="reviewer@…"
                />
              </label>
            </>
          )}
          <div className="modal-actions">
            {detail.data && (
              <>
                <button onClick={() => triage.mutate(selected)}>Save triage</button>
                {detail.data.triage.status === "needs_evidence" && (
                  <>
                    <button
                      className="ghost"
                      onClick={() => transition.mutate({ runId: selected, to: "triaged" })}
                    >
                      Mark triaged
                    </button>
                    <button
                      className="ghost danger"
                      onClick={() => transition.mutate({ runId: selected, to: "dismissed" })}
                    >
                      Dismiss
                    </button>
                  </>
                )}
                {detail.data.triage.status === "triaged" && (
                  <button
                    className="ghost danger"
                    onClick={() => transition.mutate({ runId: selected, to: "dismissed" })}
                  >
                    Dismiss
                  </button>
                )}
              </>
            )}
            <button className="ghost" onClick={() => setSelected(null)}>
              Close
            </button>
          </div>
        </Dialog>
      )}
    </main>
  );
}
