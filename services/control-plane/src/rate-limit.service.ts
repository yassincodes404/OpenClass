import { Injectable } from "@nestjs/common";

export type RateClass = "ingest" | "classify";

type Bucket = { tokens: number; updatedAt: number };

export type RateDecision = { allowed: boolean; retryAfterSeconds: number; limit: number; remaining: number };

const MINUTE_MS = 60_000;

/**
 * In-memory token buckets per (principal, class). The control plane applies
 * per-key and per-workspace limits on proxied engine routes; the engine keeps
 * its own per-client backstop.
 */
@Injectable()
export class RateLimitService {
  private readonly limits: Record<RateClass, number> = {
    ingest: Number(process.env.RATE_LIMIT_INGEST_PER_MIN ?? 60),
    classify: Number(process.env.RATE_LIMIT_CLASSIFY_PER_MIN ?? 300),
  };
  private readonly buckets = new Map<string, Bucket>();

  check(identity: string, rateClass: RateClass, now = Date.now()): RateDecision {
    const capacity = this.limits[rateClass];
    const key = `${identity}:${rateClass}`;
    let bucket = this.buckets.get(key);
    if (!bucket) {
      bucket = { tokens: capacity, updatedAt: now };
      this.buckets.set(key, bucket);
    }
    const elapsed = Math.max(0, now - bucket.updatedAt);
    bucket.tokens = Math.min(capacity, bucket.tokens + (elapsed / MINUTE_MS) * capacity);
    bucket.updatedAt = now;
    if (bucket.tokens >= 1) {
      bucket.tokens -= 1;
      return { allowed: true, retryAfterSeconds: 0, limit: capacity, remaining: Math.floor(bucket.tokens) };
    }
    const deficit = 1 - bucket.tokens;
    return {
      allowed: false,
      retryAfterSeconds: Math.max(1, Math.ceil((deficit / capacity) * 60)),
      limit: capacity,
      remaining: 0,
    };
  }

  /** Test/ops helper: forget one identity's buckets. */
  reset(identity: string): void {
    for (const rateClass of ["ingest", "classify"] as const) this.buckets.delete(`${identity}:${rateClass}`);
  }
}
