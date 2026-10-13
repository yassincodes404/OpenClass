import {
  BadRequestException,
  Body,
  Controller,
  ForbiddenException,
  Get,
  HttpCode,
  HttpException,
  Inject,
  Injectable,
  NotFoundException,
  Param,
  Post,
  Query,
  Req,
  Res,
  UseGuards,
} from "@nestjs/common";
import type { CanActivate, ExecutionContext } from "@nestjs/common";
type Response = { status: (code: number) => Response };
import { z } from "zod";
import { ApiKeyService, type ApiKeyScope } from "./api-key.service.js";
import { AuditService } from "./audit.service.js";
import { KeycloakGuard, type Principal } from "./auth.js";
import { CONTROL_DB } from "./db.js";
import { EngineClient, type EngineDecisionRun } from "./engine.js";
import { RateLimitService } from "./rate-limit.service.js";
import { ROLE_RANK, type Role } from "./workspace.service.js";
import type { Pool } from "pg";

export type RequestWithPrincipal = {
  principal: Principal;
  keyPrefix?: string;
  keyProjectId?: string;
  keyScopes?: ApiKeyScope[];
};

@Injectable()
export class DecisionGuard implements CanActivate {
  constructor(
    private readonly keycloak: KeycloakGuard,
    private readonly apiKeys: ApiKeyService,
  ) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest<{
      method?: string;
      headers: Record<string, string | undefined>;
      principal?: Principal;
      keyPrefix?: string;
      keyProjectId?: string;
      keyScopes?: ApiKeyScope[];
    }>();
    const token = request.headers.authorization?.startsWith("Bearer ")
      ? request.headers.authorization.slice(7)
      : undefined;
    if (token?.startsWith("oc_dev_")) {
      try {
        const requiredScope: ApiKeyScope =
          request.method?.toUpperCase() === "GET" ? "read" : "classify";
        const verified = await this.apiKeys.verify(token, requiredScope);
        request.principal = { subject: `api-key:${verified.projectId}` };
        request.keyPrefix = token.slice(0, 14);
        request.keyProjectId = verified.projectId;
        request.keyScopes = verified.scopes;
        return true;
      } catch (error) {
        if (error instanceof HttpException) throw error;
        throw new ForbiddenException("API key is invalid or revoked");
      }
    }
    return this.keycloak.canActivate(context);
  }
}

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

const datasetSchema = z.object({
  name: z.string().trim().min(2).max(200),
  description: z.string().trim().max(2000).optional().default(""),
});

const exampleSchema = z.object({
  text: z.string().trim().min(1).max(10_000),
  label: z.string().trim().min(1).max(100),
  source: z.enum(["human", "verified_external"]),
  annotator: z.string().trim().min(2).max(200),
  rationale: z.string().trim().max(2000).optional().default(""),
  slice_tag: z.enum(["historical", "recent", "rare", "hard", "unknown", "adversarial"]).optional().default("historical"),
});

// Genesis integration types are fixed (webhook/rest_api/...); a support
// adapter (zendesk/intercom) is represented as a webhook integration whose
// NAME is the source, routed by /webhooks/{source}.
const integrationSchema = z.object({
  name: z.string().trim().min(2).max(60),
  type: z.enum(["webhook"]),
  secret_ref: z.string().trim().regex(/^[A-Z][A-Z0-9_]{2,}$/).optional(),
  endpoint: z.string().trim().url().optional(),
});

const routeSchema = z.object({
  integration_id: z.string().uuid().optional(),
  match_choice: z.string().trim().min(1).max(100),
  action: z.enum(["tag", "assign_queue"]),
  action_value: z.string().trim().max(200).optional().default(""),
});

const alertRuleSchema = z.object({
  metric: z.enum(["unknown_rate", "recurring_unknowns", "latency", "cost"]),
  threshold: z.number().positive(),
  window: z.string().trim().max(20).optional().default("1h"),
});

