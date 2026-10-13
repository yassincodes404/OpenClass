"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { OpenClass, type Project } from "@openclass/sdk";

const client = new OpenClass("");

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [createError, setCreateError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setLoading(true);
    setLoadError("");
    try {
      setProjects(await client.projects());
    } catch (error) {
      setLoadError(
        error instanceof Error && "status" in error
          ? `Server error ${String((error as { status?: number }).status)}`
          : "Server unavailable · start the API and refresh",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function create(event: FormEvent) {
    event.preventDefault();
    setCreateError("");
    if (!name.trim()) {
      setCreateError("Project name is required");
      return;
    }
    setBusy(true);
    try {
      const project = await client.createProject({
        name: name.trim(),
        description: description.trim(),
      });
      setProjects((current) => [project, ...current]);
      setName("");
      setDescription("");
    } catch (error) {
      setCreateError(
        error instanceof Error && "status" in error
          ? `Create failed (server error ${String((error as { status?: number }).status)})`
          : "Create failed: server unavailable",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <section className="intro compact-intro">
        <p className="eyebrow">OPENCLASS / PORTAL</p>
        <h1>Projects</h1>
        <p className="lede">
          A project is a persistent workspace that owns data, decisions, knowledge and every
          evolution of them.
        </p>
      </section>

      <section className="panel">
        <h2 className="section-heading">Create project</h2>
        <form className="project-form" onSubmit={create}>
          <label>
            Name
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="GymHolic Intelligence"
              maxLength={200}
            />
          </label>
          <label>
            Description
            <input
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Customer intelligence experiment"
              maxLength={2000}
            />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? "Creating…" : "Create project"}
          </button>
        </form>
        {createError ? (
          <p role="alert" className="form-error">
            {createError}
          </p>
        ) : null}
      </section>

      <section className="panel">
        <h2 className="section-heading">Projects</h2>
        {loading ? (
          <p className="empty" role="status">
            Loading projects…
          </p>
        ) : loadError ? (
          <p className="empty" role="alert">
            {loadError}
          </p>
        ) : projects.length === 0 ? (
          <p className="empty">
            No projects yet. <span>Create your first project above.</span>
          </p>
        ) : (
          <ul className="project-list">
            {projects.map((project) => (
              <li key={project.id}>
                <Link href={`/projects/${project.slug}`} className="project-link">
                  <strong>{project.name}</strong>
                  <span className="muted">
                    Created {new Date(project.created_at).toLocaleDateString()} · {project.status}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
