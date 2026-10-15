import {
  BadRequestException,
  ForbiddenException,
  Inject,
  Injectable,
  NotFoundException,
} from "@nestjs/common";
import type { Pool } from "pg";
import { ApiKeyService, type ApiKeyScope } from "./api-key.service.js";
import { AuditService } from "./audit.service.js";
import type { Principal } from "./auth.js";
import { CONTROL_DB } from "./db.js";
import { EngineClient, type EngineOntologyClass, type EngineProject } from "./engine.js";
import { ROLE_RANK, type Role } from "./workspace.service.js";

export type ControlProject = {
  id: string;
  workspace_id: string;
  engine_project_id: string;
  slug: string;
  name: string;
  description?: string;
  created_at: Date;
  redaction_enabled?: boolean;
  retention_days?: number;
};
export type ControlClassifier = {
  id: string;
  project_id: string;
  engine_classifier_id: string;
  slug: string;
  name: string;
  created_at: Date;
};
export type ClassifierDetail = ControlClassifier & {
  active_ontology_version_id: string;
  classes: EngineOntologyClass[];
};
export type ProjectSettings = { redaction_enabled: boolean; retention_days: number };

const RESERVED_CLASS_NAMES = new Set(["unknown", "other"]);

/**
 * Projects live in the engine (canonical decision data) while the control plane
 * owns the workspace mapping and scoped API keys. Classifiers are mapped per
 * project because the engine keeps them classifier-scoped.
 */
@Injectable()
export class ProjectService {
  constructor(
    @Inject(CONTROL_DB) private readonly db: Pool,
    private readonly engine: EngineClient,
    private readonly apiKeys: ApiKeyService,
    private readonly audit: AuditService,
  ) {}

  async create(
    principal: Principal,
    workspaceId: string,
    name: string,
    description: string,
  ): Promise<ControlProject> {
    await this.requireRole(principal, workspaceId, "admin");
    const engineProject = await this.engine.createProject(name, description, {
      workspaceId,
      actor: principal.subject,
    });
    const base = this.slugify(name);
    // The request interceptor commits the mapping, audit, and receipt together.
    // Never archive a successful remote creation on a local failure: a retry
    // must reconcile with the engine's idempotent response, not an archived id.
    const slug = await this.uniqueSlug(workspaceId, base);
    const result = await this.db.query(
      "INSERT INTO control_projects (workspace_id, engine_project_id, slug, name)" +
        " VALUES ($1, $2, $3, $4) RETURNING id, workspace_id, engine_project_id, slug, name, created_at, redaction_enabled, retention_days",
      [workspaceId, engineProject.id, slug, name.trim()],
    );
    const project = result.rows[0] as ControlProject;
    await this.audit.record({
      workspaceId,
      projectId: project.id,
      actor: principal.subject,
      action: "project.created",
      target: `project:${project.slug}`,
    });
    return project;
  }

  async list(
    principal: Principal | { sub: string; email?: string },
    workspaceId: string,
  ): Promise<ControlProject[]> {
    const normalized = this.normalizePrincipal(principal);
    await this.requireRole(normalized, workspaceId, "viewer");
    const result = await this.db.query(
      "SELECT id, workspace_id, engine_project_id, slug, name, created_at FROM control_projects WHERE workspace_id = $1 ORDER BY created_at",
      [workspaceId],
    );
    const rows = [...(result.rows as ControlProject[])];

    if (typeof this.engine?.listProjects === "function") {
      try {
        const engineProjects = await this.engine.listProjects({
          workspaceId,
          actor: normalized.subject,
        });
        if (Array.isArray(engineProjects)) {
          for (const ep of engineProjects) {
            if (!ep?.id || !ep?.slug) continue;
            if (ep.workspace_id !== workspaceId) continue;
            const claimed = await this.db.query(
              "SELECT workspace_id FROM control_projects WHERE engine_project_id = $1 OR slug = $2",
              [ep.id, ep.slug],
            );
            if (
              claimed.rows?.some(
                (row: { workspace_id?: string }) =>
                  row.workspace_id && row.workspace_id !== workspaceId,
              )
            ) {
              continue;
            }
            const existing = rows.find(
              (row) => row.engine_project_id === ep.id || row.slug === ep.slug,
            );
            if (!existing) {
              const base = this.slugify(ep.slug || ep.name);
              const slug = await this.uniqueSlug(workspaceId, base);
              const inserted = await this.db.query(
                "INSERT INTO control_projects (workspace_id, engine_project_id, slug, name)" +
                  " VALUES ($1, $2, $3, $4)" +
                  " ON CONFLICT (workspace_id, slug) DO UPDATE SET engine_project_id = EXCLUDED.engine_project_id" +
                  " RETURNING id, workspace_id, engine_project_id, slug, name, created_at, redaction_enabled, retention_days",
                [workspaceId, ep.id, slug, (ep.name || ep.slug).trim()],
              );
              if (inserted.rows?.[0]) {
                rows.push(inserted.rows[0] as ControlProject);
              }
            } else if (!existing.engine_project_id) {
              const updated = await this.db.query(
                "UPDATE control_projects SET engine_project_id = $3 WHERE id = $1 AND workspace_id = $2" +
                  " RETURNING id, workspace_id, engine_project_id, slug, name, created_at, redaction_enabled, retention_days",
                [existing.id, workspaceId, ep.id],
              );
              if (updated.rows?.[0]) {
                Object.assign(existing, updated.rows[0]);
              } else {
                existing.engine_project_id = ep.id;
              }
            }
          }
        }
      } catch {
        // Best-effort reconciliation: keep control_projects rows if engine is offline or unmocked.
      }
    }

    return rows;
  }

