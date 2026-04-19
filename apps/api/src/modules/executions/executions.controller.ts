import { Body, Controller, Get, Param, Post } from "@nestjs/common";
import { Roles } from "../../common/auth/roles.decorator";
import { ExecuteTestCaseDto } from "./dto";
import { ExecutionsService } from "./executions.service";

@Controller()
export class ExecutionsController {
  constructor(private readonly executionsService: ExecutionsService) {}

  @Post("test-cases/:tcId/execute")
  @Roles("owner", "tester")
  execute(@Param("tcId") testCaseId: string, @Body() body: ExecuteTestCaseDto) {
    return this.executionsService.execute(testCaseId, body);
  }

  @Get("executions/:execId")
  get(@Param("execId") executionId: string) {
    return this.executionsService.get(executionId);
  }

  @Get("executions/:execId/results")
  results(@Param("execId") executionId: string) {
    return this.executionsService.results(executionId);
  }

  @Get("projects/:id/executions")
  history(@Param("id") projectId: string) {
    return this.executionsService.history(projectId);
  }
}
