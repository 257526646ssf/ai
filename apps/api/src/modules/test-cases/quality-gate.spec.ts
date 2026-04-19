import { validateGeneratedTestCase } from "./quality-gate";

describe("validateGeneratedTestCase", () => {
  it("flags selector review when selector is missing", () => {
    const { parsed, warnings } = validateGeneratedTestCase({
      title: "Login happy path",
      module: "auth",
      priority: "P0",
      type: "functional",
      preconditions: [],
      steps: [{ order: 1, action: "open login page", expected: "form is visible" }],
      tags: ["smoke"],
      source: "ai",
      confidence: 0.8,
    });

    expect(parsed.needsSelectorReview).toBe(true);
    expect(warnings.length).toBeGreaterThan(0);
  });
});