  async listProjects(
    first: Principal | { sub: string; email?: string } | string,
    second: Principal | { sub: string; email?: string } | string,
  ): Promise<ControlProject[]> {
    if (typeof first === "string") {
      return this.list(second as Principal | { sub: string; email?: string }, first);
    }
    return this.list(first, second as string);
  }

  async get(
    principal: Principal | { sub: string; email?: string },
    workspaceId: string,
    projectId: string,
  ): Promise<ControlProject> {
    const normalized = this.normalizePrincipal(principal);
    await this.requireRole(normalized, workspaceId, "viewer");
    return this.byId(workspaceId, projectId, normalized);
  }

  async getProjectForWorkspace(
    first: Principal | { sub: string; email?: string } | string,
    second: string,
    third: Principal | { sub: string; email?: string } | string,
  ): Promise<ControlProject> {
    if (typeof first === "string") {
      const workspaceId = first;
      const projectId = second;
      const normalized = this.normalizePrincipal(
        third as Principal | { sub: string; email?: string },
      );
      await this.requireRole(normalized, workspaceId, "viewer");
      return this.byId(workspaceId, projectId, normalized);
    }
    const normalized = this.normalizePrincipal(first);
    const workspaceId = second;
    const projectId = third as string;
    await this.requireRole(normalized, workspaceId, "viewer");
    return this.byId(workspaceId, projectId, normalized);
  }

  /** Resolve a project for portal deep links: membership is checked via join, non-members get 404. */
  async resolve(
    principal: Principal | { sub: string; email?: string },
    projectId: string,
  ): Promise<ControlProject> {
    const normalized = this.normalizePrincipal(principal);
    const result = await this.db.query(
      "SELECT p.id, p.workspace_id, p.engine_project_id, p.slug, p.name, p.created_at, p.redaction_enabled, p.retention_days" +
        " FROM control_projects p JOIN control_workspace_memberships m ON m.workspace_id = p.workspace_id AND m.subject = $2" +
        " WHERE (p.id::text = $1 OR p.engine_project_id::text = $1 OR p.slug = $1)",
      [projectId, normalized.subject],
    );
    if (!result.rowCount) throw new NotFoundException("Project not found");
    const row = result.rows[0] as ControlProject;
    if (!row.engine_project_id) {
      return this.syncMissingEngineProject(row, row.workspace_id, normalized.subject);
    }
    return row;
  }

  async settings(
    principal: Principal,
    workspaceId: string,
    projectId: string,
  ): Promise<ProjectSettings> {
    await this.requireRole(principal, workspaceId, "viewer");
    const project = await this.byId(workspaceId, projectId, principal);
    return {
      redaction_enabled: Boolean(project.redaction_enabled),
      retention_days: project.retention_days ?? 90,
    };
  }

  async updateSettings(
    principal: Principal,
    workspaceId: string,
    projectId: string,
    patch: Partial<ProjectSettings>,
  ): Promise<ProjectSettings> {
    await this.requireRole(principal, workspaceId, "admin");
    const current = await this.byId(workspaceId, projectId, principal);
    const redaction = patch.redaction_enabled ?? Boolean(current.redaction_enabled);
    const retention = patch.retention_days ?? current.retention_days ?? 90;
    const result = await this.db.query(
      "UPDATE control_projects SET redaction_enabled = $3, retention_days = $4 WHERE id = $1 AND workspace_id = $2" +
        " RETURNING redaction_enabled, retention_days",
      [current.id, workspaceId, redaction, retention],
    );
    const settings = result.rows[0] as ProjectSettings;
    await this.audit.record({
      workspaceId,
      projectId: current.id,
      actor: principal.subject,
      action: "project.settings_updated",
      target: `settings:redaction=${settings.redaction_enabled},retention=${settings.retention_days}d`,
    });
    return settings;
  }

