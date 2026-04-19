import { Injectable } from "@nestjs/common";
import { FailureCategory } from "@ai-test-agent/shared";
import { PrismaService } from "../../infra/prisma.service";

@Injectable()
export class ReportsService {
  constructor(private readonly prisma: PrismaService) {}

  async projectSummary(projectId: string) {
    const executions = await this.prisma.executionRecord.findMany({ where: { projectId } });
    const total = executions.length;
    const passed = executions.filter((item: { status: string }) => item.status === "passed").length;
    const failed = executions.filter((item: { status: string }) => item.status === "failed").length;

    return {
      projectId,
      total,
      passed,
      failed,
      passRate: total > 0 ? Number(((passed / total) * 100).toFixed(2)) : 0,
    };
  }

  async executionReport(executionId: string) {
    const execution = await this.prisma.executionRecord.findUnique({ where: { id: executionId } });
    const steps = await this.prisma.stepResult.findMany({ where: { executionId }, orderBy: { stepOrder: "asc" } });

    const failureCategory: FailureCategory = this.classifyFailure(execution?.errorLog || "");

    return {
      execution,
      steps,
      failureCategory,
      suggestion: this.suggestFix(failureCategory),
    };
  }

  async exportReport(executionId: string, format: "json" | "markdown") {
    const report = await this.executionReport(executionId);

    if (format === "json") {
      return report;
    }

    return {
      markdown: [
        `# Execution Report ${executionId}`,
        `- Status: ${report.execution?.status || "unknown"}`,
        `- Failure Category: ${report.failureCategory}`,
        `- Suggestion: ${report.suggestion}`,
      ].join("\n"),
    };
  }

  private classifyFailure(errorLog: string): FailureCategory {
    if (/selector|not found/i.test(errorLog)) return "selector_not_found";
    if (/assert/i.test(errorLog)) return "assertion_failed";
    if (/timeout|timed out/i.test(errorLog)) return "network_timeout";
    if (/crash/i.test(errorLog)) return "page_crash";
    return "env_error";
  }

  private suggestFix(category: FailureCategory): string {
    const map: Record<FailureCategory, string> = {
      selector_not_found: "Update selector with stable data-testid or semantic locator.",
      assertion_failed: "Re-check expected result and wait conditions.",
      network_timeout: "Increase timeout or mock unstable network dependency.",
      page_crash: "Inspect browser console logs and frontend runtime errors.",
      env_error: "Verify environment variables and target URL accessibility.",
    };

    return map[category];
  }
}
