import { Controller, Get } from "@nestjs/common";

@Controller()
export class HealthController {
  @Get("health")
  getHealth() {
    return { status: "ok", service: "api", timestamp: new Date().toISOString() };
  }
}
