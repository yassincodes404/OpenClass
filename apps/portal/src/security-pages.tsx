import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { controlFetch } from "./api";
import { useAuth } from "./auth";
import { ProjectShell, type Project } from "./projects";

export type Settings = { redaction_enabled: boolean; retention_days: number };
export type ProviderCard = { name: string; model?: string; simulated?: boolean; capabilities?: string[] };
export type ProviderStatus = Record<string, unknown>;
export type AuditEvent = { id: string; actor: string; action: string; target: string; created_at: string; project_id: string | null };
export type AuditPage = { items: AuditEvent[]; next_cursor: string | null };

function useProject(projectId: string) {
  const token = useAuth().token() ?? "";
  return useQuery({
    queryKey: ["project", projectId],
    queryFn: async (): Promise<Project> => (await controlFetch(`/projects/${projectId}`, token)) as Project,
  });
}

export function ProjectSettingsPage() {
  const { projectId = "" } = useParams();
  const token = useAuth().token() ?? "";
  const queryClient = useQueryClient();
  const project = useProject(projectId);
  const settings = useQuery({
    queryKey: ["settings", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<Settings> =>
      (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/settings`, token)) as Settings,
  });
  const [saved, setSaved] = useState(false);
  const save = useMutation({
    mutationFn: async (patch: Settings) =>
      controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/settings`, token, {
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
    onSuccess: () => {
      setSaved(true);
      void queryClient.invalidateQueries({ queryKey: ["settings", projectId] });
    },
  });

  if (project.isPending || settings.isPending) return <main><p className="lede">Loading settings…</p></main>;
  if (!project.data || !settings.data) return <main><p className="lede">Settings unavailable.</p></main>;

  return (
    <main>
      <ProjectShell project={project.data} active="/settings">
        <section className="signal">
          <p className="eyebrow">SETTINGS / PRIVACY &amp; RETENTION</p>
          <h2>Secrets are never displayed. Redaction applies to every derived copy.</h2>
          <div className="panel">
            <div className="panel-head">
              <h3>Redaction &amp; retention</h3>
              <button onClick={() => save.mutate(settings.data!)} disabled={save.isPending || saved}>Save{saved ? "d ✓" : ""}</button>
            </div>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={settings.data.redaction_enabled}
                onChange={(event) => {
                  setSaved(false);
                  settings.data && queryClient.setQueryData(["settings", projectId], { ...settings.data, redaction_enabled: event.target.checked });
                }}
              />
              <span>PII redaction on list previews and derived copies (emails, cards, tokens, blocklist)</span>
            </label>
            <label className="toggle-row">
              <span>Retention window</span>
              <input
                type="number"
                min={1}
                max={3650}
                value={settings.data.retention_days}
                onChange={(event) => {
                  setSaved(false);
                  queryClient.setQueryData(["settings", projectId], { ...settings.data, retention_days: Number(event.target.value) });
                }}
              />
              <span className="muted">days — originals are kept only for the retention window</span>
            </label>
            <p className="muted">Provider credentials are write-only environment references; they are never echoed back by the API.</p>
          </div>
        </section>
      </ProjectShell>
    </main>
  );
}

export function ProjectProvidersPage() {
  const { projectId = "" } = useParams();
  const token = useAuth().token() ?? "";
  const project = useProject(projectId);
  const providers = useQuery({
    queryKey: ["providers", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<{ catalog: ProviderCard[]; status: ProviderStatus }> =>
      (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/providers`, token)) as {
        catalog: ProviderCard[];
        status: ProviderStatus;
      },
  });
  if (project.isPending || providers.isPending) return <main><p className="lede">Loading providers…</p></main>;
  if (!project.data) return <main><p className="lede">Project unavailable.</p></main>;
  if (providers.isError) {
    return (
      <main>
        <ProjectShell project={project.data} active="/settings">
          <section className="signal">
            <p className="eyebrow">PROVIDERS / STATUS</p>
            <h2>Provider status is temporarily unavailable.</h2>
            <p className="muted">{(providers.error as Error).message} — no credentials are ever included in error payloads.</p>
          </section>
        </ProjectShell>
      </main>
    );
  }
  return (
    <main>
      <ProjectShell project={project.data} active="/settings">
        <section className="signal">
          <p className="eyebrow">PROVIDERS / STATUS</p>
          <h2>Decision providers</h2>
          <div className="card-grid">
            {providers.data?.catalog.map((provider, index) => (
              <article key={`${provider.name}-${index}`} className="project-card">
                <p className="status"><i /> {provider.model ?? "—"}</p>
                <h3>{provider.name}</h3>
                <p>{provider.capabilities?.join(", ") ?? "choice"}</p>
                {provider.simulated && <p><span className="chip locked">simulated</span></p>}
              </article>
            ))}
          </div>
          <p className="muted">Failures surface as sanitized 502 responses; provider errors never include secrets or request bodies.</p>
        </section>
      </ProjectShell>
    </main>
  );
}

export function ProjectAuditPage() {
  const { projectId = "" } = useParams();
  const token = useAuth().token() ?? "";
  const project = useProject(projectId);
  const [actionFilter, setActionFilter] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const audit = useQuery({
    queryKey: ["audit", project.data?.workspace_id, actionFilter, cursor],
    enabled: project.isSuccess,
    queryFn: async (): Promise<AuditPage> => {
      const params = new URLSearchParams({ limit: "50" });
      if (actionFilter) params.set("action", actionFilter);
      if (cursor) params.set("cursor", cursor);
      return (await controlFetch(`/workspaces/${project.data!.workspace_id}/audit?${params}`, token)) as AuditPage;
    },
  });
  if (project.isPending) return <main><p className="lede">Loading audit log…</p></main>;
  if (!project.data) return <main><p className="lede">Project unavailable.</p></main>;
  return (
    <main>
      <ProjectShell project={project.data} active="/settings">
        <section className="signal">
          <p className="eyebrow">AUDIT / APPEND-ONLY</p>
          <h2>Every mutation is recorded with actor and timestamp.</h2>
          <div className="panel-head">
            <input
              placeholder="Filter by action (e.g. project.created)"
              defaultValue={actionFilter}
              onBlur={(event) => {
                setCursor(null);
                setActionFilter(event.target.value.trim());
              }}
            />
          </div>
          {audit.isPending && <p className="muted">Loading…</p>}
          {audit.isError && <p className="field-error">{(audit.error as Error).message}</p>}
          <table className="table">
            <thead>
              <tr><th>When</th><th>Actor</th><th>Action</th><th>Target</th></tr>
            </thead>
            <tbody>
              {audit.data?.items.map((event) => (
                <tr key={event.id}>
                  <td>{new Date(event.created_at).toLocaleString()}</td>
                  <td><code>{event.actor.slice(0, 8)}…</code></td>
                  <td>{event.action}</td>
                  <td>{event.target}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {audit.data?.next_cursor && (
            <button className="ghost" onClick={() => setCursor(audit.data!.next_cursor)}>Older →</button>
          )}
        </section>
      </ProjectShell>
    </main>
  );
}
