import { Module } from "@nestjs/common";
import { PortalController } from "./portal.controller.js";

@Module({ controllers: [PortalController] })
export class AppModule {}
