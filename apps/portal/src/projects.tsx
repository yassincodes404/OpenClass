import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { Link, NavLink, useParams } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ControlApiError, controlFetch } from "./api";
import { useAuth } from "./auth";
import { OverviewKpis } from "./analytics";

export type Workspace = { id: string; slug: string; name: string; role: string };
export type Project = {
  id: string;
  workspace_id: string;
  engine_project_id: string;
  slug: string;
  name: string;
  created_at: string;
};
export type OntologyClass = { canonical_name: string; display_name: string; aliases?: string[] };
export type Classifier = {
  id: string;
  project_id: string;
  engine_classifier_id: string;
  slug: string;
  name: string;
  active_ontology_version_id: string;
  classes: OntologyClass[];
};
export type ApiKeyRow = {
  id: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  revoked_at: string | null;
};

export const sectionLinks = [
  { label: "Overview", path: "" },
  { label: "Classifiers", path: "/classifiers" },
  { label: "Decisions", path: "/decisions" },
  { label: "Runs", path: "/runs" },
  { label: "Data", path: "/data" },
  { label: "Observations", path: "/observations" },
  { label: "Unknowns", path: "/unknowns" },
  { label: "Discoveries", path: "/discoveries" },
  { label: "Evaluations", path: "/evaluations" },
  { label: "Analytics", path: "/analytics" },
  { label: "Ontology", path: "/ontology" },
  { label: "Integrations", path: "/integrations" },
  { label: "Providers", path: "/providers" },
  { label: "Audit", path: "/audit" },
  { label: "Settings", path: "/settings" },
];

function useToken() {
  const auth = useAuth();
  return auth.token() ?? "";
}

function SectionNav({ projectId }: { projectId: string; active: string }) {
  return (
    <nav className="section-nav" aria-label="Project navigation">
      {sectionLinks.map((section) => (
        <NavLink
          key={section.label}
          to={`/projects/${projectId}${section.path}`}
          end={section.path === ""}
          className={({ isActive }) => (isActive ? "active" : undefined)}
        >
          {section.label}
        </NavLink>
      ))}
    </nav>
  );
}

export function Projects() {
  const auth = useAuth();
  const token = useToken();
  const queryClient = useQueryClient();
  const [creatingIn, setCreatingIn] = useState<Workspace | null>(null);

  const workspaces = useQuery({
    queryKey: ["workspaces"],
    enabled: auth.ready && auth.authenticated,
    queryFn: async (): Promise<Workspace[]> => {
      try {
        return (await controlFetch("/workspaces", token)) as Workspace[];
      } catch (error) {
        if (error instanceof ControlApiError && error.status === 401) auth.clearSession();
        throw error;
      }
    },
  });

  if (!auth.ready)
    return (
      <main>
        <p className="lede">Checking secure session…</p>
      </main>
    );
  if (!auth.authenticated) {
    return (
      <main className="access-gate">
        <p className="eyebrow">SECURE PORTAL</p>
        <h1>Sign in to your workspace.</h1>
        <p className="lede">Projects are visible only to authorized workspace members.</p>
        <button onClick={() => void auth.login()}>Continue with Keycloak ↗</button>
      </main>
    );
  }

  return (
    <main>
      <p className="eyebrow">WORKSPACES / AUTHENTICATED</p>
      <h1>Projects</h1>
      {workspaces.isPending && <p className="lede">Loading workspaces…</p>}
      {workspaces.isError && <p className="lede">{(workspaces.error as Error).message}</p>}
      {workspaces.data?.map((workspace) => (
        <WorkspaceCard
          key={workspace.id}
          workspace={workspace}
          onCreate={() => setCreatingIn(workspace)}
          token={token}
        />
      ))}
      {creatingIn && (
        <CreateProjectModal
          workspace={creatingIn}
          token={token}
          onClose={() => setCreatingIn(null)}
          onCreated={() => {
            setCreatingIn(null);
            void queryClient.invalidateQueries({ queryKey: ["projects", creatingIn.id] });
          }}
        />
      )}
    </main>
  );
}

