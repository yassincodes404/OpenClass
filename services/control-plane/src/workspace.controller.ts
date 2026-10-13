import {
  BadRequestException,
  Body,
  Controller,
  Get,
  HttpCode,
  Param,
  Post,
  Req,
  UseGuards,
} from "@nestjs/common";
import { z } from "zod";
import { KeycloakGuard, type Principal } from "./auth.js";
import { WorkspaceService } from "./workspace.service.js";

type RequestWithPrincipal = { principal: Principal };

const createSchema = z.object({ name: z.string().trim().min(2).max(200) });
const memberSchema = z.object({
  subject: z.string().trim().min(1).max(200),
  role: z.enum(["owner", "admin", "reviewer", "analyst", "developer", "viewer"]),
});

function parseBody<T>(schema: z.ZodType<T>, body: unknown): T {
  const result = schema.safeParse(body);
  if (!result.success) throw new BadRequestException("Invalid request body");
  return result.data;
}

@Controller("control/workspaces")
@UseGuards(KeycloakGuard)
export class WorkspaceController {
  constructor(private readonly workspaces: WorkspaceService) {}

  @Get()
  mine(@Req() request: RequestWithPrincipal) {
    return this.workspaces.mine(request.principal);
  }

  @Post()
  create(@Req() request: RequestWithPrincipal, @Body() body: unknown) {
    return this.workspaces.create(request.principal, parseBody(createSchema, body).name);
  }

  @Get(":id/members")
  members(@Req() request: RequestWithPrincipal, @Param("id") id: string) {
    return this.workspaces.members(request.principal, id);
  }

  @Post(":id/members")
  @HttpCode(200)
  invite(@Req() request: RequestWithPrincipal, @Param("id") id: string, @Body() body: unknown) {
    const member = parseBody(memberSchema, body);
    return this.workspaces.invite(request.principal, id, member.subject, member.role);
  }
}
