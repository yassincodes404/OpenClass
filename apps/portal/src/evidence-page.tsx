import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type {
  DiagnosisCategory,
  DiagnosisResult,
  EvidenceItem,
  EvidenceStatus,
} from "@openclass/sdk";
import { controlClient } from "./api";
import { useAuth } from "./auth";
import { ProjectShell } from "./projects";
import { useWorkflowClient } from "./workflow-client";

const diagnoses: DiagnosisCategory[] = [
  "decision_space",
  "procedure",
  "state_representation",
  "precondition",
  "missing_capability",
  "provider_failure",
  "out_of_domain",
  "ambiguous_or_insufficient",
  "analytical_gap",
];
const transitions: Record<EvidenceStatus, EvidenceStatus[]> = {
  pending: ["triaged", "resolved", "dismissed"],
  triaged: ["ready_for_evolution", "resolved", "dismissed"],
  ready_for_evolution: ["resolved", "dismissed"],
  resolved: [],
  dismissed: [],
};

export function EvidencePage() {
  const { projectId = "" } = useParams();
  const auth = useAuth();
  const client = useWorkflowClient();
  const cache = useQueryClient();
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const [caseId, setCaseId] = useState("");
  const [caseOffset, setCaseOffset] = useState(0);
  const [proposalServiceId, setProposalServiceId] = useState("");
  const [proposalEvidence, setProposalEvidence] = useState<string[]>([]);
  const [rejection, setRejection] = useState("");
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState<DiagnosisCategory>("ambiguous_or_insufficient");
  const [rationale, setRationale] = useState("");
  const [diagnosis, setDiagnosis] = useState<DiagnosisResult | null>(null);
  const [message, setMessage] = useState("");
  const project = useQuery({
    queryKey: ["project", projectId],
    enabled: auth.ready && auth.authenticated,
    queryFn: () => controlClient.getProject(projectId, { token: auth.token() }),
  });
  const evidence = useQuery({
    queryKey: ["workflow-evidence", projectId, status, offset],
    enabled: project.isSuccess,
    queryFn: () => client.evidence(projectId, { limit: 25, offset, ...(status ? { status } : {}) }),
  });
  const cases = useQuery({
    queryKey: ["workflow-cases", projectId, caseOffset],
    enabled: project.isSuccess,
    queryFn: () => client.evidenceCases(projectId, { limit: 25, offset: caseOffset }),
  });
  const services = useQuery({
    queryKey: ["workflow-services", projectId],
    enabled: project.isSuccess,
    queryFn: () => client.decisionServices(projectId),
  });
  const candidates = useQuery({
    queryKey: ["workflow-candidates", projectId],
    enabled: project.isSuccess,
    queryFn: () => client.projectCandidates(projectId),
  });
  const detail = useQuery({
    queryKey: ["workflow-evidence-detail", projectId, selected],
    enabled: project.isSuccess && Boolean(selected),
    queryFn: () => client.evidenceItem({ project: projectId, evidenceId: selected }),
  });
  const caseItems = useQuery({
    queryKey: ["workflow-case-items", projectId, caseId],
    enabled: project.isSuccess && Boolean(caseId),
    queryFn: () => client.caseEvidence({ project: projectId, caseId }),
  });
  useEffect(() => {
    setDiagnosis(null);
    setMessage("");
  }, [selected]);
  useEffect(() => {
    setCategory(detail.data?.diagnosis ?? "ambiguous_or_insufficient");
    setRationale(detail.data?.diagnosis_rationale ?? "");
  }, [selected, detail.data]);
  const mutate = useMutation({
    retry: false,
    mutationFn: (task: () => Promise<unknown>) => {
      setMessage("");
      return task();
    },
    onSuccess: () => {
      setMessage(
        "Action completed. Provider advice does not change ground truth or activate a proposal.",
      );
      void cache.invalidateQueries({ queryKey: ["workflow-evidence", projectId] });
      void cache.invalidateQueries({ queryKey: ["workflow-evidence-detail", projectId, selected] });
      void cache.invalidateQueries({ queryKey: ["workflow-cases", projectId] });
      void cache.invalidateQueries({ queryKey: ["workflow-case-items", projectId, caseId] });
      void cache.invalidateQueries({ queryKey: ["workflow-candidates", projectId] });
    },
  });
  const item = detail.data;
  function select(item: EvidenceItem) {
    setSelected(item.id);
    mutate.reset();
  }
  if (!auth.ready)
    return (
      <main>
        <p role="status">Checking secure session…</p>
      </main>
    );
  if (!auth.authenticated)
    return (
      <main className="access-gate">
        <h1>Sign in to your workspace.</h1>
        <button onClick={() => void auth.login()}>Continue with Keycloak</button>
      </main>
    );
  if (project.isError)
    return (
      <main>
        <p role="alert">{project.error.message}</p>
      </main>
    );
  if (!project.data)
    return (
      <main>
        <p role="status">Loading evidence workspace…</p>
      </main>
    );
  return (
    <main>
      <ProjectShell project={project.data} active="/evidence">
        <section className="signal workflow">
          <h2>Evidence, diagnosis & cases</h2>
          <p>
            UNKNOWN is evidence of uncertainty, not proof of a new class. Diagnosis is advisory;
            human triage never activates a proposal.
          </p>
          <label>
            Evidence status
            <select
              disabled={mutate.isPending}
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setOffset(0);
                setSelected("");
              }}
            >
              <option value="">All statuses</option>
              {Object.keys(transitions).map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          {evidence.isPending && <p role="status">Loading evidence…</p>}
          {evidence.isError && <p role="alert">{evidence.error.message}</p>}
          {evidence.data?.length === 0 && <p>No evidence matches this page.</p>}
          <ul>
            {evidence.data?.map((entry) => (
              <li key={entry.id}>
                <label className="toggle-row">
                  <input
                    type="checkbox"
                    disabled={mutate.isPending || entry.status !== "ready_for_evolution"}
                    checked={proposalEvidence.includes(entry.id)}
                    onChange={(e) =>
                      setProposalEvidence((ids) =>
                        e.target.checked ? [...ids, entry.id] : ids.filter((id) => id !== entry.id),
                      )
                    }
                  />{" "}
                  Select {entry.id.slice(0, 8)} for inactive proposal
                </label>
                <button
                  className={selected === entry.id ? undefined : "ghost"}
                  disabled={mutate.isPending}
                  onClick={() => select(entry)}
                >
                  {entry.trigger_type} · {entry.selected_choice ?? "unavailable"} · {entry.status} ·{" "}
                  {entry.id.slice(0, 8)}
                </button>
              </li>
            ))}
          </ul>
          <div className="modal-actions">
            <button
              className="ghost"
              disabled={offset === 0 || evidence.isFetching}
              onClick={() => setOffset((v) => Math.max(0, v - 25))}
            >
              Previous evidence page
            </button>
            <button
              className="ghost"
              disabled={evidence.data?.length !== 25 || evidence.isFetching}
              onClick={() => setOffset((v) => v + 25)}
            >
              Next evidence page
            </button>
          </div>
          {selected && (
            <section className="panel" aria-label="Evidence detail">
              {detail.isPending && <p role="status">Loading evidence detail…</p>}
              {detail.isError && <p role="alert">{detail.error.message}</p>}
              {item && (
                <>
                  <h3>
                    Evidence {item.id.slice(0, 8)} · {item.status}
                  </h3>
                  <p>{item.human_note ?? item.supervision_reason ?? "No note provided."}</p>
                  <dl>
                    <dt>Decision run</dt>
                    <dd>{item.decision_run_id ?? "Unavailable"}</dd>
                    <dt>Provider / model</dt>
                    <dd>
                      {item.provider ?? "Unavailable"} / {item.model ?? "Unavailable"} ·{" "}
                      {item.execution_mode ?? "Unavailable"}
                    </dd>
                    <dt>Selected choice (prediction, not label)</dt>
                    <dd>{item.selected_choice ?? "Unavailable"}</dd>
                  </dl>
                  <button
                    disabled={mutate.isPending}
                    onClick={() =>
                      mutate.mutate(async () => {
                        setDiagnosis(
                          await client.aiDiagnoseEvidence({
                            project: projectId,
                            evidenceId: item.id,
                          }),
                        );
                      })
                    }
                  >
                    Request advisory diagnosis
                  </button>
                  {diagnosis && (
                    <aside aria-label="Advisory diagnosis">
                      <h4>{diagnosis.diagnosis.replaceAll("_", " ")}</h4>
                      <p>{diagnosis.rationale}</p>
                      <p>
                        {diagnosis.provider} / {diagnosis.model} ·{" "}
                        {diagnosis.simulated ? "simulated" : "provider advice"} · confidence{" "}
                        {(diagnosis.confidence * 100).toFixed(1)}%
                      </p>
                      <button
                        className="ghost"
                        onClick={() => {
                          setCategory(diagnosis.diagnosis);
                          setRationale(diagnosis.rationale);
                        }}
                      >
                        Use as editable triage draft
                      </button>
                    </aside>
                  )}
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      mutate.mutate(() =>
                        client.triageEvidence({
                          project: projectId,
                          evidenceId: item.id,
                          diagnosis: category,
                          rationale,
                        }),
                      );
                    }}
                  >
                    <fieldset
                      disabled={mutate.isPending || ["resolved", "dismissed"].includes(item.status)}
                    >
                      <legend>Human triage</legend>
                      <label>
                        Diagnosis category
                        <select
                          value={category}
                          onChange={(e) => setCategory(e.target.value as DiagnosisCategory)}
                        >
                          {diagnoses.map((value) => (
                            <option key={value} value={value}>
                              {value.replaceAll("_", " ")}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Human rationale
                        <textarea
                          required
                          maxLength={2000}
                          value={rationale}
                          onChange={(e) => setRationale(e.target.value)}
                        />
                      </label>
                      <button disabled={!rationale.trim()}>Save human triage</button>
                    </fieldset>
                  </form>
                  <div className="modal-actions">
                    {transitions[item.status].map((target) => (
                      <button
                        key={target}
                        className="ghost"
                        disabled={mutate.isPending}
                        onClick={() =>
                          mutate.mutate(() =>
                            client.transitionEvidence({
                              project: projectId,
                              evidenceId: item.id,
                              targetStatus: target,
                              note: rationale || undefined,
                            }),
                          )
                        }
                      >
                        {target.replaceAll("_", " ")}
                      </button>
                    ))}
                  </div>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      mutate.mutate(async () => {
                        const created = await client.createEvidenceCase({
                          project: projectId,
                          title,
                          evidenceIds: [item.id],
                          ...(item.decision_service_id
                            ? { decisionServiceId: item.decision_service_id }
                            : {}),
                        });
                        setCaseId(created.id);
                        setTitle("");
                      });
                    }}
                  >
                    <label>
                      New case title
                      <input
                        required
                        maxLength={200}
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                      />
                    </label>
                    <button disabled={mutate.isPending}>Create case with this evidence</button>
                  </form>
                  <button
                    className="ghost"
                    disabled={mutate.isPending || !caseId}
                    onClick={() =>
                      mutate.mutate(() =>
                        client.addEvidenceToCase({
                          project: projectId,
                          caseId,
                          evidenceId: item.id,
                        }),
                      )
                    }
                  >
                    Attach evidence to selected case
                  </button>
                </>
              )}
            </section>
          )}
          <section className="panel" aria-label="Evidence cases">
            <h3>Evidence cases</h3>
            {cases.isError && <p role="alert">{cases.error.message}</p>}
            {cases.isPending && <p role="status">Loading cases…</p>}
            {cases.data?.length === 0 && <p>No cases yet. Inspect evidence to create a case.</p>}
            <label>
              Case
              <select value={caseId} onChange={(e) => setCaseId(e.target.value)}>
                <option value="">Select a case</option>
                {cases.data?.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.title} · {entry.status}
                  </option>
                ))}
              </select>
            </label>
            <div className="modal-actions">
              <button
                className="ghost"
                disabled={caseOffset === 0 || cases.isFetching || mutate.isPending}
                onClick={() => {
                  setCaseOffset((v) => Math.max(0, v - 25));
                  setCaseId("");
                }}
              >
                Previous cases page
              </button>
              <button
                className="ghost"
                disabled={cases.data?.length !== 25 || cases.isFetching || mutate.isPending}
                onClick={() => {
                  setCaseOffset((v) => v + 25);
                  setCaseId("");
                }}
              >
                Next cases page
              </button>
            </div>
            {caseId && (
              <>
                {caseItems.isPending && <p role="status">Loading case evidence…</p>}
                {caseItems.isError && <p role="alert">{caseItems.error.message}</p>}
                <ul>
                  {caseItems.data?.map((entry) => (
                    <li key={entry.id}>
                      <button className="ghost" onClick={() => select(entry)}>
                        {entry.id.slice(0, 8)} · {entry.trigger_type} · {entry.status}
                      </button>
                    </li>
                  ))}
                </ul>
                {caseItems.data?.length === 0 && <p>No attached evidence.</p>}
              </>
            )}
          </section>
          <section className="panel" aria-label="Inactive evidence proposals">
            <h3>Inactive evidence proposals</h3>
            <p>
              Teacher advice cannot activate a choice. Gather distinct ready evidence, then use
              verified replay and explicit human review.
            </p>
            <label>
              Proposal target service
              <select
                value={proposalServiceId}
                disabled={mutate.isPending}
                onChange={(e) => setProposalServiceId(e.target.value)}
              >
                <option value="">Select a service</option>
                {services.data?.map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.name}
                  </option>
                ))}
              </select>
            </label>
            {services.isError && <p role="alert">{services.error.message}</p>}
            <button
              disabled={
                mutate.isPending ||
                !proposalServiceId ||
                proposalEvidence.length < 3 ||
                proposalEvidence.length > 20
              }
              onClick={() =>
                mutate.mutate(() =>
                  client.proposeFromEvidence({
                    project: projectId,
                    serviceId: proposalServiceId,
                    evidenceIds: proposalEvidence,
                  }),
                )
              }
            >
              Request inactive proposal from {proposalEvidence.length} selected items
            </button>
            <button
              className="ghost"
              disabled={
                mutate.isPending ||
                !caseId ||
                (caseItems.data?.filter((e) => e.status === "ready_for_evolution").length ?? 0) < 3
              }
              onClick={() =>
                mutate.mutate(() =>
                  client.proposeFromEvidence({ project: projectId, evidenceCaseId: caseId }),
                )
              }
            >
              Request inactive proposal from selected case
            </button>
            {candidates.isError && <p role="alert">{candidates.error.message}</p>}
            {candidates.isPending && <p role="status">Loading inactive proposals…</p>}
            {candidates.data?.length === 0 && <p>No evidence proposals yet.</p>}
            <label>
              Human rejection reason
              <input
                value={rejection}
                onChange={(e) => setRejection(e.target.value)}
                maxLength={1000}
              />
            </label>
            <ul>
              {candidates.data?.map((candidate) => (
                <li key={candidate.id}>
                  <h4>
                    {candidate.proposal.label ?? candidate.proposal.key ?? candidate.proposal.kind}{" "}
                    · {candidate.status}
                  </h4>
                  <p>{candidate.proposal.rationale}</p>
                  <p>
                    {candidate.evidence_run_ids.length} supporting runs ·{" "}
                    {candidate.proposal.provider} / {candidate.proposal.model}
                    {candidate.proposal.simulated ? " · simulated" : ""}
                  </p>
                  {candidate.status === "candidate" && (
                    <button
                      className="ghost danger"
                      disabled={mutate.isPending || !rejection.trim()}
                      onClick={() =>
                        mutate.mutate(() =>
                          client.rejectProjectChoice({
                            project: projectId,
                            candidateId: candidate.id,
                            reason: rejection,
                          }),
                        )
                      }
                    >
                      Reject proposal {candidate.id.slice(0, 8)}
                    </button>
                  )}
                </li>
              ))}
            </ul>
            <Link to={`/projects/${projectId}/evaluations`}>Open verified replay evaluations</Link>
          </section>
          {mutate.isError && (
            <p role="alert">{mutate.error.message} No automatic retry was attempted.</p>
          )}
          {message && <p role="status">{message}</p>}
        </section>
      </ProjectShell>
    </main>
  );
}