function WorkspaceCard({
  workspace,
  onCreate,
  token,
}: {
  workspace: Workspace;
  onCreate: () => void;
  token: string;
}) {
  const projects = useQuery({
    queryKey: ["projects", workspace.id],
    queryFn: async (): Promise<Project[]> =>
      (await controlFetch(`/workspaces/${workspace.id}/projects`, token)) as Project[],
  });
  return (
    <section className="workspace-block">
      <div className="workspace-head">
        <div>
          <p className="eyebrow">WORKSPACE / {workspace.role.toUpperCase()}</p>
          <h2>{workspace.name}</h2>
        </div>
        {(workspace.role === "owner" || workspace.role === "admin") && (
          <button className="ghost" onClick={onCreate}>
            + New project
          </button>
        )}
      </div>
      {projects.isPending && <p className="lede">Loading projects…</p>}
      {projects.isError && <p className="lede">{(projects.error as Error).message}</p>}
      {projects.isSuccess && projects.data.length === 0 && (
        <p className="lede">No projects yet in this workspace.</p>
      )}
      <div className="card-grid">
        {projects.data?.map((project) => (
          <article key={project.id} className="project-card">
            <p className="status">
              <i /> ACTIVE
            </p>
            <h3>{project.name}</h3>
            <p>
              Slug <code>{project.slug}</code>
            </p>
            <Link to={`/projects/${project.id}`}>Open project →</Link>
          </article>
        ))}
      </div>
    </section>
  );
}

const projectSchema = z.object({
  name: z
    .string()
    .trim()
    .min(2, "Name must be 2–200 characters")
    .max(200, "Name must be 2–200 characters"),
  description: z.string().trim().max(2000, "Description is too long").optional(),
});
type ProjectForm = z.infer<typeof projectSchema>;

function CreateProjectModal({
  workspace,
  token,
  onClose,
  onCreated,
}: {
  workspace: Workspace;
  token: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ProjectForm>({ resolver: zodResolver(projectSchema) });
  const [serverError, setServerError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: async (form: ProjectForm) =>
      controlFetch(`/workspaces/${workspace.id}/projects`, token, {
        method: "POST",
        body: JSON.stringify(form),
      }),
    onSuccess: onCreated,
    onError: (error: Error) => setServerError(error.message),
  });
  return (
    <div className="modal-backdrop" role="dialog" aria-label="Create project">
      <form className="modal" onSubmit={handleSubmit((form) => create.mutate(form))}>
        <p className="eyebrow">NEW PROJECT / {workspace.name.toUpperCase()}</p>
        <h2>Create a project</h2>
        <label>
          Name
          <input {...register("name")} placeholder="Acme Support" />
          {errors.name && <span className="field-error">{errors.name.message}</span>}
        </label>
        <label>
          Description <span className="muted">(optional)</span>
          <textarea
            {...register("description")}
            rows={3}
            placeholder="Customer support intent routing"
          />
          {errors.description && <span className="field-error">{errors.description.message}</span>}
        </label>
        {serverError && <p className="field-error">{serverError}</p>}
        <div className="modal-actions">
          <button type="button" className="ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" disabled={isSubmitting || create.isPending}>
            Create project
          </button>
        </div>
      </form>
    </div>
  );
}

export function ProjectOverview() {
  const { projectId = "" } = useParams();
  const token = useToken();
  const auth = useAuth();
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: async (): Promise<Project> => {
      try {
        return (await controlFetch(`/projects/${projectId}`, token)) as Project;
      } catch (error) {
        if (error instanceof ControlApiError && error.status === 401) auth.clearSession();
        throw error;
      }
    },
  });
  if (project.isPending)
    return (
      <main>
        <p className="lede">Loading project…</p>
      </main>
    );
  if (project.isError)
    return (
      <main>
        <p className="lede">{(project.error as Error).message}</p>
      </main>
    );
  return (
    <main>
      <ProjectShell project={project.data} active="">
        <OverviewKpis projectId={projectId || ""} />
        <OverviewPanels project={project.data} token={token} />
      </ProjectShell>
    </main>
  );
}

export function ProjectShell({
  project,
  active,
  children,
}: {
  project: Project;
  active: string;
  children: ReactNode;
}) {
  return (
    <>
      <div className="project-kicker">
        <div>
          <p className="eyebrow">{project.name.toUpperCase()} / PROJECT</p>
          <h1>
            {active === ""
              ? "The decision system, in focus."
              : sectionLinks.find((s) => s.path === active)?.label}
          </h1>
        </div>
        <span className="status">
          <i /> ACTIVE
        </span>
      </div>
      <SectionNav projectId={project.id} active={active} />
      {children}
    </>
  );
}

