"use client";

import { useEffect, useState, useMemo, type FormEvent } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  OpenClass,
  type Project,
  type EvidenceItem,
  type EvidenceCase,
  type EvolutionSummary,
  type DiagnosisResult,
  type DiagnosisCategory,
  type EvidenceStatus,
  type EvidenceTriggerType,
  type ChoiceCandidate,
  type DecisionService,
} from "@openclass/sdk";
import { ProjectShell } from "../../shell";

const client = new OpenClass("");

const DIAGNOSIS_OPTIONS: Array<{ value: DiagnosisCategory; label: string; description: string }> = [
  {
    value: "decision_space",
    label: "Decision Space Gap",
    description: "Input describes a legitimate pattern not currently represented in choices",
  },
  {
    value: "missing_capability",
    label: "Missing Capability",
    description: "System lacks capability or integration to satisfy requirement",
  },
  {
    value: "ambiguous_or_insufficient",
    label: "Ambiguous / Insufficient",
    description: "Input lacks sufficient detail to determine correct classification",
  },
  {
    value: "out_of_domain",
    label: "Out of Domain",
    description: "Observation does not belong to this decision service scope",
  },
  {
    value: "procedure",
    label: "Procedure / Workflow",
    description: "Flow, routing, or state machine sequence issue",
  },
  {
    value: "state_representation",
    label: "State Representation",
    description: "Entity state representation is inaccurate or incomplete",
  },
  {
    value: "precondition",
    label: "Precondition Violated",
    description: "Prerequisite for execution was not met",
  },
  {
    value: "provider_failure",
    label: "Provider / Model Failure",
    description: "Underlying provider erred, timed out, or hallucinated",
  },
  {
    value: "analytical_gap",
    label: "Analytical Gap",
    description: "Missing business metrics or evaluation data",
  },
];

function triggerLabel(trigger: EvidenceTriggerType): string {
  switch (trigger) {
    case "semantic_unknown":
      return "UNKNOWN Choice";
    case "low_trust":
      return "Low Trust";
    case "human_correction":
      return "Human Correction";
    case "human_marked_missing_concept":
      return "Missing Concept";
    case "supervisor_finding":
      return "Supervisor Finding";
    case "postcondition_failure":
      return "Postcondition Failure";
    case "repeated_pattern":
      return "Repeated Pattern";
    case "state_gap":
      return "State Gap";
    case "analytical_gap":
      return "Analytical Gap";
    default:
      return trigger;
  }
}

function percent(val: number): string {
  return `${(val * 100).toFixed(1)}%`;
}

