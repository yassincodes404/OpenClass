import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { controlFetch } from "./api";
import { useAuth } from "./auth";
import { ProjectShell, type Project } from "./projects";

export type Adapter = { source: string; implemented: boolean; kind: string; note?: string };
export type Integration = { id: string; name: string; type: string; status: string; secret_ref?: string | null };
export type RouteRule = { id: string; match_choice: string; action: string; action_value: string };
export type Outcome = { selected_choice: string; action: string; detail: Record<string, string>; created_at: string };

function useToken() {
  return useAuth().token() ?? "";
}

export function IntegrationsPage() {
  const { projectId = "" } = useParams();
  const token = useToken();
  const queryClient = useQueryClient();
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: async (): Promise<Project> => (await controlFetch(`/projects/${projectId}`, token)) as Project,
  });
  const base = `/workspaces/${project.data?.workspace_id}/projects/${projectId}/integrations`;
  const adapters = useQuery({
    queryKey: ["adapters", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<Adapter[]> => (await controlFetch(`${base}/adapters`, token)) as Adapter[],
  });
  const integrations = useQuery({
    queryKey: ["integrations", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<Integration[]> => (await controlFetch(base, token)) as Integration[],
  });
  const routes = useQuery({
    queryKey: ["routes", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<RouteRule[]> => (await controlFetch(`${base}/routes`, token)) as RouteRule[],
  });
  const outcomes = useQuery({
    queryKey: ["outcomes", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<Outcome[]> => (await controlFetch(`${base}/outcomes`, token)) as Outcome[],
  });
  const [feedback, setFeedback] = useState<string | null>(null);
  const connect = useMutation({
    mutationFn: async (source: string) =>
      controlFetch(base, token, {
        method: "POST",
        body: JSON.stringify({
          name: source,
          type: "webhook",
          secret_ref: `OPENCLASS_WEBHOOK_TOKEN_${source.toUpperCase()}`,
        }),
      }),
    onSuccess: () => {
      setFeedback("Connected (simulated local dev connection)");
      void queryClient.invalidateQueries({ queryKey: ["integrations", projectId] });
    },
    onError: (error: Error) => setFeedback(error.message),
  });
  const [rule, setRule] = useState({ match_choice: "BILLING", action: "tag", action_value: "billing" });
  const addRule = useMutation({
    mutationFn: async () => {
      const integration = integrations.data?.[0];
      if (!integration) throw new Error("connect an integration first");
      return controlFetch(`${base}/routes`, token, { method: "POST", body: JSON.stringify({ integration_id: integration.id, ...rule }) });
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["routes", projectId] }),
    onError: (error: Error) => setFeedback(error.message),
  });

  if (project.isPending) return <main><p className="lede">Loading integrations…</p></main>;
  if (!project.data) return <main><p className="lede">Project unavailable.</p></main>;
  return (
    <main>
      <ProjectShell project={project.data} active="/integrations">
        <section className="signal">
          <p className="eyebrow">INTEGRATIONS / SUPPORT ROUTING</p>
          <h2>Known → tag or queue. UNKNOWN → human triage. Never auto-reply.</h2>
          <p className="muted">Connections are simulated local dev fixtures; outcomes are recorded, nothing is sent.</p>
          <div className="card-grid">
            {adapters.data?.map((adapter) => (
              <article key={adapter.source} className="project-card">
                <p className="status"><i /> {adapter.kind}</p>
                <h3>{adapter.source}</h3>
                {adapter.implemented ? (
                  integrations.data?.some((entry) => entry.name === adapter.source) ? (
                    <p><span className="chip locked">connected (simulated)</span></p>
                  ) : (
                    <button className="ghost" onClick={() => connect.mutate(adapter.source)}>Connect</button>
                  )
                ) : (
                  <p className="muted">{adapter.note ?? "not implemented"}</p>
                )}
              </article>
            ))}
          </div>
          {feedback && <p className="muted">{feedback}</p>}
          <div className="panel">
            <div className="panel-head"><h3>Routing rules (UNKNOWN is fixed to escalation)</h3></div>
            <table className="table"><tbody>
              {routes.data?.map((entry) => (
                <tr key={entry.id}>
                  <td><code>{entry.match_choice}</code></td>
                  <td>{entry.action}</td>
                  <td>{entry.action_value || "—"}</td>
                </tr>
              ))}
              {routes.data?.length === 0 && <tr><td className="muted">No rules yet — known choices get a default tag.</td></tr>}
            </tbody></table>
            <div className="panel-head">
              <input value={rule.match_choice} onChange={(event) => setRule({ ...rule, match_choice: event.target.value.toUpperCase() })} placeholder="CHOICE" style={{ width: 140 }} />
              <select value={rule.action} onChange={(event) => setRule({ ...rule, action: event.target.value })}>
                <option value="tag">tag</option>
                <option value="assign_queue">assign_queue</option>
              </select>
              <input value={rule.action_value} onChange={(event) => setRule({ ...rule, action_value: event.target.value })} placeholder="value" style={{ width: 120 }} />
              <button disabled={addRule.isPending} onClick={() => addRule.mutate()}>Add rule</button>
            </div>
          </div>
          <div className="panel">
            <div className="panel-head"><h3>Routing outcomes (receipt log)</h3></div>
            <table className="table"><tbody>
              {outcomes.data?.map((outcome, index) => (
                <tr key={index}>
                  <td><code>{outcome.selected_choice}</code></td>
                  <td>{outcome.action}</td>
                  <td className="muted">{Object.entries(outcome.detail).map(([key, value]) => `${key}=${value}`).join(" · ").slice(0, 60)}</td>
                </tr>
              ))}
              {outcomes.data?.length === 0 && <tr><td className="muted">No deliveries yet.</td></tr>}
            </tbody></table>
          </div>
        </section>
      </ProjectShell>
    </main>
  );
}
