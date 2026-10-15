import {
  BadRequestException,
  ForbiddenException,
  Inject,
  Injectable,
  NotFoundException,
  UnauthorizedException,
} from "@nestjs/common";
import type { CallHandler, ExecutionContext, NestInterceptor } from "@nestjs/common";
import { Reflector } from "@nestjs/core";
import { createHash } from "node:crypto";
import type { Pool } from "pg";
import { from, lastValueFrom, type Observable } from "rxjs";
import { CONTROL_DB } from "./db.js";
import { IdempotencyService } from "./idempotency.service.js";
import { requestContext } from "./request-context.js";
import type { ApiKeyScope } from "./api-key.service.js";
import { SECRET_MUTATION_RESPONSE } from "./mutation-metadata.js";

/** Runs after authentication guards and before any controller side effects. */
@Injectable()
export class MutationInterceptor implements NestInterceptor {
  private readonly reflector = new Reflector();
  constructor(
    @Inject(CONTROL_DB) private readonly db: Pool,
    private readonly idempotency: IdempotencyService,
  ) {}

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const http = context.switchToHttp();
    const request = http.getRequest<{
      method: string;
      originalUrl: string;
      body?: unknown;
      params: { workspaceId?: string; id?: string; projectId?: string };
      headers: Record<string, string | undefined>;
      principal?: { subject: string };
      keyId?: string;
      keyProjectId?: string;
      keyScopes?: ApiKeyScope[];
      keyRequiredScope?: ApiKeyScope;
    }>();
    if (!["POST", "PUT", "PATCH", "DELETE"].includes(request.method)) return next.handle();
    const response = http.getResponse<{ statusCode: number; status(code: number): unknown }>();
    return from(
      (async () => {
        const key = request.headers["idempotency-key"];
        // One-time API key material must never enter the response cache.
        if (
          key !== undefined &&
          this.reflector.getAllAndOverride<boolean>(SECRET_MUTATION_RESPONSE, [
            context.getHandler(),
            context.getClass(),
          ])
        ) {
          throw new BadRequestException("Idempotency-Key is not supported for API key creation");
        }
        const workspaceId = request.params.workspaceId ?? request.params.id;
        const subject = request.principal?.subject;
        if (!subject) throw new UnauthorizedException("Authentication required");
        const scope = workspaceId ? `workspace:${workspaceId}` : `actor:${subject}`;
        const stored = await this.idempotency.execute(
          scope,
          key,
          async () => {
            let authorization: unknown = { subject };
            if (workspaceId) {
              if (request.keyProjectId || request.keyId) {
                if (!request.keyId || !request.keyRequiredScope) {
                  throw new ForbiddenException("API key verification context is missing");
                }
                // Recheck the exact key after waiting for the receipt lock. A
                // shared row lock also prevents revocation during this operation.
                const verified = await this.db.query(
                  "SELECT k.id, k.workspace_id, k.project_id, k.scopes, k.revoked_at" +
                    " FROM control_api_keys k JOIN control_projects p" +
                    " ON p.id = k.project_id AND p.workspace_id = k.workspace_id" +
                    " WHERE k.id = $1 FOR SHARE OF k",
                  [request.keyId],
                );
                const current = verified.rows[0];
                if (
                  !current ||
                  current.revoked_at ||
                  !current.scopes.includes(request.keyRequiredScope)
                ) {
                  throw new ForbiddenException(
                    "API key is invalid, revoked, or lacks required scope",
                  );
                }
                if (
                  current.workspace_id !== workspaceId ||
                  current.project_id !== request.params.projectId ||
                  current.project_id !== request.keyProjectId
                ) {
                  throw new NotFoundException("Project not found");
                }
                request.keyScopes = current.scopes;
                authorization = {
                  subject,
                  keyId: current.id,
                  project: current.project_id,
                  scopes: [...current.scopes].sort(),
                };
              } else {
                const membership = await this.db.query(
                  "SELECT role FROM control_workspace_memberships WHERE workspace_id = $1 AND subject = $2",
                  [workspaceId, subject],
                );
                if (!membership.rowCount) throw new NotFoundException("Workspace not found");
                authorization = { subject, role: membership.rows[0].role };
              }
            }
            return {
              method: request.method,
              path: request.originalUrl,
              body: request.body,
              authorization,
            };
          },
          async (identityHash) => {
            const existing = requestContext.getStore();
            // Do not forward a client-selected global key into unrelated engine paths.
            const downstreamKey =
              key === undefined
                ? undefined
                : createHash("sha256")
                    .update(JSON.stringify([scope, key, identityHash]))
                    .digest("hex");
            return requestContext.run(
              {
                correlationId: existing?.correlationId ?? "control-plane",
                idempotencyKey: downstreamKey,
              },
              async () => ({
                body: await lastValueFrom(next.handle()),
                status: response.statusCode,
              }),
            );
          },
        );
        response.status(stored.status);
        return stored.body;
      })(),
    );
  }
}