function OverviewPanels({ project, token }: { project: Project; token: string }) {
  const queryClient = useQueryClient();
  const keys = useQuery({
    queryKey: ["keys", project.id],
    queryFn: async (): Promise<ApiKeyRow[]> =>
      (await controlFetch(
        `/workspaces/${project.workspace_id}/projects/${project.id}/keys`,
        token,
      )) as ApiKeyRow[],
  });
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const createKey = useMutation({
    mutationFn: async () =>
      (await controlFetch(
        `/workspaces/${project.workspace_id}/projects/${project.id}/keys`,
        token,
        { method: "POST", body: JSON.stringify({ scopes: ["ingest", "read"] }) },
      )) as { key: string },
    onSuccess: (row) => {
      setCreatedKey(row.key);
      void queryClient.invalidateQueries({ queryKey: ["keys", project.id] });
    },
  });
  const revokeKey = useMutation({
    mutationFn: async (keyId: string) =>
      controlFetch(
        `/workspaces/${project.workspace_id}/projects/${project.id}/keys/${keyId}/revoke`,
        token,
        { method: "POST" },
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["keys", project.id] }),
  });
  return (
    <section className="signal">
      <p className="eyebrow">OVERVIEW / FOUNDATION</p>
      <h2>Counts appear as ingestion and decisions come online (Phase 05+).</h2>
      <div className="panel">
        <div className="panel-head">
          <h3>Scoped API keys</h3>
          <button onClick={() => createKey.mutate()}>+ Create key</button>
        </div>
        <p className="muted">
          Keys are shown once and stored as hashes. Secrets are never displayed again.
        </p>
        {createdKey && (
          <div className="key-reveal">
            <p className="eyebrow">SHOWN ONCE / SIMULATED LOCAL DEV KEY</p>
            <code>{createdKey}</code>
            <button
              className="ghost"
              onClick={() => void navigator.clipboard?.writeText(createdKey)}
            >
              Copy
            </button>
          </div>
        )}
        {keys.isPending && <p className="muted">Loading keys…</p>}
        {keys.data?.length === 0 && <p className="muted">No keys yet.</p>}
        <table className="table">
          <tbody>
            {keys.data?.map((key) => (
              <tr key={key.id}>
                <td>
                  <code>{key.prefix}…</code>
                </td>
                <td>{key.scopes.join(", ")}</td>
                <td>
                  {key.revoked_at ? (
                    <span className="chip danger">revoked</span>
                  ) : (
                    <span className="chip">active</span>
                  )}
                </td>
                <td>
                  {key.revoked_at ? null : (
                    <button className="ghost danger" onClick={() => revokeKey.mutate(key.id)}>
                      Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function ClassifiersPage() {
  const { projectId = "" } = useParams();
  const token = useToken();
  const queryClient = useQueryClient();
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: async () => (await controlFetch(`/projects/${projectId}`, token)) as Project,
  });
  const classifiers = useQuery({
    queryKey: ["classifiers", projectId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<Classifier[]> =>
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/classifiers`,
        token,
      )) as Classifier[],
  });
  const [creating, setCreating] = useState(false);
  if (project.isPending)
    return (
      <main>
        <p className="lede">Loading project…</p>
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
      <ProjectShell project={project.data} active="/classifiers">
        <section className="signal">
          <div className="panel-head">
            <div>
              <p className="eyebrow">CLASSIFIERS / ONTOLOGY V1</p>
              <h2>Every classifier ships with the permanent UNKNOWN fallback.</h2>
            </div>
            <button onClick={() => setCreating(true)}>+ New classifier</button>
          </div>
          {classifiers.isPending && <p className="lede">Loading classifiers…</p>}
          {classifiers.data?.length === 0 && (
            <p className="lede">No classifiers yet. Create the first one.</p>
          )}
          <div className="card-grid">
            {classifiers.data?.map((classifier) => (
              <article key={classifier.id} className="project-card">
                <p className="status">
                  <i /> v1
                </p>
                <h3>{classifier.name}</h3>
                <p>
                  {classifier.classes.length} classes +{" "}
                  <span className="chip locked">UNKNOWN — locked</span>
                </p>
                <Link to={`/projects/${projectId}/classifiers/${classifier.id}`}>
                  Open classifier →
                </Link>
              </article>
            ))}
          </div>
        </section>
      </ProjectShell>
      {creating && project.data && (
        <CreateClassifierModal
          project={project.data}
          token={token}
          onClose={() => setCreating(false)}
          onCreated={() => {
            setCreating(false);
            void queryClient.invalidateQueries({ queryKey: ["classifiers", projectId] });
          }}
        />
      )}
    </main>
  );
}

const classifierSchema = z.object({
  name: z.string().trim().min(2, "Name must be 2–200 characters").max(200),
  classes: z
    .string()
    .trim()
    .min(3, "At least one class is required")
    .refine(
      (value) => value.split("\n").every((line) => /^[a-z][a-z0-9_]*$/.test(line.trim())),
      "Each line must be a lowercase snake_case class name",
    ),
});
type ClassifierForm = z.infer<typeof classifierSchema>;

function CreateClassifierModal({
  project,
  token,
  onClose,
  onCreated,
}: {
  project: Project;
  token: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ClassifierForm>({ resolver: zodResolver(classifierSchema) });
  const [serverError, setServerError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: async (form: ClassifierForm) => {
      const classes = form.classes
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((canonical) => ({
          canonical_name: canonical,
          display_name: canonical.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase()),
        }));
      return controlFetch(
        `/workspaces/${project.workspace_id}/projects/${project.id}/classifiers`,
        token,
        {
          method: "POST",
          body: JSON.stringify({ name: form.name, classes, unknown_fallback: true }),
        },
      );
    },
    onSuccess: onCreated,
    onError: (error: Error) => setServerError(error.message),
  });
  return (
    <div className="modal-backdrop" role="dialog" aria-label="Create classifier">
      <form className="modal" onSubmit={handleSubmit((form) => create.mutate(form))}>
        <p className="eyebrow">NEW CLASSIFIER / {project.name.toUpperCase()}</p>
        <h2>Create a classifier</h2>
        <label>
          Name
          <input {...register("name")} placeholder="Support intent" />
          {errors.name && <span className="field-error">{errors.name.message}</span>}
        </label>
        <label>
          Classes <span className="muted">(one lowercase snake_case name per line)</span>
          <textarea {...register("classes")} rows={5} placeholder={"billing\nrefund\ndelivery"} />
          {errors.classes && <span className="field-error">{errors.classes.message}</span>}
        </label>
        <p className="muted">
          The UNKNOWN fallback is added automatically and can never be removed.
        </p>
        {serverError && <p className="field-error">{serverError}</p>}
        <div className="modal-actions">
          <button type="button" className="ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" disabled={isSubmitting || create.isPending}>
            Create classifier
          </button>
        </div>
      </form>
    </div>
  );
}

export function ClassifierDetailPage() {
  const { projectId = "", classifierId = "" } = useParams();
  const token = useToken();
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: async () => (await controlFetch(`/projects/${projectId}`, token)) as Project,
  });
  const classifier = useQuery({
    queryKey: ["classifier", projectId, classifierId],
    enabled: project.isSuccess,
    queryFn: async (): Promise<Classifier> =>
      (await controlFetch(
        `/workspaces/${project.data!.workspace_id}/projects/${projectId}/classifiers/${classifierId}`,
        token,
      )) as Classifier,
  });
  if (project.isPending || classifier.isPending)
    return (
      <main>
        <p className="lede">Loading classifier…</p>
      </main>
    );
  if (!project.data || !classifier.data)
    return (
      <main>
        <p className="lede">Classifier unavailable.</p>
      </main>
    );
  return (
    <main>
      <ProjectShell project={project.data} active="/classifiers">
        <section className="signal">
          <p className="eyebrow">
            ONTOLOGY VERSION / {classifier.data.active_ontology_version_id.slice(0, 8)}
          </p>
          <h2>{classifier.data.name}</h2>
          <p className="muted">
            Slug <code>{classifier.data.slug}</code> · initial version is immutable; evolution
            arrives in later phases.
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>Canonical name</th>
                <th>Display name</th>
              </tr>
            </thead>
            <tbody>
              {classifier.data.classes.map((cls) => (
                <tr key={cls.canonical_name}>
                  <td>
                    <code>{cls.canonical_name}</code>
                  </td>
                  <td>{cls.display_name}</td>
                </tr>
              ))}
              <tr>
                <td>
                  <code>UNKNOWN</code>
                </td>
                <td>
                  <span className="chip locked">permanent fallback — locked</span>
                </td>
              </tr>
            </tbody>
          </table>
        </section>
      </ProjectShell>
    </main>
  );
}
