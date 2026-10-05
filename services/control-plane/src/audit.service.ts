import { Inject, Injectable } from "@nestjs/common";
import type { Pool } from "pg";
import { CONTROL_DB } from "./db.js";

export type AuditEvent = {
  id: string;
  workspace_id: string;
  project_id: string | null;
  actor: string;
  action: string;
  target: string;
  created_at: Date;
};

export type AuditPage = { items: AuditEvent[]; next_cursor: string | null };

/** Append-only audit trail. There is intentionally no update or delete path. */
@Injectable()
export class AuditService {
  constructor(@Inject(CONTROL_DB) private readonly db: Pool) {}

  async record(input: { workspaceId: string; projectId?: string | null; actor: string; action: string; target: string }): Promise<void> {
    await this.db.query(
      "INSERT INTO control_audit_events (workspace_id, project_id, actor, action, target) VALUES ($1, $2, $3, $4, $5)",
      [input.workspaceId, input.projectId ?? null, input.actor.slice(0, 200), input.action.slice(0, 80), input.target.slice(0, 300)],
    );
  }

  async list(workspaceId: string, options: { limit?: number; cursor?: string; action?: string } = {}): Promise<AuditPage> {
    const limit = Math.min(Math.max(options.limit ?? 50, 1), 100);
    const params: unknown[] = [workspaceId, limit];
    let filter = "";
    if (options.action) {
      params.push(options.action);
      filter = ` AND action = $${params.length}`;
    }
    if (options.cursor) {
      params.push(new Date(options.cursor));
      filter += ` AND created_at < $${params.length}`;
    }
    const result = await this.db.query(
      `SELECT id, workspace_id, project_id, actor, action, target, created_at FROM control_audit_events` +
        ` WHERE workspace_id = $1${filter} ORDER BY created_at DESC LIMIT $2`,
      params,
    );
    const items = result.rows as AuditEvent[];
    const next_cursor = items.length === limit && items.length > 0 ? items[items.length - 1].created_at.toISOString() : null;
    return { items, next_cursor };
  }
}
