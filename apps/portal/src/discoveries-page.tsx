import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
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
    queryFn: async (): Promise<Project> => (await controlFetch(`/projects/${projectId}`, token)) as Project,
  });
}

function TypeChip({ type }: { type: string }) {
  const cls = type === "NEW_CLASS" ? "chip locked" : type === "INSUFFICIENT_EVIDENCE" ? "chip" : "chip";
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
      (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/candidates`, token)) as Candidate[],
  });
  const detail = useQuery({
    queryKey: ["candidate", projectId, open],
    enabled: open !== null,
    queryFn: async (): Promise<CandidateDetail> =>
      (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/candidates/${open}`, token)) as CandidateDetail,
  });
  if (project.isPending) return <main><p className="lede">Loading discoveries…</p></main>;
  if (!project.data) return <main><p className="lede">Project unavailable.</p></main>;
  return (
    <main>
      <ProjectShell project={project.data} active="/discoveries">
        <section className="signal">
          <p className="eyebrow">DISCOVERIES / INACTIVE CANDIDATES</p>
          <h2>Evidence-backed proposals — never active behavior.</h2>
          <p className="muted">Candidates are read-only here; review and promotion arrive in later phases. No ontology write happens on this page.</p>
          {candidates.data?.length === 0 && (
            <p className="muted">No candidates yet. Discover a cluster from the Clusters page.</p>
          )}
          <div className="card-grid">
            {candidates.data?.map((candidate) => (
              <article key={candidate.id} className="project-card">
                <p className="status"><i /> {(candidate.confidence * 100).toFixed(0)}% confidence</p>
                <h3>{candidate.display_name ?? candidate.canonical_name ?? candidate.type}</h3>
                <p>
                  <TypeChip type={candidate.type} /> · {candidate.evidence_count} evidence runs
                  {candidate.simulated ? " · simulated" : ""}
                </p>
                <button className="ghost" onClick={() => setOpen(candidate.id)}>View candidate</button>
              </article>
            ))}
          </div>
        </section>
      </ProjectShell>
      {open && (
        <div className="modal-backdrop" role="dialog" aria-label="Candidate detail" onClick={() => setOpen(null)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <p className="eyebrow">CANDIDATE / {detail.data?.status?.toUpperCase() ?? "…"}</p>
            <h2>{detail.data?.display_name ?? detail.data?.canonical_name ?? "…"}</h2>
            {detail.isPending && <p className="muted">Loading…</p>}
            {detail.data && (
              <>
                <p><TypeChip type={detail.data.type} /> · confidence {(detail.data.confidence * 100).toFixed(0)}%</p>
                {detail.data.definition && <p className="muted">{detail.data.definition}</p>}
                {detail.data.aliases.length > 0 && (
                  <p className="muted">aliases: {detail.data.aliases.join(", ")}</p>
                )}
                <p className="muted">
                  existing match: {detail.data.existing_match ?? "none"} · reason: {detail.data.reason}
                </p>
                <p className="muted">
                  evidence: {detail.data.evidence_run_ids.length} member runs (
                  {detail.data.evidence_run_ids.slice(0, 3).map((id) => id.slice(0, 8)).join(", ")})
                </p>
                <p className="muted">provider {detail.data.provider}{detail.data.simulated ? " (simulated)" : ""}</p>
              </>
            )}
            <div className="modal-actions">
              <button className="ghost" onClick={() => setOpen(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
