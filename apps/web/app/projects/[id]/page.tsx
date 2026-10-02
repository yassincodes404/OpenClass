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
      <section className="project-hero" aria-labelledby="project-overview-title">
        <div className="project-hero-copy">
          <p className="eyebrow">PROJECT / CONTROL ROOM</p>
          <h2 id="project-overview-title">A governed view of what the system knows.</h2>
          <p>{project.description || "No description yet. Add context in Settings to orient reviewers."}</p>
          <div className="project-actions">
            <Link className="primary-link" href={`/projects/${project.slug}/data`}>Ingest observations <span aria-hidden="true">↗</span></Link>
            <Link className="quiet-link" href={`/projects/${project.slug}/decisions`}>Configure decisions</Link>
          </div>
        </div>
        <dl className="project-facts">
          <div><dt>Workspace ID</dt><dd><code>{project.slug}</code></dd></div>
          <div><dt>Established</dt><dd>{new Date(project.created_at).toLocaleDateString()}</dd></div>
          <div><dt>Lifecycle</dt><dd><span className="status-dot" />{project.status}</dd></div>
        </dl>
      </section>

      <section className="project-activity" aria-labelledby="project-activity-title">
        <div className="project-section-heading">
          <div><p className="eyebrow">LIVE PROJECT SIGNAL</p><h2 id="project-activity-title">Activity at a glance</h2></div>
          <p>Scoped, persisted counters—not samples.</p>
        </div>
        <ul className="counter-grid">
          {counters.map(([label, value]) => (
            <li key={label}>
              <span className="counter-value">{String(value)}</span>
              <span className="counter-label">{label}</span>
            </li>
          ))}
        </ul>
      </section>
    </ProjectShell>
  );
}
