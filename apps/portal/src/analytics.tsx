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
  provider_cost_measurement?: {
    status: "complete" | "partial" | "unavailable";
    amount: number | null;
    declared_cost: number;
  };
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
  const width = 1120;
  const height = 200;
  const padX = 48;
  const padRight = 36;
  const padTop = 38;
  const padBottom = 34;
  const plotW = width - padX - padRight;
  const plotH = height - padTop - padBottom;
  const max = Math.max(...daily.map((point) => Math.max(point.total, point.unknowns)), 1);
  const points = daily.map((point, index) => {
    const x =
      daily.length === 1
        ? padX + plotW / 2
        : padX + (index / Math.max(daily.length - 1, 1)) * plotW;
    const yTotal = padTop + plotH - (point.total / max) * plotH;
    const yUnknown = padTop + plotH - (point.unknowns / max) * plotH;
    return { x, yTotal, yUnknown, point };
  });
  const totalArea =
    points.length > 1
      ? `M ${points[0]!.x},${padTop + plotH} ` +
        points.map((p) => `L ${p.x},${p.yTotal}`).join(" ") +
        ` L ${points[points.length - 1]!.x},${padTop + plotH} Z`
      : "";
  const unknownArea =
    points.length > 1
      ? `M ${points[0]!.x},${padTop + plotH} ` +
        points.map((p) => `L ${p.x},${p.yUnknown}`).join(" ") +
        ` L ${points[points.length - 1]!.x},${padTop + plotH} Z`
      : "";
  const midTick = Math.round(max / 2);

  return (
    <svg
      className="trend"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Runs and UNKNOWN daily trend"
    >
      <defs>
        <linearGradient id="oc-total-area-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#c6f277" stopOpacity="0.14" />
          <stop offset="100%" stopColor="#c6f277" stopOpacity="0.0" />
        </linearGradient>
        <linearGradient id="oc-unk-series-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#f2c879" stopOpacity="0.22" />
          <stop offset="100%" stopColor="#f2c879" stopOpacity="0.0" />
        </linearGradient>
      </defs>
      <g aria-hidden="true">
        <circle cx={padX + 6} cy={14} r="4" fill="#c6f277" />
        <text x={padX + 16} y={17} fontSize="9.5" fill="#a8b4aa" fontFamily="var(--font-mono)">
          TOTAL RUNS
        </text>
        <circle cx={padX + 106} cy={14} r="4" fill="#f2c879" />
        <text x={padX + 116} y={17} fontSize="9.5" fill="#f2c879" fontFamily="var(--font-mono)">
          UNKNOWN EVIDENCE
        </text>
      </g>
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
      {totalArea && <path d={totalArea} fill="url(#oc-total-area-grad)" />}
      {unknownArea && <path d={unknownArea} fill="url(#oc-unk-series-grad)" />}
      <polyline
        fill="none"
        stroke="#c6f277"
        strokeWidth="1.75"
        strokeDasharray="4 3"
        points={points.map((p) => `${p.x},${p.yTotal}`).join(" ")}
      />
      <polyline
        fill="none"
        stroke="#f2c879"
        strokeWidth="2.25"
        points={points.map((p) => `${p.x},${p.yUnknown}`).join(" ")}
      />
      {points.map(({ x, yTotal, yUnknown, point }) => (
        <g key={point.date}>
          <circle cx={x} cy={yTotal} r="3" fill="#c6f277" />
          <circle cx={x} cy={yUnknown} r="3.5" fill="#0e1512" stroke="#f2c879" strokeWidth="2" />
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
          <text
            x={x}
            y={yUnknown - 8}
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
              <em className={delta > 0 ? "field-error" : "chip locked"}>
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
          <b>
            {summary.data.provider_cost == null
              ? "Unavailable"
              : `$${summary.data.provider_cost.toFixed(4)}`}
          </b>
          <span>provider cost (window)</span>
          {summary.data.provider_cost_measurement?.status === "partial" && (
            <span>
              Partial: declared subtotal $
              {summary.data.provider_cost_measurement.declared_cost.toFixed(4)}; missing costs
              remain unknown.
            </span>
          )}
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
  const maxClassCount = Math.max(...summary.data.top_classes.map((c) => c.count), 1);

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
            <div className="table-wrap" role="region" aria-label="Top classes" tabIndex={0}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Class</th>
                    <th>Volume</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.data.top_classes.map((entry) => (
                    <tr key={entry.class}>
                      <td>
                        <code>{entry.class}</code>
                        <div className="prob-track" aria-hidden="true" style={{ marginTop: 6 }}>
                          <div
                            className="prob-fill"
                            style={{
                              transform: `scaleX(${Math.max(0.03, entry.count / maxClassCount)})`,
                            }}
                          />
                        </div>
                      </td>
                      <td>{entry.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="panel">
            <div className="panel-head">
              <h3>Alert rules</h3>
              <button className="ghost" onClick={() => evaluate.mutate()}>
                Evaluate now
              </button>
            </div>
            <div className="table-wrap" role="region" aria-label="Alert rules" tabIndex={0}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Threshold</th>
                    <th>Window</th>
                  </tr>
                </thead>
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
                      <td colSpan={3} className="muted">
                        No rules yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="panel-head filter-toolbar">
              <select
                aria-label="Alert metric"
                value={metric}
                onChange={(event) => setMetric(event.target.value)}
              >
                <option value="unknown_rate">unknown_rate</option>
                <option value="recurring_unknowns">recurring_unknowns</option>
                <option value="latency">latency</option>
                <option value="cost">cost</option>
              </select>
              <input
                aria-label="Alert threshold"
                value={threshold}
                onChange={(event) => setThreshold(event.target.value)}
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
