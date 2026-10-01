"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { OpenClass, type Project, type ProjectSummary } from "@openclass/sdk";
import { ProjectShell } from "../shell";

const client = new OpenClass("");

export default function ProjectOverview({ params }: { params: Promise<{ id: string }> }) {
  const [id, setId] = useState<string | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [error, setError] = useState("");
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    params.then((value) => setId(value.id));
  }, [params]);

  useEffect(() => {
    if (!id) return;
    client
      .project(id)
      .then(setProject)
      .catch(() => setNotFound(true));
    client
      .projectSummary(id)
      .then(setSummary)
      .catch(() => setSummary(null));
  }, [id]);

  if (notFound) {
    return (
      <main>
        <p className="empty" role="alert">
          Project not found.
        </p>
        <p>
          <Link href="/projects">Back to projects</Link>
        </p>
      </main>
    );
  }

  if (!project) {
    return (
      <main>
        <p className="empty" role="status">
          Loading project…
        </p>
      </main>
    );
  }

  const counters: Array<[string, string | number | null]> = [
    ["Events", summary?.events ?? 0],
    ["Decision runs", summary?.decision_runs ?? 0],
    ["Unknowns", summary?.unknowns ?? 0],
    ["Pending evidence", summary?.pending_evidence ?? 0],
    ["Active policy", summary?.active_policy ?? "—"],
    ["Pending candidates", summary?.pending_candidates ?? 0],
  ];

  return (
    <ProjectShell project={project} active="overview">
      <section className="panel">
        <h2 className="section-heading">Overview</h2>
        <p className="lede">{project.description || "No description yet."}</p>
        <dl className="project-meta">
          <div>
            <dt>Slug</dt>
            <dd>{project.slug}</dd>
          </div>
          <div>
            <dt>Created</dt>
            <dd>{new Date(project.created_at).toLocaleDateString()}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{project.status}</dd>
          </div>
        </dl>
      </section>

      <section className="panel">
        <h2 className="section-heading">Activity</h2>
        <ul className="counter-grid">
          {counters.map(([label, value]) => (
            <li key={label}>
              <span className="counter-value">{String(value)}</span>
              <span className="counter-label">{label}</span>
            </li>
          ))}
        </ul>
        <p className="hint">
          Counters reflect project-scoped data that arrives with later slices; they are real server
          values, not samples.
        </p>
      </section>
    </ProjectShell>
  );
}
