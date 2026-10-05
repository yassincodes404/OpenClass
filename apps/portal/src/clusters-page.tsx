import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { controlFetch } from "./api";
import { useAuth } from "./auth";
import { ProjectShell, type Project } from "./projects";

export type Cluster = { id: string; algorithm: string; model: string; threshold: number; size: number; simulated?: boolean };
export type ClusterDetail = {
  id: string;
  algorithm: string;
  model: string;
  threshold: number;
  members: Array<{ run_id: string; similarity: number }>;
};

function useToken() {
  return useAuth().token() ?? "";
}

export function ClustersPage() {
  const { projectId = "" } = useParams();
  const token = useToken();
  const queryClient = useQueryClient();
  const auth = useAuth();
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: async (): Promise<Project> => (await controlFetch(`/projects/${projectId}`, token)) as Project,
  });
  const clusters = useQuery({
    queryKey: ["clusters", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<Cluster[]> =>
      (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/clusters`, token)) as Cluster[],
  });
  const [open, setOpen] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: ["cluster", projectId, open],
    enabled: open !== null,
    queryFn: async (): Promise<ClusterDetail> =>
      (await controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/clusters/${open}`, token)) as ClusterDetail,
  });
  const run = useMutation({
    mutationFn: async () =>
      controlFetch(`/workspaces/${project.data!.workspace_id}/projects/${projectId}/unknowns/cluster`, token, {
        method: "POST",
        body: JSON.stringify({ threshold: 0.5 }),
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["clusters", projectId] }),
  });

  if (project.isPending) return <main><p className="lede">Loading clusters…</p></main>;
  if (!project.data) return <main><p className="lede">Project unavailable.</p></main>;

  return (
    <main>
      <ProjectShell project={project.data} active="/unknowns">
        <section className="signal">
          <p className="eyebrow">UNKNOWN / CLUSTERS</p>
          <h2>Recurring unknowns group here — evidence, never classes.</h2>
          <p className="muted">Cluster names (if any) are display-only. Grouping is deterministic and reruns are idempotent. <Link to={`/projects/${projectId}/discoveries`}>View discovery candidates →</Link></p>
          <div className="panel-head">
            <span className="muted">
              {clusters.data?.length
                ? `${clusters.data.length} clusters`
                : "No clusters yet"}
            </span>
            <button onClick={() => run.mutate()} disabled={run.isPending}>
              {run.isPending ? "Clustering…" : "Run clustering"}
            </button>
          </div>
          {clusters.data?.length === 0 && <p className="muted">Run clustering to group the UNKNOWN pool (needs ≥ 2 unknowns).</p>}
          <div className="card-grid">
            {clusters.data?.map((cluster) => (
              <article key={cluster.id} className="project-card">
                <p className="status"><i /> {cluster.size} members</p>
                <h3>Cluster {cluster.id.slice(0, 8)}…</h3>
                <p>
                  {cluster.algorithm} · {cluster.model}
                  {cluster.simulated && <> · <span className="chip locked">simulated</span></>}
                </p>
                <p className="muted">threshold {cluster.threshold}</p>
                <button className="ghost" onClick={() => setOpen(cluster.id)}>View members</button>
              </article>
            ))}
          </div>
        </section>
      </ProjectShell>
      {open && (
        <div className="modal-backdrop" role="dialog" aria-label="Cluster members" onClick={() => setOpen(null)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <p className="eyebrow">CLUSTER / PROVENANCE</p>
            <h2>Members</h2>
            {detail.isPending && <p className="muted">Loading…</p>}
            {detail.data && (
              <>
                <p className="muted">
                  model {detail.data.model} · threshold {detail.data.threshold} · algorithm {detail.data.algorithm}
                </p>
                <table className="table">
                  <thead><tr><th>Run</th><th>Similarity</th></tr></thead>
                  <tbody>
                    {detail.data.members.map((member) => (
                      <tr key={member.run_id}>
                        <td><code>{member.run_id.slice(0, 8)}…</code></td>
                        <td>{member.similarity.toFixed(3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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
