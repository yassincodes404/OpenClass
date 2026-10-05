import { Module } from "@nestjs/common";
import { PortalController } from "./portal.controller.js";
import { KeycloakGuard } from "./auth.js";
import { CONTROL_DB, createControlPool } from "./db.js";
import { WorkspaceController } from "./workspace.controller.js";
import { WorkspaceService } from "./workspace.service.js";

@Module({
  controllers: [PortalController, WorkspaceController],
  providers: [KeycloakGuard, WorkspaceService, { provide: CONTROL_DB, useFactory: createControlPool }],
})
export class AppModule {}
