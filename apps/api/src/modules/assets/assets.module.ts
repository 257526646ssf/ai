import { Module } from "@nestjs/common";
import { PrismaService } from "../../infra/prisma.service";
import { JobsModule } from "../jobs/jobs.module";
import { AssetsController } from "./assets.controller";
import { AssetsService } from "./assets.service";

@Module({
  imports: [JobsModule],
  controllers: [AssetsController],
  providers: [AssetsService, PrismaService],
  exports: [AssetsService],
})
export class AssetsModule {}