const evaluationSchema = z.object({
  dataset_id: z.string().uuid(),
  candidate_id: z.string().uuid(),
  service_id: z.string().optional(),
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
@UseGuards(DecisionGuard)
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
    const project = await this.requireMember(request.principal, workspaceId, projectId, request);
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
    const project = await this.requireMember(request.principal, workspaceId, projectId, request);
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
    const project = await this.requireMember(
      request.principal,
      workspaceId,
      projectId,
      request,
      "classify",
    );
    const rateIdentity = request.keyPrefix ?? request.principal.subject;
    const decision = this.rateLimits.check(rateIdentity, "classify");
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

  @Get("eval-datasets")
  async listDatasets(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string) {
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    return this.engine.listDatasets(project.engine_project_id);
  }

  @Post("eval-datasets")
  async createDataset(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Body() body: unknown,
  ) {
    const input = parseBody(datasetSchema, body);
    const project = await this.requireRole(request.principal, workspaceId, projectId, "admin");
    return this.engine.createDataset(project.engine_project_id, input);
  }

  @Get("eval-datasets/:datasetId")
  async datasetDetail(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string, @Param("datasetId") datasetId: string) {
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    return this.engine.datasetDetail(project.engine_project_id, datasetId);
  }

  @Post("eval-datasets/:datasetId/examples")
  async addExample(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("datasetId") datasetId: string,
    @Body() body: unknown,
  ) {
    const input = parseBody(exampleSchema, body);
    const project = await this.requireRole(request.principal, workspaceId, projectId, "reviewer");
    return this.engine.addExample(project.engine_project_id, datasetId, input);
  }

  @Post("eval-datasets/:datasetId/seal")
  @HttpCode(200)
  async sealDataset(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("datasetId") datasetId: string,
  ) {
    const project = await this.requireRole(request.principal, workspaceId, projectId, "admin");
    const result = await this.engine.sealDataset(project.engine_project_id, datasetId);
    await this.audit.record({
      workspaceId,
      projectId,
      actor: request.principal.subject,
      action: "evaluation.dataset_sealed",
      target: `dataset:${datasetId.slice(0, 8)}`,
    });
    return result;
  }

  @Get("evaluations")
  async listEvaluations(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string) {
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    return this.engine.listEvaluations(project.engine_project_id);
  }

  @Post("evaluations")
  async runEvaluation(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Body() body: unknown,
  ) {
    const input = parseBody(evaluationSchema, body);
    const project = await this.requireRole(request.principal, workspaceId, projectId, "admin");
    const result = await this.engine.runEvaluation(project.engine_project_id, input);
    await this.audit.record({
      workspaceId,
      projectId,
      actor: request.principal.subject,
      action: "evaluation.run",
      target: `candidate:${input.candidate_id.slice(0, 8)}`,
    });
    return result;
  }

  @Get("evaluations/:evaluationId")
  async evaluationDetail(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string, @Param("evaluationId") evaluationId: string) {
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    return this.engine.evaluationDetail(project.engine_project_id, evaluationId);
  }

  @Get("analytics/summary")
  async analyticsSummary(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string) {
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    return this.engine.analyticsSummary(project.engine_project_id);
  }

  @Get("alerts/rules")
  async listAlertRules(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string) {
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    return this.engine.listAlertRules(project.engine_project_id);
  }

  @Post("alerts/rules")
  async createAlertRule(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Body() body: unknown,
  ) {
    const input = parseBody(alertRuleSchema, body);
    const project = await this.requireRole(request.principal, workspaceId, projectId, "admin");
    return this.engine.createAlertRule(project.engine_project_id, input);
  }

  @Post("alerts/evaluate")
  @HttpCode(200)
  async evaluateAlerts(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string) {
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    return this.engine.evaluateAlerts(project.engine_project_id);
  }

  @Get("ops/events")
  async opsEvents(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Query("after") after?: string,
  ) {
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    return this.engine.opsEvents(project.engine_project_id, after);
  }

  @Get("integrations")
  async listIntegrations(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string) {
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    return this.engine.listIntegrations(project.engine_project_id);
  }

  @Post("integrations")
  async createIntegration(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Body() body: unknown,
  ) {
    const input = parseBody(integrationSchema, body);
    const project = await this.requireRole(request.principal, workspaceId, projectId, "admin");
    const created = await this.engine.createIntegration(project.engine_project_id, input);
    await this.audit.record({
      workspaceId,
      projectId,
      actor: request.principal.subject,
      action: "integration.connected",
      target: `integration:${input.name}:${input.type}`,
    });
    return created;
  }

  @Get("integrations/adapters")
  async listAdapters(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string) {
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    return this.engine.listAdapters(project.engine_project_id);
  }

  @Get("integrations/routes")
  async listRoutes(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string) {
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    return this.engine.listRoutes(project.engine_project_id);
  }

  @Post("integrations/routes")
  async createRoute(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Body() body: unknown,
  ) {
    const input = parseBody(routeSchema, body);
    if (input.integration_id === undefined) throw new BadRequestException("integration_id is required");
    const project = await this.requireRole(request.principal, workspaceId, projectId, "admin");
    return this.engine.createRoute(project.engine_project_id, input.integration_id, {
      match_choice: input.match_choice,
      action: input.action,
      action_value: input.action_value,
    });
  }

  @Get("integrations/outcomes")
  async routingOutcomes(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string) {
    const project = await this.requireMember(request.principal, workspaceId, projectId);
    return this.engine.routingOutcomes(project.engine_project_id);
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

  private async requireMember(
    principal: Principal,
    workspaceId: string,
    projectId: string,
    request?: RequestWithPrincipal,
    requiredScope: ApiKeyScope = "read",
  ) {
    if (request?.keyProjectId && request.keyProjectId !== projectId) {
      throw new NotFoundException("Project not found");
    }
    if (
      request?.keyProjectId &&
      request.keyScopes &&
      !request.keyScopes.includes(requiredScope) &&
      !request.keyScopes.includes("admin")
    ) {
      throw new ForbiddenException(`API key is missing the '${requiredScope}' scope`);
    }
    const membership = await this.db.query(
      "SELECT role FROM control_workspace_memberships WHERE workspace_id = $1 AND subject = $2",
      [workspaceId, principal.subject],
    );
    if (!membership.rowCount) {
      if (request?.keyProjectId) {
        const project = await this.projectOf(workspaceId, projectId);
        if (!project) throw new NotFoundException("Project not found");
        return project;
      }
      throw new NotFoundException("Workspace not found");
    }
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
