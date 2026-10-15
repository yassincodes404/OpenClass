import { createHash } from "node:crypto";
import { BadRequestException, ConflictException, Inject, Injectable } from "@nestjs/common";
import type { Pool } from "pg";
import { CONTROL_DB, controlTransaction } from "./db.js";

export type RequestIdentity = {
  method: string;
  path: string;
  body: unknown;
  /** Authenticated caller and current authorization, never bearer credentials. */
  authorization: unknown;
};
export type StoredResponse<T> = { status: number; body: T };

/** JSON object ordering is immaterial; array ordering and absent/null remain distinct. */
export function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.entries(value)
      .filter(([, item]) => item !== undefined)
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value ?? null);
}

export function requestHash(identity: RequestIdentity): string {
  return createHash("sha256")
    .update(canonicalJson({ ...identity, method: identity.method.toUpperCase() }))
    .digest("hex");
}

@Injectable()
export class IdempotencyService {
  constructor(@Inject(CONTROL_DB) private readonly db: Pool) {}

  /**
   * The reservation, domain/audit writes, and response commit together. Concurrent
   * requests wait on a transaction lock, then replay without invoking operation.
   * A failed operation leaves neither a reservation nor partial local writes.
   */
  async execute<T>(
    scope: string,
    key: string | undefined,
    identity: RequestIdentity | (() => Promise<RequestIdentity>),
    operation: (identityHash?: string) => Promise<StoredResponse<T>>,
  ): Promise<StoredResponse<T>> {
    if (key !== undefined && (!key.trim() || key.length > 200 || /[\x00-\x1f\x7f]/.test(key))) {
      throw new BadRequestException("Idempotency-Key must contain 1–200 printable characters");
    }
    const ttl = Number(process.env.IDEMPOTENCY_TTL_HOURS ?? 24);
    if (!Number.isFinite(ttl) || ttl <= 0) throw new Error("Invalid idempotency TTL configuration");
    return controlTransaction(this.db, async (client) => {
      if (key !== undefined) {
        await client.query("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", [
          canonicalJson([scope, key]),
        ]);
      }
      // Authorization must be rechecked after waiting for another request, not
      // captured before the lock and then trusted when replaying a response.
      const resolved = typeof identity === "function" ? await identity() : identity;
      if (key === undefined) return operation();
      const hash = requestHash(resolved);
      const stored = await client.query(
        "SELECT request_hash, response, response_status FROM control_idempotency_keys" +
          " WHERE scope = $1 AND key = $2 AND expires_at > clock_timestamp() FOR UPDATE",
        [scope, key],
      );
      if (stored.rowCount) {
        if (stored.rows[0].request_hash !== hash) {
          throw new ConflictException("Idempotency-Key already belongs to a different request");
        }
        return { status: stored.rows[0].response_status, body: stored.rows[0].response as T };
      }
      // Reserve before invoking code; uncommitted reservations disappear on failure.
      await client.query(
        "INSERT INTO control_idempotency_keys" +
          " (scope, key, request_hash, response_hash, response, response_status, expires_at)" +
          " VALUES ($1, $2, $3, '', 'null'::jsonb, 200, clock_timestamp() + ($4 * interval '1 hour'))" +
          " ON CONFLICT (scope, key) DO UPDATE SET request_hash = EXCLUDED.request_hash," +
          " response_hash = '', response = 'null'::jsonb, response_status = 200," +
          " created_at = clock_timestamp(), expires_at = EXCLUDED.expires_at",
        [scope, key, hash, ttl],
      );
      const result = await operation(hash);
      const serialized = JSON.stringify(result.body ?? null);
      await client.query(
        "UPDATE control_idempotency_keys SET response = $3::jsonb, response_hash = $4," +
          " response_status = $5, expires_at = clock_timestamp() + ($6 * interval '1 hour')" +
          " WHERE scope = $1 AND key = $2",
        [
          scope,
          key,
          serialized,
          createHash("sha256").update(serialized).digest("hex"),
          result.status,
          ttl,
        ],
      );
      return result;
    });
  }
}
