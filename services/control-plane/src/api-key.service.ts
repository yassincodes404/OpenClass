import { createHash, randomBytes } from "node:crypto";
import { ForbiddenException, Inject, Injectable, NotFoundException } from "@nestjs/common";
import type { Pool } from "pg";
import { CONTROL_DB } from "./db.js";

export const API_KEY_SCOPES = ["ingest", "classify", "read", "admin"] as const;
export type ApiKeyScope = (typeof API_KEY_SCOPES)[number];

export type ApiKeyRow = {
  id: string;
  workspace_id: string;
  project_id: string;
  prefix: string;
  scopes: ApiKeyScope[];
  created_at: Date;
  revoked_at: Date | null;
};

export type VerifiedKey = { workspaceId: string; projectId: string; scopes: ApiKeyScope[] };

export function hashKey(raw: string): string {
  return createHash("sha256").update(raw).digest("hex");
}

/** Scoped project API keys. The raw value is returned exactly once and only the hash is stored. */
@Injectable()
export class ApiKeyService {
  constructor(@Inject(CONTROL_DB) private readonly db: Pool) {}

  async create(
    workspaceId: string,
    projectId: string,
    scopes: ApiKeyScope[],
  ): Promise<{ key: string; row: ApiKeyRow }> {
    const secret = randomBytes(24).toString("hex");
    const raw = `oc_dev_${secret}`;
    const prefix = raw.slice(0, 14);
    const result = await this.db.query(
      "INSERT INTO control_api_keys (workspace_id, project_id, key_hash, prefix, scopes)" +
        " VALUES ($1, $2, $3, $4, $5) RETURNING id, workspace_id, project_id, prefix, scopes, created_at, revoked_at",
      [workspaceId, projectId, hashKey(raw), prefix, scopes],
    );
    return { key: raw, row: result.rows[0] as ApiKeyRow };
  }

  async list(projectId: string): Promise<ApiKeyRow[]> {
    const result = await this.db.query(
      "SELECT id, workspace_id, project_id, prefix, scopes, created_at, revoked_at FROM control_api_keys" +
        " WHERE project_id = $1 ORDER BY created_at DESC",
      [projectId],
    );
    return result.rows as ApiKeyRow[];
  }

  async revoke(projectId: string, keyId: string): Promise<ApiKeyRow> {
    const result = await this.db.query(
      "UPDATE control_api_keys SET revoked_at = now() WHERE id = $1 AND project_id = $2 AND revoked_at IS NULL" +
        " RETURNING id, workspace_id, project_id, prefix, scopes, created_at, revoked_at",
      [keyId, projectId],
    );
    if (!result.rowCount) throw new NotFoundException("API key not found");
    return result.rows[0] as ApiKeyRow;
  }

  /** Verify a raw key for engine-proxy use. Never returns the hash. */
  async verify(raw: string, requiredScope?: ApiKeyScope): Promise<VerifiedKey> {
    const result = await this.db.query(
      "SELECT workspace_id, project_id, scopes, revoked_at FROM control_api_keys WHERE key_hash = $1",
      [hashKey(raw)],
    );
    const row = result.rows[0] as
      | { workspace_id: string; project_id: string; scopes: ApiKeyScope[]; revoked_at: Date | null }
      | undefined;
    if (!row || row.revoked_at) throw new ForbiddenException("API key is invalid or revoked");
    if (requiredScope && !row.scopes.includes(requiredScope)) {
      throw new ForbiddenException(`API key is missing the '${requiredScope}' scope`);
    }
    return { workspaceId: row.workspace_id, projectId: row.project_id, scopes: row.scopes };
  }
}
