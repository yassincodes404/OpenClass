"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "next/navigation";
import { OpenClass, type Integration, type IntegrationType, type Project } from "@openclass/sdk";
import { ProjectShell } from "../../shell";

const client = new OpenClass("");

export default function IntegrationsPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{
    id: string;
    status: string;
    latency_ms: number | null;
    capabilities: string[];
    error_message: string | null;
  } | null>(null);

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [type, setType] = useState<IntegrationType>("mcp");
  const [endpoint, setEndpoint] = useState("");
  const [secretRef, setSecretRef] = useState("");
  const [capabilitiesStr, setCapabilitiesStr] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  const loadData = async () => {
    if (!id) return;
    try {
      const [proj, ints] = await Promise.all([client.project(id), client.projectIntegrations(id)]);
      setProject(proj);
      setIntegrations(ints);
      setError("");
    } catch {
      setError("Failed to load integrations.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [id]);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!id || !name.trim()) {
      setFormError("Name is required");
      return;
    }
    setSubmitting(true);
    setFormError("");
    try {
      const caps = capabilitiesStr
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);
      await client.createProjectIntegration({
        project: id,
        name: name.trim(),
        type,
        endpoint: endpoint.trim() || null,
        secret_ref: secretRef.trim() || null,
        capabilities: caps,
      });
      setName("");
      setEndpoint("");
      setSecretRef("");
      setCapabilitiesStr("");
      setModalOpen(false);
      await loadData();
    } catch {
      setFormError("Failed to create integration");
    } finally {
      setSubmitting(false);
    }
  };

  const handleTest = async (integrationId: string) => {
    if (!id) return;
    setTestingId(integrationId);
    setTestResult(null);
    try {
      const res = await client.testProjectIntegration({ project: id, integrationId });
      setTestResult({
        id: integrationId,
        status: res.status,
        latency_ms: res.latency_ms,
        capabilities: res.capabilities,
        error_message: res.error_message,
      });
      await loadData();
    } catch {
      setTestResult({
        id: integrationId,
        status: "disconnected",
        latency_ms: null,
        capabilities: [],
        error_message: "Connection test request failed",
      });
    } finally {
      setTestingId(null);
    }
  };

  const handleDelete = async (integrationId: string) => {
    if (!id) return;
    try {
      await client.deleteProjectIntegration({ project: id, integrationId });
      await loadData();
    } catch {
      setError("Failed to delete integration");
    }
  };

  if (loading) return <main role="status">Loading integrations…</main>;
  if (error) return <main role="alert">{error}</main>;
  if (!project) return <main role="alert">Project not found.</main>;

  const connectedCount = integrations.filter((i) => i.status === "connected").length;
  const mcpCount = integrations.filter((i) => i.type === "mcp").length;
  const webhookCount = integrations.filter((i) => i.type === "webhook").length;
  const totalCapabilities = integrations.reduce((acc, i) => acc + (i.capabilities?.length || 0), 0);

  return (
    <ProjectShell project={project} active="integrations">
      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Integrations & External Capabilities</h2>
            <p className="hint">
              Receive authenticated webhook events and check REST endpoints. MCP, provider, and
              database entries are configuration only; their adapters are planned.
            </p>
          </div>
          <button type="button" onClick={() => setModalOpen(true)} className="action-btn">
            + Connect Integration
          </button>
        </div>

        <div className="analytics-metrics-grid" style={{ marginBottom: "24px" }}>
          <div className="metric-card">
            <span className="metric-label">Connected Integrations</span>
            <span className="metric-value">
              {connectedCount} / {integrations.length}
            </span>
          </div>
          <div className="metric-card">
            <span className="metric-label">MCP Servers</span>
            <span className="metric-value">{mcpCount}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Inbound Webhooks</span>
            <span className="metric-value">{webhookCount}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Declared Capabilities</span>
            <span className="metric-value">{totalCapabilities}</span>
          </div>
        </div>

        {integrations.length === 0 ? (
          <div className="empty-state" style={{ padding: "40px 20px", textAlign: "center" }}>
            <p className="empty">No integrations configured yet.</p>
            <p className="hint">
              Add a webhook receiver or REST endpoint. Other connector types are configuration
              placeholders until their adapters are implemented.
            </p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="runs-table" style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Endpoint / Secret</th>
                  <th>Capabilities</th>
                  <th>Latency</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {integrations.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.name}</strong>
                    </td>
                    <td>
                      <span
                        className="badge"
                        style={{ textTransform: "uppercase", fontSize: "11px" }}
                      >
                        {item.type}
                      </span>
                    </td>
                    <td>
                      <span
                        className="badge"
                        style={{
                          background:
                            item.status === "connected"
                              ? "rgba(34, 197, 94, 0.2)"
                              : item.status === "degraded"
                                ? "rgba(234, 179, 8, 0.2)"
                                : "rgba(239, 68, 68, 0.2)",
                          color:
                            item.status === "connected"
                              ? "#22c55e"
                              : item.status === "degraded"
                                ? "#eab308"
                                : "#ef4444",
                        }}
                      >
                        ● {item.status}
                      </span>
                    </td>
                    <td style={{ maxWidth: "220px", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {item.endpoint ? (
                        <code style={{ fontSize: "12px" }}>{item.endpoint}</code>
                      ) : item.secret_ref ? (
                        <span style={{ fontSize: "12px", color: "var(--muted)" }}>
                          Ref: {item.secret_ref}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      {item.capabilities && item.capabilities.length > 0 ? (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                          {item.capabilities.map((c, i) => (
                            <span
                              key={i}
                              style={{
                                fontSize: "11px",
                                background: "var(--panel-alt)",
                                padding: "2px 6px",
                                borderRadius: "3px",
                              }}
                            >
                              {c}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span style={{ color: "var(--muted)", fontSize: "12px" }}>None</span>
                      )}
                    </td>
                    <td style={{ fontSize: "13px" }}>
                      {item.latency_ms !== null ? `${item.latency_ms.toFixed(1)} ms` : "—"}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: "8px" }}>
                        <button
                          type="button"
                          className="button-subtle"
                          style={{ padding: "6px 12px", fontSize: "12px" }}
                          disabled={testingId === item.id}
                          onClick={() => handleTest(item.id)}
                        >
                          {testingId === item.id ? "Pinging…" : "⚡ Ping Test"}
                        </button>
                        <button
                          type="button"
                          className="button-subtle"
                          style={{
                            padding: "6px 10px",
                            fontSize: "12px",
                            color: "var(--danger, #ef4444)",
                          }}
                          onClick={() => handleDelete(item.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {testResult && (
          <div
            className="panel"
            style={{
              marginTop: "20px",
              background: "var(--panel-alt)",
              border: "1px solid var(--line)",
              padding: "16px",
              borderRadius: "6px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h4>⚡ Live Connectivity Test Result</h4>
              <button
                type="button"
                className="button-subtle"
                style={{ padding: "2px 8px", fontSize: "11px" }}
                onClick={() => setTestResult(null)}
              >
                Dismiss
              </button>
            </div>
            <p style={{ margin: "8px 0", fontSize: "13px" }}>
              Status: <strong>{testResult.status}</strong> | Latency:{" "}
              <strong>{testResult.latency_ms ? `${testResult.latency_ms} ms` : "N/A"}</strong>
            </p>
            {testResult.capabilities.length > 0 && (
              <p style={{ margin: "4px 0", fontSize: "13px" }}>
                Discovered Capabilities: {testResult.capabilities.join(", ")}
              </p>
            )}
            {testResult.error_message && (
              <p style={{ color: "#ef4444", margin: "4px 0", fontSize: "13px" }}>
                Error: {testResult.error_message}
              </p>
            )}
          </div>
        )}

        <div style={{ marginTop: "32px", borderTop: "1px solid var(--line)", paddingTop: "20px" }}>
          <h3>Inbound Webhook Specification</h3>
          <p className="hint">
            To ingest raw observations directly into this project from your backend or third-party
            webhooks through your own adapter. Set the referenced environment variable on the
            server, then send its value as the token. Reuse event_key for retries: identical
            deliveries return the original event; changed payloads return a conflict.
          </p>
          <pre
            style={{
              background: "var(--panel-alt)",
              padding: "16px",
              borderRadius: "6px",
              fontSize: "12px",
              overflowX: "auto",
              color: "var(--text)",
            }}
          >
            {`curl -X POST http://localhost:7331/api/v1/projects/${project.slug}/integrations/{integration_id}/webhook \\
  -H "Content-Type: application/json" \\
  -H "X-OpenClass-Token: <your-configured-secret>" \\
  -d '{
    "event_key": "stripe:event:revision:1",
    "source": "stripe",
    "content": "Customer subscription cancelled for plan enterprise",
    "metadata": { "customer_id": "cus_999", "tier": "enterprise" }
  }'`}
          </pre>
        </div>
      </section>

      {modalOpen && (
        <div className="modal-backdrop">
          <div className="modal-content" style={{ maxWidth: "560px" }}>
            <div className="modal-header">
              <h3>Connect New Integration</h3>
              <button type="button" className="modal-close" onClick={() => setModalOpen(false)}>
                ✕
              </button>
            </div>
            <form onSubmit={handleCreate} style={{ padding: "16px 0 0" }}>
              <label>
                Integration Name
                <input
                  type="text"
                  required
                  placeholder="e.g. DevOps MCP Server, Stripe Webhook"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  style={{ width: "100%", padding: "10px", marginTop: "6px" }}
                />
              </label>

              <label style={{ marginTop: "14px" }}>
                Integration Type
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value as IntegrationType)}
                  style={{ width: "100%", padding: "10px", marginTop: "6px" }}
                >
                  <option value="mcp">MCP Server (Model Context Protocol)</option>
                  <option value="webhook">Inbound Webhook Receiver</option>
                  <option value="rest_api">External REST API</option>
                  <option value="provider">AI Gateway / Provider Credentials</option>
                  <option value="database">Database Connector</option>
                </select>
              </label>

              <label style={{ marginTop: "14px" }}>
                Endpoint URL (Optional)
                <input
                  type="url"
                  placeholder="https://mcp.internal.domain.com or https://api.service.com"
                  value={endpoint}
                  onChange={(e) => setEndpoint(e.target.value)}
                  style={{ width: "100%", padding: "10px", marginTop: "6px" }}
                />
              </label>

              <label style={{ marginTop: "14px" }}>
                Environment Secret Reference
                <input
                  type="text"
                  required={type === "webhook"}
                  pattern="[A-Z][A-Z0-9_]*"
                  placeholder="e.g. STRIPE_WEBHOOK_SECRET, OPENCLASS_VERCEL_GATEWAY_KEY"
                  value={secretRef}
                  onChange={(e) => setSecretRef(e.target.value)}
                  style={{ width: "100%", padding: "10px", marginTop: "6px" }}
                />
              </label>

              <label style={{ marginTop: "14px" }}>
                Declared Capabilities (Comma-separated)
                <input
                  type="text"
                  placeholder="e.g. read_logs, query_metrics, event_ingestion"
                  value={capabilitiesStr}
                  onChange={(e) => setCapabilitiesStr(e.target.value)}
                  style={{ width: "100%", padding: "10px", marginTop: "6px" }}
                />
              </label>

              {formError && (
                <p style={{ color: "#ef4444", fontSize: "13px", marginTop: "10px" }}>{formError}</p>
              )}

              <div
                style={{
                  display: "flex",
                  justifyContent: "flex-end",
                  gap: "10px",
                  marginTop: "20px",
                }}
              >
                <button type="button" className="button-subtle" onClick={() => setModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" disabled={submitting}>
                  {submitting ? "Connecting…" : "Connect"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </ProjectShell>
  );
}
