import { apiRequest, getEnv, loginAsOwner, waitForJob } from "./demo-utils.mjs";

async function seedDemo() {
  const { DEMO_BASE_URL } = getEnv();
  const token = await loginAsOwner();

  const project = await apiRequest("/projects", {
    method: "POST",
    token,
    body: {
      name: `Demo Project ${new Date().toISOString()}`,
      description: "Auto seeded for E2E demo",
      baseUrl: DEMO_BASE_URL,
    },
  });

  const assetResp = await apiRequest(`/projects/${project.id}/assets`, {
    method: "POST",
    token,
    body: {
      type: "document",
      filename: "demo-requirement.md",
      originalPath: "/demo/demo-requirement.md",
    },
  });

  await waitForJob(assetResp.parseJobId, token);

  const testCase = await apiRequest(`/projects/${project.id}/test-cases`, {
    method: "POST",
    token,
    body: {
      title: "Demo login success",
      module: "auth",
      priority: "P0",
      type: "functional",
      preconditions: ["demo-site is running"],
      tags: ["demo", "login"],
      source: "manual",
      confidence: 0.99,
      steps: [
        {
          order: 1,
          action: "goto",
          expected: "login page visible",
          data: { path: "/login" },
        },
        {
          order: 2,
          action: "fill",
          selector: "#username",
          expected: "username filled",
          data: { value: "demo" },
        },
        {
          order: 3,
          action: "fill",
          selector: "#password",
          expected: "password filled",
          data: { value: "demo123" },
        },
        {
          order: 4,
          action: "click",
          selector: "#login-btn",
          expected: "submitted",
        },
        {
          order: 5,
          action: "wait",
          selector: "#welcome",
          expected: "welcome appears",
        },
        {
          order: 6,
          action: "assert",
          selector: "#welcome",
          expected: "Welcome, demo",
        },
      ],
    },
  });

  const output = {
    seededAt: new Date().toISOString(),
    projectId: project.id,
    testCaseId: testCase.id,
    baseUrl: DEMO_BASE_URL,
  };

  console.log(JSON.stringify(output, null, 2));
}

seedDemo().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
