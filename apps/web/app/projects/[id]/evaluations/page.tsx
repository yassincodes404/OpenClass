"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import type { Project } from "@openclass/sdk";
import { workspaceClient } from "../../../../lib/workspace-client";
import { ProjectShell } from "../../shell";
import { ReplayWorkspace } from "../../../../../portal/src/replay-workspace";

export default function EvaluationsPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    void workspaceClient
      .project(id)
      .then((value) => {
        if (!cancelled) setProject(value);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Project unavailable.");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);
  if (error)
    return (
      <main>
        <p role="alert">{error}</p>
      </main>
    );
  if (!project)
    return (
      <main>
        <p role="status">Loading evaluations…</p>
      </main>
    );
  return (
    <ProjectShell project={project} active="evaluations">
      <ReplayWorkspace key={id} client={workspaceClient} projectId={id} />
    </ProjectShell>
  );
}
