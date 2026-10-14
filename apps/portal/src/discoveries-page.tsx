import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { controlFetch } from "./api";
import { useAuth } from "./auth";
import { ProjectShell, type Project } from "./projects";

export type Candidate = {
  id: string;
  cluster_id: string;
  type: string;
  canonical_name: string | null;
  display_name: string | null;
  confidence: number;
  status: string;
  provider: string;
  simulated?: boolean;
  evidence_count: number;
  created_at: string;
};
export type CandidateDetail = Candidate & {
  definition: string | null;
  aliases: string[];
  existing_match: string | null;
  reason: string;
  evidence_run_ids: string[];
};

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

function TypeChip({ type }: { type: string }) {
  const cls =
    type === "NEW_CLASS" ? "chip locked" : type === "INSUFFICIENT_EVIDENCE" ? "chip" : "chip";
  return <span className={cls}>{type.replaceAll("_", " ")}</span>;
}

export function DiscoveriesPage() {
  const { projectId = "" } = useParams();
  const token = useToken();
  const project = useProjectQuery(projectId);
  const [open, setOpen] = useState<string | null>(null);
  const candidates = useQuery({
    queryKey: ["candidates", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<Candidate[]> =>
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/candidates`,
        token,
      )) as Candidate[],
  });
  const detail = useQuery({
    queryKey: ["candidate", projectId, open],
    enabled: open !== null,
    queryFn: async (): Promise<CandidateDetail> =>
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/candidates/${open}`,
        token,
      )) as CandidateDetail,
  });
  if (project.isPending)
    return (
      <main>
        <p className="lede">Loading discoveries…</p>
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
      <ProjectShell project={project.data} active="/discoveries">
        <section className="signal">
          <p className="eyebrow">DISCOVERIES / INACTIVE CANDIDATES</p>
          <h2>Evidence-backed proposals — never active behavior.</h2>
          <p className="muted">
            Candidates are read-only here; review and promotion arrive in later phases. No ontology
            write happens on this page.
          </p>
          {candidates.data?.length === 0 && (
            <p className="muted">No candidates yet. Discover a cluster from the Clusters page.</p>
          )}
          <div className="card-grid">
            {candidates.data?.map((candidate) => (
              <article key={candidate.id} className="project-card">
                <p className="status">
                  <i /> {(candidate.confidence * 100).toFixed(0)}% confidence
                </p>
                <h3>{candidate.display_name ?? candidate.canonical_name ?? candidate.type}</h3>
                <p>
                  <TypeChip type={candidate.type} /> · {candidate.evidence_count} evidence runs
                  {candidate.simulated ? " · simulated" : ""}
                </p>
                <Link to={`/projects/${projectId}/discoveries/${candidate.id}`}>
                  Open candidate →
                </Link>
              </article>
            ))}
          </div>
        </section>
      </ProjectShell>
      {open && (
        <div
          className="modal-backdrop"
          role="dialog"
          aria-label="Candidate detail"
          onClick={() => setOpen(null)}
        >
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <p className="eyebrow">CANDIDATE / {detail.data?.status?.toUpperCase() ?? "…"}</p>
            <h2>{detail.data?.display_name ?? detail.data?.canonical_name ?? "…"}</h2>
            {detail.isPending && <p className="muted">Loading…</p>}
            {detail.data && (
              <>
                <p>
                  <TypeChip type={detail.data.type} /> · confidence{" "}
                  {(detail.data.confidence * 100).toFixed(0)}%
                </p>
                {detail.data.definition && <p className="muted">{detail.data.definition}</p>}
                {detail.data.aliases.length > 0 && (
                  <p className="muted">aliases: {detail.data.aliases.join(", ")}</p>
                )}
                <p className="muted">
                  existing match: {detail.data.existing_match ?? "none"} · reason:{" "}
                  {detail.data.reason}
                </p>
                <p className="muted">
                  evidence: {detail.data.evidence_run_ids.length} member runs (
                  {detail.data.evidence_run_ids
                    .slice(0, 3)
                    .map((id) => id.slice(0, 8))
                    .join(", ")}
                  )
                </p>
                <p className="muted">
                  provider {detail.data.provider}
                  {detail.data.simulated ? " (simulated)" : ""}
                </p>
              </>
            )}
            <div className="modal-actions">
              <button className="ghost" onClick={() => setOpen(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

export type CandidateHistory = {
  events: Array<{
    event: string;
    actor: string;
    from: string | null;
    to: string | null;
    created_at: string;
  }>;
  reviews: Array<{ reviewer: string; decision: string; rationale: string; created_at: string }>;
};

const MIN_EVIDENCE = 5;

export function CandidateReviewPage() {
  const { projectId = "", candidateId = "" } = useParams();
  const token = useToken();
  const queryClient = useQueryClient();
  const project = useProjectQuery(projectId);
  const [decision, setDecision] = useState("approve");
  const [rationale, setRationale] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);

  const base = `/workspaces/${project.data?.workspace_id}/projects/${projectId}/unknowns/candidates/${candidateId}`;
  const detail = useQuery({
    queryKey: ["candidate", projectId, candidateId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<CandidateDetail> =>
      (await controlFetch(base, token)) as CandidateDetail,
  });
  const history = useQuery({
    queryKey: ["candidate-history", projectId, candidateId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<CandidateHistory> =>
      (await controlFetch(`${base}/history`, token)) as CandidateHistory,
  });
  const pool = useQuery({
    queryKey: ["unknowns", projectId, ""],
    enabled: project.isSuccess,
    queryFn: async (): Promise<{ items: Array<{ run_id: string; content: string }> }> =>
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns?limit=50`,
        token,
      )) as {
        items: Array<{ run_id: string; content: string }>;
      },
  });

  const act = useMutation({
    mutationFn: async (payload: { action: string; body?: unknown }) =>
      controlFetch(`${base}/${payload.action}`, token, {
        method: "POST",
        body: JSON.stringify(payload.body ?? {}),
      }),
    onSuccess: (result) => {
      const message = (result as { detail?: string; status?: string; evidence?: number }) ?? {};
      setFeedback(
        message.detail
          ? `Blocked: ${message.detail}`
          : `Done — status: ${message.status ?? "updated"}${message.evidence !== undefined ? ` (evidence: ${message.evidence})` : ""}`,
      );
      void queryClient.invalidateQueries({ queryKey: ["candidate", projectId, candidateId] });
      void queryClient.invalidateQueries({
        queryKey: ["candidate-history", projectId, candidateId],
      });
    },
    onError: (error: Error) => setFeedback(error.message),
  });

  if (project.isPending || detail.isPending)
    return (
      <main>
        <p className="lede">Loading candidate…</p>
      </main>
    );
  if (!project.data || !detail.data)
    return (
      <main>
        <p className="lede">Candidate unavailable.</p>
      </main>
    );

  const evidenceCount = detail.data.evidence_run_ids.length;
  const belowThreshold = evidenceCount < MIN_EVIDENCE;
  const notAttached = (pool.data?.items ?? []).filter(
    (item) => !detail.data!.evidence_run_ids.includes(item.run_id),
  );

  return (
    <main>
      <ProjectShell project={project.data} active="/discoveries">
        <section className="signal">
          <p className="eyebrow">CANDIDATE / {detail.data.status.toUpperCase()}</p>
          <h2>{detail.data.display_name ?? detail.data.canonical_name ?? detail.data.type}</h2>
          <p className="muted">
            <TypeChip type={detail.data.type} /> · {evidenceCount}/{MIN_EVIDENCE} evidence ·
            confidence {(detail.data.confidence * 100).toFixed(0)}% ·{" "}
            <Link to={`/projects/${projectId}/discoveries`}>all candidates</Link>
          </p>
          {detail.data.definition && <p className="muted">{detail.data.definition}</p>}
          {belowThreshold && (
            <p className="field-error">
              Insufficient evidence ({evidenceCount}/{MIN_EVIDENCE}) — review completion is blocked
              until you collect more.
            </p>
          )}
          <div className="panel">
            <div className="panel-head">
              <h3>Evidence manager</h3>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>Evidence run</th>
                </tr>
              </thead>
              <tbody>
                {detail.data.evidence_run_ids.map((id) => (
                  <tr key={id}>
                    <td>
                      <code>{id}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {notAttached.length > 0 && (
              <>
                <p className="muted">Attach more evidence from the UNKNOWN pool:</p>
                <div className="panel-head">
                  <select defaultValue="">
                    {notAttached.slice(0, 10).map((item) => (
                      <option key={item.run_id} value={item.run_id}>
                        {item.run_id.slice(0, 8)}… · {item.content.slice(0, 40)}
                      </option>
                    ))}
                  </select>
                  <button
                    className="ghost"
                    onClick={(event) => {
                      const select = (event.target as HTMLElement).parentElement?.querySelector(
                        "select",
                      );
                      const value = select instanceof HTMLSelectElement ? select.value : "";
                      if (value) act.mutate({ action: "collect", body: { unknown_ids: [value] } });
                    }}
                  >
                    Attach selected
                  </button>
                </div>
              </>
            )}
          </div>
          <div className="panel">
            <div className="panel-head">
              <h3>Review panel</h3>
            </div>
            <p className="muted">
              Request review, then decide. Model output has zero authority — only this human
              decision counts, and it still needs evaluation + promotion gates before activation.
              There is deliberately no Activate button.
            </p>
            <div className="modal-actions">
              <button className="ghost" onClick={() => act.mutate({ action: "request-review" })}>
                Request review
              </button>
            </div>
            <label>
              Decision
              <select value={decision} onChange={(event) => setDecision(event.target.value)}>
                <option value="approve">approve</option>
                <option value="reject">reject</option>
                <option value="needs_evidence">needs_evidence</option>
              </select>
            </label>
            <label>
              Rationale (required)
              <textarea
                rows={3}
                value={rationale}
                onChange={(event) => setRationale(event.target.value)}
                placeholder="Why this decision…"
              />
            </label>
            <div className="modal-actions">
              <button
                disabled={rationale.trim().length < 5 || act.isPending}
                onClick={() => act.mutate({ action: "review", body: { decision, rationale } })}
              >
                Submit review
              </button>
            </div>
            <label>
              Or reject outright with a reason
              <input
                value={rejectReason}
                onChange={(event) => setRejectReason(event.target.value)}
                placeholder="Reason (min 5 chars)"
              />
            </label>
            <div className="modal-actions">
              <button
                className="ghost danger"
                disabled={rejectReason.trim().length < 5 || act.isPending}
                onClick={() => act.mutate({ action: "reject", body: { reason: rejectReason } })}
              >
                Reject candidate
              </button>
            </div>
            {feedback && (
              <p className="muted" role="status">
                {feedback}
              </p>
            )}
          </div>
          <div className="panel">
            <div className="panel-head">
              <h3>Promotion (Phase 14)</h3>
            </div>
            <p className="muted">
              Requires: approved status, ≥5 evidence, and a passing evaluation — then an explicit
              human reviewer. There is no automatic activation anywhere.
            </p>
            {detail.data.status === "approved" ? (
              <PromotePanel projectId={projectId} candidateId={candidateId} token={token} />
            ) : (
              <p className="field-error">
                Promotion is disabled — candidate is {detail.data.status} (must be approved with a
                passing evaluation).
              </p>
            )}
          </div>
          <div className="panel">
            <div className="panel-head">
              <h3>History (append-only)</h3>
            </div>
            <ul className="timeline">
              <li>created · candidate proposed (discovery)</li>
              {history.data?.events.map((entry, index) => (
                <li key={index}>
                  {entry.event} · {entry.from ?? "?"} → {entry.to ?? "?"} ·{" "}
                  {new Date(entry.created_at).toLocaleString()}
                </li>
              ))}
              {history.data?.reviews.map((entry, index) => (
                <li key={`r${index}`}>
                  review · {entry.decision} by {entry.reviewer} — “{entry.rationale}”
                </li>
              ))}
            </ul>
          </div>
        </section>
      </ProjectShell>
    </main>
  );
}

export type EvaluationRow = { id: string; candidate_id: string; overall_passed: boolean };

function PromotePanel({
  projectId,
  candidateId,
  token,
}: {
  projectId: string;
  candidateId: string;
  token: string;
}) {
  const auth = useAuth();
  const workspace = useQuery({
    queryKey: ["project", projectId],
    queryFn: async (): Promise<{ workspace_id: string }> =>
      (await controlFetch(`/projects/${projectId}`, token)) as { workspace_id: string },
  });
  const evaluations = useQuery({
    queryKey: ["evaluations", projectId],
    enabled: workspace.isSuccess,
    queryFn: async (): Promise<EvaluationRow[]> =>
      (await controlFetch(
        `/workspaces/${workspace.data!.workspace_id}/projects/${projectId}/evaluations`,
        token,
      )) as EvaluationRow[],
  });
  const latest = evaluations.data?.find(
    (row) => row.candidate_id === candidateId && row.overall_passed,
  );
  const [reviewer, setReviewer] = useState("owner@acme.openclass.test");
  const [rationale, setRationale] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const promote = useMutation({
    mutationFn: async () =>
      controlFetch(
        `/workspaces/${workspace.data!.workspace_id}/projects/${projectId}/unknowns/candidates/${candidateId}/promote`,
        token,
        {
          method: "POST",
          body: JSON.stringify({ evaluation_id: latest!.id, reviewer, rationale }),
        },
      ),
    onSuccess: (result) => {
      const version = (result as { version?: { version_number?: number } }).version;
      setMessage(
        `Promoted — ontology v${version?.version_number ?? "?"} created; candidate is now active.`,
      );
    },
    onError: (error: Error) => setMessage(error.message),
  });
  if (!latest) {
    return (
      <p className="field-error">
        No passing evaluation found for this candidate — run a passing evaluation first.
      </p>
    );
  }
  return (
    <>
      <div className="panel-head">
        <span className="muted">evaluation {latest.id.slice(0, 8)}… (passing)</span>
      </div>
      <label>
        Reviewer
        <input value={reviewer} onChange={(event) => setReviewer(event.target.value)} />
      </label>
      <label>
        Rationale
        <textarea
          rows={2}
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
          placeholder="Why this promotion is safe…"
        />
      </label>
      <div className="modal-actions">
        <button
          disabled={reviewer.trim().length < 3 || rationale.trim().length < 5 || promote.isPending}
          onClick={() => promote.mutate()}
        >
          Promote to new ontology version
        </button>
      </div>
      {message && (
        <p className="muted" role="status">
          {message}
        </p>
      )}
    </>
  );
}
