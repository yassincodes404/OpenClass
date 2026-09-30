"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  OpenClass,
  type Project,
  type DecisionService,
  type ChoiceCandidate,
  type ProjectAuditEvent,
} from "@openclass/sdk";
import { ProjectShell } from "../../shell";

const client = new OpenClass("");

export default function KnowledgeExplorerPage() {
  const params = useParams<{ id: string }>();
  const slug = params?.id;

  const [project, setProject] = useState<Project | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [services, setServices] = useState<DecisionService[]>([]);
  const [candidates, setCandidates] = useState<ChoiceCandidate[]>([]);
  const [auditEvents, setAuditEvents] = useState<ProjectAuditEvent[]>([]);
  const [selectedServiceId, setSelectedServiceId] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!slug) return;
    client
      .project(slug)
      .then(setProject)
      .catch(() => setNotFound(true));

    loadData(slug);
  }, [slug]);

  async function loadData(projectSlug: string) {
    setLoading(true);
    try {
      const [svcList, candList, auditList] = await Promise.all([
        client.decisionServices(projectSlug).catch(() => []),
        client.projectCandidates(projectSlug).catch(() => []),
        client.projectAudit(projectSlug).catch(() => []),
      ]);
      setServices(svcList);
      setCandidates(candList);
      setAuditEvents(auditList);
      if (svcList.length > 0 && !selectedServiceId) {
        setSelectedServiceId(svcList[0].id);
      }
    } catch {
      // Best-effort
    } finally {
      setLoading(false);
    }
  }

  if (notFound) {
    return (
      <main>
        <p className="empty" role="alert">
          Project not found.
        </p>
        <p>
          <Link href="/projects">Back to projects</Link>
        </p>
      </main>
    );
  }

  if (!project) {
    return (
      <main>
        <p className="empty" role="status">
          Loading knowledge explorer…
        </p>
      </main>
    );
  }

  const selectedService = services.find((s) => s.id === selectedServiceId) ?? services[0];
  const promotedCandidates = candidates.filter((c) => c.status === "promoted");
  const promotedKeys = new Set(
    promotedCandidates.map((c) => c.proposal.key).filter((k): k is string => Boolean(k)),
  );

  const totalChoices = services.reduce(
    (acc, svc) =>
      acc + (svc.nodes ? svc.nodes.reduce((nAcc, n) => nAcc + (n.choices?.length ?? 0), 0) : 0),
    0,
  );

  return (
    <ProjectShell project={project} active="knowledge">
      {/* Header and Knowledge Metrics */}
      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Knowledge Explorer & Evolved Decision Taxonomies</h2>
            <p className="lede">
              Inspect active decision graphs, operational taxonomies, and the audit trail of
              human-authorized choice promotions grounded in UNKNOWN evidence.
            </p>
          </div>
          <Link
            href={`/projects/${project.slug}/evolution`}
            style={{
              padding: "8px 16px",
              background: "rgba(196, 244, 138, 0.15)",
              border: "1px solid var(--accent)",
              color: "var(--accent)",
              fontWeight: 600,
              borderRadius: "6px",
              textDecoration: "none",
              fontSize: "13px",
            }}
          >
            ⚡ Evolution Inbox & Candidates →
          </Link>
        </div>

        <ul className="counter-grid">
          <li>
            <span className="counter-value">{services.length}</span>
            <span className="counter-label">Active Services</span>
          </li>
          <li style={{ borderColor: "rgba(100, 180, 255, 0.4)" }}>
            <span className="counter-value" style={{ color: "#64b4ff" }}>
              {totalChoices}
            </span>
            <span className="counter-label">Total Choices</span>
          </li>
          <li style={{ borderColor: "rgba(196, 244, 138, 0.5)" }}>
            <span className="counter-value" style={{ color: "var(--accent)" }}>
              {promotedCandidates.length}
            </span>
            <span className="counter-label">Promoted Evolved Choices</span>
          </li>
          <li>
            <span className="counter-value">{auditEvents.length}</span>
            <span className="counter-label">Knowledge Audit Events</span>
          </li>
        </ul>
      </section>

      {/* Decision Service Taxonomy Explorer */}
      <section className="panel" style={{ marginTop: "20px" }}>
        <div className="section-heading">
          <div>
            <h2>Decision Service Taxonomies</h2>
            <p className="hint">
              Select an active service to view its current classification choices, fallback
              boundaries, and evolved additions.
            </p>
          </div>
        </div>

        {services.length === 0 ? (
          <p className="empty">
            No decision services found. Create one in the{" "}
            <Link href={`/projects/${project.slug}/decisions`}>Decisions tab</Link>.
          </p>
        ) : (
          <div>
            {/* Service selector tabs */}
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "8px",
                borderBottom: "1px solid var(--line)",
                paddingBottom: "12px",
                marginBottom: "20px",
              }}
            >
              {services.map((svc) => (
                <button
                  key={svc.id}
                  type="button"
                  className={`project-tab ${selectedService?.id === svc.id ? "active-tab" : ""}`}
                  onClick={() => setSelectedServiceId(svc.id)}
                  style={{ cursor: "pointer", background: "none", fontSize: "14px" }}
                >
                  {svc.name} ({svc.nodes?.[0]?.choices?.length ?? 0} choices)
                </button>
              ))}
            </div>

            {selectedService && (
              <div>
                <div
                  style={{
                    background: "var(--bg)",
                    border: "1px solid var(--line)",
                    borderRadius: "8px",
                    padding: "16px",
                    marginBottom: "20px",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <h3 style={{ margin: "0 0 4px" }}>{selectedService.name}</h3>
                      <p style={{ margin: 0, fontSize: "13px", color: "var(--muted)" }}>
                        Slug: <code>{selectedService.slug}</code> · Last Updated:{" "}
                        {new Date(selectedService.updated_at).toLocaleString()}
                      </p>
                    </div>
                    <span
                      style={{
                        padding: "3px 8px",
                        borderRadius: "4px",
                        fontSize: "11px",
                        fontWeight: 700,
                        textTransform: "uppercase",
                        background: "rgba(120, 216, 160, 0.15)",
                        color: "#78d8a0",
                        border: "1px solid #78d8a0",
                      }}
                    >
                      {selectedService.status}
                    </span>
                  </div>
                  {selectedService.instructions && (
                    <div style={{ marginTop: "12px", fontSize: "13px" }}>
                      <strong style={{ color: "var(--muted)" }}>Instructions:</strong>
                      <p style={{ margin: "4px 0 0", color: "var(--text)" }}>
                        {selectedService.instructions}
                      </p>
                    </div>
                  )}
                </div>

                {/* Choices Table */}
                <h3>Active Choice Taxonomy</h3>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "10px" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--line)", textAlign: "left" }}>
                        <th style={{ padding: "8px 12px" }}>Key</th>
                        <th style={{ padding: "8px 12px" }}>Label</th>
                        <th style={{ padding: "8px 12px" }}>Description</th>
                        <th style={{ padding: "8px 12px" }}>Origin & Nature</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(selectedService.nodes?.[0]?.choices ?? []).map((choice) => {
                        const isUnknown = choice.key === "UNKNOWN";
                        const isEvolved = promotedKeys.has(choice.key);

                        return (
                          <tr
                            key={choice.key}
                            style={{
                              borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
                              background: isEvolved
                                ? "rgba(196, 244, 138, 0.04)"
                                : isUnknown
                                  ? "rgba(180, 140, 255, 0.04)"
                                  : "transparent",
                            }}
                          >
                            <td style={{ padding: "10px 12px" }}>
                              <span
                                style={{
                                  fontFamily: "ui-monospace, monospace",
                                  fontWeight: 700,
                                  fontSize: "13px",
                                  color: isUnknown
                                    ? "#c4a0ff"
                                    : isEvolved
                                      ? "var(--accent)"
                                      : "inherit",
                                }}
                              >
                                {choice.key}
                              </span>
                            </td>
                            <td style={{ padding: "10px 12px", fontWeight: 500 }}>
                              {choice.label}
                            </td>
                            <td
                              style={{
                                padding: "10px 12px",
                                fontSize: "13px",
                                color: "var(--muted)",
                                maxWidth: "340px",
                              }}
                            >
                              {choice.description || "—"}
                            </td>
                            <td style={{ padding: "10px 12px" }}>
                              {isUnknown ? (
                                <span
                                  style={{
                                    padding: "2px 8px",
                                    borderRadius: "4px",
                                    fontSize: "11px",
                                    fontWeight: 600,
                                    background: "rgba(180, 140, 255, 0.15)",
                                    color: "#c4a0ff",
                                    border: "1px solid rgba(180, 140, 255, 0.3)",
                                  }}
                                >
                                  Permanent Fallback
                                </span>
                              ) : isEvolved ? (
                                <span
                                  style={{
                                    padding: "2px 8px",
                                    borderRadius: "4px",
                                    fontSize: "11px",
                                    fontWeight: 600,
                                    background: "rgba(196, 244, 138, 0.15)",
                                    color: "var(--accent)",
                                    border: "1px solid var(--accent)",
                                  }}
                                >
                                  ⚡ Evolved & Promoted
                                </span>
                              ) : (
                                <span
                                  style={{
                                    padding: "2px 8px",
                                    borderRadius: "4px",
                                    fontSize: "11px",
                                    color: "var(--muted)",
                                    border: "1px solid var(--line)",
                                  }}
                                >
                                  Baseline Choice
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Promoted Evolution Lineage */}
      <section className="panel" style={{ marginTop: "20px" }}>
        <div className="section-heading">
          <div>
            <h2>Promoted Knowledge Lineage</h2>
            <p className="hint">
              Traces each promoted choice back to the Teacher LLM proposal, zero-regression
              verification, and the original evidence runs.
            </p>
          </div>
        </div>

        {promotedCandidates.length === 0 ? (
          <p className="empty">
            No promoted evolution choices yet. Use the{" "}
            <Link href={`/projects/${project.slug}/evolution`}>Evolution tab</Link> to synthesize
            and promote choices from UNKNOWN evidence.
          </p>
        ) : (
          <div style={{ display: "grid", gap: "16px" }}>
            {promotedCandidates.map((cand) => (
              <div
                key={cand.id}
                style={{
                  border: "1px solid #78d8a0",
                  background: "var(--bg)",
                  borderRadius: "8px",
                  padding: "16px",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                  }}
                >
                  <div>
                    <span
                      style={{
                        fontFamily: "ui-monospace, monospace",
                        fontSize: "16px",
                        fontWeight: 700,
                        color: "var(--accent)",
                      }}
                    >
                      {cand.proposal.key}
                    </span>{" "}
                    <span style={{ fontWeight: 600, color: "var(--muted)" }}>
                      ({cand.proposal.label})
                    </span>
                    <p style={{ margin: "4px 0", fontSize: "13px" }}>{cand.proposal.description}</p>
                  </div>
                  <span
                    style={{
                      padding: "2px 8px",
                      borderRadius: "4px",
                      fontSize: "11px",
                      fontWeight: 600,
                      background: "rgba(120, 216, 160, 0.15)",
                      color: "#78d8a0",
                      border: "1px solid #78d8a0",
                    }}
                  >
                    Promoted
                  </span>
                </div>

                <div
                  style={{
                    marginTop: "12px",
                    padding: "10px 12px",
                    borderRadius: "6px",
                    background: "rgba(255, 255, 255, 0.03)",
                    fontSize: "12px",
                    color: "var(--muted)",
                  }}
                >
                  <div>
                    <strong>Teacher:</strong> {cand.proposal.provider} ({cand.proposal.model}) ·{" "}
                    <strong>Rationale:</strong> {cand.proposal.rationale}
                  </div>
                  <div style={{ marginTop: "6px" }}>
                    <strong>Lineage Grounding:</strong> {cand.evidence_run_ids?.length ?? 0}{" "}
                    historical UNKNOWN runs · Promoted:{" "}
                    {cand.promoted_at ? new Date(cand.promoted_at).toLocaleString() : "Recently"}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Knowledge Audit Log */}
      <section className="panel" style={{ marginTop: "20px" }}>
        <div className="section-heading">
          <div>
            <h2>Knowledge & Evolution Audit Trail</h2>
            <p className="hint">
              Append-only, immutable record of candidate promotions, taxonomy updates, and evidence
              resolutions.
            </p>
          </div>
        </div>

        {auditEvents.length === 0 ? (
          <p className="empty">No audit events recorded yet.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--line)", textAlign: "left" }}>
                  <th style={{ padding: "8px 12px" }}>Timestamp</th>
                  <th style={{ padding: "8px 12px" }}>Event Type</th>
                  <th style={{ padding: "8px 12px" }}>Actor</th>
                  <th style={{ padding: "8px 12px" }}>Details</th>
                </tr>
              </thead>
              <tbody>
                {auditEvents.slice(0, 50).map((evt) => (
                  <tr key={evt.id} style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.05)" }}>
                    <td
                      style={{
                        padding: "8px 12px",
                        fontSize: "12px",
                        color: "var(--muted)",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {new Date(evt.created_at).toLocaleTimeString()}{" "}
                      {new Date(evt.created_at).toLocaleDateString()}
                    </td>
                    <td style={{ padding: "8px 12px" }}>
                      <span
                        style={{
                          fontFamily: "ui-monospace, monospace",
                          fontSize: "12px",
                          fontWeight: 600,
                          color:
                            evt.event_type === "choice_candidate.promoted"
                              ? "var(--accent)"
                              : evt.event_type === "decision_service.updated"
                                ? "#64b4ff"
                                : evt.event_type === "evidence.resolved"
                                  ? "#78d8a0"
                                  : "inherit",
                        }}
                      >
                        {evt.event_type}
                      </span>
                    </td>
                    <td
                      style={{
                        padding: "8px 12px",
                        fontSize: "12px",
                        fontFamily: "ui-monospace, monospace",
                      }}
                    >
                      {evt.actor}
                    </td>
                    <td
                      style={{
                        padding: "8px 12px",
                        fontSize: "12px",
                        color: "var(--muted)",
                        maxWidth: "400px",
                      }}
                    >
                      {evt.payload ? JSON.stringify(evt.payload) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </ProjectShell>
  );
}
