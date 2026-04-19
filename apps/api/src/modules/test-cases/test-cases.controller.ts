import { Body, Controller, Get, Param, Post, Put } from "@nestjs/common";
import { Roles } from "../../common/auth/roles.decorator";
import { CreateTestCaseDto, GenerateTestCasesDto, UpdateTestCaseDto } from "./dto";
import { TestCasesService } from "./test-cases.service";

@Controller()
export class TestCasesController {
  constructor(private readonly testCasesService: TestCasesService) {}

  @Post("projects/:id/test-cases/generate")
  @Roles("owner", "tester")
  generate(@Param("id") projectId: string, @Body() body: GenerateTestCasesDto) {
    return this.testCasesService.generate(projectId, body);
  }

  @Post("projects/:id/test-cases")
  @Roles("owner", "tester")
  createManual(@Param("id") projectId: string, @Body() body: CreateTestCaseDto) {
    return this.testCasesService.createManual(projectId, body);
  }

  @Get("projects/:id/test-cases")
  list(@Param("id") projectId: string) {
    return this.testCasesService.list(projectId);
  }

  @Get("test-cases/:tcId")
  get(@Param("tcId") tcId: string) {
    return this.testCasesService.get(tcId);
  }

  @Put("test-cases/:tcId")
  @Roles("owner", "tester")
  update(@Param("tcId") tcId: string, @Body() body: UpdateTestCaseDto) {
    return this.testCasesService.update(tcId, body);
  }
}
