import { Module } from "@nestjs/common";
import { PrismaService } from "../../infra/prisma.service";
import { ReportsController } from "./reports.controller";
import { ReportsService } from "./reports.service";

@Module({
  controllers: [ReportsController],
  providers: [ReportsService, PrismaService],
})
export class ReportsModule {}
