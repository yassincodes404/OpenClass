import { Module } from "@nestjs/common";
import { PortalController } from "./portal.controller.js";
import { ApiKeyService } from "./api-key.service.js";
import { AuditService } from "./audit.service.js";
import { KeycloakGuard } from "./auth.js";
import { CONTROL_DB, createControlPool } from "./db.js";
import { EngineClient } from "./engine.js";
import { IdempotencyService } from "./idempotency.service.js";
import { IngestionController } from "./ingestion.controller.js";
import { IngestionGuard, IngestionService } from "./ingestion.service.js";
import { ProjectController, ProjectResolveController } from "./project.controller.js";
import { ProjectService } from "./project.service.js";
import { RateLimitService } from "./rate-limit.service.js";
import { SecurityController } from "./security.controller.js";
import { WorkspaceController } from "./workspace.controller.js";
import { WorkspaceService } from "./workspace.service.js";

@Module({
  controllers: [
    PortalController,
    WorkspaceController,
    ProjectController,
    ProjectResolveController,
    SecurityController,
    IngestionController,
  ],
  providers: [
    KeycloakGuard,
    WorkspaceService,
    ProjectService,
    ApiKeyService,
    AuditService,
    IdempotencyService,
    EngineClient,
    RateLimitService,
    IngestionGuard,
    IngestionService,
    { provide: CONTROL_DB, useFactory: createControlPool },
  ],
})
export class AppModule {}
