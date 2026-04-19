import { describe, expect, it } from "vitest";
import { FailureCategorySchema, TestCaseSchema } from "../src";

describe("shared schemas", () => {
  it("accepts valid test case", () => {
    const parsed = TestCaseSchema.parse({
      title: "Valid login flow",
      module: "auth",
      priority: "P0",
      type: "functional",
      preconditions: [],
      steps: [{ order: 1, action: "goto /login", expected: "login page shown" }],
      tags: ["smoke"],
      source: "ai",
      confidence: 0.9,
    });

    expect(parsed.title).toBe("Valid login flow");
  });

  it("supports failure categories", () => {
    const category = FailureCategorySchema.parse("selector_not_found");
    expect(category).toBe("selector_not_found");
  });
});
