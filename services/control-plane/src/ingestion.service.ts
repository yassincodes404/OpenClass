import {
  BadRequestException,
  ForbiddenException,
  HttpException,
  Injectable,
  NotFoundException,
  PayloadTooLargeException,
} from "@nestjs/common";

import type { Pool } from "pg";
import { ApiKeyService } from "./api-key.service.js";
import { AuditService } from "./audit.service.js";
import type { Principal } from "./auth.js";
import { KeycloakGuard } from "./auth.js";
import { CONTROL_DB } from "./db.js";
import { EngineClient, type EngineRawEvent } from "./engine.js";
import { RateLimitService } from "./rate-limit.service.js";
import { redactText } from "./redaction.js";
import { ROLE_RANK, type Role } from "./workspace.service.js";
import { Inject } from "@nestjs/common";
import type { CanActivate, ExecutionContext } from "@nestjs/common";

export const MAX_EVENT_CHARS = 10_000;
export const MAX_BATCH_ITEMS = 500;
const MONTHLY_QUOTA = Number(process.env.WORKSPACE_MONTHLY_EVENT_QUOTA ?? 10_000);

export type Caller = {
  principal: Principal;
  keyPrefix?: string;
  keyProjectId?: string;
  rateIdentity: string;
};

/**
 * Accepts either a workspace member's Keycloak JWT or a scoped project API key
 * (oc_dev_…) for programmatic ingestion.
 */
@Injectable()
export class IngestionGuard implements CanActivate {
  constructor(
    private readonly keycloak: KeycloakGuard,
    private readonly apiKeys: ApiKeyService,
  ) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest<{
      headers: Record<string, string | undefined>;
      principal?: Principal;
      keyPrefix?: string;
      keyProjectId?: string;
    }>();
    const token = request.headers.authorization?.startsWith("Bearer ")
      ? request.headers.authorization.slice(7)
      : undefined;
    if (token?.startsWith("oc_dev_")) {
      try {
        const verified = await this.apiKeys.verify(token, "ingest");
        request.principal = { subject: `api-key:${verified.projectId}` };
        request.keyPrefix = token.slice(0, 14);
        request.keyProjectId = verified.projectId;
        return true;
      } catch (error) {
        if (error instanceof HttpException) throw error;
        throw new ForbiddenException("API key is invalid or revoked");
      }
    }
    return this.keycloak.canActivate(context);
  }
}

@Injectable()
export class IngestionService {
  constructor(
    @Inject(CONTROL_DB) private readonly db: Pool,
    private readonly engine: EngineClient,
    private readonly rateLimits: RateLimitService,
    private readonly audit: AuditService,
  ) {}

  async ingest(
    caller: Caller,
    workspaceId: string,
    projectId: string,
    body: { content: string; source_type?: string; metadata?: Record<string, unknown> },
    idempotencyKey?: string,
  ) {
    const project = await this.authorize(caller, workspaceId, projectId, "viewer");
    this.throttle(caller, project.id);
    await this.enforceQuota(workspaceId);
    if (!body.content?.trim()) throw new BadRequestException("content cannot be blank");
    if (body.content.length > MAX_EVENT_CHARS) {
      throw new PayloadTooLargeException(`content exceeds ${MAX_EVENT_CHARS} characters`);
    }
    const result = await this.engine.ingestEvent(
      project.engine_project_id,
      {
        content: body.content,
        source_type: body.source_type ?? "text",
        ...(body.metadata ? { metadata: body.metadata } : {}),
      },
      idempotencyKey,
    );
    const payload = { ...(result.body as { id: string; deduped?: boolean }) };
    if (!payload.deduped) {
      await this.audit.record({
        workspaceId,
        projectId,
        actor: caller.principal.subject,
        action: "observation.ingested",
        target: `event:${payload.id}`,
      });
    }
    return { status: result.status, payload };
  }

  async ingestBatch(
    caller: Caller,
    workspaceId: string,
    projectId: string,
    items: Array<{ content: string; metadata?: Record<string, unknown> }>,
    sourceType: string,
    idempotencyKey?: string,
  ) {
    const project = await this.authorize(caller, workspaceId, projectId, "viewer");
    this.throttle(caller, project.id);
    await this.enforceQuota(workspaceId);
    if (items.length > MAX_BATCH_ITEMS)
      throw new PayloadTooLargeException(`batch exceeds ${MAX_BATCH_ITEMS} items`);
    if (items.length === 0) throw new BadRequestException("items cannot be empty");
    const entries: Array<{
      index: number;
      status: number | null;
      error?: string;
      event?: unknown;
      deduped?: boolean;
    }> = items.map((item, index) => {
      if (!item.content?.trim()) return { index, status: 400, error: "content cannot be blank" };
      if (item.content.length > MAX_EVENT_CHARS) {
        return { index, status: 413, error: `content exceeds ${MAX_EVENT_CHARS} characters` };
      }
      return { index, status: null };
    });
    const valid = items.filter((_, index) => entries[index].status === null);
    if (valid.length) {
      const result = await this.engine.ingestEventsBatch(
        project.engine_project_id,
        { items: valid, source_type: sourceType },
        idempotencyKey,
      );
      const body = result.body as {
        items?: Array<{
          index: number;
          status: number;
          event?: unknown;
          deduped?: boolean;
          error?: string;
        }>;
      };
      const engineEntries = body.items ?? [];
      let cursor = 0;
      for (const entry of entries) {
        if (entry.status !== null) continue;
        const engineEntry = engineEntries[cursor++];
        if (engineEntry) {
          entry.status = engineEntry.status;
          entry.event = engineEntry.event;
          entry.deduped = engineEntry.deduped;
          if (engineEntry.error) entry.error = engineEntry.error;
        }
      }
    }
    for (const entry of entries) {
      if (entry.status === 201) {
        await this.audit.record({
          workspaceId,
          projectId,
          actor: caller.principal.subject,
          action: "observation.ingested",
          target: `event:${(entry.event as { id?: string })?.id ?? "?"}`,
        });
      }
    }
    return { items: entries };
  }

