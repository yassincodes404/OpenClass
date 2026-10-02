import {
  BadRequestException,
  Body,
  Controller,
  Get,
  HttpCode,
  HttpException,
  Inject,
  NotFoundException,
  Param,
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
import { ROLE_RANK, type Role } from "./workspace.service.js";

type RequestWithPrincipal = { principal: Principal };

const triageSchema = z.object({
  category: z.enum(["truly_novel", "ambiguous", "out_of_scope", "missing_info", "schema_problem"]),
  assignee: z.string().trim().max(200).optional(),
  note: z.string().trim().max(2000).optional(),
});

const transitionSchema = z.object({ to: z.enum(["needs_evidence", "triaged", "dismissed"]) });

function parseBody<T>(schema: z.ZodType<T>, body: unknown): T {
  const result = schema.safeParse(body);
  if (!result.success) throw new BadRequestException("Invalid request body");
  return result.data;
}

/** UNKNOWN workspace proxy: viewer+ reads, reviewer+ triage. Categories are advisory only. */
@Controller("control/workspaces/:workspaceId/projects/:projectId/unknowns")
@UseGuards(KeycloakGuard)
export class UnknownController {
  constructor(
    @Inject(CONTROL_DB) private readonly db: Pool,
    private readonly engine: EngineClient,
    private readonly audit: AuditService,
  ) {}

  @Get()
  async list(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Query("state") state?: string,
    @Query("category") category?: string,
    @Query("q") q?: string,
  ) {
    const project = await this.gate(request.principal, workspaceId, projectId, "viewer");
    return this.engine.listUnknowns(project.engine_project_id, { state, category, query: q });
  }

  @Get("stats")
  async stats(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
  ) {
    const project = await this.gate(request.principal, workspaceId, projectId, "viewer");
    return this.engine.unknownStats(project.engine_project_id);
  }

  @Post("cluster")
  async cluster(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Body() body: unknown,
  ) {
    const threshold =
      typeof (body as { threshold?: number })?.threshold === "number"
        ? (body as { threshold: number }).threshold
        : undefined;
    const project = await this.gate(request.principal, workspaceId, projectId, "reviewer");
    const result = await this.engine.runClustering(project.engine_project_id, threshold);
    await this.audit.record({
      workspaceId,
      projectId,
      actor: request.principal.subject,
      action: "clusters.rebuilt",
      target: `threshold:${threshold ?? "default"}`,
    });
    return result;
  }

  @Get("clusters")
  async clusters(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
  ) {
    const project = await this.gate(request.principal, workspaceId, projectId, "viewer");
    return this.engine.listClusters(project.engine_project_id);
  }

  @Get("clusters/:clusterId")
  async clusterDetail(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("clusterId") clusterId: string,
  ) {
    const project = await this.gate(request.principal, workspaceId, projectId, "viewer");
    return this.engine.clusterDetail(project.engine_project_id, clusterId);
  }

  @Post("clusters/:clusterId/discover")
  async discover(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("clusterId") clusterId: string,
  ) {
    const project = await this.gate(request.principal, workspaceId, projectId, "admin");
    const candidate = await this.engine.discoverCluster(project.engine_project_id, clusterId);
    await this.audit.record({
      workspaceId,
      projectId,
      actor: request.principal.subject,
      action: "candidate.discovered",
      target: `cluster:${clusterId.slice(0, 8)}`,
    });
    return candidate;
  }

  @Get("candidates")
  async candidates(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
  ) {
    const project = await this.gate(request.principal, workspaceId, projectId, "viewer");
    return this.engine.listCandidates(project.engine_project_id);
  }

  @Get("candidates/:candidateId")
  async candidateDetail(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("candidateId") candidateId: string,
  ) {
    const project = await this.gate(request.principal, workspaceId, projectId, "viewer");
    return this.engine.candidateDetail(project.engine_project_id, candidateId);
  }

  @Get(":runId")
  async detail(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("runId") runId: string,
  ) {
    const project = await this.gate(request.principal, workspaceId, projectId, "viewer");
    return this.engine.unknownDetail(project.engine_project_id, runId);
  }

  @Post(":runId/triage")
  @HttpCode(200)
  async triage(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("runId") runId: string,
    @Body() body: unknown,
  ) {
    const input = parseBody(triageSchema, body);
    const project = await this.gate(request.principal, workspaceId, projectId, "reviewer");
    const result = await this.engine.triageUnknown(project.engine_project_id, runId, input);
    await this.audit.record({
      workspaceId,
      projectId,
      actor: request.principal.subject,
      action: "unknown.triaged",
      target: `run:${runId.slice(0, 8)}:${input.category}`,
    });
    return result;
  }

  @Post(":runId/transition")
  @HttpCode(200)
  async transition(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("runId") runId: string,
    @Body() body: unknown,
  ) {
    const input = parseBody(transitionSchema, body);
    const project = await this.gate(request.principal, workspaceId, projectId, "reviewer");
    const result = await this.engine.transitionUnknown(project.engine_project_id, runId, input.to);
    await this.audit.record({
      workspaceId,
      projectId,
      actor: request.principal.subject,
      action: "unknown.transitioned",
      target: `run:${runId.slice(0, 8)}:${input.to}`,
    });
    return result;
  }

  private async gate(principal: Principal, workspaceId: string, projectId: string, minimum: Role) {
    const membership = await this.db.query(
      "SELECT role FROM control_workspace_memberships WHERE workspace_id = $1 AND subject = $2",
      [workspaceId, principal.subject],
    );
    if (!membership.rowCount) throw new NotFoundException("Workspace not found");
    const role = membership.rows[0].role as Role;
    if (ROLE_RANK[role] < ROLE_RANK[minimum])
      throw new HttpException("Workspace role cannot triage unknowns", 403);
    const project = await this.db.query(
      "SELECT id, engine_project_id FROM control_projects WHERE id = $1 AND workspace_id = $2",
      [projectId, workspaceId],
    );
    if (!project.rowCount) throw new NotFoundException("Project not found");
    return project.rows[0] as { id: string; engine_project_id: string };
  }
}
