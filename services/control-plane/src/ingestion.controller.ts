import {
  BadRequestException,
  Body,
  Controller,
  Get,
  Headers,
  HttpCode,
  Param,
  Post,
  Query,
  Req,
  Res,
  UseGuards,
} from "@nestjs/common";
type Response = { status: (code: number) => Response };
import { z } from "zod";
import type { ApiKeyScope } from "./api-key.service.js";
import type { Principal } from "./auth.js";
import { IngestionGuard, IngestionService, type Caller } from "./ingestion.service.js";

export type RequestWithCaller = {
  principal: Principal;
  keyPrefix?: string;
  keyProjectId?: string;
  keyScopes?: ApiKeyScope[];
};

const ingestSchema = z.object({
  content: z.string().min(1),
  source_type: z.enum(["text", "json", "csv", "webhook"]).optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
});

const batchSchema = z.object({
  items: z
    .array(
      z.object({ content: z.string(), metadata: z.record(z.string(), z.unknown()).optional() }),
    )
    .min(1),
  source_type: z.enum(["text", "json", "csv", "webhook"]).optional(),
});

function parseBody<T>(schema: z.ZodType<T>, body: unknown): T {
  const result = schema.safeParse(body);
  if (!result.success) throw new BadRequestException("Invalid request body");
  return result.data;
}

export function callerOf(request: RequestWithCaller): Caller {
  return {
    principal: request.principal,
    keyPrefix: request.keyPrefix,
    keyProjectId: request.keyProjectId,
    keyScopes: request.keyScopes,
    rateIdentity: request.keyPrefix ?? request.principal.subject,
  };
}

@Controller("control/workspaces/:workspaceId/projects/:projectId/events")
@UseGuards(IngestionGuard)
export class IngestionController {
  constructor(private readonly ingestion: IngestionService) {}

  @Post()
  async ingest(
    @Req() request: RequestWithCaller,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Body() body: unknown,
    @Headers("idempotency-key") idempotencyKey: string | undefined,
    @Res({ passthrough: true }) response: Response,
  ) {
    const input = parseBody(ingestSchema, body);
    const result = await this.ingestion.ingest(
      callerOf(request),
      workspaceId,
      projectId,
      input,
      idempotencyKey ? idempotencyKey.slice(0, 200) : undefined,
    );
    response.status(result.status);
    return result.payload;
  }

  @Post("batch")
  @HttpCode(207)
  async ingestBatch(
    @Req() request: RequestWithCaller,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Body() body: unknown,
    @Headers("idempotency-key") idempotencyKey?: string,
  ) {
    const input = parseBody(batchSchema, body);
    return this.ingestion.ingestBatch(
      callerOf(request),
      workspaceId,
      projectId,
      input.items,
      input.source_type ?? "text",
      idempotencyKey ? idempotencyKey.slice(0, 200) : undefined,
    );
  }

  @Get()
  list(
    @Req() request: RequestWithCaller,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Query("limit") limitParam?: string,
    @Query("cursor") cursor?: string,
    @Query("q") q?: string,
    @Query("source_type") sourceType?: string,
  ) {
    const limit = limitParam ? Number(limitParam) : undefined;
    if (limit !== undefined && (!Number.isInteger(limit) || limit < 1 || limit > 100)) {
      throw new BadRequestException("limit must be an integer between 1 and 100");
    }
    return this.ingestion.list(callerOf(request), workspaceId, projectId, {
      limit,
      cursor,
      q,
      sourceType,
    });
  }

  @Get(":eventId")
  detail(
    @Req() request: RequestWithCaller,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("eventId") eventId: string,
  ) {
    return this.ingestion.detail(callerOf(request), workspaceId, projectId, eventId);
  }
}