  /** List observations with redacted previews; members may open originals in detail. */
  async list(
    caller: Caller,
    workspaceId: string,
    projectId: string,
    options: { limit?: number; cursor?: string; q?: string; sourceType?: string },
  ) {
    const project = await this.authorize(caller, workspaceId, projectId, "viewer");
    const limit = Math.min(Math.max(options.limit ?? 25, 1), 100);
    const offset = options.cursor ? this.decodeCursor(options.cursor) : 0;
    // Local-scale search: fetch a bounded window from the engine, then filter.
    const window = await this.engine.listEvents(project.engine_project_id, 200, offset);
    let filtered = window;
    if (options.q) {
      const needle = options.q.toLowerCase();
      filtered = filtered.filter((event) => event.content.toLowerCase().includes(needle));
    }
    if (options.sourceType) {
      filtered = filtered.filter((event) => event.source_type === options.sourceType);
    }
    const items = filtered
      .slice(0, limit)
      .map((event) => this.toPreview(event, Boolean(project.redaction_enabled)));
    const hasMore = filtered.length > limit || window.length === 200;
    return {
      items,
      next_cursor:
        hasMore && offset + window.length > offset + limit
          ? this.encodeCursor(offset + limit)
          : null,
    };
  }

  async detail(
    caller: Caller,
    workspaceId: string,
    projectId: string,
    eventId: string,
  ): Promise<EngineRawEvent> {
    await this.authorize(caller, workspaceId, projectId, "viewer");
    const project = await this.byId(workspaceId, projectId);
    try {
      return await this.engine.getEvent(project.engine_project_id, eventId);
    } catch {
      throw new NotFoundException("Observation not found");
    }
  }

  private toPreview(event: EngineRawEvent, redact: boolean) {
    const preview = redact ? redactText(event.content).slice(0, 160) : event.content.slice(0, 160);
    return { id: event.id, source_type: event.source_type, preview, created_at: event.created_at };
  }

  private throttle(caller: Caller, projectId: string) {
    const decision = this.rateLimits.check(caller.rateIdentity, "ingest");
    if (!decision.allowed) {
      throw new HttpException(
        {
          message: `Rate limit exceeded; retry in ${decision.retryAfterSeconds}s`,
          retryAfterSeconds: decision.retryAfterSeconds,
        },
        429,
      );
    }
  }

  private async enforceQuota(workspaceId: string) {
    const projects = await this.db.query(
      "SELECT engine_project_id FROM control_projects WHERE workspace_id = $1",
      [workspaceId],
    );
    let total = 0;
    for (const row of projects.rows as Array<{ engine_project_id: string }>) {
      const summary = await this.engine
        .projectSummary(row.engine_project_id)
        .catch(() => ({ events: 0 }));
      total += summary.events ?? 0;
    }
    if (total >= MONTHLY_QUOTA) {
      throw new HttpException(
        `Workspace monthly ingestion quota reached (${MONTHLY_QUOTA} events, simulated demo cap)`,
        429,
      );
    }
  }

  private async authorize(caller: Caller, workspaceId: string, projectId: string, minimum: Role) {
    if (caller.keyProjectId && caller.keyProjectId !== projectId) {
      throw new NotFoundException("Project not found");
    }
    const result = await this.db.query(
      "SELECT role FROM control_workspace_memberships WHERE workspace_id = $1 AND subject = $2",
      [workspaceId, caller.principal.subject],
    );
    // API-key callers are not workspace members; their key already gates the project.
    if (!result.rowCount) {
      if (caller.keyProjectId) return this.byId(workspaceId, projectId);
      throw new NotFoundException("Workspace not found");
    }
    const role = result.rows[0].role as Role;
    if (ROLE_RANK[role] < ROLE_RANK[minimum])
      throw new ForbiddenException("Workspace role cannot access observations");
    return this.byId(workspaceId, projectId);
  }

  private async byId(workspaceId: string, projectId: string) {
    const result = await this.db.query(
      "SELECT id, workspace_id, engine_project_id, slug, name, redaction_enabled FROM control_projects WHERE id = $1 AND workspace_id = $2",
      [projectId, workspaceId],
    );
    if (!result.rowCount) throw new NotFoundException("Project not found");
    return result.rows[0] as {
      id: string;
      workspace_id: string;
      engine_project_id: string;
      slug: string;
      name: string;
      redaction_enabled: boolean;
    };
  }

  private encodeCursor(offset: number): string {
    return Buffer.from(String(offset), "utf8").toString("base64");
  }

  private decodeCursor(cursor: string): number {
    const value = Number(Buffer.from(cursor, "base64").toString("utf8"));
    return Number.isInteger(value) && value >= 0 ? value : 0;
  }
}
