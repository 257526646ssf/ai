import { Injectable } from "@nestjs/common";
import { PrismaService } from "../../infra/prisma.service";
import { JobsService } from "../jobs/jobs.service";
import { ExecuteTestCaseDto } from "./dto";

@Injectable()
export class ExecutionsService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly jobsService: JobsService,
  ) {}

  async execute(testCaseId: string, input: ExecuteTestCaseDto) {
    const testCase = await this.prisma.testCase.findUniqueOrThrow({ where: { id: testCaseId } });

    const execution = await this.prisma.executionRecord.create({
      data: {
        projectId: testCase.projectId,
        testCaseId: testCase.id,
        status: "queued",
        headless: input.options?.headless ?? true,
        startTime: new Date(),
      },
    });

    const job = await this.jobsService.create({
      type: "execution.run",
      payload: {
        executionId: execution.id,
        testCaseId,
        environmentId: input.environmentId,
        options: input.options ?? {},
      },
    });

    await this.prisma.executionEvent.create({
      data: {
        executionId: execution.id,
        type: "execution.started",
        payload: { jobId: job.id },
      },
    });

    return { executionId: execution.id, jobId: job.id };
  }

  get(executionId: string) {
    return this.prisma.executionRecord.findUnique({ where: { id: executionId } });
  }

  async results(executionId: string) {
    const execution = await this.prisma.executionRecord.findUnique({ where: { id: executionId } });
    const steps = await this.prisma.stepResult.findMany({ where: { executionId }, orderBy: { stepOrder: "asc" } });
    const events = await this.prisma.executionEvent.findMany({ where: { executionId }, orderBy: { createdAt: "asc" } });

    return { execution, steps, events };
  }

  history(projectId: string) {
    return this.prisma.executionRecord.findMany({ where: { projectId }, orderBy: { createdAt: "desc" } });
  }
}
