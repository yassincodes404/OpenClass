"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  type Project,
  type DecisionService,
  type DecisionRun,
  type ProviderStatus,
} from "@openclass/sdk";
import { ProjectShell } from "../../shell";

import { workspaceClient as client } from "../../../../lib/workspace-client";
import { GraphEditor } from "../../../../../portal/src/graph-editor";

interface ChoiceInput {
  key: string;
  label: string;
  description: string;
}

export default function ProjectDecisionsPage() {
  const params = useParams<{ id: string }>();
  const slug = params?.id;

  const [project, setProject] = useState<Project | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [services, setServices] = useState<DecisionService[]>([]);
  const [runs, setRuns] = useState<DecisionRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null);
  const [editing, setEditing] = useState<DecisionService | null>(null);
  const [loadError, setLoadError] = useState("");

  // New Service Modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [serviceName, setServiceName] = useState("");
  const [serviceDesc, setServiceDesc] = useState("");
  const [serviceInstructions, setServiceInstructions] = useState("");
  const [providerOverride, setProviderOverride] = useState("");
  const [choices, setChoices] = useState<ChoiceInput[]>([
    {
      key: "ENTERPRISE",
      label: "Enterprise Support",
      description: "Complex high-value enterprise issue",
    },
    { key: "SMB", label: "SMB Support", description: "Standard business support request" },
  ]);
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState("");

  // Inspect Run Drawer / Modal
  const [inspectingRun, setInspectingRun] = useState<DecisionRun | null>(null);

  useEffect(() => {
    if (!slug) return;
    client
      .project(slug)
      .then(setProject)
      .catch(() => setNotFound(true));

    loadData(slug);

    client
      .providerStatus()
      .then(setProviderStatus)
      .catch(() => {});
  }, [slug]);

  async function loadData(projectSlug: string) {
    setLoading(true);
    try {
      const [svcList, runList] = await Promise.all([
        client.decisionServices(projectSlug),
        client.decisionRuns(projectSlug, { limit: 100 }),
      ]);
      setServices(svcList);
      setRuns(runList);
    } catch {
      setLoadError("Could not load services and runs. Refresh after checking the control plane.");
    } finally {
      setLoading(false);
    }
  }

  function addChoice() {
    setChoices((prev) => [...prev, { key: "", label: "", description: "" }]);
  }

  function removeChoice(index: number) {
    setChoices((prev) => prev.filter((_, i) => i !== index));
  }

  function updateChoice(index: number, field: keyof ChoiceInput, val: string) {
    setChoices((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index]!, [field]: val };
      return copy;
    });
  }

  async function handleCreateService(e: FormEvent) {
    e.preventDefault();
    if (!slug) return;
    setCreateError("");

    if (!serviceName.trim()) {
      setCreateError("Service name is required.");
      return;
    }
    if (!serviceInstructions.trim()) {
      setCreateError("Instructions are required.");
      return;
    }

    const cleanedChoices = choices
      .map((c) => ({
        key: c.key.trim().toUpperCase(),
        label: c.label.trim() || c.key.trim().toUpperCase(),
        description: c.description.trim(),
      }))
      .filter((c) => c.key && c.key !== "UNKNOWN");

    if (cleanedChoices.length === 0) {
      setCreateError("Define at least one choice beside UNKNOWN.");
      return;
    }

    setCreateBusy(true);
    try {
      await client.createDecisionService({
        project: slug,
        name: serviceName.trim(),
        instructions: serviceInstructions.trim(),
        description: serviceDesc.trim(),
        provider_override: providerOverride.trim() || null,
        choices: cleanedChoices,
      });

      setShowCreateModal(false);
      setServiceName("");
      setServiceDesc("");
      setServiceInstructions("");
      setProviderOverride("");
      setChoices([
        {
          key: "ENTERPRISE",
          label: "Enterprise Support",
          description: "Complex high-value enterprise issue",
        },
        { key: "SMB", label: "SMB Support", description: "Standard business support request" },
      ]);
      await loadData(slug);
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : "Failed to create decision service.");
    } finally {
      setCreateBusy(false);
    }
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
          Loading project…
        </p>
      </main>
    );
  }

  return (
    <ProjectShell project={project} active="decisions">
      {providerStatus ? (
        <div className="provider-banner" data-testid="provider-banner">
          <div>
            <strong>Active Provider:</strong>{" "}
            <span style={{ textTransform: "uppercase" }}>{providerStatus.default_provider}</span>{" "}
            {providerStatus.default_provider === "laya" && (
              <span>(ModernBERT router · local System 1 engine)</span>
            )}
          </div>
          <span className="badge">
            Laya: {providerStatus.laya.mode} · {providerStatus.laya.status}
          </span>
        </div>
      ) : null}

      {/* Decision Services Panel */}
      <section className="panel" style={{ marginBottom: "28px" }}>
        {loadError && <p role="alert">{loadError}</p>}
        <div className="section-heading">
          <div>
            <h2 style={{ margin: "0 0 4px" }}>Decision Services</h2>
            <p className="lede" style={{ fontSize: "14px", margin: 0 }}>
              First-class decision definitions with instructions, bounded choices, and permanent
              UNKNOWN authority.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            data-testid="create-service-btn"
          >
            + New Decision Service
          </button>
        </div>

        {services.length === 0 ? (
          <p className="empty" data-testid="empty-services">
            No decision services defined yet. Create a service to define how raw events are
            classified.
          </p>
        ) : (
          <div className="services-grid">
            {services.map((svc) => (
              <div key={svc.id} className="service-card" data-testid={`service-card-${svc.slug}`}>
                <div className="service-card-header">
                  <div>
                    <h3 className="service-card-title">{svc.name}</h3>
                    <span className="status" style={{ fontSize: "11px" }}>
                      /{svc.slug}
                    </span>
                  </div>
                  <span className="badge">{svc.status}</span>
                </div>
                {svc.description ? (
                  <p style={{ fontSize: "13px", color: "var(--muted)", margin: 0 }}>
                    {svc.description}
                  </p>
                ) : null}
                <div style={{ fontSize: "12px", color: "var(--muted)" }}>
                  <strong>Instructions:</strong> {svc.instructions.slice(0, 100)}
                  {svc.instructions.length > 100 ? "…" : ""}
                </div>
                <div>
                  <div style={{ fontSize: "11px", color: "var(--muted)", marginBottom: "6px" }}>
                    Choices ({svc.nodes[0]?.choices.length ?? 0}):
                  </div>
                  <div className="service-choices-tags">
                    {svc.nodes[0]?.choices.map((c) => (
                      <span
                        key={c.key}
                        className={`choice-tag ${c.key === "UNKNOWN" ? "unknown" : ""}`}
                        title={c.description || c.label}
                      >
                        {c.key} {c.key === "UNKNOWN" ? "★" : ""}
                      </span>
                    ))}
                  </div>
                </div>
                <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "auto" }}>
                  Provider: {svc.provider_override || "Project / server default"}
                </div>
                <button type="button" onClick={() => setEditing(svc)}>
                  Edit graph for {svc.name}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
      {editing && (
        <section className="panel">
          <button type="button" onClick={() => setEditing(null)}>
            Close graph editor
          </button>
          <GraphEditor
            key={editing.active_version_id ?? editing.updated_at}
            service={editing}
            onSave={async (graph) => {
              if (!slug) return;
              const latest = await client.decisionService({ project: slug, serviceId: editing.id });
              if (
                latest.active_version_id !== editing.active_version_id ||
                latest.updated_at !== editing.updated_at
              )
                throw new Error("Service changed since loading. Refresh before editing.");
              await client.updateDecisionService({
                project: slug,
                serviceId: editing.id,
                changes: graph,
              });
              await loadData(slug);
            }}
          />
        </section>
      )}

      {/* Decision Runs Explorer Panel */}
      <section className="panel">
        <div className="section-heading">
          <div>
            <h2 style={{ margin: "0 0 4px" }}>Decision Runs History</h2>
            <p className="lede" style={{ fontSize: "14px", margin: 0 }}>
              Immutable operational decisions executed over ingested raw events.
            </p>
          </div>
          <Link
            href={`/projects/${project.id}/data`}
            style={{
              fontSize: "13px",
              color: "var(--accent)",
              textDecoration: "none",
              fontWeight: 600,
            }}
          >
            Go to Data → Select Events to Run
          </Link>
        </div>

        {loading ? (
          <p className="empty">Loading decision runs…</p>
        ) : runs.length === 0 ? (
          <p className="empty" data-testid="empty-runs">
            No decision runs recorded yet. Ingest raw events on the{" "}
            <Link href={`/projects/${project.id}/data`} style={{ color: "var(--accent)" }}>
              Data page
            </Link>{" "}
            and run intelligence.
          </p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="data-table" data-testid="decision-runs-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Observation Content</th>
                  <th>Selected Choice</th>
                  <th>Top P</th>
                  <th>Margin</th>
                  <th>UNKNOWN P</th>
                  <th>Supervision</th>
                  <th>Provider / Mode</th>
                  <th>Inference</th>
                  <th>Latency</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const content = String(run.input_snapshot?.content ?? "");
                  const preview = content.length > 50 ? `${content.slice(0, 50)}…` : content;
                  const supClass =
                    run.supervision_outcome === "TRUSTED"
                      ? "trusted"
                      : run.supervision_outcome === "UNKNOWN"
                        ? "unknown"
                        : "review";
                  return (
                    <tr key={run.id} data-testid={`run-row-${run.id}`}>
                      <td style={{ whiteSpace: "nowrap", fontFamily: "ui-monospace, monospace" }}>
                        {new Date(run.created_at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })}
                      </td>
                      <td className="content-preview" title={content}>
                        {preview}
                      </td>
                      <td>
                        <strong
                          style={{
                            color: run.selected_choice === "UNKNOWN" ? "#c4a0ff" : "var(--accent)",
                            fontFamily: "ui-monospace, monospace",
                          }}
                        >
                          {run.selected_choice}
                        </strong>
                      </td>
                      <td style={{ fontFamily: "ui-monospace, monospace" }}>
                        {(run.top_probability * 100).toFixed(1)}%
                      </td>
                      <td style={{ fontFamily: "ui-monospace, monospace" }}>
                        +{((run.margin ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td style={{ fontFamily: "ui-monospace, monospace", color: "#c4a0ff" }}>
                        {(run.unknown_probability * 100).toFixed(1)}%
                      </td>
                      <td>
                        <span className={`supervision-badge ${supClass}`}>
                          {run.supervision_outcome}
                        </span>
                      </td>
                      <td style={{ fontSize: "12px", fontFamily: "ui-monospace, monospace" }}>
                        {run.provider} · {run.execution_mode}
                      </td>
                      <td>
                        <span
                          className={`provenance-badge ${run.real_inference ? "real" : "fallback"}`}
                        >
                          {run.real_inference ? "✓ Real" : "⚠ Fallback"}
                        </span>
                      </td>
                      <td style={{ fontFamily: "ui-monospace, monospace", color: "var(--muted)" }}>
                        {run.latency_ms.toFixed(0)}ms
                      </td>
                      <td>
                        <button
                          type="button"
                          className="inspect-btn"
                          onClick={() => setInspectingRun(run)}
                          data-testid={`inspect-run-${run.id}`}
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

      {/* New Decision Service Modal */}
      {showCreateModal && (
        <div className="modal-backdrop" onClick={() => setShowCreateModal(false)}>
          <div
            className="modal-content"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: "700px" }}
          >
            <div className="modal-header">
              <h3>Create Decision Service</h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => setShowCreateModal(false)}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateService} style={{ padding: 0, border: "none" }}>
              {createError && (
                <p className="error" role="alert" style={{ marginBottom: "16px" }}>
                  {createError}
                </p>
              )}

              <label htmlFor="service-name">Service Name</label>
              <input
                id="service-name"
                type="text"
                value={serviceName}
                onChange={(e) => setServiceName(e.target.value)}
                placeholder="e.g., Support Ticket Routing"
                required
                style={{
                  width: "100%",
                  background: "var(--bg)",
                  color: "var(--text)",
                  border: "1px solid var(--line)",
                  borderRadius: "5px",
                  padding: "13px",
                  marginBottom: "16px",
                  fontSize: "14px",
                }}
              />

              <label htmlFor="service-desc">Description (Optional)</label>
              <input
                id="service-desc"
                type="text"
                value={serviceDesc}
                onChange={(e) => setServiceDesc(e.target.value)}
                placeholder="Brief purpose of this decision boundary"
                style={{
                  width: "100%",
                  background: "var(--bg)",
                  color: "var(--text)",
                  border: "1px solid var(--line)",
                  borderRadius: "5px",
                  padding: "13px",
                  marginBottom: "16px",
                  fontSize: "14px",
                }}
              />

              <label htmlFor="service-instructions">Instructions / Classification Prompt</label>
              <textarea
                id="service-instructions"
                rows={3}
                value={serviceInstructions}
                onChange={(e) => setServiceInstructions(e.target.value)}
                placeholder="Classify customer message by department and severity..."
                required
                style={{ marginBottom: "16px" }}
              />

              <label htmlFor="provider-override">Provider Override (Optional)</label>
              <select
                id="provider-override"
                value={providerOverride}
                onChange={(e) => setProviderOverride(e.target.value)}
                style={{ marginBottom: "20px" }}
              >
                <option value="">Default (Project / System Provider - Laya)</option>
                <option value="laya">Laya (Local ModernBERT Engine)</option>
                <option value="jev">Jev (External Provider)</option>
                <option value="mock">Mock (Simulated)</option>
              </select>

              <div style={{ marginBottom: "20px" }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "12px",
                  }}
                >
                  <label style={{ margin: 0, fontWeight: 600 }}>Decision Choices</label>
                  <button
                    type="button"
                    onClick={addChoice}
                    style={{
                      padding: "6px 12px",
                      fontSize: "12px",
                      background: "transparent",
                      color: "var(--accent)",
                      border: "1px solid var(--accent)",
                    }}
                  >
                    + Add Choice
                  </button>
                </div>

                {/* Permanent UNKNOWN choice notice */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "12px",
                    background: "rgba(196, 160, 255, 0.08)",
                    border: "1px dashed rgba(196, 160, 255, 0.4)",
                    borderRadius: "6px",
                    padding: "10px 14px",
                    marginBottom: "12px",
                    fontSize: "13px",
                  }}
                >
                  <strong style={{ color: "#c4a0ff", fontFamily: "ui-monospace, monospace" }}>
                    UNKNOWN
                  </strong>
                  <span style={{ color: "var(--muted)", flex: 1 }}>
                    Permanent semantic fallback. Automatically preserved by OpenClass domain
                    authority.
                  </span>
                  <span className="badge" style={{ borderColor: "#c4a0ff", color: "#c4a0ff" }}>
                    Locked
                  </span>
                </div>

                {/* Dynamic choices */}
                <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                  {choices.map((choice, idx) => (
                    <div
                      key={idx}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "140px 180px 1fr auto",
                        gap: "8px",
                        alignItems: "center",
                      }}
                    >
                      <input
                        type="text"
                        placeholder="KEY (e.g. BILLING)"
                        value={choice.key}
                        onChange={(e) => updateChoice(idx, "key", e.target.value)}
                        required
                        style={{
                          background: "var(--bg)",
                          color: "var(--text)",
                          border: "1px solid var(--line)",
                          borderRadius: "4px",
                          padding: "8px 10px",
                          fontSize: "12px",
                          fontFamily: "ui-monospace, monospace",
                        }}
                      />
                      <input
                        type="text"
                        placeholder="Label"
                        value={choice.label}
                        onChange={(e) => updateChoice(idx, "label", e.target.value)}
                        style={{
                          background: "var(--bg)",
                          color: "var(--text)",
                          border: "1px solid var(--line)",
                          borderRadius: "4px",
                          padding: "8px 10px",
                          fontSize: "12px",
                        }}
                      />
                      <input
                        type="text"
                        placeholder="Description / Criteria"
                        value={choice.description}
                        onChange={(e) => updateChoice(idx, "description", e.target.value)}
                        style={{
                          background: "var(--bg)",
                          color: "var(--text)",
                          border: "1px solid var(--line)",
                          borderRadius: "4px",
                          padding: "8px 10px",
                          fontSize: "12px",
                        }}
                      />
                      <button
                        type="button"
                        onClick={() => removeChoice(idx)}
                        style={{
                          background: "transparent",
                          color: "var(--muted)",
                          border: "1px solid var(--line)",
                          borderRadius: "4px",
                          padding: "6px 10px",
                          cursor: "pointer",
                        }}
                        title="Remove choice"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  style={{
                    background: "transparent",
                    color: "var(--text)",
                    border: "1px solid var(--line)",
                  }}
                >
                  Cancel
                </button>
                <button type="submit" disabled={createBusy} data-testid="submit-service-btn">
                  {createBusy ? "Creating…" : "Create Decision Service"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Inspect Run Drawer / Modal */}
      {inspectingRun && (
        <div className="modal-backdrop" onClick={() => setInspectingRun(null)}>
          <div
            className="modal-content"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: "750px" }}
          >
            <div className="modal-header">
              <div>
                <h3 style={{ margin: "0 0 4px" }}>Decision Run Details</h3>
                <span className="status" style={{ fontSize: "11px" }}>
                  Run ID: {inspectingRun.id}
                </span>
              </div>
              <button type="button" className="modal-close" onClick={() => setInspectingRun(null)}>
                ✕
              </button>
            </div>

            <div
              className="detail-view"
              style={{ display: "flex", flexDirection: "column", gap: "18px" }}
            >
              {/* Outcome summary card */}
              <div
                style={{
                  background: "var(--bg)",
                  border: "1px solid var(--line)",
                  borderRadius: "8px",
                  padding: "16px",
                  display: "grid",
                  gridTemplateColumns: "repeat(3, 1fr)",
                  gap: "12px",
                }}
              >
                <div>
                  <div style={{ fontSize: "11px", color: "var(--muted)", marginBottom: "4px" }}>
                    SELECTED CHOICE
                  </div>
                  <div
                    style={{
                      fontSize: "18px",
                      fontWeight: 700,
                      color:
                        inspectingRun.selected_choice === "UNKNOWN" ? "#c4a0ff" : "var(--accent)",
                      fontFamily: "ui-monospace, monospace",
                    }}
                  >
                    {inspectingRun.selected_choice}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: "11px", color: "var(--muted)", marginBottom: "4px" }}>
                    SUPERVISION
                  </div>
                  <div>
                    <span
                      className={`supervision-badge ${
                        inspectingRun.supervision_outcome === "TRUSTED"
                          ? "trusted"
                          : inspectingRun.supervision_outcome === "UNKNOWN"
                            ? "unknown"
                            : "review"
                      }`}
                    >
                      {inspectingRun.supervision_outcome}
                    </span>
                  </div>
                  <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "4px" }}>
                    {inspectingRun.supervision_reason}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: "11px", color: "var(--muted)", marginBottom: "4px" }}>
                    INFERENCE PROVENANCE
                  </div>
                  <div style={{ fontSize: "13px", fontWeight: 600 }}>
                    {inspectingRun.provider} ({inspectingRun.model})
                  </div>
                  <div style={{ display: "flex", gap: "6px", marginTop: "4px" }}>
                    <span
                      className={`provenance-badge ${inspectingRun.real_inference ? "real" : "fallback"}`}
                    >
                      {inspectingRun.real_inference ? "✓ Real Inference" : "⚠ Test Fallback"}
                    </span>
                    <span className="badge" style={{ padding: "2px 6px", fontSize: "10px" }}>
                      {inspectingRun.execution_mode}
                    </span>
                  </div>
                </div>
              </div>

              {/* Complete Probability Distribution Visualizer */}
              <div>
                <h4 style={{ margin: "0 0 8px", fontSize: "14px" }}>Probability Distribution</h4>
                <div className="prob-dist-bar-container">
                  {Object.entries(inspectingRun.probabilities)
                    .sort(([, a], [, b]) => b - a)
                    .map(([key, prob]) => {
                      const pct = (prob * 100).toFixed(1);
                      const isSelected = key === inspectingRun.selected_choice;
                      const isUnknown = key === "UNKNOWN";
                      return (
                        <div key={key} className="prob-dist-row">
                          <span
                            className="prob-dist-label"
                            style={{
                              fontWeight: isSelected ? 700 : 400,
                              color: isUnknown
                                ? "#c4a0ff"
                                : isSelected
                                  ? "var(--accent)"
                                  : "var(--text)",
                            }}
                          >
                            {key} {isSelected ? "◀" : ""}
                          </span>
                          <div className="prob-dist-bar-track">
                            <div
                              className={`prob-dist-bar-fill ${isUnknown ? "unknown" : ""}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <span className="prob-dist-val">{pct}%</span>
                        </div>
                      );
                    })}
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: "16px",
                    fontSize: "12px",
                    color: "var(--muted)",
                    marginTop: "8px",
                  }}
                >
                  <span>Top: {(inspectingRun.top_probability * 100).toFixed(1)}%</span>
                  <span>Margin: +{((inspectingRun.margin ?? 0) * 100).toFixed(1)}%</span>
                  <span>UNKNOWN: {(inspectingRun.unknown_probability * 100).toFixed(1)}%</span>
                  <span>Latency: {inspectingRun.latency_ms.toFixed(1)}ms</span>
                </div>
              </div>

              {/* Input observation snapshot */}
              <div>
                <h4 style={{ margin: "0 0 6px", fontSize: "14px" }}>
                  Input Snapshot (Observation)
                </h4>
                <pre>{JSON.stringify(inspectingRun.input_snapshot, null, 2)}</pre>
              </div>

              {/* Instructions snapshot */}
              <div>
                <h4 style={{ margin: "0 0 6px", fontSize: "14px" }}>Instructions Snapshot</h4>
                <div
                  style={{
                    background: "var(--bg)",
                    border: "1px solid var(--line)",
                    borderRadius: "6px",
                    padding: "12px",
                    fontSize: "13px",
                    color: "var(--text)",
                  }}
                >
                  {inspectingRun.instructions_snapshot}
                </div>
              </div>

              {/* Choices snapshot */}
              <div>
                <h4 style={{ margin: "0 0 6px", fontSize: "14px" }}>Choices Snapshot</h4>
                <pre>{JSON.stringify(inspectingRun.choices_snapshot, null, 2)}</pre>
              </div>

              {/* Provider metadata */}
              <div>
                <h4 style={{ margin: "0 0 6px", fontSize: "14px" }}>Provider Metadata</h4>
                <pre>{JSON.stringify(inspectingRun.provider_metadata, null, 2)}</pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </ProjectShell>
  );
}
