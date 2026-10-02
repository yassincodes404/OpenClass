import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { controlFetch } from "./api";
import { useAuth } from "./auth";
import { ProjectShell, type Project } from "./projects";

export type EventPreview = { id: string; source_type: string; preview: string; created_at: string };
export type EventPage = { items: EventPreview[]; next_cursor: string | null };
export type EventDetail = { id: string; source_type: string; content: string; metadata?: Record<string, unknown>; created_at: string };

function useToken() {
  return useAuth().token() ?? "";
}

function useProjectQuery(projectId: string) {
  const token = useToken();
  return useQuery({
    queryKey: ["project", projectId],
    queryFn: async (): Promise<Project> => (await controlFetch(`/projects/${projectId}`, token)) as Project,
  });
}

type IngestMode = "text" | "json" | "csv";

export function DataIngestPage() {
  const { projectId = "" } = useParams();
  const token = useToken();
  const queryClient = useQueryClient();
  const project = useProjectQuery(projectId);
  const [mode, setMode] = useState<IngestMode>("text");
  const [text, setText] = useState("");
  const [lastResult, setLastResult] = useState<string | null>(null);
  const idempotencyKey = crypto.randomUUID();

  const ingest = useMutation({
    mutationFn: async (payload: { content: string; source_type: string }) => {
      const [single] = payload.content.split("\n").length === 1 || mode === "text"
        ? [payload.content]
        : payload.content.split("\n").map((line) => line.trim()).filter(Boolean);
      if (mode === "text") {
        return controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/events`, token, {
          method: "POST",
          body: JSON.stringify(payload),
          headers: { "Idempotency-Key": idempotencyKey },
        });
      }
      const items = (mode === "csv"
        ? payload.content.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => ({ content: line }))
        : parseJsonItems(payload.content)) as Array<{ content: string }>;
      return controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/events/batch`, token, {
        method: "POST",
        body: JSON.stringify({ items, source_type: mode }),
      });
    },
    onSuccess: (result) => {
      const parsed = result as { id?: string; items?: Array<{ status: number; event?: { id: string } }> };
      if (parsed.items) {
        const ok = parsed.items.filter((item) => item.status === 201).length;
        const deduped = parsed.items.filter((item) => item.status === 200).length;
        const failed = parsed.items.filter((item) => item.status !== 200 && item.status !== 201).length;
        setLastResult(`Ingested ${ok} new · ${deduped} deduped · ${failed} failed`);
      } else {
        setLastResult(`Saved observation ${parsed.id?.slice(0, 8)}…`);
      }
      setText("");
      void queryClient.invalidateQueries({ queryKey: ["observations", projectId] });
    },
    onError: (error: Error) => setLastResult(error.message),
  });

  if (project.isPending) return <main><p className="lede">Loading…</p></main>;
  if (!project.data) return <main><p className="lede">Project unavailable.</p></main>;

  return (
    <main>
      <ProjectShell project={project.data} active="/observations">
        <section className="signal">
          <p className="eyebrow">DATA / INGESTION</p>
          <h2>Observations enter the loop here.</h2>
          <p className="muted">Redaction applies to derived copies; identical content deduplicates automatically.</p>
          <div className="panel-head">
            <div className="tab-row" role="tablist">
              {(["text", "json", "csv"] as IngestMode[]).map((option) => (
                <button key={option} role="tab" aria-selected={mode === option} className={mode === option ? "active" : "ghost"} onClick={() => setMode(option)}>
                  {option.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <textarea
            className="ingest-area"
            rows={mode === "text" ? 4 : 8}
            placeholder={
              mode === "text"
                ? "I was charged twice for my subscription"
                : mode === "csv"
                  ? "One observation per line"
                  : '[{"content": "first"}, {"content": "second"}]'
            }
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <div className="panel-head">
            <span className="muted">Idempotency key (auto): <code>{idempotencyKey.slice(0, 13)}…</code></span>
            <button onClick={() => ingest.mutate({ content: text, source_type: mode })} disabled={!text.trim() || ingest.isPending}>
              Ingest {mode === "text" ? "observation" : "batch"}
            </button>
          </div>
          {lastResult && <p className="muted" role="status">{lastResult}</p>}
        </section>
      </ProjectShell>
    </main>
  );
}

function parseJsonItems(raw: string): Array<{ content: string }> {
  try {
    const parsed = JSON.parse(raw) as unknown;
    const array = Array.isArray(parsed) ? parsed : [parsed];
    return array
      .map((item) => (typeof item === "string" ? { content: item } : item as { content?: string }))
      .filter((item): item is { content: string } => typeof item.content === "string" && item.content.trim().length > 0);
  } catch {
    return [];
  }
}

export function ObservationsPage() {
  const { projectId = "" } = useParams();
  const token = useToken();
  const project = useProjectQuery(projectId);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const observations = useQuery({
    queryKey: ["observations", projectId, query, source, cursor],
    enabled: project.isSuccess,
    queryFn: async (): Promise<EventPage> => {
      const params = new URLSearchParams();
      if (query) params.set("q", query);
      if (source) params.set("source_type", source);
      if (cursor) params.set("cursor", cursor);
      return (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/events?${params}`, token)) as EventPage;
    },
  });

  const detail = useQuery({
    queryKey: ["observation", projectId, selected],
    enabled: selected !== null,
    queryFn: async (): Promise<EventDetail> =>
      (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/events/${selected}`, token)) as EventDetail,
  });

  if (project.isPending) return <main><p className="lede">Loading observations…</p></main>;
  if (!project.data) return <main><p className="lede">Project unavailable.</p></main>;

  return (
    <main>
      <ProjectShell project={project.data} active="/observations">
        <section className="signal">
          <p className="eyebrow">OBSERVATIONS / HISTORY</p>
          <h2>Every ingested observation, newest first.</h2>
          <div className="panel-head">
            <input
              placeholder="Search content…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  setCursor(null);
                  setQuery(search.trim());
                }
              }}
            />
            <select value={source} onChange={(event) => { setCursor(null); setSource(event.target.value); }}>
              <option value="">All sources</option>
              <option value="text">text</option>
              <option value="json">json</option>
              <option value="csv">csv</option>
              <option value="webhook">webhook</option>
            </select>
          </div>
          {observations.isPending && <p className="muted">Loading…</p>}
          {observations.isError && <p className="field-error">{(observations.error as Error).message}</p>}
          {observations.isSuccess && observations.data.items.length === 0 && (
            <p className="muted">No observations match. Ingest data from the Data tab.</p>
          )}
          <table className="table">
            <tbody>
              {observations.data?.items.map((item) => (
                <tr key={item.id} onClick={() => setSelected(item.id)} className={selected === item.id ? "selected" : undefined}>
                  <td><code>{item.id.slice(0, 8)}…</code></td>
                  <td>{item.preview}</td>
                  <td><span className="chip">{item.source_type}</span></td>
                  <td className="muted">{new Date(item.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {observations.data?.next_cursor && (
            <button className="ghost" onClick={() => setCursor(observations.data!.next_cursor)}>More →</button>
          )}
        </section>
      </ProjectShell>
      {selected && (
        <div className="modal-backdrop" role="dialog" aria-label="Observation detail" onClick={() => setSelected(null)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <p className="eyebrow">OBSERVATION / {detail.data?.source_type ?? "…"}</p>
            <h2>Detail</h2>
            {detail.isPending && <p className="muted">Loading…</p>}
            {detail.data && (
              <>
                <p className="muted">Ingested {new Date(detail.data.created_at).toLocaleString()} · id <code>{detail.data.id.slice(0, 8)}…</code></p>
                <p>Members see the original content; list previews are redacted.</p>
                <pre className="detail-pre">{detail.data.content}</pre>
                {detail.data.metadata && Object.keys(detail.data.metadata).length > 0 && (
                  <pre className="detail-pre">{JSON.stringify(detail.data.metadata, null, 2)}</pre>
                )}
              </>
            )}
            <div className="modal-actions">
              <button className="ghost" onClick={() => setSelected(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
