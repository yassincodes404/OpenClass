"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { OpenClass, type Project } from "@openclass/sdk";
import { ProjectShell, UnavailableSection } from "../../shell";

const client = new OpenClass("");
const TITLES: Record<string, string> = {
  data: "Data",
  decisions: "Decisions",
  knowledge: "Knowledge",
  evolution: "Evolution",
  analytics: "Analytics",
  runs: "Runs",
};

export default function ProjectSection() {
  const params = useParams<{ id: string; section: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!params?.id) return;
    client
      .project(params.id)
      .then(setProject)
      .catch(() => setNotFound(true));
  }, [params?.id]);

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
          Loading project…
        </p>
      </main>
    );
  }

  const title = TITLES[params.section] ?? params.section;

  return (
    <ProjectShell project={project} active={params.section}>
      <UnavailableSection section={title} />
    </ProjectShell>
  );
}
