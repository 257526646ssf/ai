import { Module } from "@nestjs/common";
import { PrismaService } from "../../infra/prisma.service";
import { JobsModule } from "../jobs/jobs.module";
import { TestCasesController } from "./test-cases.controller";
import { TestCasesService } from "./test-cases.service";

@Module({
  imports: [JobsModule],
  controllers: [TestCasesController],
  providers: [TestCasesService, PrismaService],
  exports: [TestCasesService],
})
export class TestCasesModule {}
