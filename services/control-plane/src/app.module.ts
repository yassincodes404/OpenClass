import { Module } from "@nestjs/common";
import { PortalController } from "./portal.controller.js";
import { ApiKeyService } from "./api-key.service.js";
import { KeycloakGuard } from "./auth.js";
import { CONTROL_DB, createControlPool } from "./db.js";
import { EngineClient } from "./engine.js";
import { ProjectController, ProjectResolveController } from "./project.controller.js";
import { ProjectService } from "./project.service.js";
import { WorkspaceController } from "./workspace.controller.js";
import { WorkspaceService } from "./workspace.service.js";

@Module({
  controllers: [PortalController, WorkspaceController, ProjectController, ProjectResolveController],
  providers: [KeycloakGuard, WorkspaceService, ProjectService, ApiKeyService, EngineClient, { provide: CONTROL_DB, useFactory: createControlPool }],
})
export class AppModule {}
