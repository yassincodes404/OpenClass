import {
  BadRequestException,
  Body,
  Controller,
  Get,
  Inject,
  NotFoundException,
  Param,
  Patch,
  Post,
  Query,
  Req,
  UseGuards,
} from "@nestjs/common";
import type { Pool } from "pg";
import { z } from "zod";
import { AuditService } from "./audit.service.js";
import { KeycloakGuard, type Principal } from "./auth.js";
import { CONTROL_DB } from "./db.js";
import { EngineClient } from "./engine.js";
import { ProjectService } from "./project.service.js";

type RequestWithPrincipal = { principal: Principal };

const settingsSchema = z.object({
  redaction_enabled: z.boolean().optional(),
  retention_days: z.number().int().min(1).max(3650).optional(),
});

const providerConfigSchema = z.object({
  type: z.enum(["mock", "jev", "laya", "ollama", "openai-compatible"]),
  endpoint_ref: z.string().trim().max(200).optional(),
  model: z.string().trim().max(200).optional(),
  timeout_seconds: z.number().int().min(1).max(60).optional(),
  is_default: z.boolean().optional(),
});

function parseBody<T>(schema: z.ZodType<T>, body: unknown): T {
  const result = schema.safeParse(body);
  if (!result.success) throw new BadRequestException("Invalid request body");
  return result.data;
}

@Controller("control/workspaces/:workspaceId")
@UseGuards(KeycloakGuard)
export class SecurityController {
  constructor(
    @Inject(CONTROL_DB) private readonly db: Pool,
    private readonly projects: ProjectService,
    private readonly audit: AuditService,
    private readonly engine: EngineClient,
  ) {}

  @Get("audit")
  async auditLog(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Query("cursor") cursor?: string,
    @Query("action") action?: string,
    @Query("limit") limitParam?: string,
  ) {
    const limit = limitParam ? Number(limitParam) : undefined;
    if (limit !== undefined && (!Number.isInteger(limit) || limit < 1 || limit > 100)) {
      throw new BadRequestException("limit must be an integer between 1 and 100");
    }
    await this.projects.list(request.principal, workspaceId); // membership gate
    return this.audit.list(workspaceId, { cursor, action, limit });
  }

  @Get("projects/:projectId/settings")
  getSettings(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
  ) {
    return this.projects.settings(request.principal, workspaceId, projectId);
  }

  @Patch("projects/:projectId/settings")
  updateSettings(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Body() body: unknown,
  ) {
    const patch = parseBody(settingsSchema, body);
    return this.projects.updateSettings(request.principal, workspaceId, projectId, patch);
  }

  @Get("projects/:projectId/providers")
  async providers(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
  ) {
    await this.projects.get(request.principal, workspaceId, projectId);
    const [catalog, status, configs] = await Promise.all([
      this.engine.providers(),
      this.engine.providerStatus(),
      this.db.query(
        "SELECT id, type, endpoint_ref, model, timeout_seconds, is_default, created_at FROM control_provider_configs WHERE project_id = $1 ORDER BY created_at",
        [projectId],
      ),
    ]);
    return { catalog, status, configs: configs.rows };
  }

  @Post("projects/:projectId/providers")
  async configureProvider(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Body() body: unknown,
  ) {
    const input = parseBody(providerConfigSchema, body);
    if (input.endpoint_ref && !/^[A-Z][A-Z0-9_]{2,}$/.test(input.endpoint_ref)) {
      throw new BadRequestException(
        "endpoint_ref must be an environment variable name (UPPER_SNAKE_CASE)",
      );
    }
    await this.projects.assertManager(request.principal, workspaceId, projectId);
    const result = await this.db.query(
      "INSERT INTO control_provider_configs (workspace_id, project_id, type, endpoint_ref, model, timeout_seconds, is_default)" +
        " VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id, type, endpoint_ref, model, timeout_seconds, is_default, created_at",
      [
        workspaceId,
        projectId,
        input.type,
        input.endpoint_ref ?? null,
        input.model ?? null,
        input.timeout_seconds ?? 20,
        input.is_default ?? false,
      ],
    );
    const config = result.rows[0];
    await this.audit.record({
      workspaceId,
      projectId,
      actor: request.principal.subject,
      action: "provider.configured",
      target: `provider:${input.type}:${input.endpoint_ref ?? "default"}`,
    });
    return config;
  }

  @Post("projects/:projectId/providers/:configId/test")
  async testProvider(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("configId") configId: string,
  ) {
    await this.projects.get(request.principal, workspaceId, projectId);
    const config = await this.db.query(
      "SELECT type FROM control_provider_configs WHERE id = $1 AND project_id = $2",
      [configId, projectId],
    );
    if (!config.rowCount) throw new NotFoundException("Provider config not found");
    const result = (await this.engine.testProvider(config.rows[0].type)) as Record<string, unknown>;
    return result;
  }

  @Get("projects/:projectId/providers/usage")
  async providerUsage(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Query("from") from?: string,
    @Query("to") to?: string,
  ) {
    const project = await this.projects.get(request.principal, workspaceId, projectId);
    return this.engine.providerUsage(project.engine_project_id, from, to);
  }
}
