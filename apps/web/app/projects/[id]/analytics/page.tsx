"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { type Project, type ProjectAnalytics } from "@openclass/sdk";
import { ProjectShell } from "../../shell";

import { workspaceClient as client } from "../../../../lib/workspace-client";

function formatLatency(value: number | null) {
  return value === null ? "—" : `${value.toFixed(1)} ms`;
}

export default function AnalyticsPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [analytics, setAnalytics] = useState<ProjectAnalytics | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    Promise.all([client.project(id), client.projectAnalytics(id)])
      .then(([loadedProject, loadedAnalytics]) => {
        setProject(loadedProject);
        setAnalytics(loadedAnalytics);
        setError("");
      })
      .catch(() => setError("Analytics could not be loaded."));
  }, [id]);

  if (error) return <main role="alert">{error}</main>;
  if (!project || !analytics) return <main role="status">Loading analytics…</main>;

  const counters: Array<[string, string | number]> = [
    ["Events", analytics.total_events],
    ["Decision runs", analytics.total_runs],
    ["UNKNOWN", analytics.unknown_runs],
    [
      "UNKNOWN rate",
      analytics.unknown_rate === null ? "—" : `${(analytics.unknown_rate * 100).toFixed(1)}%`,
    ],
    ["Real inference", analytics.real_inference_runs],
    ["Simulated", analytics.simulated_runs],
    ["p50 latency", formatLatency(analytics.p50_latency_ms)],
    ["p95 latency", formatLatency(analytics.p95_latency_ms)],
  ];

  return (
    <ProjectShell project={project} active="analytics">
      <section className="panel">
        <h2>Analytics</h2>
        <p className="lede">
          Measured from this project’s stored decision runs. No predicted label is treated as ground
          truth.
        </p>
        <ul className="counter-grid">
          {counters.map(([label, value]) => (
            <li key={label}>
              <span className="counter-value">{value}</span>
              <span className="counter-label">{label}</span>
            </li>
          ))}
        </ul>
      </section>
      <section className="panel">
        <h2>Choices</h2>
        {analytics.choices.length === 0 ? (
          <p className="empty">No decisions have been run yet.</p>
        ) : (
          <div className="analytics-bars">
            {analytics.choices.map(({ key, count }) => (
              <div className="analytics-row" key={key}>
                <span>{key}</span>
                <div className="analytics-track">
                  <span style={{ width: `${(count / analytics.total_runs) * 100}%` }} />
                </div>
                <strong>{count}</strong>
              </div>
            ))}
          </div>
        )}
      </section>
      <section className="panel">
        <h2>Providers</h2>
        {analytics.providers.length === 0 ? (
          <p className="empty">No provider calls recorded.</p>
        ) : (
          <ul>
            {analytics.providers.map(({ key, count }) => (
              <li key={key}>
                {key}: {count} runs
              </li>
            ))}
          </ul>
        )}
        <p className="hint">
          Latency is provider decision time recorded on completed runs. Accuracy requires reviewed
          labels and is not inferred here.
        </p>
      </section>
    </ProjectShell>
  );
}