  async createClassifier(
    principal: Principal,
    workspaceId: string,
    projectId: string,
    input: {
      name: string;
      slug?: string;
      description: string;
      classes: EngineOntologyClass[];
      unknownFallback: boolean;
    },
  ): Promise<ClassifierDetail> {
    await this.requireRole(principal, workspaceId, "admin");
    const project = await this.byId(workspaceId, projectId, principal);
    if (!input.unknownFallback)
      throw new BadRequestException("UNKNOWN fallback is required and permanent");
    if (input.classes.length === 0) throw new BadRequestException("At least one class is required");
    for (const cls of input.classes) {
      if (RESERVED_CLASS_NAMES.has(cls.canonical_name.toLowerCase())) {
        throw new BadRequestException(
          "UNKNOWN is a permanent fallback state, not a class; remove reserved names",
        );
      }
    }
    const slug = input.slug?.trim() || this.slugify(input.name);
    if (!/^[a-z][a-z0-9-]{0,79}$/.test(slug))
      throw new BadRequestException("Classifier slug must be lowercase kebab-case");
    const taken = await this.db.query(
      "SELECT 1 FROM control_classifiers WHERE project_id = $1 AND slug = $2",
      [project.id, slug],
    );
    if (taken.rowCount)
      throw new BadRequestException("Classifier slug already exists in this project");

    const engineClassifier = await this.engine.createClassifier(
      {
        slug,
        name: input.name.trim(),
        description: input.description,
        classes: input.classes,
      },
      { workspaceId, actor: principal.subject },
    );
    const result = await this.db.query(
      "INSERT INTO control_classifiers (project_id, engine_classifier_id, slug, name)" +
        " VALUES ($1, $2, $3, $4) RETURNING id, project_id, engine_classifier_id, slug, name, created_at",
      [project.id, engineClassifier.id, slug, input.name.trim()],
    );
    await this.audit.record({
      workspaceId,
      projectId: project.id,
      actor: principal.subject,
      action: "classifier.created",
      target: `classifier:${slug}`,
    });
    return {
      ...(result.rows[0] as ControlClassifier),
      active_ontology_version_id: engineClassifier.active_ontology_version_id,
      classes: input.classes,
    };
  }

  async listClassifiers(
    principal: Principal,
    workspaceId: string,
    projectId: string,
  ): Promise<ClassifierDetail[]> {
    await this.requireRole(principal, workspaceId, "viewer");
    const project = await this.byId(workspaceId, projectId, principal);
    const mappings = await this.db.query(
      "SELECT id, project_id, engine_classifier_id, slug, name, created_at FROM control_classifiers WHERE project_id = $1 ORDER BY created_at",
      [project.id],
    );
    return Promise.all(
      (mappings.rows as ControlClassifier[]).map(async (row) => {
        const ontology = await this.engine.getOntology(row.engine_classifier_id, {
          workspaceId,
          actor: principal.subject,
        });
        return {
          ...row,
          active_ontology_version_id: ontology.id,
          classes: ontology.classes,
        };
      }),
    );
  }

  async getClassifier(
    principal: Principal,
    workspaceId: string,
    projectId: string,
    classifierId: string,
  ): Promise<ClassifierDetail> {
    await this.requireRole(principal, workspaceId, "viewer");
    const project = await this.byId(workspaceId, projectId, principal);
    const mapping = await this.db.query(
      "SELECT id, project_id, engine_classifier_id, slug, name, created_at FROM control_classifiers WHERE id = $1 AND project_id = $2",
      [classifierId, project.id],
    );
    if (!mapping.rowCount) throw new NotFoundException("Classifier not found");
    const row = mapping.rows[0] as ControlClassifier;
    const ontology = await this.engine.getOntology(row.engine_classifier_id, {
      workspaceId,
      actor: principal.subject,
    });
    return { ...row, active_ontology_version_id: ontology.id, classes: ontology.classes };
  }

  /** Public role gate for adjacent controllers (providers, etc.). */
  async assertManager(principal: Principal, workspaceId: string, projectId: string): Promise<void> {
    await this.requireRole(principal, workspaceId, "admin");
    await this.byId(workspaceId, projectId, principal);
  }

  async createKey(
    principal: Principal,
    workspaceId: string,
    projectId: string,
    scopes: ApiKeyScope[],
  ) {
    await this.requireRole(principal, workspaceId, "admin");
    const project = await this.byId(workspaceId, projectId, principal);
    const created = await this.apiKeys.create(workspaceId, project.id, scopes);
    await this.audit.record({
      workspaceId,
      projectId: project.id,
      actor: principal.subject,
      action: "api_key.created",
      target: `key:${created.row.prefix}…`,
    });
    return created;
  }

