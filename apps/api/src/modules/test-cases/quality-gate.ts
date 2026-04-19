import { TestCaseSchema, type TestCase } from "@ai-test-agent/shared";

export function validateGeneratedTestCase(raw: unknown): { parsed: TestCase; warnings: string[] } {
  const parsed = TestCaseSchema.parse(raw);
  const warnings: string[] = [];

  const hasCompoundStep = parsed.steps.some((step: TestCase["steps"][number]) =>
    /\b(and|then)\b|然后|并且/.test(step.action),
  );
  if (hasCompoundStep) {
    warnings.push("Found non-atomic step action, please split steps manually.");
  }

  const missingSelector = parsed.steps.some((step: TestCase["steps"][number]) => !step.selector);
  if (missingSelector) {
    warnings.push("Some steps are missing selectors and need manual review.");
  }

  return { parsed: { ...parsed, needsSelectorReview: missingSelector }, warnings };
}
