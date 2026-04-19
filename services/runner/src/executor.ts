import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";
import type { RunRequest, RunResult } from "./types";

export async function runExecution(input: RunRequest): Promise<RunResult> {
  const browser = await chromium.launch({ headless: input.headless ?? true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const page = await context.newPage();

  const logs: Array<Record<string, unknown>> = [];
  const screenshots: string[] = [];
  const outputDir = path.resolve(process.cwd(), ".playwright", input.executionId);
  await fs.mkdir(outputDir, { recursive: true });

  page.on("console", (msg) => logs.push({ type: "console", level: msg.type(), text: msg.text() }));
  page.on("requestfailed", (req) => logs.push({ type: "network", url: req.url(), failure: req.failure()?.errorText }));

  try {
    for (const step of input.steps.sort((a, b) => a.order - b.order)) {
      const retryMax = input.retries ?? 2;
      let done = false;
      let lastError: Error | null = null;

      for (let attempt = 0; attempt <= retryMax && !done; attempt += 1) {
        try {
          await executeStep(page, input.baseUrl, step);
          const screenshotPath = path.join(outputDir, `step-${step.order}.png`);
          await page.screenshot({ path: screenshotPath, fullPage: true });
          screenshots.push(screenshotPath);
          logs.push({ type: "step", order: step.order, status: "passed", attempt });
          done = true;
        } catch (error) {
          lastError = error as Error;
          logs.push({ type: "step", order: step.order, status: "failed", attempt, message: lastError.message });
        }
      }

      if (!done && lastError) {
        throw lastError;
      }
    }

    await browser.close();
    return { executionId: input.executionId, status: "passed", logs, screenshots };
  } catch (error) {
    await browser.close();
    return {
      executionId: input.executionId,
      status: "failed",
      logs,
      screenshots,
      errorLog: error instanceof Error ? error.message : "unknown error",
    };
  }
}

async function executeStep(page: import("playwright").Page, baseUrl: string, step: RunRequest["steps"][number]) {
  const action = step.action.toLowerCase();
  const resolvedValue = resolveStepValue(step);

  if (action.startsWith("goto")) {
    const target = resolvedValue || action.replace("goto", "").trim() || "/";
    await page.goto(`${baseUrl}${target}`);
    return;
  }

  if (action.startsWith("click") && step.selector) {
    await page.click(step.selector);
    return;
  }

  if (action.startsWith("fill") && step.selector) {
    await page.fill(step.selector, resolvedValue || "");
    return;
  }

  if (action.startsWith("select") && step.selector) {
    await page.selectOption(step.selector, resolvedValue || "");
    return;
  }

  if (action.startsWith("wait")) {
    if (step.selector) {
      await page.waitForSelector(step.selector, { timeout: 30000 });
    } else {
      await page.waitForTimeout(Number(resolvedValue || 300));
    }
    return;
  }

  if (action.startsWith("assert") && step.selector && step.expected) {
    const text = await page.textContent(step.selector);
    if (!text?.includes(step.expected)) {
      throw new Error(`Assertion failed: expected ${step.expected}, got ${text}`);
    }
    return;
  }

  throw new Error(`Unsupported step action: ${step.action}`);
}

function resolveStepValue(step: RunRequest["steps"][number]): string {
  if (typeof step.value === "string") {
    return step.value;
  }

  if (step.data && typeof step.data === "object") {
    const directValue = (step.data as Record<string, unknown>).value;
    const pathValue = (step.data as Record<string, unknown>).path;
    if (typeof directValue === "string") return directValue;
    if (typeof pathValue === "string") return pathValue;
  }

  if (typeof step.data === "string") {
    return step.data;
  }

  return "";
}