  async listKeys(principal: Principal, workspaceId: string, projectId: string) {
    await this.requireRole(principal, workspaceId, "viewer");
    const project = await this.byId(workspaceId, projectId, principal);
    return this.apiKeys.list(project.id);
  }

  async revokeKey(principal: Principal, workspaceId: string, projectId: string, keyId: string) {
    await this.requireRole(principal, workspaceId, "admin");
    const project = await this.byId(workspaceId, projectId, principal);
    const revoked = await this.apiKeys.revoke(project.id, keyId);
    await this.audit.record({
      workspaceId,
      projectId: project.id,
      actor: principal.subject,
      action: "api_key.revoked",
      target: `key:${revoked.prefix}…`,
    });
    return revoked;
  }

  async resolveEngineProjectId(
    principal: Principal | { sub: string; email?: string },
    workspaceId: string,
    projectId: string,
  ): Promise<string> {
    const project = await this.get(principal, workspaceId, projectId);
    return project.engine_project_id;
  }

  private async byId(
    workspaceId: string,
    projectId: string,
    principal?: Principal,
  ): Promise<ControlProject> {
    const result = await this.db.query(
      "SELECT id, workspace_id, engine_project_id, slug, name, created_at, redaction_enabled, retention_days FROM control_projects WHERE (id::text = $1 OR engine_project_id::text = $1 OR slug = $1) AND workspace_id = $2",
      [projectId, workspaceId],
    );
    if (!result.rowCount) throw new NotFoundException("Project not found");
    const row = result.rows[0] as ControlProject;
    if (!row.engine_project_id) {
      return this.syncMissingEngineProject(row, workspaceId, principal?.subject);
    }
    return row;
  }

  private async syncMissingEngineProject(
    row: ControlProject,
    workspaceId: string,
    actor?: string,
  ): Promise<ControlProject> {
    let synced: EngineProject | undefined;
    const identifier = row.slug || row.id;
    if (typeof this.engine?.getProject === "function") {
      try {
        const existing = await this.engine.getProject(identifier, { workspaceId, actor });
        if (existing && (!existing.workspace_id || existing.workspace_id === workspaceId)) {
          synced = existing;
        }
      } catch (err) {
        if (err instanceof NotFoundException && typeof this.engine?.claimProject === "function") {
          synced = await this.engine
            .claimProject(identifier, { workspaceId, actor })
            .catch(() => undefined);
        }
      }
    }
    if (!synced && typeof this.engine?.createProject === "function") {
      synced = await this.engine
        .createProject(row.name || row.slug, row.description ?? "", { workspaceId, actor })
        .catch(() => undefined);
    }
    if (synced?.id) {
      const updated = await this.db.query(
        "UPDATE control_projects SET engine_project_id = $3 WHERE id = $1 AND workspace_id = $2" +
          " RETURNING id, workspace_id, engine_project_id, slug, name, created_at, redaction_enabled, retention_days",
        [row.id, workspaceId, synced.id],
      );
      if (updated.rowCount && updated.rows[0]) {
        return updated.rows[0] as ControlProject;
      }
      row.engine_project_id = synced.id;
    }
    return row;
  }

  private normalizePrincipal(
    principal: Principal | { sub?: string; subject?: string; email?: string },
  ): Principal {
    const candidate = principal as { subject?: unknown; sub?: unknown; email?: string };
    const subject =
      typeof candidate.subject === "string"
        ? candidate.subject
        : typeof candidate.sub === "string"
          ? candidate.sub
          : "";
    return { subject, email: candidate.email };
  }

  private async requireRole(
    principal: Principal,
    workspaceId: string,
    minimum: Role,
  ): Promise<Role> {
    const result = await this.db.query(
      "SELECT role FROM control_workspace_memberships WHERE workspace_id = $1 AND subject = $2",
      [workspaceId, principal.subject],
    );
    if (!result.rowCount) throw new NotFoundException("Workspace not found");
    const role = result.rows[0].role as Role;
    if (ROLE_RANK[role] < ROLE_RANK[minimum])
      throw new ForbiddenException("Workspace role cannot manage projects");
    return role;
  }

  private slugify(name: string): string {
    return (
      name
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .slice(0, 80) || "project"
    );
  }

  private async uniqueSlug(workspaceId: string, base: string): Promise<string> {
    const taken = await this.db.query(
      "SELECT slug FROM control_projects WHERE workspace_id = $1 AND (slug = $2 OR slug LIKE $3)",
      [workspaceId, base, `${base}-%`],
    );
    if (!taken.rows.some((row: { slug: string }) => row.slug === base)) return base;
    let suffix = 2;
    while (taken.rows.some((row: { slug: string }) => row.slug === `${base}-${suffix}`))
      suffix += 1;
    return `${base}-${suffix}`;
  }
}
