import { InjectQueue } from "@nestjs/bullmq";
import { Injectable } from "@nestjs/common";
import { Prisma } from "@prisma/client";
import { Queue } from "bullmq";
import { PrismaService } from "../../infra/prisma.service";
import { CreateJobDto } from "./dto";

@Injectable()
export class JobsService {
  constructor(
    private readonly prisma: PrismaService,
    @InjectQueue("jobs") private readonly jobsQueue: Queue,
  ) {}

  async create(input: CreateJobDto) {
    const job = await this.prisma.job.create({
      data: { type: input.type, payload: input.payload as Prisma.InputJsonValue, status: "queued" },
    });

    await this.jobsQueue.add(input.type, { id: job.id, ...input.payload }, { removeOnComplete: 100, attempts: 3 });
    return job;
  }

  get(id: string) {
    return this.prisma.job.findUnique({ where: { id } });
  }

  async markProcessing(id: string) {
    return this.prisma.job.update({ where: { id }, data: { status: "processing", progress: 25 } });
  }

  async markCompleted(id: string, result: Record<string, unknown>) {
    return this.prisma.job.update({
      where: { id },
      data: { status: "completed", progress: 100, result: result as Prisma.InputJsonValue },
    });
  }

  async markFailed(id: string, error: string) {
    return this.prisma.job.update({ where: { id }, data: { status: "failed", error } });
  }
}
