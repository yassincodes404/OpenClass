"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Project } from "@openclass/sdk";

const SECTIONS = [
  "overview",
  "data",
  "decisions",
  "knowledge",
  "evolution",
  "evaluations",
  "integrations",
  "analytics",
  "runs",
  "settings",
] as const;

export function ProjectShell({
  project,
  active,
  children,
}: {
  project: Project;
  active: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  return (
    <main>
      <section className="project-heading">
        <div className="brand">
          <span className="mark">OC</span>
          <div>
            <div className="eyebrow">OpenClass · Project</div>
            <h1>{project.name}</h1>
          </div>
        </div>
        <span className="badge">{project.status}</span>
      </section>

      <nav className="project-nav" aria-label="Project sections">
        {SECTIONS.map((section) => {
          const href =
            section === "overview"
              ? `/projects/${project.id}`
              : `/projects/${project.id}/${section}`;
          return (
            <Link
              key={section}
              href={href}
              className={pathname === href ? "project-tab active-tab" : "project-tab"}
            >
              {section === "evolution"
                ? "Evidence & cases"
                : section[0].toUpperCase() + section.slice(1)}
            </Link>
          );
        })}
      </nav>

      {active === "overview" ? null : <p className="hint">Project: {project.name}</p>}
      {children}
    </main>
  );
}

export function UnavailableSection({ section }: { section: string }) {
  return (
    <section className="panel">
      <h2 className="section-heading">{section}</h2>
      <p className="empty">
        Not available in this build yet.{" "}
        <span>This section lands with a later vertical slice.</span>
      </p>
    </section>
  );
}
