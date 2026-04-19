import { Controller, Get, Param, Query } from "@nestjs/common";
import { ReportsService } from "./reports.service";

@Controller()
export class ReportsController {
  constructor(private readonly reportsService: ReportsService) {}

  @Get("projects/:id/reports/summary")
  summary(@Param("id") projectId: string) {
    return this.reportsService.projectSummary(projectId);
  }

  @Get("executions/:execId/report")
  executionReport(@Param("execId") executionId: string) {
    return this.reportsService.executionReport(executionId);
  }

  @Get("reports/:reportId/export")
  exportReport(@Param("reportId") reportId: string, @Query("format") format: "json" | "markdown" = "json") {
    return this.reportsService.exportReport(reportId, format);
  }
}
