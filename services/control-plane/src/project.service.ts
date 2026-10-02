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
import { EngineClient, type EngineOntologyClass } from "./engine.js";
import { IdempotencyService } from "./idempotency.service.js";
import { ROLE_RANK, type Role } from "./workspace.service.js";

export type ControlProject = {
  id: string;
  workspace_id: string;
  engine_project_id: string;
  slug: string;
  name: string;
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
    private readonly idempotency: IdempotencyService,
  ) {}

  async create(
    principal: Principal,
    workspaceId: string,
    name: string,
    description: string,
    idempotencyKey?: string,
  ): Promise<ControlProject> {
    await this.requireRole(principal, workspaceId, "admin");
    if (idempotencyKey) {
      const replayed = await this.idempotency.replay<ControlProject>(workspaceId, idempotencyKey);
      if (replayed) return replayed;
    }
    const engineProject = await this.engine.createProject(name, description);
    const base = this.slugify(name);
    try {
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
      if (idempotencyKey) await this.idempotency.remember(workspaceId, idempotencyKey, project);
      return project;
    } catch (error) {
      await this.engine
        .request("PATCH", `/api/v1/projects/${engineProject.id}`, { status: "archived" })
        .catch(() => undefined);
      throw error;
    }
  }

  async list(principal: Principal, workspaceId: string): Promise<ControlProject[]> {
    await this.requireRole(principal, workspaceId, "viewer");
    const result = await this.db.query(
      "SELECT id, workspace_id, engine_project_id, slug, name, created_at FROM control_projects WHERE workspace_id = $1 ORDER BY created_at",
      [workspaceId],
    );
    return result.rows as ControlProject[];
  }

  async get(principal: Principal, workspaceId: string, projectId: string): Promise<ControlProject> {
    await this.requireRole(principal, workspaceId, "viewer");
    return this.byId(workspaceId, projectId);
  }

  /** Resolve a project for portal deep links: membership is checked via join, non-members get 404. */
  async resolve(principal: Principal, projectId: string): Promise<ControlProject> {
    const result = await this.db.query(
      "SELECT p.id, p.workspace_id, p.engine_project_id, p.slug, p.name, p.created_at, p.redaction_enabled, p.retention_days" +
        " FROM control_projects p JOIN control_workspace_memberships m ON m.workspace_id = p.workspace_id AND m.subject = $2" +
        " WHERE p.id = $1",
      [projectId, principal.subject],
    );
    if (!result.rowCount) throw new NotFoundException("Project not found");
    return result.rows[0] as ControlProject;
  }

  async settings(
    principal: Principal,
    workspaceId: string,
    projectId: string,
  ): Promise<ProjectSettings> {
    await this.requireRole(principal, workspaceId, "viewer");
    const project = await this.byId(workspaceId, projectId);
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
    const current = await this.byId(workspaceId, projectId);
    const redaction = patch.redaction_enabled ?? Boolean(current.redaction_enabled);
    const retention = patch.retention_days ?? current.retention_days ?? 90;
    const result = await this.db.query(
      "UPDATE control_projects SET redaction_enabled = $3, retention_days = $4 WHERE id = $1 AND workspace_id = $2" +
        " RETURNING redaction_enabled, retention_days",
      [projectId, workspaceId, redaction, retention],
    );
    const settings = result.rows[0] as ProjectSettings;
    await this.audit.record({
      workspaceId,
      projectId,
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
    const project = await this.byId(workspaceId, projectId);
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
      [projectId, slug],
    );
    if (taken.rowCount)
      throw new BadRequestException("Classifier slug already exists in this project");

    const engineClassifier = await this.engine.createClassifier({
      slug,
      name: input.name.trim(),
      description: input.description,
      classes: input.classes,
    });
    const result = await this.db.query(
      "INSERT INTO control_classifiers (project_id, engine_classifier_id, slug, name)" +
        " VALUES ($1, $2, $3, $4) RETURNING id, project_id, engine_classifier_id, slug, name, created_at",
      [project.id, engineClassifier.id, slug, input.name.trim()],
    );
    await this.audit.record({
      workspaceId,
      projectId,
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
    const project = await this.byId(workspaceId, projectId);
    const mappings = await this.db.query(
      "SELECT id, project_id, engine_classifier_id, slug, name, created_at FROM control_classifiers WHERE project_id = $1 ORDER BY created_at",
      [project.id],
    );
    return Promise.all(
      (mappings.rows as ControlClassifier[]).map(async (row) => {
        const ontology = await this.engine.getOntology(row.engine_classifier_id);
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
    const project = await this.byId(workspaceId, projectId);
    const mapping = await this.db.query(
      "SELECT id, project_id, engine_classifier_id, slug, name, created_at FROM control_classifiers WHERE id = $1 AND project_id = $2",
      [classifierId, project.id],
    );
    if (!mapping.rowCount) throw new NotFoundException("Classifier not found");
    const row = mapping.rows[0] as ControlClassifier;
    const ontology = await this.engine.getOntology(row.engine_classifier_id);
    return { ...row, active_ontology_version_id: ontology.id, classes: ontology.classes };
  }

  /** Public role gate for adjacent controllers (providers, etc.). */
  async assertManager(principal: Principal, workspaceId: string, projectId: string): Promise<void> {
    await this.requireRole(principal, workspaceId, "admin");
    await this.byId(workspaceId, projectId);
  }

  async createKey(
    principal: Principal,
    workspaceId: string,
    projectId: string,
    scopes: ApiKeyScope[],
  ) {
    await this.requireRole(principal, workspaceId, "admin");
    await this.byId(workspaceId, projectId);
    const created = await this.apiKeys.create(workspaceId, projectId, scopes);
    await this.audit.record({
      workspaceId,
      projectId,
      actor: principal.subject,
      action: "api_key.created",
      target: `key:${created.row.prefix}…`,
    });
    return created;
  }

  async listKeys(principal: Principal, workspaceId: string, projectId: string) {
    await this.requireRole(principal, workspaceId, "viewer");
    await this.byId(workspaceId, projectId);
    return this.apiKeys.list(projectId);
  }

  async revokeKey(principal: Principal, workspaceId: string, projectId: string, keyId: string) {
    await this.requireRole(principal, workspaceId, "admin");
    await this.byId(workspaceId, projectId);
    const revoked = await this.apiKeys.revoke(projectId, keyId);
    await this.audit.record({
      workspaceId,
      projectId,
      actor: principal.subject,
      action: "api_key.revoked",
      target: `key:${revoked.prefix}…`,
    });
    return revoked;
  }

  private async byId(workspaceId: string, projectId: string): Promise<ControlProject> {
    const result = await this.db.query(
      "SELECT id, workspace_id, engine_project_id, slug, name, created_at, redaction_enabled, retention_days FROM control_projects WHERE id = $1 AND workspace_id = $2",
      [projectId, workspaceId],
    );
    if (!result.rowCount) throw new NotFoundException("Project not found");
    return result.rows[0] as ControlProject;
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
