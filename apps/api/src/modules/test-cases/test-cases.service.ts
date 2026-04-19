import { Injectable } from "@nestjs/common";
import { Prisma } from "@prisma/client";
import { PrismaService } from "../../infra/prisma.service";
import { JobsService } from "../jobs/jobs.service";
import { CreateTestCaseDto, GenerateTestCasesDto, UpdateTestCaseDto } from "./dto";
import { validateGeneratedTestCase } from "./quality-gate";

@Injectable()
export class TestCasesService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly jobsService: JobsService,
  ) {}

  async generate(projectId: string, input: GenerateTestCasesDto) {
    const job = await this.jobsService.create({
      type: "testcase.generate",
      payload: { projectId, ...input },
    });

    return { jobId: job.id, status: job.status };
  }

  async createFromAi(projectId: string, rawCase: unknown) {
    const { parsed, warnings } = validateGeneratedTestCase(rawCase);
    const record = await this.prisma.testCase.create({
      data: {
        projectId,
        title: parsed.title,
        module: parsed.module,
        priority: parsed.priority,
        type: parsed.type,
        preconditions: parsed.preconditions,
        steps: parsed.steps,
        tags: parsed.tags,
        source: parsed.source,
        aiConfidence: parsed.confidence,
        reviewReport: { warnings, needsSelectorReview: parsed.needsSelectorReview },
      },
    });

    return { record, warnings };
  }

  createManual(projectId: string, input: CreateTestCaseDto) {
    return this.prisma.testCase.create({
      data: {
        projectId,
        title: input.title,
        module: input.module,
        priority: input.priority,
        type: input.type,
        preconditions: input.preconditions,
        steps: input.steps as Prisma.InputJsonValue,
        tags: input.tags,
        source: input.source || "manual",
        aiConfidence: input.confidence,
        status: "ready",
      },
    });
  }

  list(projectId: string) {
    return this.prisma.testCase.findMany({ where: { projectId }, orderBy: { createdAt: "desc" } });
  }

  get(id: string) {
    return this.prisma.testCase.findUnique({ where: { id } });
  }

  update(id: string, input: UpdateTestCaseDto) {
    return this.prisma.testCase.update({
      where: { id },
      data: {
        ...input,
        steps: input.steps as Prisma.InputJsonValue | undefined,
      },
    });
  }
}
