import { BadRequestException, Body, Controller, Get, Param, Patch, Query, Req, UseGuards } from "@nestjs/common";
import { z } from "zod";
import { AuditService } from "./audit.service.js";
import { KeycloakGuard, type Principal } from "./auth.js";
import { EngineClient } from "./engine.js";
import { ProjectService } from "./project.service.js";

type RequestWithPrincipal = { principal: Principal };

const settingsSchema = z.object({
  redaction_enabled: z.boolean().optional(),
  retention_days: z.number().int().min(1).max(3650).optional(),
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
  getSettings(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string) {
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
  async providers(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string) {
    await this.projects.get(request.principal, workspaceId, projectId);
    const [catalog, status] = await Promise.all([this.engine.providers(), this.engine.providerStatus()]);
    return { catalog, status };
  }
}