export default function EvolutionInboxPage() {
  const params = useParams<{ id: string }>();
  const slug = params?.id;

  const [project, setProject] = useState<Project | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [summary, setSummary] = useState<EvolutionSummary | null>(null);
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
  const [casesList, setCasesList] = useState<EvidenceCase[]>([]);
  const [candidatesList, setCandidatesList] = useState<ChoiceCandidate[]>([]);
  const [decisionServices, setDecisionServices] = useState<DecisionService[]>([]);
  const [activeTab, setActiveTab] = useState<"evidence" | "cases" | "candidates">("evidence");
  const [loading, setLoading] = useState(true);

  // Candidates & Synthesis state
  const [candidateActionMessage, setCandidateActionMessage] = useState<Record<string, string>>({});

  // Synthesis modal state
  const [showSynthModal, setShowSynthModal] = useState(false);
  const [synthTargetServiceId, setSynthTargetServiceId] = useState("");
  const [synthMode, setSynthMode] = useState<"case" | "items">("items");
  const [synthCaseId, setSynthCaseId] = useState("");
  const [synthSelectedEvidenceIds, setSynthSelectedEvidenceIds] = useState<string[]>([]);
  const [synthBusy, setSynthBusy] = useState(false);
  const [synthError, setSynthError] = useState("");
  const [synthSuccess, setSynthSuccess] = useState("");

  // Filter state
  const [statusFilter, setStatusFilter] = useState<string>("pending");
  const [triggerFilter, setTriggerFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState("");

  // Inspect drawer
  const [selectedItem, setSelectedItem] = useState<EvidenceItem | null>(null);
  const [inspectLoading, setInspectLoading] = useState(false);

  // AI Diagnosis state
  const [aiDiagnosis, setAiDiagnosis] = useState<DiagnosisResult | null>(null);
  const [diagnosing, setDiagnosing] = useState(false);
  const [diagnoseError, setDiagnoseError] = useState("");

  // Triage form state
  const [triageCategory, setTriageCategory] = useState<DiagnosisCategory>("decision_space");
  const [triageRationale, setTriageRationale] = useState("");
  const [triageBusy, setTriageBusy] = useState(false);
  const [triageSuccess, setTriageSuccess] = useState("");

  // Case creation/assignment modal/state
  const [showCaseModal, setShowCaseModal] = useState(false);
  const [newCaseTitle, setNewCaseTitle] = useState("");
  const [newCaseDesc, setNewCaseDesc] = useState("");
  const [caseBusy, setCaseBusy] = useState(false);

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
      const [sum, ev, cases, cands, services] = await Promise.all([
        client.evolutionSummary(projectSlug).catch(() => null),
        client.evidence(projectSlug, { limit: 100 }),
        client.evidenceCases(projectSlug, { limit: 50 }).catch(() => []),
        client.projectCandidates(projectSlug).catch(() => []),
        client.decisionServices(projectSlug).catch(() => []),
      ]);
      setSummary(sum);
      setEvidenceList(ev);
      setCasesList(cases);
      setCandidatesList(cands);
      setDecisionServices(services);
      if (services.length > 0 && !synthTargetServiceId) {
        setSynthTargetServiceId(services[0].id);
      }
    } catch {
      // Best-effort
    } finally {
      setLoading(false);
    }
  }

  const filteredItems = useMemo(() => {
    return evidenceList.filter((item) => {
      if (statusFilter !== "all" && item.status !== statusFilter) return false;
      if (triggerFilter && item.trigger_type !== triggerFilter) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const rationale = (item.diagnosis_rationale ?? "").toLowerCase();
        const note = (item.human_note ?? "").toLowerCase();
        const choice = (item.selected_choice ?? "").toLowerCase();
        const diag = (item.diagnosis ?? "").toLowerCase();
        if (
          !rationale.includes(q) &&
          !note.includes(q) &&
          !choice.includes(q) &&
          !diag.includes(q)
        ) {
          return false;
        }
      }
      return true;
    });
  }, [evidenceList, statusFilter, triggerFilter, searchQuery]);

  async function openInspect(item: EvidenceItem) {
    setSelectedItem(item);
    setAiDiagnosis(null);
    setDiagnoseError("");
    setTriageSuccess("");
    setTriageCategory(item.diagnosis ?? "decision_space");
    setTriageRationale(item.diagnosis_rationale ?? item.human_note ?? "");

    // Refresh fresh item
    setInspectLoading(true);
    try {
      if (slug) {
        const fresh = await client.evidenceItem({ project: slug, evidenceId: item.id });
        setSelectedItem(fresh);
        if (fresh.diagnosis) {
          setTriageCategory(fresh.diagnosis);
        }
        if (fresh.diagnosis_rationale) {
          setTriageRationale(fresh.diagnosis_rationale);
        }
      }
    } catch {
      // keep existing item
    } finally {
      setInspectLoading(false);
    }
  }

  async function handleDiagnose() {
    if (!slug || !selectedItem) return;
    setDiagnosing(true);
    setDiagnoseError("");
    try {
      const res = await client.aiDiagnoseEvidence({
        project: slug,
        evidenceId: selectedItem.id,
      });
      setAiDiagnosis(res);
    } catch (err: unknown) {
      setDiagnoseError(
        err instanceof Error ? err.message : "Diagnosis failed. Verify provider configuration.",
      );
    } finally {
      setDiagnosing(false);
    }
  }

  function applyAiDiagnosis() {
    if (!aiDiagnosis) return;
    setTriageCategory(aiDiagnosis.diagnosis);
    setTriageRationale(aiDiagnosis.rationale);
  }

  async function handleSaveTriage(e: FormEvent) {
    e.preventDefault();
    if (!slug || !selectedItem) return;
    setTriageBusy(true);
    setTriageSuccess("");
    try {
      const updated = await client.triageEvidence({
        project: slug,
        evidenceId: selectedItem.id,
        diagnosis: triageCategory,
        rationale: triageRationale,
      });
      setSelectedItem(updated);
      setEvidenceList((prev) => prev.map((it) => (it.id === updated.id ? updated : it)));
      setTriageSuccess("Triage saved successfully!");
      if (slug) loadData(slug);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Triage save failed");
    } finally {
      setTriageBusy(false);
    }
  }

  async function handleTransition(target: EvidenceStatus) {
    if (!slug || !selectedItem) return;
    try {
      const updated = await client.transitionEvidence({
        project: slug,
        evidenceId: selectedItem.id,
        targetStatus: target,
      });
      setSelectedItem(updated);
      setEvidenceList((prev) => prev.map((it) => (it.id === updated.id ? updated : it)));
      if (slug) loadData(slug);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Transition failed");
    }
  }

  async function handleAssignCase(caseId: string) {
    if (!slug || !selectedItem) return;
    try {
      await client.addEvidenceToCase({
        project: slug,
        caseId: caseId,
        evidenceId: selectedItem.id,
      });
      const fresh = await client.evidenceItem({ project: slug, evidenceId: selectedItem.id });
      setSelectedItem(fresh);
      setEvidenceList((prev) => prev.map((it) => (it.id === fresh.id ? fresh : it)));
      if (slug) loadData(slug);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Could not assign case");
    }
  }

  async function handleCreateCase(e: FormEvent) {
    e.preventDefault();
    if (!slug || !selectedItem || !newCaseTitle.trim()) return;
    setCaseBusy(true);
    try {
      const newCase = await client.createEvidenceCase({
        project: slug,
        title: newCaseTitle.trim(),
        description: newCaseDesc.trim(),
        evidenceIds: [selectedItem.id],
      });
      setShowCaseModal(false);
      setNewCaseTitle("");
      setNewCaseDesc("");
      const fresh = await client.evidenceItem({ project: slug, evidenceId: selectedItem.id });
      setSelectedItem(fresh);
      setEvidenceList((prev) => prev.map((it) => (it.id === fresh.id ? fresh : it)));
      if (slug) loadData(slug);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Could not create case");
    } finally {
      setCaseBusy(false);
    }
  }

  async function handleRejectCandidate(candidateId: string, reason: string) {
    if (!slug) return;
    if (!reason) {
      alert("Please provide a rejection reason.");
      return;
    }
    try {
      const updated = await client.rejectProjectChoice({
        project: slug,
        candidateId,
        reason,
      });
      setCandidatesList((prev) => prev.map((c) => (c.id === candidateId ? updated : c)));
      setCandidateActionMessage((prev) => ({
        ...prev,
        [candidateId]: `Candidate rejected: ${reason}`,
      }));
      loadData(slug);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Rejection failed");
    }
  }

  async function handleRunSynthesis(e: FormEvent) {
    e.preventDefault();
    if (!slug) return;
    setSynthBusy(true);
    setSynthError("");
    setSynthSuccess("");
    try {
      let createdCandidate: ChoiceCandidate;
      if (synthMode === "case") {
        if (!synthCaseId) {
          throw new Error("Please select an evidence case with at least 3 ready items.");
        }
        createdCandidate = await client.proposeFromEvidence({
          project: slug,
          evidenceCaseId: synthCaseId,
        });
      } else {
        if (!synthTargetServiceId) {
          throw new Error("Please select a target Decision Service.");
        }
        if (synthSelectedEvidenceIds.length < 3) {
          throw new Error("Please select at least 3 ready-for-evolution evidence items.");
        }
        createdCandidate = await client.proposeFromEvidence({
          project: slug,
          serviceId: synthTargetServiceId,
          evidenceIds: synthSelectedEvidenceIds,
        });
      }
      setCandidatesList((prev) => [createdCandidate, ...prev]);
      setSynthSuccess(
        `Candidate ${createdCandidate.proposal.key ?? "proposed"} created successfully!`,
      );
      setShowSynthModal(false);
      setActiveTab("candidates");
      loadData(slug);
    } catch (err: unknown) {
      setSynthError(err instanceof Error ? err.message : "Synthesis failed.");
    } finally {
      setSynthBusy(false);
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
          Loading evolution inbox…
        </p>
      </main>
    );
  }

  return (
    <ProjectShell project={project} active="evolution">
      {/* Overview & Metric Counters */}
      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Evolution Inbox & Human Triage</h2>
            <p className="lede">
              The bridge between operational execution and system evolution. Review semantic
              UNKNOWNs, supervision failures, and customer feedback. Diagnose root causes with the
              configured diagnosis provider and triage evidence before knowledge synthesis.
            </p>
          </div>
        </div>

        <ul className="counter-grid">
          <li>
            <span className="counter-value">{summary?.total_evidence ?? 0}</span>
            <span className="counter-label">Total Evidence</span>
          </li>
          <li style={{ borderColor: "rgba(255, 200, 80, 0.4)" }}>
            <span className="counter-value" style={{ color: "#ffc850" }}>
              {summary?.pending_evidence ?? 0}
            </span>
            <span className="counter-label">Pending Triage</span>
          </li>
          <li style={{ borderColor: "rgba(100, 180, 255, 0.4)" }}>
            <span className="counter-value" style={{ color: "#64b4ff" }}>
              {summary?.triaged_evidence ?? 0}
            </span>
            <span className="counter-label">Triaged</span>
          </li>
          <li style={{ borderColor: "rgba(196, 244, 138, 0.5)" }}>
            <span className="counter-value" style={{ color: "var(--accent)" }}>
              {summary?.ready_for_evolution ?? 0}
            </span>
            <span className="counter-label">Ready for Evolution</span>
          </li>
          <li>
            <span className="counter-value">{summary?.open_cases ?? 0}</span>
            <span className="counter-label">Open Cases</span>
          </li>
          <li style={{ borderColor: "rgba(196, 160, 255, 0.4)" }}>
            <span className="counter-value" style={{ color: "#c4a0ff" }}>
              {candidatesList.length}
            </span>
            <span className="counter-label">Choice Candidates</span>
          </li>
        </ul>
      </section>

      {/* Main View Tabs */}
      <div style={{ display: "flex", gap: "8px", margin: "16px 0" }}>
        <button
          type="button"
          className={`project-tab ${activeTab === "evidence" ? "active-tab" : ""}`}
          onClick={() => setActiveTab("evidence")}
          style={{ cursor: "pointer", background: "none", fontSize: "14px" }}
        >
          Evidence Inbox ({filteredItems.length})
        </button>
        <button
          type="button"
          className={`project-tab ${activeTab === "cases" ? "active-tab" : ""}`}
          onClick={() => setActiveTab("cases")}
          style={{ cursor: "pointer", background: "none", fontSize: "14px" }}
        >
          Evidence Cases ({casesList.length})
        </button>
        <button
          type="button"
          className={`project-tab ${activeTab === "candidates" ? "active-tab" : ""}`}
          onClick={() => setActiveTab("candidates")}
          style={{ cursor: "pointer", background: "none", fontSize: "14px" }}
        >
          Choice Candidates ({candidatesList.length})
        </button>
      </div>

      {activeTab === "evidence" && (
        <>
          {/* Filter Tabs & Controls */}
          <section className="panel">
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "12px",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "16px",
              }}
            >
              <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                {[
                  { key: "pending", label: "Pending" },
                  { key: "triaged", label: "Triaged" },
                  { key: "ready_for_evolution", label: "Ready for Evolution" },
                  { key: "resolved", label: "Resolved" },
                  { key: "dismissed", label: "Dismissed" },
                  { key: "all", label: "All Evidence" },
                ].map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    className={`project-tab ${statusFilter === tab.key ? "active-tab" : ""}`}
                    onClick={() => setStatusFilter(tab.key)}
                    style={{ cursor: "pointer", background: "none" }}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                <select
                  value={triggerFilter}
                  onChange={(e) => setTriggerFilter(e.target.value)}
                  style={{
                    background: "var(--panel)",
                    color: "var(--text)",
                    border: "1px solid var(--line)",
                    padding: "6px 12px",
                    borderRadius: "6px",
                    fontSize: "13px",
                  }}
                >
                  <option value="">All Triggers</option>
                  <option value="semantic_unknown">Semantic UNKNOWN</option>
                  <option value="low_trust">Low Trust</option>
                  <option value="human_correction">Human Correction</option>
                  <option value="supervisor_finding">Supervisor Finding</option>
                </select>

                <input
                  type="text"
                  placeholder="Search evidence..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{
                    background: "var(--panel)",
                    color: "var(--text)",
                    border: "1px solid var(--line)",
                    padding: "6px 12px",
                    borderRadius: "6px",
                    fontSize: "13px",
                  }}
                />
              </div>
            </div>

            {/* Evidence Table */}
            {loading ? (
              <p className="empty" role="status">
                Loading evidence items…
              </p>
            ) : filteredItems.length === 0 ? (
              <p className="empty">
                No evidence found matching the selected filter.
                {statusFilter === "pending" && " All current items have been triaged!"}
              </p>
            ) : (
              <div className="data-table-container">
                <table className="data-table" aria-label="Evidence Inbox">
                  <thead>
                    <tr>
                      <th>Status</th>
                      <th>Trigger</th>
                      <th>Observation / Context</th>
                      <th>Selected Choice</th>
                      <th>Diagnosis</th>
                      <th>Case</th>
                      <th>Created</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredItems.map((item) => {
                      const statusColors: Record<string, string> = {
                        pending: "#ffc850",
                        triaged: "#64b4ff",
                        ready_for_evolution: "var(--accent)",
                        resolved: "#78d8a0",
                        dismissed: "var(--muted)",
                      };
                      return (
                        <tr key={item.id}>
                          <td>
                            <span
                              style={{
                                display: "inline-block",
                                padding: "2px 8px",
                                borderRadius: "4px",
                                fontSize: "11px",
                                fontWeight: 600,
                                textTransform: "uppercase",
                                color: statusColors[item.status] ?? "var(--text)",
                                border: `1px solid ${statusColors[item.status] ?? "var(--line)"}`,
                              }}
                            >
                              {item.status.replace(/_/g, " ")}
                            </span>
                          </td>
                          <td>
                            <span className="source-badge">{triggerLabel(item.trigger_type)}</span>
                          </td>
                          <td style={{ maxWidth: "280px" }}>
                            <div
                              style={{
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                                fontWeight: 500,
                              }}
                            >
                              {item.human_note || item.diagnosis_rationale || "Automated trigger"}
                            </div>
                            <div
                              style={{
                                fontSize: "11px",
                                color: "var(--muted)",
                                fontFamily: "ui-monospace, monospace",
                              }}
                            >
                              Run: {item.decision_run_id?.slice(0, 8)}…
                            </div>
                          </td>
                          <td>
                            <span
                              style={{
                                fontFamily: "ui-monospace, monospace",
                                color: item.selected_choice === "UNKNOWN" ? "#c4a0ff" : "inherit",
                              }}
                            >
                              {item.selected_choice ?? "—"}
                            </span>
                            {item.unknown_probability > 0 && (
                              <span
                                style={{
                                  fontSize: "11px",
                                  color: "var(--muted)",
                                  marginLeft: "4px",
                                }}
                              >
                                ({percent(item.unknown_probability)})
                              </span>
                            )}
                          </td>
                          <td>
                            {item.diagnosis ? (
                              <span
                                style={{
                                  padding: "2px 6px",
                                  borderRadius: "4px",
                                  background: "rgba(100, 180, 255, 0.1)",
                                  color: "#64b4ff",
                                  fontSize: "12px",
                                  fontFamily: "ui-monospace, monospace",
                                }}
                              >
                                {item.diagnosis}
                              </span>
                            ) : (
                              <span style={{ color: "var(--muted)", fontSize: "12px" }}>
                                Untriaged
                              </span>
                            )}
                          </td>
                          <td>
                            {item.evidence_case_id ? (
                              <span
                                style={{
                                  padding: "2px 6px",
                                  borderRadius: "4px",
                                  background: "rgba(196, 244, 138, 0.1)",
                                  color: "var(--accent)",
                                  fontSize: "11px",
                                }}
                              >
                                Case {item.evidence_case_id.slice(0, 6)}
                              </span>
                            ) : (
                              <span style={{ color: "var(--muted)", fontSize: "11px" }}>
                                Unassigned
                              </span>
                            )}
                          </td>
                          <td style={{ fontSize: "12px", color: "var(--muted)" }}>
                            {new Date(item.created_at).toLocaleDateString()}
                          </td>
                          <td>
                            <button
                              type="button"
                              className="inspect-btn"
                              onClick={() => openInspect(item)}
                              style={{
                                padding: "4px 10px",
                                fontSize: "12px",
                                cursor: "pointer",
                                background: "var(--panel)",
                                border: "1px solid var(--line)",
                                color: "var(--text)",
                                borderRadius: "4px",
                              }}
                            >
                              Inspect & Triage
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

          {/* Inspect & Triage Drawer */}
          {selectedItem && (
            <section
              className="panel"
              style={{
                border: "1px solid var(--accent)",
                marginTop: "20px",
                boxShadow: "0 8px 30px rgba(0,0,0,0.5)",
              }}
            >
              <div className="section-heading">
                <div>
                  <span
                    style={{
                      fontFamily: "ui-monospace, monospace",
                      fontSize: "12px",
                      color: "var(--muted)",
                    }}
                  >
                    Evidence #{selectedItem.id}
                  </span>
                  <h2 style={{ margin: "4px 0" }}>Inspection & Human Triage</h2>
                </div>
                <button
                  type="button"
                  className="inspect-btn"
                  onClick={() => setSelectedItem(null)}
                  style={{
                    cursor: "pointer",
                    padding: "6px 12px",
                    background: "var(--bg)",
                    border: "1px solid var(--line)",
                    color: "var(--text)",
                    borderRadius: "4px",
                  }}
                >
                  Close
                </button>
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                  gap: "20px",
                  marginTop: "16px",
                }}
              >
                {/* Left Column: Decision & Provenance Details */}
                <div>
                  <h3>Execution Context</h3>
                  <dl className="runs-detail-grid">
                    <div>
                      <dt>Status</dt>
                      <dd>
                        <strong>{selectedItem.status.toUpperCase()}</strong>
                      </dd>
                    </div>
                    <div>
                      <dt>Trigger Reason</dt>
                      <dd>{triggerLabel(selectedItem.trigger_type)}</dd>
                    </div>
                    <div>
                      <dt>Decision Run</dt>
                      <dd>
                        <code>{selectedItem.decision_run_id}</code>
                      </dd>
                    </div>
                    <div>
                      <dt>Selected Choice</dt>
                      <dd>
                        <code>{selectedItem.selected_choice ?? "UNKNOWN"}</code>
                      </dd>
                    </div>
                    <div>
                      <dt>UNKNOWN Prob</dt>
                      <dd>{percent(selectedItem.unknown_probability)}</dd>
                    </div>
                    <div>
                      <dt>Margin</dt>
                      <dd>{percent(selectedItem.margin)}</dd>
                    </div>
                    <div>
                      <dt>Supervision</dt>
                      <dd>{selectedItem.supervision_outcome || "None"}</dd>
                    </div>
                    <div>
                      <dt>Provider / Mode</dt>
                      <dd>
                        {selectedItem.provider || "system"} (
                        {selectedItem.execution_mode || "standard"})
                      </dd>
                    </div>
                  </dl>

                  {/* Probabilities Breakdown */}
                  {Object.keys(selectedItem.probabilities_snapshot).length > 0 && (
                    <div style={{ marginTop: "16px" }}>
                      <h4>Probability Distribution</h4>
                      <ul className="runs-probabilities" style={{ listStyle: "none", padding: 0 }}>
                        {Object.entries(selectedItem.probabilities_snapshot).map(([key, p]) => (
                          <li
                            key={key}
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              padding: "4px 0",
                              borderBottom: "1px solid var(--line)",
                              fontSize: "13px",
                            }}
                          >
                            <span style={{ color: key === "UNKNOWN" ? "#c4a0ff" : "inherit" }}>
                              {key}
                            </span>
                            <strong>{percent(p)}</strong>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Source Note / Human Note */}
                  {selectedItem.human_note && (
                    <div style={{ marginTop: "16px" }}>
                      <h4>Human Feedback Note</h4>
                      <p
                        style={{
                          background: "var(--bg)",
                          padding: "10px",
                          borderRadius: "6px",
                          fontSize: "13px",
                          border: "1px solid var(--line)",
                        }}
                      >
                        {selectedItem.human_note}
                      </p>
                    </div>
                  )}

                  {/* Case Assignment */}
                  <div style={{ marginTop: "20px" }}>
                    <h4>Evidence Case Grouping</h4>
                    <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                      <select
                        value={selectedItem.evidence_case_id || ""}
                        onChange={(e) => handleAssignCase(e.target.value)}
                        style={{
                          background: "var(--bg)",
                          color: "var(--text)",
                          border: "1px solid var(--line)",
                          padding: "6px 12px",
                          borderRadius: "6px",
                          fontSize: "13px",
                          flex: 1,
                        }}
                      >
                        <option value="">(No Case Assigned)</option>
                        {casesList.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.title} ({c.status})
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() => setShowCaseModal(true)}
                        style={{
                          padding: "6px 12px",
                          background: "var(--panel)",
                          border: "1px solid var(--line)",
                          color: "var(--accent)",
                          borderRadius: "6px",
                          cursor: "pointer",
                          fontSize: "13px",
                        }}
                      >
                        + New Case
                      </button>
                    </div>
                  </div>
                </div>

                {/* Right Column: AI Failure Diagnosis & Human Triage */}
                <div>
                  {/* AI Diagnosis Section */}
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
                        marginBottom: "12px",
                      }}
                    >
                      <h3 style={{ margin: 0 }}>Advisory AI Diagnosis</h3>
                      <button
                        type="button"
                        onClick={handleDiagnose}
                        disabled={diagnosing}
                        style={{
                          padding: "6px 14px",
                          borderRadius: "6px",
                          background: "var(--accent)",
                          color: "#101411",
                          border: "none",
                          fontWeight: 600,
                          cursor: diagnosing ? "wait" : "pointer",
                          fontSize: "13px",
                        }}
                      >
                        {diagnosing ? "Diagnosing with Provider…" : "⚡ Diagnose with Provider"}
                      </button>
                    </div>

                    {diagnoseError && (
                      <p role="alert" style={{ color: "#ff8080", fontSize: "13px" }}>
                        {diagnoseError}
                      </p>
                    )}

                    {aiDiagnosis ? (
                      <div
                        style={{
                          background: "rgba(196, 244, 138, 0.05)",
                          border: "1px solid rgba(196, 244, 138, 0.3)",
                          borderRadius: "6px",
                          padding: "12px",
                          marginTop: "10px",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                          }}
                        >
                          <span
                            style={{
                              fontWeight: 700,
                              fontSize: "14px",
                              color: "var(--accent)",
                              textTransform: "uppercase",
                            }}
                          >
                            {aiDiagnosis.diagnosis}
                          </span>
                          <span style={{ fontSize: "12px", color: "var(--muted)" }}>
                            Confidence: {(aiDiagnosis.confidence * 100).toFixed(0)}% · Provider:{" "}
                            {aiDiagnosis.provider} ({aiDiagnosis.model})
                          </span>
                        </div>
                        <p style={{ margin: "8px 0", fontSize: "13px", lineHeight: "1.5" }}>
                          {aiDiagnosis.rationale}
                        </p>
                        {aiDiagnosis.recommended_action && (
                          <p style={{ margin: "4px 0", fontSize: "12px", color: "var(--muted)" }}>
                            <strong>Action:</strong> {aiDiagnosis.recommended_action}
                          </p>
                        )}
                        <button
                          type="button"
                          onClick={applyAiDiagnosis}
                          style={{
                            marginTop: "10px",
                            padding: "4px 10px",
                            fontSize: "12px",
                            borderRadius: "4px",
                            background: "rgba(196, 244, 138, 0.2)",
                            border: "1px solid var(--accent)",
                            color: "var(--accent)",
                            cursor: "pointer",
                          }}
                        >
                          ✓ Copy Advisory to Human Triage Form
                        </button>
                      </div>
                    ) : (
                      <p style={{ color: "var(--muted)", fontSize: "13px", margin: 0 }}>
                        Click &quot;Diagnose with Provider&quot; for advisory failure analysis from
                        the configured provider. Review the result before applying human triage.
                      </p>
                    )}
                  </div>

                  {/* Human Triage Form */}
                  <div
                    style={{
                      background: "var(--bg)",
                      border: "1px solid var(--line)",
                      borderRadius: "8px",
                      padding: "16px",
                    }}
                  >
                    <h3 style={{ marginTop: 0 }}>Human Triage Decision</h3>
                    {triageSuccess && (
                      <p style={{ color: "var(--accent)", fontSize: "13px", fontWeight: 600 }}>
                        {triageSuccess}
                      </p>
                    )}
                    <form onSubmit={handleSaveTriage}>
                      <div style={{ marginBottom: "12px" }}>
                        <label
                          style={{
                            display: "block",
                            fontSize: "12px",
                            color: "var(--muted)",
                            marginBottom: "4px",
                          }}
                        >
                          Failure Diagnosis Category
                        </label>
                        <select
                          value={triageCategory}
                          onChange={(e) => setTriageCategory(e.target.value as DiagnosisCategory)}
                          style={{
                            width: "100%",
                            background: "var(--panel)",
                            color: "var(--text)",
                            border: "1px solid var(--line)",
                            padding: "8px 12px",
                            borderRadius: "6px",
                            fontSize: "13px",
                          }}
                        >
                          {DIAGNOSIS_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label} — {opt.description}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div style={{ marginBottom: "14px" }}>
                        <label
                          style={{
                            display: "block",
                            fontSize: "12px",
                            color: "var(--muted)",
                            marginBottom: "4px",
                          }}
                        >
                          Triage Rationale & Notes
                        </label>
                        <textarea
                          rows={3}
                          value={triageRationale}
                          onChange={(e) => setTriageRationale(e.target.value)}
                          placeholder="Explain root cause or notes for future candidate synthesis..."
                          style={{
                            width: "100%",
                            background: "var(--panel)",
                            color: "var(--text)",
                            border: "1px solid var(--line)",
                            padding: "8px 12px",
                            borderRadius: "6px",
                            fontSize: "13px",
                          }}
                        />
                      </div>

                      <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                        <button
                          type="submit"
                          disabled={triageBusy}
                          style={{
                            padding: "8px 16px",
                            borderRadius: "6px",
                            background: "var(--accent)",
                            color: "#101411",
                            fontWeight: 600,
                            border: "none",
                            cursor: triageBusy ? "wait" : "pointer",
                            fontSize: "13px",
                          }}
                        >
                          {triageBusy ? "Saving…" : "Save Triage"}
                        </button>

                        {/* Transition Actions */}
                        <button
                          type="button"
                          onClick={() => handleTransition("ready_for_evolution")}
                          style={{
                            padding: "8px 14px",
                            borderRadius: "6px",
                            background: "rgba(196, 244, 138, 0.15)",
                            border: "1px solid var(--accent)",
                            color: "var(--accent)",
                            fontWeight: 600,
                            cursor: "pointer",
                            fontSize: "13px",
                          }}
                        >
                          🚀 Mark Ready for Evolution
                        </button>

                        <button
                          type="button"
                          onClick={() => handleTransition("resolved")}
                          style={{
                            padding: "8px 12px",
                            borderRadius: "6px",
                            background: "none",
                            border: "1px solid var(--line)",
                            color: "#78d8a0",
                            cursor: "pointer",
                            fontSize: "13px",
                          }}
                        >
                          Resolve
                        </button>

                        <button
                          type="button"
                          onClick={() => handleTransition("dismissed")}
                          style={{
                            padding: "8px 12px",
                            borderRadius: "6px",
                            background: "none",
                            border: "1px solid var(--line)",
                            color: "var(--muted)",
                            cursor: "pointer",
                            fontSize: "13px",
                          }}
                        >
                          Dismiss
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              </div>
            </section>
          )}
        </>
      )}

      {/* Cases View */}
      {activeTab === "cases" && (
        <section className="panel">
          <div className="section-heading">
            <div>
              <h2>Evolution Evidence Cases</h2>
              <p className="lede">
                Cases group related observations pointing to the same knowledge gap or missing
                capability. Synthesize candidates once a case reaches at least 3 ready items.
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                setShowSynthModal(true);
                setSynthMode("case");
              }}
              style={{
                padding: "8px 16px",
                background: "var(--accent)",
                color: "#101411",
                fontWeight: 600,
                border: "none",
                borderRadius: "6px",
                cursor: "pointer",
              }}
            >
              ⚡ Synthesize from Case
            </button>
          </div>

          {casesList.length === 0 ? (
            <p className="empty">
              No evidence cases created yet. Select an evidence item in the inbox and click
              &quot;Assign to Case&quot; or create a new case.
            </p>
          ) : (
            <div style={{ display: "grid", gap: "16px", marginTop: "16px" }}>
              {casesList.map((c) => (
                <div
                  key={c.id}
                  style={{
                    border: "1px solid var(--line)",
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
                      <h3 style={{ margin: "0 0 6px" }}>{c.title}</h3>
                      <p style={{ color: "var(--muted)", margin: 0, fontSize: "13px" }}>
                        {c.description || "No description provided."}
                      </p>
                    </div>
                    <span
                      style={{
                        padding: "2px 8px",
                        borderRadius: "4px",
                        fontSize: "11px",
                        fontWeight: 600,
                        textTransform: "uppercase",
                        background:
                          c.status === "ready_for_evolution"
                            ? "rgba(196, 244, 138, 0.15)"
                            : c.status === "resolved"
                              ? "rgba(120, 216, 160, 0.15)"
                              : "rgba(100, 180, 255, 0.15)",
                        color:
                          c.status === "ready_for_evolution"
                            ? "var(--accent)"
                            : c.status === "resolved"
                              ? "#78d8a0"
                              : "#64b4ff",
                        border: `1px solid ${
                          c.status === "ready_for_evolution"
                            ? "var(--accent)"
                            : c.status === "resolved"
                              ? "#78d8a0"
                              : "#64b4ff"
                        }`,
                      }}
                    >
                      {c.status.replace(/_/g, " ")}
                    </span>
                  </div>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginTop: "14px",
                      fontSize: "12px",
                      color: "var(--muted)",
                    }}
                  >
                    <div>
                      <span>
                        Evidence Count:{" "}
                        <strong>
                          {evidenceList.filter((e) => e.evidence_case_id === c.id).length} items
                        </strong>
                      </span>
                      <span style={{ marginLeft: "16px" }}>
                        Created: {new Date(c.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setSynthCaseId(c.id);
                        setSynthMode("case");
                        setShowSynthModal(true);
                      }}
                      style={{
                        padding: "6px 12px",
                        background: "rgba(196, 244, 138, 0.15)",
                        border: "1px solid var(--accent)",
                        color: "var(--accent)",
                        borderRadius: "4px",
                        fontWeight: 600,
                        cursor: "pointer",
                        fontSize: "12px",
                      }}
                    >
                      ⚡ Synthesize with Teacher
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Choice Candidates View */}
      {activeTab === "candidates" && (
        <section className="panel">
          <div className="section-heading">
            <div>
              <h2>Choice Candidates & Knowledge Synthesis</h2>
              <p className="lede">
                Advisory proposals from the configured Teacher, grounded in UNKNOWN runs. Verified
                evaluation and immutable activation are still being implemented.
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                setShowSynthModal(true);
                setSynthMode("items");
              }}
              style={{
                padding: "8px 16px",
                background: "var(--accent)",
                color: "#101411",
                fontWeight: 600,
                border: "none",
                borderRadius: "6px",
                cursor: "pointer",
              }}
            >
              ⚡ Synthesize Candidate with Teacher
            </button>
          </div>

          {candidatesList.length === 0 ? (
            <p className="empty">
              No choice candidates generated yet. Triage at least 3 UNKNOWN observations to
              &apos;Ready for Evolution&apos; and click &quot;⚡ Synthesize Candidate with
              Teacher&quot;.
            </p>
          ) : (
            <div style={{ display: "grid", gap: "20px", marginTop: "16px" }}>
              {candidatesList.map((cand) => {
                const actionMsg = candidateActionMessage[cand.id];

                return (
                  <div
                    key={cand.id}
                    style={{
                      border: `1px solid ${
                        cand.status === "promoted"
                          ? "#78d8a0"
                          : cand.status === "rejected"
                            ? "#ff6464"
                            : "var(--line)"
                      }`,
                      background: "var(--bg)",
                      borderRadius: "8px",
                      padding: "20px",
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
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "10px",
                            marginBottom: "6px",
                          }}
                        >
                          <span
                            style={{
                              fontFamily: "ui-monospace, monospace",
                              fontSize: "16px",
                              fontWeight: 700,
                              color: "var(--text)",
                              background: "rgba(255, 255, 255, 0.05)",
                              padding: "2px 8px",
                              borderRadius: "4px",
                            }}
                          >
                            {cand.proposal.key ?? "INSUFFICIENT EVIDENCE"}
                          </span>
                          <span
                            style={{ fontSize: "15px", fontWeight: 600, color: "var(--muted)" }}
                          >
                            {cand.proposal.label ?? ""}
                          </span>
                        </div>
                        <p style={{ margin: "4px 0", fontSize: "13px", color: "var(--text)" }}>
                          {cand.proposal.description || "No description provided."}
                        </p>
                      </div>
                      <span
                        style={{
                          padding: "4px 10px",
                          borderRadius: "4px",
                          fontSize: "12px",
                          fontWeight: 700,
                          textTransform: "uppercase",
                          background:
                            cand.status === "promoted"
                              ? "rgba(120, 216, 160, 0.15)"
                              : cand.status === "rejected"
                                ? "rgba(255, 100, 100, 0.15)"
                                : "rgba(255, 200, 80, 0.15)",
                          color:
                            cand.status === "promoted"
                              ? "#78d8a0"
                              : cand.status === "rejected"
                                ? "#ff6464"
                                : "#ffc850",
                          border: `1px solid ${
                            cand.status === "promoted"
                              ? "#78d8a0"
                              : cand.status === "rejected"
                                ? "#ff6464"
                                : "#ffc850"
                          }`,
                        }}
                      >
                        {cand.status === "candidate" ? "Pending Review" : cand.status}
                      </span>
                    </div>

                    {/* Teacher Rationale & Provenance */}
                    <div
                      style={{
                        margin: "14px 0",
                        padding: "12px 14px",
                        borderRadius: "6px",
                        background: "rgba(100, 180, 255, 0.08)",
                        border: "1px solid rgba(100, 180, 255, 0.2)",
                        fontSize: "13px",
                      }}
                    >
                      <div style={{ fontWeight: 600, color: "#64b4ff", marginBottom: "4px" }}>
                        Teacher Rationale ({cand.proposal.provider} / {cand.proposal.model}):
                      </div>
                      <div style={{ color: "var(--text)" }}>{cand.proposal.rationale}</div>
                      <div style={{ marginTop: "6px", fontSize: "11px", color: "var(--muted)" }}>
                        Grounded in {cand.evidence_run_ids?.length ?? 0} historical UNKNOWN runs ·
                        Hash: {cand.base_service_hash.slice(0, 12)}…
                      </div>
                    </div>

                    {actionMsg && (
                      <p
                        style={{
                          color: "var(--accent)",
                          fontWeight: 600,
                          fontSize: "13px",
                          margin: "8px 0",
                        }}
                      >
                        {actionMsg}
                      </p>
                    )}

                    {/* Candidate Actions */}
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "10px",
                        alignItems: "center",
                        marginTop: "16px",
                        paddingTop: "12px",
                        borderTop: "1px solid var(--line)",
                      }}
                    >
                      <p className="hint">
                        Verified replay evaluation and activation are not available yet. Proposals
                        remain inactive.
                      </p>
                      <button type="button" disabled>
                        Run Evaluation Replay
                      </button>
                      {cand.status === "candidate" && (
                        <>
                          <button type="button" disabled>
                            Promote &amp; Activate Choice
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              const r = prompt("Enter rejection reason:");
                              if (r) {
                                handleRejectCandidate(cand.id, r.trim());
                              }
                            }}
                            style={{
                              padding: "6px 12px",
                              background: "none",
                              border: "1px solid rgba(255, 100, 100, 0.4)",
                              color: "#ff6464",
                              borderRadius: "4px",
                              cursor: "pointer",
                              fontSize: "12px",
                            }}
                          >
                            Reject
                          </button>
                        </>
                      )}

                      {cand.status === "promoted" && (
                        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                          <span style={{ color: "#78d8a0", fontSize: "12px", fontWeight: 600 }}>
                            Historical activation recorded{" "}
                            {cand.promoted_at
                              ? `on ${new Date(cand.promoted_at).toLocaleDateString()}`
                              : ""}
                          </span>
                          <Link
                            href={`/projects/${project.slug}/knowledge`}
                            style={{
                              fontSize: "12px",
                              color: "var(--accent)",
                              textDecoration: "underline",
                            }}
                          >
                            View in Knowledge Explorer →
                          </Link>
                        </div>
                      )}

                      {cand.status === "rejected" && cand.rejection_reason && (
                        <span style={{ color: "var(--muted)", fontSize: "12px" }}>
                          Rejection note: {cand.rejection_reason}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {/* Synthesize Candidate Modal */}
      {showSynthModal && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.75)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "var(--panel)",
              border: "1px solid var(--line)",
              borderRadius: "10px",
              padding: "24px",
              maxWidth: "560px",
              width: "100%",
              maxHeight: "90vh",
              overflowY: "auto",
            }}
          >
            <h3 style={{ marginTop: 0 }}>⚡ Synthesize Choice Candidate with Teacher</h3>
            <p className="hint">
              Use the configured Teacher to inspect recurring UNKNOWN observations, hypothesize
              missing concepts, and formulate an explicit choice proposal.
            </p>

            {synthError && (
              <p style={{ color: "#ff6464", fontSize: "13px", fontWeight: 600 }}>{synthError}</p>
            )}

            <form onSubmit={handleRunSynthesis}>
              <div style={{ marginBottom: "14px" }}>
                <label style={{ display: "block", fontSize: "12px", marginBottom: "4px" }}>
                  Target Decision Service
                </label>
                <select
                  value={synthTargetServiceId}
                  onChange={(e) => setSynthTargetServiceId(e.target.value)}
                  style={{
                    width: "100%",
                    background: "var(--bg)",
                    color: "var(--text)",
                    border: "1px solid var(--line)",
                    padding: "8px 12px",
                    borderRadius: "6px",
                  }}
                >
                  {decisionServices.map((svc) => (
                    <option key={svc.id} value={svc.id}>
                      {svc.name} ({svc.slug})
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ marginBottom: "14px" }}>
                <label style={{ display: "block", fontSize: "12px", marginBottom: "4px" }}>
                  Synthesis Source
                </label>
                <div style={{ display: "flex", gap: "16px" }}>
                  <label
                    style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}
                  >
                    <input
                      type="radio"
                      name="synthMode"
                      value="items"
                      checked={synthMode === "items"}
                      onChange={() => setSynthMode("items")}
                    />
                    Select Ready Evidence Items
                  </label>
                  <label
                    style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}
                  >
                    <input
                      type="radio"
                      name="synthMode"
                      value="case"
                      checked={synthMode === "case"}
                      onChange={() => setSynthMode("case")}
                    />
                    From Evidence Case
                  </label>
                </div>
              </div>

              {synthMode === "case" ? (
                <div style={{ marginBottom: "16px" }}>
                  <label style={{ display: "block", fontSize: "12px", marginBottom: "4px" }}>
                    Select Evidence Case
                  </label>
                  <select
                    value={synthCaseId}
                    onChange={(e) => setSynthCaseId(e.target.value)}
                    style={{
                      width: "100%",
                      background: "var(--bg)",
                      color: "var(--text)",
                      border: "1px solid var(--line)",
                      padding: "8px 12px",
                      borderRadius: "6px",
                    }}
                  >
                    <option value="">-- Choose Case --</option>
                    {casesList.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.title} ({evidenceList.filter((e) => e.evidence_case_id === c.id).length}{" "}
                        items)
                      </option>
                    ))}
                  </select>
                </div>
              ) : (
                <div style={{ marginBottom: "16px" }}>
                  <label style={{ display: "block", fontSize: "12px", marginBottom: "4px" }}>
                    Select Ready Evidence Items (min 3 required):
                  </label>
                  <div
                    style={{
                      maxHeight: "180px",
                      overflowY: "auto",
                      border: "1px solid var(--line)",
                      background: "var(--bg)",
                      borderRadius: "6px",
                      padding: "8px",
                    }}
                  >
                    {evidenceList
                      .filter((e) => e.status === "ready_for_evolution")
                      .map((e) => {
                        const isChecked = synthSelectedEvidenceIds.includes(e.id);
                        return (
                          <label
                            key={e.id}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: "8px",
                              padding: "4px 0",
                              cursor: "pointer",
                              fontSize: "12px",
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={(evt) => {
                                if (evt.target.checked) {
                                  setSynthSelectedEvidenceIds((prev) => [...prev, e.id]);
                                } else {
                                  setSynthSelectedEvidenceIds((prev) =>
                                    prev.filter((id) => id !== e.id),
                                  );
                                }
                              }}
                            />
                            <span>
                              <strong>#{e.id.slice(0, 8)}</strong> -{" "}
                              {e.diagnosis_rationale || e.human_note || "Ready item"}
                            </span>
                          </label>
                        );
                      })}
                    {evidenceList.filter((e) => e.status === "ready_for_evolution").length ===
                      0 && (
                      <p style={{ color: "var(--muted)", fontSize: "12px", margin: "6px 0" }}>
                        No items in &apos;ready_for_evolution&apos; status. Triage evidence items
                        first.
                      </p>
                    )}
                  </div>
                  <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "4px" }}>
                    Selected: {synthSelectedEvidenceIds.length} items
                  </div>
                </div>
              )}

              <div
                style={{
                  display: "flex",
                  gap: "10px",
                  justifyContent: "flex-end",
                  marginTop: "20px",
                }}
              >
                <button
                  type="button"
                  onClick={() => setShowSynthModal(false)}
                  style={{
                    padding: "8px 16px",
                    background: "none",
                    border: "1px solid var(--line)",
                    color: "var(--text)",
                    borderRadius: "6px",
                    cursor: "pointer",
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={synthBusy}
                  style={{
                    padding: "8px 18px",
                    background: "var(--accent)",
                    color: "#101411",
                    fontWeight: 700,
                    border: "none",
                    borderRadius: "6px",
                    cursor: synthBusy ? "wait" : "pointer",
                  }}
                >
                  {synthBusy ? "Synthesizing with Teacher…" : "⚡ Synthesize Candidate"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* New Case Modal */}
      {showCaseModal && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.7)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "var(--panel)",
              border: "1px solid var(--line)",
              borderRadius: "10px",
              padding: "24px",
              maxWidth: "480px",
              width: "100%",
            }}
          >
            <h3 style={{ marginTop: 0 }}>Create Evidence Case</h3>
            <p className="hint">
              Group related observations that share a root cause or point to the same knowledge gap.
            </p>
            <form onSubmit={handleCreateCase}>
              <div style={{ marginBottom: "12px" }}>
                <label style={{ display: "block", fontSize: "12px", marginBottom: "4px" }}>
                  Case Title
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Workspace Feature Requests"
                  value={newCaseTitle}
                  onChange={(e) => setNewCaseTitle(e.target.value)}
                  style={{
                    width: "100%",
                    background: "var(--bg)",
                    color: "var(--text)",
                    border: "1px solid var(--line)",
                    padding: "8px 12px",
                    borderRadius: "6px",
                  }}
                />
              </div>

              <div style={{ marginBottom: "16px" }}>
                <label style={{ display: "block", fontSize: "12px", marginBottom: "4px" }}>
                  Description
                </label>
                <textarea
                  rows={3}
                  placeholder="Shared pattern details..."
                  value={newCaseDesc}
                  onChange={(e) => setNewCaseDesc(e.target.value)}
                  style={{
                    width: "100%",
                    background: "var(--bg)",
                    color: "var(--text)",
                    border: "1px solid var(--line)",
                    padding: "8px 12px",
                    borderRadius: "6px",
                  }}
                />
              </div>

              <div style={{ display: "flex", gap: "10px", justifyContent: "flex-end" }}>
                <button
                  type="button"
                  onClick={() => setShowCaseModal(false)}
                  style={{
                    padding: "8px 16px",
                    background: "none",
                    border: "1px solid var(--line)",
                    color: "var(--text)",
                    borderRadius: "6px",
                    cursor: "pointer",
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={caseBusy}
                  style={{
                    padding: "8px 16px",
                    background: "var(--accent)",
                    color: "#101411",
                    fontWeight: 600,
                    border: "none",
                    borderRadius: "6px",
                    cursor: caseBusy ? "wait" : "pointer",
                  }}
                >
                  {caseBusy ? "Creating…" : "Create & Group"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </ProjectShell>
  );
}
