import {
  BadRequestException,
  Body,
  Controller,
  Get,
  HttpException,
  NotFoundException,
  Param,
  Post,
  Query,
  Req,
  Res,
  UseGuards,
} from "@nestjs/common";
type Response = { status: (code: number) => Response };
import { z } from "zod";
import { AuditService } from "./audit.service.js";
import { KeycloakGuard, type Principal } from "./auth.js";
import { CONTROL_DB } from "./db.js";
import { EngineClient, type EngineDecisionRun } from "./engine.js";
import { RateLimitService } from "./rate-limit.service.js";
import { ROLE_RANK, type Role } from "./workspace.service.js";
import type { Pool } from "pg";
import { Inject } from "@nestjs/common";

type RequestWithPrincipal = { principal: Principal };

const createServiceSchema = z.object({
  name: z.string().trim().min(2).max(200),
  instructions: z.string().trim().min(10).max(2000),
  description: z.string().trim().max(2000).optional().default(""),
  choices: z
    .array(
      z.object({
        key: z
          .string()
          .trim()
          .regex(/^[A-Z][A-Z0-9_]{0,49}$/, "choice keys must be UPPERCASE"),
        label: z.string().trim().min(1).max(100),
        description: z.string().trim().max(1000).optional(),
      }),
    )
    .min(1)
    .max(49),
});

const runSchema = z
  .object({
    content: z.string().trim().min(1).max(10_000).optional(),
    raw_event_ids: z.array(z.string().uuid()).max(100).optional(),
  })
  .refine((value) => value.content || value.raw_event_ids?.length, {
    message: "content or raw_event_ids is required",
  });

function parseBody<T>(schema: z.ZodType<T>, body: unknown): T {
  const result = schema.safeParse(body);
  if (!result.success) throw new BadRequestException("Invalid request body");
  return result.data;
}

@Controller("control/workspaces/:workspaceId/projects/:projectId")
@UseGuards(KeycloakGuard)
export class DecisionController {
  constructor(
    @Inject(CONTROL_DB) private readonly db: Pool,
    private readonly engine: EngineClient,
    private readonly rateLimits: RateLimitService,
    private readonly audit: AuditService,
  ) {}

  @Get("decision-services")
  async listServices(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
  ) {
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    return this.engine.listDecisionServices(project.engine_project_id);
  }

  @Post("decision-services")
  async createService(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Body() body: unknown,
  ) {
    const input = parseBody(createServiceSchema, body);
    if (input.choices.some((choice) => choice.key === "UNKNOWN")) {
      throw new BadRequestException(
        "UNKNOWN is auto-appended and locked; do not send it as a choice",
      );
    }
    const project = await this.requireRole(request.principal, workspaceId, projectId, "admin");
    const created = await this.engine.createDecisionService(project.engine_project_id, input);
    await this.audit.record({
      workspaceId,
      projectId,
      actor: request.principal.subject,
      action: "decision_service.created",
      target: `service:${created.slug}`,
    });
    return created;
  }

  @Get("decision-services/:serviceId")
  async getService(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("serviceId") serviceId: string,
  ) {
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    return this.engine.getDecisionService(project.engine_project_id, serviceId);
  }

  @Post("decision-services/:serviceId/runs")
  async run(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("serviceId") serviceId: string,
    @Body() body: unknown,
    @Res({ passthrough: true }) response: Response,
  ) {
    const input = parseBody(runSchema, body);
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    const decision = this.rateLimits.check(request.principal.subject, "classify");
    if (!decision.allowed) {
      throw new HttpException(`Rate limit exceeded; retry in ${decision.retryAfterSeconds}s`, 429);
    }
    const runs = await this.engine.runDecisions(project.engine_project_id, serviceId, input);
    for (const run of runs) {
      await this.audit.record({
        workspaceId,
        projectId,
        actor: request.principal.subject,
        action: "decision_run.executed",
        target: `run:${run.id}:${run.selected_choice}`,
      });
    }
    response.status(201);
    return runs;
  }

  @Get("runs")
  async listRuns(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Query("limit") limitParam?: string,
    @Query("cursor") cursor?: string,
    @Query("result") result?: string,
  ) {
    const limit = limitParam ? Number(limitParam) : 25;
    if (!Number.isInteger(limit) || limit < 1 || limit > 100)
      throw new BadRequestException("limit must be 1–100");
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    const offset = cursor ? Number(Buffer.from(cursor, "base64").toString("utf8")) || 0 : 0;
    const runs = await this.engine.listRuns(project.engine_project_id, 200, offset);
    const filtered = result ? runs.filter((run) => this.runResult(run) === result) : runs;
    const items = filtered.slice(0, limit);
    return {
      items,
      next_cursor:
        runs.length === 200 ? Buffer.from(String(offset + limit)).toString("base64") : null,
    };
  }

  @Get("runs/:runId")
  async getRun(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("runId") runId: string,
  ) {
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    return this.engine.getRun(project.engine_project_id, runId);
  }

  private runResult(run: EngineDecisionRun): string {
    return run.selected_choice === "UNKNOWN" ? "UNKNOWN" : run.selected_choice;
  }

  private async projectOf(workspaceId: string, projectId: string) {
    const result = await this.db.query(
      "SELECT id, workspace_id, engine_project_id FROM control_projects WHERE id = $1 AND workspace_id = $2",
      [projectId, workspaceId],
    );
    if (!result.rowCount) return null;
    return result.rows[0] as { id: string; workspace_id: string; engine_project_id: string };
  }

  private async requireMember(principal: Principal, workspaceId: string, projectId: string) {
    const membership = await this.db.query(
      "SELECT role FROM control_workspace_memberships WHERE workspace_id = $1 AND subject = $2",
      [workspaceId, principal.subject],
    );
    if (!membership.rowCount) throw new NotFoundException("Workspace not found");
    const project = await this.projectOf(workspaceId, projectId);
    if (!project) throw new NotFoundException("Project not found");
    return project;
  }

  private async requireRole(
    principal: Principal,
    workspaceId: string,
    projectId: string,
    minimum: Role,
  ) {
    const membership = await this.db.query(
      "SELECT role FROM control_workspace_memberships WHERE workspace_id = $1 AND subject = $2",
      [workspaceId, principal.subject],
    );
    if (!membership.rowCount) throw new NotFoundException("Workspace not found");
    const role = membership.rows[0].role as Role;
    if (ROLE_RANK[role] < ROLE_RANK[minimum])
      throw new HttpException("Workspace role cannot manage decision services", 403);
    const project = await this.projectOf(workspaceId, projectId);
    if (!project) throw new NotFoundException("Project not found");
    return project;
  }
}
