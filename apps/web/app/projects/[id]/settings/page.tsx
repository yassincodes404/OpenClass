"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "next/navigation";
import { type Project } from "@openclass/sdk";
import { ProjectShell } from "../../shell";

import { workspaceClient as client } from "../../../../lib/workspace-client";

export default function ProjectSettings() {
  const params = useParams<{ id: string }>();
  const slug = params?.id;
  const [project, setProject] = useState<Project | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!slug) return;
    client
      .project(slug)
      .then((loaded) => {
        setProject(loaded);
        setName(loaded.name);
        setDescription(loaded.description);
      })
      .catch(() => setNotFound(true));
  }, [slug]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!slug || !project) return;
    setError("");
    setSaved(false);
    if (!name.trim()) {
      setError("Project name is required");
      return;
    }
    setBusy(true);
    try {
      const updated = await client.updateProject(slug, {
        name: name.trim(),
        description: description.trim(),
      });
      setProject(updated);
      setSaved(true);
    } catch {
      setError("Save failed: server error");
    } finally {
      setBusy(false);
    }
  }

  if (notFound) {
    return (
      <main>
        <p className="empty" role="alert">
          Project not found.
        </p>
      </main>
    );
  }
  if (!project) {
    return (
      <main>
        <p className="empty" role="status">
          Loading settings…
        </p>
      </main>
    );
  }

  return (
    <ProjectShell project={project} active="settings">
      <section className="panel">
        <h2 className="section-heading">Settings</h2>
        <form className="project-form" onSubmit={save}>
          <label>
            Name
            <input value={name} onChange={(event) => setName(event.target.value)} maxLength={200} />
          </label>
          <label>
            Description
            <input
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={2000}
            />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? "Saving…" : "Save changes"}
          </button>
        </form>
        {saved ? (
          <p role="status" className="form-ok">
            Saved. Changes are persisted server-side.
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="form-error">
            {error}
          </p>
        ) : null}
      </section>
    </ProjectShell>
  );
}
