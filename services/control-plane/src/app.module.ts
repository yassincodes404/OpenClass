import { Module } from "@nestjs/common";
import { APP_FILTER, APP_INTERCEPTOR } from "@nestjs/core";
import { MutationInterceptor } from "./mutation.interceptor.js";
import { SafeExceptionFilter } from "./safe-exception.filter.js";
import { PortalController } from "./portal.controller.js";
import { ApiKeyService } from "./api-key.service.js";
import { AuditService } from "./audit.service.js";
import { KeycloakGuard } from "./auth.js";
import { CONTROL_DB, createControlPool } from "./db.js";
import { EngineClient } from "./engine.js";
import { IdempotencyService } from "./idempotency.service.js";
import { DecisionController, DecisionGuard } from "./decision.controller.js";
import { IngestionController } from "./ingestion.controller.js";
import { IngestionGuard, IngestionService } from "./ingestion.service.js";
import { ProjectController, ProjectResolveController } from "./project.controller.js";
import { ProjectService } from "./project.service.js";
import { RateLimitService } from "./rate-limit.service.js";
import { SecurityController } from "./security.controller.js";
import { UnknownController } from "./unknown.controller.js";
import { WorkspaceController } from "./workspace.controller.js";
import { WorkspaceService } from "./workspace.service.js";
import { WorkflowController } from "./workflow.controller.js";

@Module({
  controllers: [
    PortalController,
    WorkspaceController,
    ProjectController,
    ProjectResolveController,
    SecurityController,
    IngestionController,
    DecisionController,
    UnknownController,
    WorkflowController,
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
    DecisionGuard,
    IngestionService,
    { provide: CONTROL_DB, useFactory: createControlPool },
    { provide: APP_INTERCEPTOR, useClass: MutationInterceptor },
    { provide: APP_FILTER, useClass: SafeExceptionFilter },
  ],
})
export class AppModule {}
