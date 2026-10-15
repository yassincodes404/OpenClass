import { AsyncLocalStorage } from "node:async_hooks";
import { randomUUID } from "node:crypto";

export type RequestContext = { correlationId: string; idempotencyKey?: string };
export const requestContext = new AsyncLocalStorage<RequestContext>();

/** Accept only bounded, log-safe opaque identifiers, not arbitrary header content. */
export function correlationId(value: unknown): string {
  return typeof value === "string" && /^[A-Za-z0-9._:-]{1,128}$/.test(value) ? value : randomUUID();
}

export function correlationMiddleware(
  request: { headers: Record<string, unknown> },
  response: { setHeader(name: string, value: string): unknown },
  next: () => void,
): void {
  const id = correlationId(request.headers["x-correlation-id"]);
  response.setHeader("X-Correlation-ID", id);
  requestContext.run({ correlationId: id }, next);
}
