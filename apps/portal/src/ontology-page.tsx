import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { controlFetch } from "./api";
import { useAuth } from "./auth";
import { ProjectShell, type Project } from "./projects";

export type Version = {
  version_number: number;
  origin: string;
  rationale: string;
  actor: string;
  created_at: string;
  choices: Array<{ key: string; label?: string }>;
};
export type OntologyEvent = {
  event: string;
  actor: string;
  from_version: number | null;
  to_version: number;
  detail: Record<string, unknown>;
};
export type Ontology = {
  current_choices: Array<{ key: string }>;
  versions: Version[];
  events: OntologyEvent[];
};
export type Diff = {
  from_version: number;
  to_version: number;
  changes: { added: string[]; removed: string[]; modified: string[] };
};

function useToken() {
  return useAuth().token() ?? "";
}

export function OntologyPage() {
  const { projectId = "" } = useParams();
  const token = useToken();
  const queryClient = useQueryClient();
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: async (): Promise<Project> =>
      (await controlFetch(`/projects/${projectId}`, token)) as Project,
  });
  const ontology = useQuery({
    queryKey: ["ontology", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<Ontology> =>
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/ontology`,
        token,
      )) as Ontology,
  });
  const [range, setRange] = useState<{ from: number; to: number } | null>(null);
  const diff = useQuery({
    queryKey: ["ontology-diff", projectId, range],
    enabled: range !== null,
    queryFn: async (): Promise<Diff> =>
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/ontology/diff?from=${range!.from}&to=${range!.to}`,
        token,
      )) as Diff,
  });
  const [rollbackTo, setRollbackTo] = useState<number | "">("");
  const [message, setMessage] = useState<string | null>(null);
  const rollback = useMutation({
    mutationFn: async (fromVersion: number) =>
      controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/ontology/rollback`,
        token,
        {
          method: "POST",
          body: JSON.stringify({ from_version: fromVersion, rationale: "portal rollback" }),
        },
      ),
    onSuccess: (result) => {
      const version = (result as { version?: { version_number?: number } }).version;
      setMessage(
        `Rollback complete — new version v${version?.version_number ?? "?"} derived from the older snapshot.`,
      );
      setRollbackTo("");
      void queryClient.invalidateQueries({ queryKey: ["ontology", projectId] });
    },
    onError: (error: Error) => setMessage(error.message),
  });
  if (project.isPending || ontology.isPending)
    return (
      <main>
        <p className="lede">Loading ontology…</p>
      </main>
    );
  if (!project.data || !ontology.data)
    return (
      <main>
        <p className="lede">Ontology unavailable.</p>
      </main>
    );
  const versions = ontology.data.versions;
  const latest = versions.length ? versions[versions.length - 1].version_number : 0;
  return (
    <main>
      <ProjectShell project={project.data} active="/ontology">
        <section className="signal">
          <p className="eyebrow">ONTOLOGY / IMMUTABLE VERSIONS</p>
          <h2>vN never changes; rollback creates a new version.</h2>
          <p className="muted">
            Current: {ontology.data.current_choices.map((choice) => choice.key).join(", ")} ·{" "}
            {versions.length} version(s)
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>Version</th>
                <th>Origin</th>
                <th>Actor</th>
                <th>Rationale</th>
                <th>Choices</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {versions.map((version) => (
                <tr key={version.version_number}>
                  <td>
                    <b>v{version.version_number}</b>
                    {version.version_number === latest ? " (current)" : ""}
                  </td>
                  <td>{version.origin}</td>
                  <td className="muted">{version.actor}</td>
                  <td className="muted">{version.rationale.slice(0, 50)}</td>
                  <td>{version.choices.map((choice) => choice.key).join(", ")}</td>
                  <td>
                    {version.version_number !== latest && version.version_number < latest && (
                      <button
                        className="ghost"
                        onClick={() => setRange({ from: version.version_number, to: latest })}
                      >
                        Diff to latest
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {range && (
            <div className="panel">
              <div className="panel-head">
                <h3>
                  Diff v{range.from} → v{range.to}
                </h3>
                <button className="ghost" onClick={() => setRange(null)}>
                  Close
                </button>
              </div>
              {diff.data && (
                <>
                  <p>added: {diff.data.changes.added.join(", ") || "—"}</p>
                  <p>removed: {diff.data.changes.removed.join(", ") || "—"}</p>
                  <p>modified: {diff.data.changes.modified.join(", ") || "—"}</p>
                </>
              )}
            </div>
          )}
          <div className="panel">
            <div className="panel-head">
              <h3>Rollback (creates a new version)</h3>
            </div>
            <div className="panel-head">
              <select
                value={rollbackTo}
                onChange={(event) =>
                  setRollbackTo(event.target.value ? Number(event.target.value) : "")
                }
              >
                <option value="">Target version…</option>
                {versions
                  .filter((v) => v.version_number !== latest)
                  .map((v) => (
                    <option key={v.version_number} value={v.version_number}>
                      v{v.version_number}
                    </option>
                  ))}
              </select>
              <button
                className="ghost danger"
                disabled={rollbackTo === "" || rollback.isPending}
                onClick={() => rollback.mutate(Number(rollbackTo))}
              >
                Roll back to selected
              </button>
            </div>
            {message && (
              <p className="muted" role="status">
                {message}
              </p>
            )}
          </div>
          <div className="panel">
            <div className="panel-head">
              <h3>Event history</h3>
            </div>
            <ul className="timeline">
              {ontology.data.events.map((event, index) => (
                <li key={index}>
                  {event.event} · v{event.from_version ?? "?"} → v{event.to_version} · by{" "}
                  {event.actor}
                </li>
              ))}
              {ontology.data.events.length === 0 && <li>No promotion events yet.</li>}
            </ul>
          </div>
        </section>
      </ProjectShell>
    </main>
  );
}
