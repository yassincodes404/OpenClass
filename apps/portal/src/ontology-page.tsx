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
  const latest = versions.length ? Math.max(...versions.map((v) => v.version_number)) : 0;
  const orderedVersions = [...versions].sort((a, b) => a.version_number - b.version_number);
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
          {orderedVersions.length > 0 && (
            <div className="panel">
              <div className="panel-head">
                <h3>Immutable snapshot lineage</h3>
                <span className="chip locked">UNKNOWN — permanent</span>
              </div>
              <svg
                className="trend"
                role="img"
                aria-label="Ontology version lineage"
                viewBox={`0 0 ${Math.max(920, orderedVersions.length * 180 + 280)} 88`}
                preserveAspectRatio="xMinYMid meet"
              >
                {orderedVersions.map((v, idx) => {
                  const x = 68 + idx * 172;
                  const isCurrent = v.version_number === latest;
                  return (
                    <g key={v.version_number}>
                      {idx > 0 && (
                        <line
                          x1={x - 116}
                          y1={44}
                          x2={x - 56}
                          y2={44}
                          stroke="rgba(198, 242, 119, 0.45)"
                          strokeWidth="2"
                        />
                      )}
                      <rect
                        x={x - 56}
                        y={16}
                        width="112"
                        height="56"
                        rx="8"
                        fill={isCurrent ? "rgba(198, 242, 119, 0.1)" : "#0e1512"}
                        stroke={isCurrent ? "#c6f277" : "#314039"}
                        strokeWidth={isCurrent ? "1.75" : "1"}
                      />
                      <text
                        x={x}
                        y={39}
                        textAnchor="middle"
                        fontSize="12"
                        fontWeight="700"
                        fill={isCurrent ? "#c6f277" : "#f0f2e9"}
                        fontFamily="var(--font-mono)"
                      >
                        v{v.version_number}
                      </text>
                      <text
                        x={x}
                        y={56}
                        textAnchor="middle"
                        fontSize="9"
                        fill="#a8b4aa"
                        fontFamily="var(--font-mono)"
                      >
                        {v.origin} · {v.choices.length}c
                      </text>
                    </g>
                  );
                })}
                {(() => {
                  const gx = 68 + versions.length * 172;
                  return (
                    <g aria-hidden="true">
                      <line
                        x1={gx - 116}
                        y1={44}
                        x2={gx - 56}
                        y2={44}
                        stroke="rgba(242, 200, 121, 0.4)"
                        strokeWidth="1.5"
                        strokeDasharray="4 4"
                      />
                      <rect
                        x={gx - 56}
                        y={16}
                        width="210"
                        height="56"
                        rx="8"
                        fill="rgba(242, 200, 121, 0.05)"
                        stroke="rgba(242, 200, 121, 0.36)"
                        strokeDasharray="4 4"
                      />
                      <text
                        x={gx + 49}
                        y={38}
                        textAnchor="middle"
                        fontSize="9.5"
                        fontWeight="700"
                        fill="#f2c879"
                        fontFamily="var(--font-mono)"
                      >
                        NEXT SNAPSHOT GATE (v{latest + 1})
                      </text>
                      <text
                        x={gx + 49}
                        y={55}
                        textAnchor="middle"
                        fontSize="8.5"
                        fill="#a8b4aa"
                        fontFamily="var(--font-mono)"
                      >
                        Replay (OC-008) + Human (OC-009)
                      </text>
                    </g>
                  );
                })()}
              </svg>
            </div>
          )}
          <div className="table-wrap" role="region" aria-label="Ontology versions" tabIndex={0}>
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
          </div>
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
            <div className="panel-head filter-toolbar">
              <select
                aria-label="Target rollback version"
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
