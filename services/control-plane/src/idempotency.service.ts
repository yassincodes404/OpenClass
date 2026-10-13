import { createHash } from "node:crypto";
import { Inject, Injectable } from "@nestjs/common";
import type { Pool } from "pg";
import { CONTROL_DB } from "./db.js";

const TTL_HOURS = Number(process.env.IDEMPOTENCY_TTL_HOURS ?? 24);

/**
 * Idempotency-Key support for control-plane mutations: a repeated key replays
 * the stored response instead of writing twice.
 */
@Injectable()
export class IdempotencyService {
  constructor(@Inject(CONTROL_DB) private readonly db: Pool) {}

  async replay<T>(workspaceId: string, key: string): Promise<T | null> {
    const result = await this.db.query(
      "SELECT response FROM control_idempotency_keys WHERE key = $1 AND workspace_id = $2 AND expires_at > now()",
      [key, workspaceId],
    );
    return (result.rows[0]?.response as T) ?? null;
  }

  async remember(workspaceId: string, key: string, response: unknown): Promise<void> {
    const serialized = JSON.stringify(response ?? null);
    await this.db.query(
      "INSERT INTO control_idempotency_keys (key, workspace_id, response_hash, response, expires_at)" +
        " VALUES ($1, $2, $3, $4::jsonb, now() + ($5 || ' hours')::interval)" +
        " ON CONFLICT (key, workspace_id) DO NOTHING",
      [
        key,
        workspaceId,
        createHash("sha256").update(serialized).digest("hex"),
        serialized,
        TTL_HOURS,
      ],
    );
  }
}
