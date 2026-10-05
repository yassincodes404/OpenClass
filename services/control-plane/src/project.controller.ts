import { BadRequestException, Body, Controller, Get, HttpCode, Param, Post, Req, UseGuards } from "@nestjs/common";
import { z } from "zod";
import { API_KEY_SCOPES } from "./api-key.service.js";
import { KeycloakGuard, type Principal } from "./auth.js";
import { ProjectService } from "./project.service.js";

type RequestWithPrincipal = { principal: Principal };

const classSchema = z.object({
  canonical_name: z.string().trim().min(1).max(80),
  display_name: z.string().trim().min(1).max(200),
  aliases: z.array(z.string().trim().min(1).max(80)).max(50).optional(),
});

const createProjectSchema = z.object({
  name: z.string().trim().min(2).max(200),
  description: z.string().trim().max(2000).optional().default(""),
});

const createClassifierSchema = z.object({
  name: z.string().trim().min(2).max(200),
  slug: z
    .string()
    .trim()
    .regex(/^[a-z][a-z0-9-]{0,79}$/, "slug must be lowercase kebab-case")
    .optional(),
  description: z.string().trim().max(4000).optional().default(""),
  classes: z.array(classSchema).min(1).max(1000),
  // UNKNOWN is a permanent fallback state; opting out is a 400 by design.
  unknown_fallback: z.literal(true).default(true),
});

const createKeySchema = z.object({
  scopes: z.array(z.enum(API_KEY_SCOPES)).min(1).default(["ingest", "read"]),
});

function parseBody<T>(schema: z.ZodType<T>, body: unknown): T {
  const result = schema.safeParse(body);
  if (!result.success) throw new BadRequestException("Invalid request body");
  return result.data;
}

@Controller("control/workspaces/:workspaceId/projects")
@UseGuards(KeycloakGuard)
export class ProjectController {
  constructor(private readonly projects: ProjectService) {}

  @Get()
  list(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string) {
    return this.projects.list(request.principal, workspaceId);
  }

  @Post()
  create(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Body() body: unknown) {
    const input = parseBody(createProjectSchema, body);
    return this.projects.create(request.principal, workspaceId, input.name, input.description);
  }

  @Get(":projectId")
  get(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string) {
    return this.projects.get(request.principal, workspaceId, projectId);
  }

  @Get(":projectId/classifiers")
  listClassifiers(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string) {
    return this.projects.listClassifiers(request.principal, workspaceId, projectId);
  }

  @Post(":projectId/classifiers")
  createClassifier(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Body() body: unknown,
  ) {
    const input = parseBody(createClassifierSchema, body);
    return this.projects.createClassifier(request.principal, workspaceId, projectId, {
      name: input.name,
      slug: input.slug,
      description: input.description,
      classes: input.classes,
      unknownFallback: input.unknown_fallback,
    });
  }

  @Get(":projectId/classifiers/:classifierId")
  getClassifier(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("classifierId") classifierId: string,
  ) {
    return this.projects.getClassifier(request.principal, workspaceId, projectId, classifierId);
  }

  @Post(":projectId/keys")
  createKey(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Body() body: unknown,
  ) {
    const input = parseBody(createKeySchema, body);
    return this.projects.createKey(request.principal, workspaceId, projectId, input.scopes);
  }

  @Get(":projectId/keys")
  listKeys(@Req() request: RequestWithPrincipal, @Param("workspaceId") workspaceId: string, @Param("projectId") projectId: string) {
    return this.projects.listKeys(request.principal, workspaceId, projectId);
  }

  @Post(":projectId/keys/:keyId/revoke")
  @HttpCode(200)
  revokeKey(
    @Req() request: RequestWithPrincipal,
    @Param("workspaceId") workspaceId: string,
    @Param("projectId") projectId: string,
    @Param("keyId") keyId: string,
  ) {
    return this.projects.revokeKey(request.principal, workspaceId, projectId, keyId);
  }
}

/** Portal deep links resolve a project by control id across the caller's workspaces. */
@Controller("control/projects")
@UseGuards(KeycloakGuard)
export class ProjectResolveController {
  constructor(private readonly projects: ProjectService) {}

  @Get(":projectId")
  resolve(@Req() request: RequestWithPrincipal, @Param("projectId") projectId: string) {
    return this.projects.resolve(request.principal, projectId);
  }
}
