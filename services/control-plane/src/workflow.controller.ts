import {
  All,
  Body,
  Controller,
  ForbiddenException,
  HttpException,
  Inject,
  NotFoundException,
  Param,
  Query,
  Req,
  Res,
  UseGuards,
} from "@nestjs/common";
import type { Pool } from "pg";
import { KeycloakGuard, type Principal } from "./auth.js";
import { CONTROL_DB } from "./db.js";
import { EngineClient } from "./engine.js";
import { callerOf } from "./ingestion.controller.js";
import { IngestionService } from "./ingestion.service.js";
import { ProjectService } from "./project.service.js";
import { RateLimitService } from "./rate-limit.service.js";
import { ROLE_RANK, type Role } from "./workspace.service.js";
import { workflowContract, workflowQuery } from "./workflow-contracts.js";

@Controller("control/workspaces/:workspaceId/projects/:projectId")
@UseGuards(KeycloakGuard)
export class WorkflowController {
  constructor(
    @Inject(CONTROL_DB) private readonly db: Pool,
    private readonly projects: ProjectService,
    private readonly engine: EngineClient,
    private readonly ingestion: IngestionService,
    private readonly rateLimits: RateLimitService,
  ) {}

  @All(["workflow", "workflow/*path"])
  async handle(
    @Req() request: { principal: Principal; method: string },
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("path") segments: string[] | string | undefined,
    @Query() query: Record<string, unknown>,
    @Body() body: unknown,
    @Res({ passthrough: true }) response: { status: (value: number) => unknown },
  ) {
    const path = Array.isArray(segments) ? segments.join("/") : (segments ?? "");
    const contract = workflowContract(request.method, path, body);
    const suffix = workflowQuery(query);
    // Always resolve the caller's membership and project mapping BEFORE engine I/O.
    const project = await this.projects.get(request.principal, workspaceId, projectId);
    const member = await this.db.query(
      "SELECT role FROM control_workspace_memberships WHERE workspace_id = $1 AND subject = $2",
      [workspaceId, request.principal.subject],
    );
    if (!member.rowCount) throw new NotFoundException("Workspace not found");
    const role = member.rows[0].role as Role;
    if (!Object.hasOwn(ROLE_RANK, role) || ROLE_RANK[role] < ROLE_RANK[contract.role])
      throw new ForbiddenException("Workspace role cannot perform this workflow action");
    // The HTTP RPC is NOT part of the control database's local transaction.
    // No automatic retries: a failed response may follow an accepted engine mutation.
    const options = { workspaceId, actor: request.principal.subject };
    if (request.method === "POST" && (path === "events" || path === "events/batch"))
      await this.ingestion.authorizeIngestion(callerOf(request), workspaceId, project.id);
    if (request.method === "POST" && /^decision-services\/[^/]+\/runs$/.test(path)) {
      const decision = this.rateLimits.check(request.principal.subject, "classify");
      if (!decision.allowed)
        throw new HttpException(
          `Rate limit exceeded; retry in ${decision.retryAfterSeconds}s`,
          429,
        );
    }
    if (request.method === "POST" && path === "events") {
      const result = await this.engine.ingestEvent(
        project.engine_project_id,
        contract.body as Parameters<EngineClient["ingestEvent"]>[1],
        options,
      );
      response.status(result.status);
      return result.body;
    }
    if (request.method === "POST" && path === "events/batch") {
      const result = await this.engine.ingestEventsBatch(
        project.engine_project_id,
        contract.body as Parameters<EngineClient["ingestEventsBatch"]>[1],
        options,
      );
      response.status(result.status);
      return result.body;
    }
    const result = await this.engine.request(
      request.method,
      `/api/v1/projects/${encodeURIComponent(project.engine_project_id)}${path ? `/${path}` : ""}${suffix}`,
      contract.body,
      contract.status,
      options,
    );
    response.status(contract.status);
    return result;
  }
}
