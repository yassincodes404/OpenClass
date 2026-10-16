"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  type Project,
  type RawEvent,
  type ProviderStatus,
  type DecisionService,
} from "@openclass/sdk";
import { ProjectShell } from "../../shell";

import { workspaceClient as client } from "../../../../lib/workspace-client";

type IngestMode = "text" | "json" | "csv";

export default function ProjectDataPage() {
  const params = useParams<{ id: string }>();
  const slug = params?.id;

  const [project, setProject] = useState<Project | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [events, setEvents] = useState<RawEvent[]>([]);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null);

  // Decision Services & Run Intelligence
  const [services, setServices] = useState<DecisionService[]>([]);
  const [selectedServiceId, setSelectedServiceId] = useState<string>("");
  const [selectedEventIds, setSelectedEventIds] = useState<Set<string>>(new Set());
  const [runningIntel, setRunningIntel] = useState(false);
  const [intelResult, setIntelResult] = useState<{ count: number; serviceName: string } | null>(
    null,
  );
  const [intelError, setIntelError] = useState("");

  const [mode, setMode] = useState<IngestMode>("text");
  const [inputContent, setInputContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [inspectingEvent, setInspectingEvent] = useState<RawEvent | null>(null);

  useEffect(() => {
    if (!slug) return;
    client
      .project(slug)
      .then(setProject)
      .catch(() => setNotFound(true));

    loadEvents(slug);

    client
      .decisionServices(slug)
      .then((list) => {
        setServices(list);
        if (list.length > 0) {
          setSelectedServiceId(list[0]!.id);
        }
      })
      .catch(() => {});

    client
      .providerStatus()
      .then(setProviderStatus)
      .catch(() => {
        // Provider status endpoint optional/best effort
      });
  }, [slug]);

  async function loadEvents(projectSlug: string) {
    try {
      setLoadingEvents(true);
      const list = await client.events(projectSlug, { limit: 100, offset: 0 });
      setEvents(list);
    } catch {
      // Ignore or log error
    } finally {
      setLoadingEvents(false);
    }
  }

  function toggleSelectAll() {
    if (selectedEventIds.size === events.length) {
      setSelectedEventIds(new Set());
    } else {
      setSelectedEventIds(new Set(events.map((e) => e.id)));
    }
  }

  function toggleSelect(id: string) {
    setSelectedEventIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleRunIntelligence() {
    if (!slug || selectedEventIds.size === 0 || !selectedServiceId) return;
    setRunningIntel(true);
    setIntelError("");
    setIntelResult(null);
    try {
      const runs = await client.executeDecisionRuns({
        project: slug,
        serviceId: selectedServiceId,
        rawEventIds: Array.from(selectedEventIds),
      });
      const svc = services.find((s) => s.id === selectedServiceId);
      setIntelResult({ count: runs.length, serviceName: svc?.name || "service" });
      setSelectedEventIds(new Set());
    } catch (err: unknown) {
      setIntelError(err instanceof Error ? err.message : "Failed to execute decision runs.");
    } finally {
      setRunningIntel(false);
    }
  }

  async function handleIngest(e: FormEvent) {
    e.preventDefault();
    if (!slug || !inputContent.trim()) {
      setError("Please provide content to ingest.");
      return;
    }
    setError("");
    setSuccess("");
    setBusy(true);

    try {
      if (mode === "text") {
        await client.createEvent({
          project: slug,
          content: inputContent.trim(),
          sourceType: "text",
        });
        setSuccess("1 event ingested successfully.");
      } else if (mode === "json") {
        let parsed: unknown;
        try {
          parsed = JSON.parse(inputContent.trim());
        } catch {
          throw new Error("Invalid JSON format. Please verify your JSON payload.");
        }

        if (Array.isArray(parsed)) {
          const items = parsed.map((item, idx) => {
            if (typeof item === "string") return { content: item };
            if (typeof item === "object" && item !== null) {
              const obj = item as Record<string, unknown>;
              const content =
                typeof obj.content === "string"
                  ? obj.content
                  : typeof obj.text === "string"
                    ? obj.text
                    : JSON.stringify(item);
              const metadata =
                typeof obj.metadata === "object" && obj.metadata !== null
                  ? (obj.metadata as Record<string, unknown>)
                  : obj;
              return { content, metadata };
            }
            return { content: `Item ${idx + 1}: ${String(item)}` };
          });
          const created = await client.createEventsBatch({
            project: slug,
            items,
            sourceType: "json",
          });
          setSuccess(`${created.length} events ingested successfully.`);
        } else if (typeof parsed === "object" && parsed !== null) {
          const obj = parsed as Record<string, unknown>;
          const content =
            typeof obj.content === "string"
              ? obj.content
              : typeof obj.text === "string"
                ? obj.text
                : JSON.stringify(parsed);
          const metadata =
            typeof obj.metadata === "object" && obj.metadata !== null
              ? (obj.metadata as Record<string, unknown>)
              : obj;
          await client.createEvent({
            project: slug,
            content,
            sourceType: "json",
            metadata,
          });
          setSuccess("1 event ingested successfully.");
        } else {
          throw new Error("JSON must be an object or an array of objects.");
        }
      } else if (mode === "csv") {
        const lines = inputContent
          .trim()
          .split(/\r?\n/)
          .map((l) => l.trim())
          .filter(Boolean);

        if (lines.length === 0) {
          throw new Error("CSV input is empty.");
        }

        // Parse header and rows
        const hasHeader = lines.length > 1 && lines[0].includes(",");
        const header = hasHeader ? lines[0].split(",").map((c) => c.trim()) : [];
        const dataLines = hasHeader ? lines.slice(1) : lines;

        const items = dataLines.map((line, idx) => {
          const cells = line.split(",").map((c) => c.trim().replace(/^["']|["']$/g, ""));
          const metadata: Record<string, unknown> = { row_index: idx + 1 };
          if (header.length > 0) {
            header.forEach((col, i) => {
              if (i < cells.length) metadata[col] = cells[i];
            });
          }
          const content = cells[0] || line;
          return { content, metadata };
        });

        const created = await client.createEventsBatch({
          project: slug,
          items,
          sourceType: "csv",
        });
        setSuccess(`${created.length} CSV rows ingested successfully.`);
      }

      setInputContent("");
      await loadEvents(slug);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Ingestion failed.");
    } finally {
      setBusy(false);
    }
  }

  function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      if (text) {
        setInputContent(text);
        if (file.name.endsWith(".json")) setMode("json");
        else if (file.name.endsWith(".csv")) setMode("csv");
        else setMode("text");
      }
    };
    reader.readAsText(file);
  }

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
          Loading project data…
        </p>
      </main>
    );
  }

  const isLayaActive = providerStatus?.default_provider === "laya";

  return (
    <ProjectShell project={project} active="data">
      <div className="data-panel">
        {/* Provider Status Banner */}
        <aside className="provider-banner" aria-label="Decision Engine Status">
          <div>
            <strong>Default Decision Engine:</strong>{" "}
            {isLayaActive ? (
              <span>
                Laya (Local ModernBERT) · {providerStatus?.laya.status} ({providerStatus?.laya.mode}
                )
              </span>
            ) : (
              <span>{providerStatus?.default_provider ?? "Status unavailable"}</span>
            )}
          </div>
          <span className="badge">Decision services may override the default</span>
        </aside>

        {/* Ingestion Panel */}
        <section className="ingest-card">
          <h2 className="section-heading">Ingest Raw Data</h2>
          <p className="muted" style={{ marginBottom: "16px" }}>
            Paste observations or import files. All observations are saved immutably to PostgreSQL
            before decision classification.
          </p>

          <div className="ingest-tabs" role="tablist" aria-label="Ingestion format">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "text"}
              className={`ingest-tab ${mode === "text" ? "active" : ""}`}
              onClick={() => {
                setMode("text");
                setError("");
              }}
            >
              Paste Text
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "json"}
              className={`ingest-tab ${mode === "json" ? "active" : ""}`}
              onClick={() => {
                setMode("json");
                setError("");
              }}
            >
              Paste JSON
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "csv"}
              className={`ingest-tab ${mode === "csv" ? "active" : ""}`}
              onClick={() => {
                setMode("csv");
                setError("");
              }}
            >
              Upload / Paste CSV
            </button>
          </div>

          <form onSubmit={handleIngest} style={{ padding: 0, border: "none" }}>
            <div style={{ marginBottom: "12px" }}>
              {mode === "csv" && (
                <div style={{ marginBottom: "12px" }}>
                  <label htmlFor="csv-file-input" style={{ marginBottom: "6px" }}>
                    Select file or paste CSV lines below:
                  </label>
                  <input
                    id="csv-file-input"
                    type="file"
                    accept=".csv,.txt"
                    onChange={handleFileUpload}
                    style={{ fontSize: "13px" }}
                  />
                </div>
              )}
              <textarea
                aria-label="Event content input"
                rows={5}
                value={inputContent}
                onChange={(e) => setInputContent(e.target.value)}
                placeholder={
                  mode === "text"
                    ? "Enter observation text (e.g. customer support message, log excerpt, review)..."
                    : mode === "json"
                      ? '[\n  {"content": "First event text", "metadata": {"source": "support"}},\n  {"content": "Second event text"}\n]'
                      : "content,category,user_id\nUser charged twice,billing,u-101\nPassword reset link expired,auth,u-102"
                }
              />
            </div>

            <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
              <button type="submit" disabled={busy || !inputContent.trim()}>
                {busy
                  ? "Ingesting…"
                  : `Ingest ${mode.toUpperCase()} Event${mode !== "text" ? "s" : ""}`}
              </button>
              {inputContent && (
                <button
                  type="button"
                  onClick={() => setInputContent("")}
                  className="inspect-btn"
                  style={{ padding: "12px 16px" }}
                >
                  Clear
                </button>
              )}
            </div>

            {error && (
              <p role="alert" className="form-error" style={{ marginTop: "12px" }}>
                {error}
              </p>
            )}
            {success && (
              <p role="status" className="form-ok" style={{ marginTop: "12px" }}>
                {success}
              </p>
            )}
          </form>
        </section>

        {/* Events Table */}
        <section className="panel" style={{ padding: 0 }}>
          <div
            style={{
              padding: "20px 24px",
              borderBottom: "1px solid var(--line)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div>
              <h2 className="section-heading" style={{ margin: 0 }}>
                Raw Events Stream
              </h2>
              <p className="muted" style={{ margin: "4px 0 0" }}>
                {events.length} event{events.length === 1 ? "" : "s"} persisted
              </p>
            </div>
            <button
              type="button"
              className="inspect-btn"
              onClick={() => slug && loadEvents(slug)}
              disabled={loadingEvents}
            >
              {loadingEvents ? "Refreshing…" : "Refresh"}
            </button>
          </div>

          {selectedEventIds.size > 0 && (
            <div
              className="action-bar"
              data-testid="run-intelligence-bar"
              style={{ margin: "16px 24px" }}
            >
              <div className="action-bar-info">
                <strong>
                  {selectedEventIds.size} event{selectedEventIds.size === 1 ? "" : "s"} selected
                </strong>
              </div>
              <div className="action-bar-controls">
                {services.length === 0 ? (
                  <span style={{ fontSize: "13px", color: "var(--muted)" }}>
                    No decision services found.{" "}
                    <Link href={`/projects/${slug}/decisions`} style={{ color: "var(--accent)" }}>
                      Create one in Decisions first →
                    </Link>
                  </span>
                ) : (
                  <>
                    <label
                      htmlFor="select-decision-service"
                      style={{ margin: 0, fontSize: "13px" }}
                    >
                      Service:
                    </label>
                    <select
                      id="select-decision-service"
                      value={selectedServiceId}
                      onChange={(e) => setSelectedServiceId(e.target.value)}
                      data-testid="select-service-dropdown"
                    >
                      {services.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name} ({s.nodes[0]?.choices.length ?? 0} choices)
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={handleRunIntelligence}
                      disabled={runningIntel}
                      data-testid="run-intelligence-btn"
                    >
                      {runningIntel ? "Executing…" : `Run Intelligence (${selectedEventIds.size})`}
                    </button>
                  </>
                )}
              </div>
            </div>
          )}

          {intelResult && (
            <div
              style={{
                margin: "16px 24px",
                padding: "12px 16px",
                background: "rgba(196, 244, 138, 0.1)",
                border: "1px solid rgba(196, 244, 138, 0.3)",
                borderRadius: "6px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
              data-testid="intel-success-banner"
            >
              <span style={{ color: "var(--accent)", fontSize: "13px" }}>
                ✓ Successfully executed {intelResult.count} decision run
                {intelResult.count === 1 ? "" : "s"} with {intelResult.serviceName}.
              </span>
              <Link
                href={`/projects/${slug}/decisions`}
                style={{ color: "var(--accent)", fontWeight: 600, fontSize: "13px" }}
              >
                View Runs in Decisions →
              </Link>
            </div>
          )}

          {intelError && (
            <div
              style={{
                margin: "16px 24px",
                padding: "12px 16px",
                background: "rgba(255, 100, 100, 0.1)",
                border: "1px solid rgba(255, 100, 100, 0.3)",
                borderRadius: "6px",
              }}
              data-testid="intel-error-banner"
            >
              <span style={{ color: "#ff8888", fontSize: "13px" }}>{intelError}</span>
            </div>
          )}

          {events.length === 0 ? (
            <div style={{ padding: "36px 24px" }}>
              <p className="empty">
                {loadingEvents
                  ? "Loading raw events…"
                  : "No raw events ingested yet. Paste text, JSON, or CSV above to begin."}
              </p>
            </div>
          ) : (
            <div className="data-table-container" style={{ border: "none", borderRadius: 0 }}>
              <table className="data-table" aria-label="Raw events table">
                <thead>
                  <tr>
                    <th scope="col" style={{ width: "36px" }}>
                      <input
                        type="checkbox"
                        checked={events.length > 0 && selectedEventIds.size === events.length}
                        onChange={toggleSelectAll}
                        aria-label="Select all events"
                        data-testid="select-all-events"
                      />
                    </th>
                    <th scope="col">ID</th>
                    <th scope="col">Source</th>
                    <th scope="col">Content Preview</th>
                    <th scope="col">Metadata</th>
                    <th scope="col">Date</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((evt) => {
                    const metaKeys = Object.keys(evt.metadata || {});
                    return (
                      <tr key={evt.id}>
                        <td>
                          <input
                            type="checkbox"
                            checked={selectedEventIds.has(evt.id)}
                            onChange={() => toggleSelect(evt.id)}
                            aria-label={`Select event ${evt.id.slice(0, 8)}`}
                            data-testid={`select-event-${evt.id}`}
                          />
                        </td>
                        <td>
                          <code style={{ fontSize: "12px" }}>{evt.id.slice(0, 8)}…</code>
                        </td>
                        <td>
                          <span className={`source-badge ${evt.source_type}`}>
                            {evt.source_type}
                          </span>
                        </td>
                        <td>
                          <div className="content-preview" title={evt.content}>
                            {evt.content}
                          </div>
                        </td>
                        <td>
                          <span className="muted">
                            {metaKeys.length === 0
                              ? "—"
                              : `${metaKeys.length} key${metaKeys.length === 1 ? "" : "s"}`}
                          </span>
                        </td>
                        <td className="muted" style={{ whiteSpace: "nowrap" }}>
                          {new Date(evt.created_at).toLocaleString()}
                        </td>
                        <td>
                          <button
                            type="button"
                            className="inspect-btn"
                            onClick={() => setInspectingEvent(evt)}
                          >
                            Inspect
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {/* Inspect Modal */}
      {inspectingEvent && (
        <div className="modal-backdrop" onClick={() => setInspectingEvent(null)}>
          <div
            className="modal-content"
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="modal-title">Event Detail: {inspectingEvent.id.slice(0, 8)}</h3>
              <button
                type="button"
                className="modal-close"
                aria-label="Close dialog"
                onClick={() => setInspectingEvent(null)}
              >
                ✕
              </button>
            </div>

            <div className="detail-view">
              <div style={{ marginBottom: "16px", display: "grid", gap: "6px" }}>
                <div>
                  <strong>Full ID:</strong> <code>{inspectingEvent.id}</code>
                </div>
                <div>
                  <strong>Project ID:</strong> <code>{inspectingEvent.project_id}</code>
                </div>
                <div>
                  <strong>Source:</strong>{" "}
                  <span className={`source-badge ${inspectingEvent.source_type}`}>
                    {inspectingEvent.source_type}
                  </span>
                </div>
                <div>
                  <strong>Timestamp:</strong> {new Date(inspectingEvent.created_at).toISOString()}
                </div>
              </div>

              <div style={{ marginBottom: "16px" }}>
                <strong>Content:</strong>
                <pre>{inspectingEvent.content}</pre>
              </div>

              <div>
                <strong>Metadata:</strong>
                <pre>
                  {Object.keys(inspectingEvent.metadata || {}).length > 0
                    ? JSON.stringify(inspectingEvent.metadata, null, 2)
                    : "No metadata attached."}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </ProjectShell>
  );
}
