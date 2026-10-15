import {
  ForbiddenException,
  Inject,
  Injectable,
  NotFoundException,
  forwardRef,
} from "@nestjs/common";
import type { Pool, PoolClient, QueryResult } from "pg";
import type { Principal } from "./auth.js";
import { AuditService } from "./audit.service.js";
import { CONTROL_DB, controlTransaction } from "./db.js";

export type Role = "owner" | "admin" | "reviewer" | "analyst" | "developer" | "viewer";
export type MemberRow = { subject: string; role: Role; created_at: Date };
export type WorkspaceRow = { id: string; slug: string; name: string; role?: Role };

const MANAGER_ROLES: readonly Role[] = ["owner", "admin"];

/** Higher rank = more authority; "minimum role" checks use >= comparison. */
export const ROLE_RANK: Record<Role, number> = {
  owner: 5,
  admin: 4,
  reviewer: 3,
  analyst: 2,
  developer: 1,
  viewer: 0,
};

@Injectable()
export class WorkspaceService {
  constructor(
    @Inject(CONTROL_DB) private readonly db: Pool,
    @Inject(forwardRef(() => AuditService)) private readonly audit: AuditService,
  ) {}

  async mine(principal: Principal): Promise<WorkspaceRow[]> {
    const result = await this.db.query(
      "SELECT w.id, w.slug, w.name, m.role FROM control_workspaces w" +
        " JOIN control_workspace_memberships m ON m.workspace_id = w.id" +
        " WHERE m.subject = $1 ORDER BY w.created_at",
      [principal.subject],
    );
    return result.rows as WorkspaceRow[];
  }

  async create(principal: Principal, name: string): Promise<WorkspaceRow> {
    const base = this.slugify(name);
    return controlTransaction(this.db, async (client) => {
      const slug = await this.uniqueSlug(client, base);
      const workspace = await client.query(
        "INSERT INTO control_workspaces (slug, name) VALUES ($1, $2) RETURNING id, slug, name",
        [slug, name.trim()],
      );
      await client.query(
        "INSERT INTO control_workspace_memberships (workspace_id, subject, role) VALUES ($1, $2, 'owner')",
        [workspace.rows[0].id, principal.subject],
      );
      const row = { ...workspace.rows[0], role: "owner" } as WorkspaceRow;
      await this.audit.record({
        workspaceId: row.id,
        actor: principal.subject,
        action: "workspace.created",
        target: `workspace:${row.slug}`,
      });
      return row;
    });
  }

  async members(principal: Principal, workspaceId: string): Promise<MemberRow[]> {
    await this.requireMembership(principal, workspaceId);
    const result = await this.db.query(
      "SELECT subject, role, created_at FROM control_workspace_memberships WHERE workspace_id = $1 ORDER BY created_at",
      [workspaceId],
    );
    return result.rows as MemberRow[];
  }

  async invite(
    principal: Principal,
    workspaceId: string,
    subject: string,
    role: Role,
  ): Promise<{ subject: string; role: Role }> {
    await this.requireRole(principal, workspaceId, MANAGER_ROLES);
    const result = await this.db.query(
      "INSERT INTO control_workspace_memberships (workspace_id, subject, role) VALUES ($1, $2, $3)" +
        " ON CONFLICT (workspace_id, subject) DO UPDATE SET role = EXCLUDED.role RETURNING subject, role",
      [workspaceId, subject, role],
    );
    await this.audit.record({
      workspaceId,
      actor: principal.subject,
      action: "member.invited",
      target: `member:${subject}:${role}`,
    });
    return result.rows[0];
  }

  private async requireMembership(principal: Principal, workspaceId: string): Promise<Role> {
    const result = await this.roleOf(principal, workspaceId);
    if (!result.rowCount) throw new NotFoundException("Workspace not found");
    return result.rows[0].role as Role;
  }

  private async requireRole(
    principal: Principal,
    workspaceId: string,
    allowed: readonly Role[],
  ): Promise<Role> {
    const role = await this.requireMembership(principal, workspaceId);
    if (!allowed.includes(role))
      throw new ForbiddenException("Workspace role cannot manage members");
    return role;
  }

  private roleOf(principal: Principal, workspaceId: string): Promise<QueryResult<{ role: Role }>> {
    return this.db.query(
      "SELECT role FROM control_workspace_memberships WHERE workspace_id = $1 AND subject = $2",
      [workspaceId, principal.subject],
    );
  }

  private slugify(name: string): string {
    return (
      name
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .slice(0, 80) || "workspace"
    );
  }

  private async uniqueSlug(client: PoolClient, base: string): Promise<string> {
    const taken = await client.query(
      "SELECT slug FROM control_workspaces WHERE slug = $1 OR slug LIKE $2",
      [base, `${base}-%`],
    );
    if (!taken.rows.some((row: { slug: string }) => row.slug === base)) return base;
    let suffix = 2;
    while (taken.rows.some((row: { slug: string }) => row.slug === `${base}-${suffix}`))
      suffix += 1;
    return `${base}-${suffix}`;
  }
}
