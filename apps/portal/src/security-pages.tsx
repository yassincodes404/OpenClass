import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { controlFetch } from "./api";
import { useAuth } from "./auth";

function useToken() {
  return useAuth().token() ?? "";
}
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

export type ProviderConfig = { id: string; type: string; endpoint_ref: string | null; model: string | null; timeout_seconds: number; is_default: boolean };
export type UsageRow = { provider: string; model: string; date: string; calls: number; errors: number; estimated_cost: number; avg_latency_ms: number };
export type TestResult = { ok: boolean; provider?: string; error?: string; model?: string; simulated?: boolean; latency_ms?: number; normalized_preview?: { selected: string; top_probability: number; unknown_probability: number } };

export function ProjectProvidersPage() {
  const { projectId = "" } = useParams();
  const token = useToken();
  const queryClient = useQueryClient();
  const project = useProject(projectId);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const providers = useQuery({
    queryKey: ["providers", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<{ catalog: ProviderCard[]; status: ProviderStatus; configs: ProviderConfig[] }> =>
      (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/providers`, token)) as {
        catalog: ProviderCard[];
        status: ProviderStatus;
        configs: ProviderConfig[];
      },
  });
  const usage = useQuery({
    queryKey: ["provider-usage", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<UsageRow[]> =>
      (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/providers/usage`, token)) as UsageRow[],
  });
  const test = useMutation({
    mutationFn: async (configId: string) =>
      (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/providers/${configId}/test`, token, {
        method: "POST",
      })) as TestResult,
    onSuccess: (result) => setTestResult(result),
    onError: (error: Error) => setTestResult({ ok: false, error: error.message }),
  });

  if (project.isPending) return <main><p className="lede">Loading providers…</p></main>;
  if (!project.data) return <main><p className="lede">Project unavailable.</p></main>;
  if (providers.isError) {
    return (
      <main>
        <ProjectShell project={project.data} active="/providers">
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
      <ProjectShell project={project.data} active="/providers">
        <section className="signal">
          <p className="eyebrow">PROVIDERS / PROTOCOL &amp; COSTS</p>
          <h2>Provider configurations are stored as secret references.</h2>
          <p className="muted">Credentials are write-only environment references; values are never echoed back.</p>
          <div className="card-grid">
            {providers.data?.configs.map((config) => (
              <article key={config.id} className="project-card">
                <p className="status"><i /> {config.type}{config.is_default ? " / DEFAULT" : ""}</p>
                <h3>{config.type}</h3>
                <p>endpoint ref <code>{config.endpoint_ref ?? "—"}</code> · model <code>{config.model ?? "—"}</code> · timeout {config.timeout_seconds}s</p>
                <button className="ghost" onClick={() => test.mutate(config.id)}>Test provider</button>
              </article>
            ))}
            {providers.data?.configs.length === 0 && <p className="muted">No provider configs yet — add one below (seed script or API).</p>}
          </div>
          {testResult && (
            <div className="key-reveal">
              <p className="eyebrow">TEST RESULT / {testResult.ok ? "OK" : "FAILED"}</p>
              {testResult.ok ? (
                <p>
                  {testResult.provider} · {testResult.model} · {testResult.latency_ms}ms ·{" "}
                  preview: {testResult.normalized_preview?.selected}
                  {testResult.simulated && <> · <span className="chip locked">simulated</span></>}
                </p>
              ) : (
                <p className="field-error">{testResult.error}</p>
              )}
            </div>
          )}
          <div className="panel">
            <div className="panel-head"><h3>Usage (engine rollups)</h3></div>
            {usage.data?.length ? (
              <table className="table">
                <thead><tr><th>Date</th><th>Provider</th><th>Calls</th><th>Errors</th><th>Avg latency</th><th>Est. cost</th></tr></thead>
                <tbody>
                  {usage.data.map((row, index) => (
                    <tr key={index}>
                      <td>{row.date}</td>
                      <td><code>{row.provider}</code>{row.provider === "mock" && " (simulated)"}</td>
                      <td>{row.calls}</td>
                      <td>{row.errors}</td>
                      <td>{row.avg_latency_ms}ms</td>
                      <td>${row.estimated_cost.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted">No usage recorded yet — runs accrue here.</p>
            )}
          </div>
          <div className="panel">
            <div className="panel-head"><h3>Engine catalog</h3></div>
            <p className="muted">{providers.data?.catalog.map((entry) => `${entry.name} (${entry.capabilities?.join("/")})`).join(" · ")}</p>
          </div>
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
