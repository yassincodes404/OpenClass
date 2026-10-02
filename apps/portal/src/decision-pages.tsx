import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { controlFetch } from "./api";
import { useAuth } from "./auth";
import { ProjectShell, type Project } from "./projects";

export type DecisionChoice = { key: string; label: string; description?: string };
export type DecisionService = {
  id: string;
  slug: string;
  name: string;
  instructions: string;
  status: string;
  nodes: Array<{ id: string; choices: DecisionChoice[] }>;
};
export type DecisionRun = {
  id: string;
  raw_event_id: string;
  decision_service_id: string;
  provider: string;
  model?: string;
  selected_choice: string;
  supervision_outcome: string;
  probabilities: Record<string, number>;
  latency_ms?: number;
  created_at: string;
};
export type RunPage = { items: DecisionRun[]; next_cursor: string | null };

function useToken() {
  return useAuth().token() ?? "";
}

function useProjectQuery(projectId: string) {
  const token = useToken();
  return useQuery({
    queryKey: ["project", projectId],
    queryFn: async (): Promise<Project> =>
      (await controlFetch(`/projects/${projectId}`, token)) as Project,
  });
}

export function DecisionsPage() {
  const { projectId = "" } = useParams();
  const token = useToken();
  const queryClient = useQueryClient();
  const project = useProjectQuery(projectId);
  const [creating, setCreating] = useState(false);
  const services = useQuery({
    queryKey: ["decision-services", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<DecisionService[]> =>
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/decision-services`,
        token,
      )) as DecisionService[],
  });
  if (project.isPending)
    return (
      <main>
        <p className="lede">Loading…</p>
      </main>
    );
  if (!project.data)
    return (
      <main>
        <p className="lede">Project unavailable.</p>
      </main>
    );
  return (
    <main>
      <ProjectShell project={project.data} active="/decisions">
        <section className="signal">
          <div className="panel-head">
            <div>
              <p className="eyebrow">DECISION SERVICES / GOVERNED</p>
              <h2>Every service carries the permanent UNKNOWN fallback.</h2>
            </div>
            <button onClick={() => setCreating(true)}>+ New decision service</button>
          </div>
          {services.isPending && <p className="lede">Loading services…</p>}
          {services.data?.length === 0 && <p className="lede">No decision services yet.</p>}
          <div className="card-grid">
            {services.data?.map((service) => (
              <article key={service.id} className="project-card">
                <p className="status">
                  <i /> {service.status.toUpperCase()}
                </p>
                <h3>{service.name}</h3>
                <p>
                  {service.nodes[0].choices.filter((c) => c.key !== "UNKNOWN").length} choices +{" "}
                  <span className="chip locked">UNKNOWN — locked</span>
                </p>
                <Link to={`/projects/${projectId}/decisions/${service.id}`}>Open service →</Link>
              </article>
            ))}
          </div>
          <p className="muted">
            <Link to={`/projects/${projectId}/runs`}>View all runs →</Link>
          </p>
        </section>
      </ProjectShell>
      {creating && (
        <CreateServiceModal
          project={project.data}
          token={token}
          onClose={() => setCreating(false)}
          onCreated={() => {
            setCreating(false);
            void queryClient.invalidateQueries({ queryKey: ["decision-services", projectId] });
          }}
        />
      )}
    </main>
  );
}

function CreateServiceModal({
  project,
  token,
  onClose,
  onCreated,
}: {
  project: Project;
  token: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [instructions, setInstructions] = useState("");
  const [choices, setChoices] = useState("BILLING\nREFUND\nDELIVERY");
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: async () => {
      const parsedChoices = choices
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((key) => ({ key, label: key }));
      return controlFetch(
        `/workspaces/${project.workspace_id}/projects/${project.id}/decision-services`,
        token,
        {
          method: "POST",
          body: JSON.stringify({ name, instructions, choices: parsedChoices }),
        },
      );
    },
    onSuccess: onCreated,
    onError: (err: Error) => setError(err.message),
  });
  return (
    <div className="modal-backdrop" role="dialog" aria-label="Create decision service">
      <form
        className="modal"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <p className="eyebrow">NEW DECISION SERVICE / {project.name.toUpperCase()}</p>
        <h2>Create a decision service</h2>
        <label>
          Name
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Support router"
            required
            minLength={2}
          />
        </label>
        <label>
          Instructions
          <textarea
            value={instructions}
            onChange={(event) => setInstructions(event.target.value)}
            rows={3}
            placeholder="Route each customer message to the best-fitting intent."
            required
            minLength={10}
          />
        </label>
        <label>
          Choices <span className="muted">(one UPPERCASE key per line)</span>
          <textarea
            value={choices}
            onChange={(event) => setChoices(event.target.value)}
            rows={5}
            required
          />
        </label>
        <p className="muted">UNKNOWN is appended automatically and can never be removed.</p>
        {error && <p className="field-error">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" disabled={create.isPending}>
            Create service
          </button>
        </div>
      </form>
    </div>
  );
}

export function DecisionServicePage() {
  const { projectId = "", serviceId = "" } = useParams();
  const token = useToken();
  const queryClient = useQueryClient();
  const project = useProjectQuery(projectId);
  const service = useQuery({
    queryKey: ["decision-service", projectId, serviceId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<DecisionService> =>
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/decision-services/${serviceId}`,
        token,
      )) as DecisionService,
  });
  const [testInput, setTestInput] = useState("");
  const [testResult, setTestResult] = useState<DecisionRun | null>(null);
  const run = useMutation({
    mutationFn: async () => {
      const runs = (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/decision-services/${serviceId}/runs`,
        token,
        { method: "POST", body: JSON.stringify({ content: testInput }) },
      )) as DecisionRun[];
      return runs[0];
    },
    onSuccess: (result) => {
      setTestResult(result);
      void queryClient.invalidateQueries({ queryKey: ["runs", projectId] });
    },
  });
  if (project.isPending || service.isPending)
    return (
      <main>
        <p className="lede">Loading service…</p>
      </main>
    );
  if (!project.data || !service.data)
    return (
      <main>
        <p className="lede">Service unavailable.</p>
      </main>
    );
  return (
    <main>
      <ProjectShell project={project.data} active="/decisions">
        <section className="signal">
          <p className="eyebrow">DECISION SERVICE / {service.data.slug.toUpperCase()}</p>
          <h2>{service.data.name}</h2>
          <p className="muted">{service.data.instructions}</p>
          <table className="table">
            <thead>
              <tr>
                <th>Key</th>
                <th>Label</th>
              </tr>
            </thead>
            <tbody>
              {service.data.nodes[0].choices.map((choice) => (
                <tr
                  key={choice.key}
                  className={choice.key === "UNKNOWN" ? "unknown-row" : undefined}
                >
                  <td>
                    <code>{choice.key}</code>
                  </td>
                  <td>
                    {choice.key === "UNKNOWN" ? (
                      <span className="chip locked">permanent fallback — locked</span>
                    ) : (
                      choice.label
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="panel">
            <div className="panel-head">
              <h3>Test panel</h3>
              {testResult?.provider === "mock" && <span className="chip locked">simulated</span>}
            </div>
            <textarea
              className="ingest-area"
              rows={2}
              placeholder='Try "I was charged twice"'
              value={testInput}
              onChange={(event) => setTestInput(event.target.value)}
            />
            <div className="modal-actions">
              <button onClick={() => run.mutate()} disabled={!testInput.trim() || run.isPending}>
                {run.isPending ? "Running…" : "Run decision"}
              </button>
            </div>
            {testResult && <ProbabilityBars run={testResult} />}
          </div>
        </section>
      </ProjectShell>
    </main>
  );
}

function ProbabilityBars({ run }: { run: DecisionRun }) {
  const entries = Object.entries(run.probabilities).sort((a, b) => b[1] - a[1]);
  return (
    <div className="prob-panel">
      <p className="eyebrow">
        RESULT /{" "}
        {run.selected_choice === "UNKNOWN"
          ? "UNKNOWN — not forced into a choice"
          : run.selected_choice}{" "}
        · {run.supervision_outcome}
      </p>
      {entries.map(([key, value]) => (
        <div key={key} className={`prob-row ${key === "UNKNOWN" ? "unknown-row" : ""}`}>
          <code>{key}</code>
          <div className="prob-track">
            <div
              className={key === "UNKNOWN" ? "prob-fill unknown" : "prob-fill"}
              style={{ width: `${Math.round(value * 100)}%` }}
            />
          </div>
          <span>{(value * 100).toFixed(1)}%</span>
        </div>
      ))}
      <p className="muted">
        provider {run.provider} · {run.latency_ms ?? 0}ms
      </p>
    </div>
  );
}

export function RunsPage() {
  const { projectId = "" } = useParams();
  const token = useToken();
  const project = useProjectQuery(projectId);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const runs = useQuery({
    queryKey: ["runs", projectId, cursor],
    enabled: project.isSuccess,
    queryFn: async (): Promise<RunPage> => {
      const params = new URLSearchParams({ limit: "25" });
      if (cursor) params.set("cursor", cursor);
      return (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/runs?${params}`,
        token,
      )) as RunPage;
    },
  });
  const detail = useQuery({
    queryKey: ["run", projectId, selected],
    enabled: selected !== null,
    queryFn: async (): Promise<DecisionRun> =>
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/runs/${selected}`,
        token,
      )) as DecisionRun,
  });
  if (project.isPending)
    return (
      <main>
        <p className="lede">Loading runs…</p>
      </main>
    );
  if (!project.data)
    return (
      <main>
        <p className="lede">Project unavailable.</p>
      </main>
    );
  return (
    <main>
      <ProjectShell project={project.data} active="/runs">
        <section className="signal">
          <p className="eyebrow">RUNS / PERSISTED HISTORY</p>
          <h2>Every decision is recorded with its full distribution.</h2>
          {runs.data?.items.length === 0 && (
            <p className="muted">No runs yet. Test a decision service first.</p>
          )}
          <table className="table">
            <tbody>
              {runs.data?.items.map((item) => (
                <tr key={item.id} onClick={() => setSelected(item.id)}>
                  <td>
                    <code>{item.id.slice(0, 8)}…</code>
                  </td>
                  <td>
                    {item.selected_choice === "UNKNOWN" ? (
                      <span className="chip locked">UNKNOWN</span>
                    ) : (
                      <span className="chip">{item.selected_choice}</span>
                    )}
                  </td>
                  <td>{item.supervision_outcome}</td>
                  <td className="muted">{new Date(item.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {runs.data?.next_cursor && (
            <button className="ghost" onClick={() => setCursor(runs.data!.next_cursor)}>
              More →
            </button>
          )}
        </section>
      </ProjectShell>
      {selected && (
        <div
          className="modal-backdrop"
          role="dialog"
          aria-label="Run detail"
          onClick={() => setSelected(null)}
        >
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <p className="eyebrow">RUN / {detail.data?.supervision_outcome ?? "…"}</p>
            <h2>Run detail</h2>
            {detail.isPending && <p className="muted">Loading…</p>}
            {detail.data && (
              <>
                <ProbabilityBars run={detail.data} />
                <p className="muted">
                  event <code>{detail.data.raw_event_id.slice(0, 8)}…</code>
                </p>
              </>
            )}
            <div className="modal-actions">
              <button className="ghost" onClick={() => setSelected(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
