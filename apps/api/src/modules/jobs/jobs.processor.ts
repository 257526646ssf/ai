import { Processor, WorkerHost } from "@nestjs/bullmq";
import { Prisma } from "@prisma/client";
import { Job } from "bullmq";
import { PrismaService } from "../../infra/prisma.service";
import { validateGeneratedTestCase } from "../test-cases/quality-gate";
import { JobsService } from "./jobs.service";

@Processor("jobs")
export class JobsProcessor extends WorkerHost {
  constructor(
    private readonly jobsService: JobsService,
    private readonly prisma: PrismaService,
  ) {
    super();
  }

  async process(job: Job<Record<string, unknown>>) {
    const id = String(job.data.id || "");

    try {
      if (id) {
        await this.jobsService.markProcessing(id);
      }

      if (job.name === "asset.parse") {
        await this.handleAssetParse(job.data);
      }

      if (job.name === "testcase.generate") {
        await this.handleTestCaseGenerate(job.data);
      }

      if (job.name === "execution.run") {
        await this.handleExecutionRun(job.data);
      }

      if (job.name === "report.build") {
        // Placeholder for future async report rendering.
      }

      if (id) {
        await this.jobsService.markCompleted(id, { acceptedAt: new Date().toISOString(), queueName: job.name });
      }
      return { ok: true };
    } catch (error) {
      if (id) {
        await this.jobsService.markFailed(id, error instanceof Error ? error.message : "unknown error");
      }
      throw error;
    }
  }

  private async handleAssetParse(payload: Record<string, unknown>) {
    const aiUrl = process.env.AI_SERVICE_URL || "http://localhost:8000";

    const response = await fetch(`${aiUrl}/parse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        asset_id: payload.assetId,
        project_id: payload.projectId,
        asset_type: payload.assetType,
        text: "",
      }),
    });

    const parsed = (await response.json()) as { summary?: string; ocrText?: string };

    await this.prisma.requirementAsset.update({
      where: { id: String(payload.assetId) },
      data: {
        parsedContent: parsed,
        ocrText: parsed.ocrText || null,
      },
    });
  }

  private async handleTestCaseGenerate(payload: Record<string, unknown>) {
    const aiUrl = process.env.AI_SERVICE_URL || "http://localhost:8000";
    const projectId = String(payload.projectId);

    const response = await fetch(`${aiUrl}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: projectId,
        requirement_summary: "Generate initial cases from uploaded assets",
        focus_modules: (payload.options as Record<string, unknown> | undefined)?.focusModules || [],
      }),
    });

    const generated = (await response.json()) as { cases: unknown[] };

    for (const rawCase of generated.cases || []) {
      const { parsed, warnings } = validateGeneratedTestCase(rawCase);

      await this.prisma.testCase.create({
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
          status: "ready",
        },
      });
    }
  }

  private async handleExecutionRun(payload: Record<string, unknown>) {
    const runnerUrl = process.env.RUNNER_URL || "http://localhost:8100";
    const executionId = String(payload.executionId);

    const execution = await this.prisma.executionRecord.findUniqueOrThrow({ where: { id: executionId } });
    const testCase = await this.prisma.testCase.findUniqueOrThrow({ where: { id: execution.testCaseId } });
    const project = await this.prisma.project.findUniqueOrThrow({ where: { id: execution.projectId } });

    await this.prisma.executionRecord.update({
      where: { id: executionId },
      data: { status: "running" },
    });

    const response = await fetch(`${runnerUrl}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        executionId,
        baseUrl: project.baseUrl,
        headless: execution.headless,
        retries: 2,
        steps: testCase.steps,
      }),
    });

    const result = (await response.json()) as {
      status: "passed" | "failed";
      logs: Array<Record<string, unknown>>;
      screenshots: string[];
      errorLog?: string;
    };

    for (const log of result.logs || []) {
      const isStep = log.type === "step";
      if (!isStep) continue;

      await this.prisma.stepResult.create({
        data: {
          executionId,
          stepOrder: Number(log.order || 0),
          action: "step",
          status: String(log.status) === "passed" ? "passed" : "failed",
          errorMessage: log.message ? String(log.message) : null,
          retryCount: Number(log.attempt || 0),
        },
      });
    }

    await this.prisma.executionEvent.create({
      data: {
        executionId,
        type: "execution.finished",
        payload: result as unknown as Prisma.InputJsonValue,
      },
    });

    await this.prisma.executionRecord.update({
      where: { id: executionId },
      data: {
        status: result.status,
        endTime: new Date(),
        errorLog: result.errorLog || null,
        finalScreenshotUrl: result.screenshots?.[result.screenshots.length - 1] || null,
      },
    });
  }
}
