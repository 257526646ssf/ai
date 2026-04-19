import { Module } from "@nestjs/common";
import { PrismaService } from "../../infra/prisma.service";
import { JobsModule } from "../jobs/jobs.module";
import { ExecutionsController } from "./executions.controller";
import { ExecutionsService } from "./executions.service";

@Module({
  imports: [JobsModule],
  controllers: [ExecutionsController],
  providers: [ExecutionsService, PrismaService],
})
export class ExecutionsModule {}
