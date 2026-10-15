import { BadRequestException, Inject, Injectable } from "@nestjs/common";
import type { Pool } from "pg";
import { z } from "zod";
import { CONTROL_DB } from "./db.js";
import { requestContext } from "./request-context.js";

export type AuditEvent = {
  id: string;
  workspace_id: string;
  project_id: string | null;
  actor: string;
  action: string;
  target: string;
  created_at: Date;
  correlation_id?: string | null;
};

export type AuditPage = { items: AuditEvent[]; next_cursor: string | null };
export type AuditListOptions = { limit?: number; cursor?: string; action?: string };

const cursorSchema = z
  .object({
    v: z.literal(1),
    at: z.iso.datetime({ precision: 6 }),
    id: z.uuid(),
  })
  .strict();

function decodeCursor(value: string): z.infer<typeof cursorSchema> {
  try {
    if (typeof value !== "string" || value.length > 512 || !/^[A-Za-z0-9_-]+$/.test(value)) {
      throw new Error("Invalid cursor encoding");
    }
    const decoded = Buffer.from(value, "base64url");
    if (decoded.toString("base64url") !== value) throw new Error("Noncanonical cursor");
    return cursorSchema.parse(JSON.parse(decoded.toString("utf8")));
  } catch {
    throw new BadRequestException("Invalid audit cursor; restart pagination without a cursor");
  }
}

/** Append-only audit trail. There is intentionally no update or delete path. */
@Injectable()
export class AuditService {
  constructor(@Inject(CONTROL_DB) private readonly db: Pool) {}

  async record(input: {
    workspaceId: string;
    projectId?: string | null;
    actor: string;
    action: string;
    target: string;
  }): Promise<void> {
    await this.db.query(
      "INSERT INTO control_audit_events (workspace_id, project_id, actor, action, target, correlation_id) VALUES ($1, $2, $3, $4, $5, $6)",
      [
        input.workspaceId,
        input.projectId ?? null,
        input.actor.slice(0, 200),
        input.action.slice(0, 80),
        input.target.slice(0, 300),
        requestContext.getStore()?.correlationId ?? null,
      ],
    );
  }

  async list(workspaceId: string, options: AuditListOptions = {}): Promise<AuditPage> {
    const limit = options.limit ?? 50;
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
      throw new BadRequestException("limit must be an integer between 1 and 100");
    }
    if (
      options.action !== undefined &&
      (typeof options.action !== "string" ||
        options.action.length < 1 ||
        options.action.length > 80)
    ) {
      throw new BadRequestException("action must contain 1–80 characters");
    }
    const params: unknown[] = [workspaceId, limit];
    let filter = "";
    if (options.action) {
      params.push(options.action);
      filter = ` AND action = $${params.length}`;
    }
    if (options.cursor !== undefined) {
      const cursor = decodeCursor(options.cursor);
      params.push(cursor.at, cursor.id);
      filter += ` AND (created_at, id) < ($${params.length - 1}::timestamptz, $${params.length}::uuid)`;
    }
    const result = await this.db.query(
      `SELECT id, workspace_id, project_id, actor, action, target, created_at, correlation_id,` +
        ` to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS cursor_created_at` +
        ` FROM control_audit_events WHERE workspace_id = $1${filter}` +
        ` ORDER BY created_at DESC, id DESC LIMIT $2`,
      params,
    );
    const rows = result.rows as Array<AuditEvent & { cursor_created_at: string }>;
    const items = rows.map(({ cursor_created_at: _cursor, ...event }) => event);
    const last = rows[rows.length - 1];
    const next_cursor =
      rows.length === limit && last
        ? Buffer.from(JSON.stringify({ v: 1, at: last.cursor_created_at, id: last.id })).toString(
            "base64url",
          )
        : null;
    return { items, next_cursor };
  }
}
