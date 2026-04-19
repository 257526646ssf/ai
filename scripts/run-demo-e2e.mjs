import { apiRequest, getEnv, loginAsOwner, waitForExecution } from "./demo-utils.mjs";

async function runDemoE2E() {
  const { DEMO_BASE_URL } = getEnv();
  const token = await loginAsOwner();

  const project = await apiRequest("/projects", {
    method: "POST",
    token,
    body: {
      name: `Demo E2E ${new Date().toISOString()}`,
      description: "One-click E2E demo run",
      baseUrl: DEMO_BASE_URL,
    },
  });

  const testCase = await apiRequest(`/projects/${project.id}/test-cases`, {
    method: "POST",
    token,
    body: {
      title: "E2E demo login",
      module: "auth",
      priority: "P0",
      type: "functional",
      preconditions: ["demo-site reachable"],
      tags: ["e2e", "demo"],
      source: "manual",
      confidence: 0.99,
      steps: [
        { order: 1, action: "goto", expected: "login page loaded", data: { path: "/login" } },
        { order: 2, action: "fill", selector: "#username", expected: "username typed", data: { value: "demo" } },
        { order: 3, action: "fill", selector: "#password", expected: "password typed", data: { value: "demo123" } },
        { order: 4, action: "click", selector: "#login-btn", expected: "login submitted" },
        { order: 5, action: "wait", selector: "#welcome", expected: "dashboard rendered" },
        { order: 6, action: "assert", selector: "#welcome", expected: "Welcome, demo" }
      ],
    },
  });

  const execution = await apiRequest(`/test-cases/${testCase.id}/execute`, {
    method: "POST",
    token,
    body: {
      environmentId: "demo-env",
      options: {
        headless: true,
        recordVideo: false,
        captureScreenshots: true,
      },
    },
  });

  const finalExecution = await waitForExecution(execution.executionId, token);
  const results = await apiRequest(`/executions/${execution.executionId}/results`, { token });
  const report = await apiRequest(`/executions/${execution.executionId}/report`, { token });

  console.log(
    JSON.stringify(
      {
        projectId: project.id,
        testCaseId: testCase.id,
        executionId: execution.executionId,
        status: finalExecution.status,
        stepCount: results.steps?.length ?? 0,
        failureCategory: report.failureCategory,
        suggestion: report.suggestion,
      },
      null,
      2,
    ),
  );

  if (finalExecution.status !== "passed") {
    process.exitCode = 2;
  }
}

runDemoE2E().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
