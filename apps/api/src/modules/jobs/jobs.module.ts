import { BullModule } from "@nestjs/bullmq";
import { Module } from "@nestjs/common";
import { PrismaService } from "../../infra/prisma.service";
import { JobsController } from "./jobs.controller";
import { JobsProcessor } from "./jobs.processor";
import { JobsService } from "./jobs.service";

@Module({
  imports: [BullModule.registerQueue({ name: "jobs" })],
  controllers: [JobsController],
  providers: [JobsService, JobsProcessor, PrismaService],
  exports: [JobsService],
})
export class JobsModule {}
