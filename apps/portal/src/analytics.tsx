import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { controlFetch } from "./api";
import { useAuth } from "./auth";
import { ProjectShell, type Project } from "./projects";

export type Summary = {
  window_days: number;
  unknown_rate: number | null;
  previous_unknown_rate: number | null;
  unknown_rate_delta: number | null;
  latency_avg_ms: number | null;
  provider_cost: number | null;
  recurring_unknowns: number | null;
  top_classes: Array<{ class: string; count: number }>;
  daily: Array<{ date: string; total: number; unknowns: number }>;
  pending_reviews: number;
  recent_versions: Array<{ to_version: number; event: string; created_at: string }>;
  recent_alerts: Array<{ metric: string; measured: number; threshold: number; created_at: string }>;
  simulated?: boolean;
};
export type AlertRule = {
  id: string;
  metric: string;
  threshold: number;
  window: string;
  enabled: boolean;
};
export type OpsEvent = { event: string; actor: string; created_at: string };

export function useSummary(projectId: string) {
  const token = useAuth().token() ?? "";
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: async (): Promise<Project> =>
      (await controlFetch(`/projects/${projectId}`, token)) as Project,
  });
  const summary = useQuery({
    queryKey: ["summary", projectId],
    enabled: project.isSuccess,
    refetchInterval: 10_000,
    queryFn: async (): Promise<Summary> =>
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/analytics/summary`,
        token,
      )) as Summary,
  });
  return { project, summary };
}

function TrendChart({
  daily,
}: {
  daily: Array<{ date: string; total: number; unknowns: number }>;
}) {
  if (daily.length === 0) return <p className="muted">No runs in the window yet.</p>;
  const width = Math.min(daily.length * 46, 620);
  const height = 120;
  const max = Math.max(...daily.map((point) => point.total), 1);
  const points = daily.map((point, index) => {
    const x = (index / Math.max(daily.length - 1, 1)) * (width - 24) + 12;
    const yTotal = height - 14 - (point.total / max) * (height - 34);
    const yUnknown = height - 14 - (point.unknowns / max) * (height - 34);
    return { x, yTotal, yUnknown, point };
  });
  return (
    <svg
      className="trend"
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height={height}
      role="img"
      aria-label="Runs and UNKNOWN daily trend"
    >
      <polyline
        fill="none"
        stroke="#7a8a6a"
        strokeWidth="1.5"
        points={points.map((p) => `${p.x},${p.yTotal}`).join(" ")}
      />
      <polyline
        fill="none"
        stroke="#c4f48a"
        strokeWidth="2"
        points={points.map((p) => `${p.x},${p.yUnknown}`).join(" ")}
      />
      {points.map(({ x, yUnknown, point }) => (
        <g key={point.date}>
          <circle cx={x} cy={yUnknown} r="3" fill="#c4f48a" />
          <text x={x} y={height - 2} textAnchor="middle" fontSize="8" fill="#a6b0a6">
            {point.date.slice(5)}
          </text>
          <text x={x} y={yUnknown - 6} textAnchor="middle" fontSize="8" fill="#eef0e8">
            {point.unknowns}
          </text>
        </g>
      ))}
    </svg>
  );
}

export function OverviewKpis({ projectId }: { projectId: string }) {
  const { project, summary } = useSummary(projectId);
  if (summary.data) {
    const delta = summary.data.unknown_rate_delta;
    return (
      <div className="metrics">
        <div>
          <b>
            {summary.data.unknown_rate === null
              ? "—"
              : `${(summary.data.unknown_rate * 100).toFixed(1)}%`}
          </b>
          <span>
            UNKNOWN rate ({summary.data.window_days}d)
            {delta !== null && (
              <em
                className={delta > 0 ? "field-error" : "chip locked"}
                style={{ display: "block" }}
              >
                {delta > 0 ? "▲" : "▼"} {Math.abs(delta * 100).toFixed(1)} pts vs prior window
              </em>
            )}
          </span>
        </div>
        <div>
          <b>{summary.data.pending_reviews}</b>
          <span>pending reviews</span>
        </div>
        <div>
          <b>{summary.data.recurring_unknowns ?? 0}×</b>
          <span>most repeated unknown</span>
        </div>
        <div>
          <b>${(summary.data.provider_cost ?? 0).toFixed(4)}</b>
          <span>provider cost (window)</span>
        </div>
      </div>
    );
  }
  return project.isPending ? (
    <p className="lede">Loading…</p>
  ) : (
    <p className="muted">Metrics unavailable.</p>
  );
}

export function AnalyticsPage() {
  const { projectId = "" } = useParams();
  const token = useAuth().token() ?? "";
  const queryClient = useQueryClient();
  const { project, summary } = useSummary(projectId);
  const rules = useQuery({
    queryKey: ["alert-rules", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<AlertRule[]> =>
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/alerts/rules`,
        token,
      )) as AlertRule[],
  });
  const [metric, setMetric] = useState("unknown_rate");
  const [threshold, setThreshold] = useState("0.1");
  const [feedback, setFeedback] = useState<string | null>(null);
  const createRule = useMutation({
    mutationFn: async () =>
      controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/alerts/rules`,
        token,
        {
          method: "POST",
          body: JSON.stringify({ metric, threshold: Number(threshold) }),
        },
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["alert-rules", projectId] }),
    onError: (error: Error) => setFeedback(error.message),
  });
  const evaluate = useMutation({
    mutationFn: async () =>
      controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/alerts/evaluate`,
        token,
        { method: "POST" },
      ),
    onSuccess: (result) => {
      const fired = (result as { fired?: number }).fired ?? 0;
      setFeedback(`Evaluate: ${fired} alert(s) fired`);
      void queryClient.invalidateQueries({ queryKey: ["summary", projectId] });
    },
    onError: (error: Error) => setFeedback(error.message),
  });

  // Live updates: poll the resumable event log (SSE fallback transport).
  const [live, setLive] = useState<string>("waiting for events…");
  useEffect(() => {
    if (!project.isSuccess) return;
    let cursor = "";
    let stopped = false;
    const tick = async () => {
      try {
        const params = cursor ? `?after=${encodeURIComponent(cursor)}` : "";
        const page = (await controlFetch(
          `/workspaces/${project.data!.workspace_id}/projects/${projectId}/ops/events${params}`,
          token,
        )) as { events: OpsEvent[]; next_cursor: string };
        if (page.events.length > 0) {
          cursor = page.next_cursor;
          setLive(
            `${page.events[page.events.length - 1].event} · ${new Date(page.events[page.events.length - 1].created_at).toLocaleTimeString()}`,
          );
        }
      } catch {
        /* polling continues */
      }
      if (!stopped) window.setTimeout(tick, 5000);
    };
    void tick();
    return () => {
      stopped = true;
    };
  }, [project.isSuccess, projectId, token, project.data]);

  if (project.isPending || summary.isPending)
    return (
      <main>
        <p className="lede">Loading analytics…</p>
      </main>
    );
  if (!project.data || !summary.data)
    return (
      <main>
        <p className="lede">Analytics unavailable.</p>
      </main>
    );
  return (
    <main>
      <ProjectShell project={project.data} active="/analytics">
        <section className="signal">
          <p className="eyebrow">
            ANALYTICS / LIVE{summary.data.simulated ? " / SIMULATED PROVIDER" : ""}
          </p>
          <h2>Is the system healthy?</h2>
          <p className="muted">Every number is a measured persisted value. Live tail: {live}</p>
          <div className="panel">
            <div className="panel-head">
              <h3>Runs vs UNKNOWN ({summary.data.window_days}d)</h3>
            </div>
            <TrendChart daily={summary.data.daily} />
          </div>
          <div className="panel">
            <div className="panel-head">
              <h3>Top classes</h3>
            </div>
            <table className="table">
              <tbody>
                {summary.data.top_classes.map((entry) => (
                  <tr key={entry.class}>
                    <td>
                      <code>{entry.class}</code>
                    </td>
                    <td>{entry.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="panel">
            <div className="panel-head">
              <h3>Alert rules</h3>
              <button className="ghost" onClick={() => evaluate.mutate()}>
                Evaluate now
              </button>
            </div>
            <table className="table">
              <tbody>
                {rules.data?.map((rule) => (
                  <tr key={rule.id}>
                    <td>{rule.metric}</td>
                    <td>&gt; {rule.threshold}</td>
                    <td>{rule.window}</td>
                  </tr>
                ))}
                {(rules.data?.length ?? 0) === 0 && (
                  <tr>
                    <td className="muted">No rules yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
            <div className="panel-head">
              <select value={metric} onChange={(event) => setMetric(event.target.value)}>
                <option value="unknown_rate">unknown_rate</option>
                <option value="recurring_unknowns">recurring_unknowns</option>
                <option value="latency">latency</option>
                <option value="cost">cost</option>
              </select>
              <input
                value={threshold}
                onChange={(event) => setThreshold(event.target.value)}
                style={{ width: 90 }}
              />
              <button
                disabled={!threshold || createRule.isPending}
                onClick={() => createRule.mutate()}
              >
                Add rule
              </button>
            </div>
            {feedback && <p className="muted">{feedback}</p>}
          </div>
          {summary.data.recent_alerts.length > 0 && (
            <div className="panel">
              <div className="panel-head">
                <h3>Recent alerts</h3>
              </div>
              <ul className="timeline">
                {summary.data.recent_alerts.map((alert, index) => (
                  <li key={index}>
                    {alert.metric} {alert.measured.toFixed(3)} &gt; {alert.threshold} ·{" "}
                    {new Date(alert.created_at).toLocaleString()}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="panel">
            <div className="panel-head">
              <h3>Recent versions</h3>
            </div>
            <ul className="timeline">
              {summary.data.recent_versions.map((version, index) => (
                <li key={index}>
                  {version.event} → v{version.to_version} ·{" "}
                  {new Date(version.created_at).toLocaleString()}
                </li>
              ))}
              {summary.data.recent_versions.length === 0 && <li>No promotions yet.</li>}
            </ul>
          </div>
        </section>
      </ProjectShell>
    </main>
  );
}
