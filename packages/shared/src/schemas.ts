import { z } from "zod";

export const FailureCategorySchema = z.enum([
  "selector_not_found",
  "assertion_failed",
  "network_timeout",
  "page_crash",
  "env_error",
]);

export type FailureCategory = z.infer<typeof FailureCategorySchema>;

export const TestStepSchema = z.object({
  order: z.number().int().nonnegative(),
  action: z.string().min(1),
  expected: z.string().min(1),
  selector: z.string().optional().nullable(),
  data: z.record(z.string(), z.any()).optional(),
});

export const TestCaseSchema = z.object({
  id: z.string().optional(),
  title: z.string().min(3),
  module: z.string().min(1),
  priority: z.enum(["P0", "P1", "P2", "P3"]),
  type: z.enum(["functional", "boundary", "exception", "ui", "performance", "compatibility"]),
  preconditions: z.array(z.string()).default([]),
  steps: z.array(TestStepSchema).min(1),
  tags: z.array(z.string()).default([]),
  source: z.enum(["ai", "manual", "imported"]).default("ai"),
  confidence: z.number().min(0).max(1).optional(),
  needsSelectorReview: z.boolean().default(false),
});

export type TestCase = z.infer<typeof TestCaseSchema>;

export const ExecutionEventSchema = z.object({
  executionId: z.string(),
  type: z.enum([
    "execution.started",
    "step.started",
    "step.passed",
    "step.failed",
    "execution.finished",
  ]),
  timestamp: z.string(),
  payload: z.record(z.string(), z.any()).default({}),
});

export type ExecutionEvent = z.infer<typeof ExecutionEventSchema>;

export const JobStatusSchema = z.enum([
  "queued",
  "processing",
  "completed",
  "failed",
]);

export type JobStatus = z.infer<typeof JobStatusSchema>;
