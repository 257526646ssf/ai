const API_BASE_URL = process.env.API_BASE_URL || "http://localhost:3000/api/v1";
const DEMO_BASE_URL = process.env.DEMO_BASE_URL || "http://localhost:8200";

export function getEnv() {
  return { API_BASE_URL, DEMO_BASE_URL };
}

export async function loginAsOwner() {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId: "demo-owner", role: "owner" }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Login failed: ${response.status} ${text}`);
  }

  const json = await response.json();
  return json.accessToken;
}

export async function apiRequest(path, { method = "GET", token, body } = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API ${method} ${path} failed: ${response.status} ${text}`);
  }

  if (response.status === 204) return null;
  return response.json();
}

export async function waitForJob(jobId, token, timeoutMs = 120000) {
  const start = Date.now();

  while (Date.now() - start < timeoutMs) {
    const job = await apiRequest(`/jobs/${jobId}`, { token });
    if (job.status === "completed") return job;
    if (job.status === "failed") {
      throw new Error(`Job ${jobId} failed: ${job.error || "unknown error"}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }

  throw new Error(`Job ${jobId} timeout after ${timeoutMs}ms`);
}

export async function waitForExecution(execId, token, timeoutMs = 120000) {
  const start = Date.now();

  while (Date.now() - start < timeoutMs) {
    const execution = await apiRequest(`/executions/${execId}`, { token });
    if (["passed", "failed", "error", "blocked"].includes(execution.status)) {
      return execution;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }

  throw new Error(`Execution ${execId} timeout after ${timeoutMs}ms`);
}
