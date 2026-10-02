import { Controller, Get } from "@nestjs/common";

/** Control-plane boundary. It does not duplicate any FastAPI decision logic. */
@Controller("control")
export class PortalController {
  @Get("health")
  health() { return { status: "ready", service: "openclass-control-plane" }; }

  @Get("portal-phase")
  portalPhase() {
    return { phase: 1, status: "foundation", simulated: true, capabilities: ["portal-shell", "project-navigation"] };
  }
}
