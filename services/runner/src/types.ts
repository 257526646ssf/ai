export type RunnerStep = {
  order: number;
  action: string;
  selector?: string | null;
  value?: string;
  data?: Record<string, unknown> | string | number | boolean | null;
  expected?: string;
};

export type RunRequest = {
  executionId: string;
  baseUrl: string;
  headless?: boolean;
  retries?: number;
  steps: RunnerStep[];
};

export type RunResult = {
  executionId: string;
  status: "passed" | "failed";
  logs: Array<Record<string, unknown>>;
  screenshots: string[];
  errorLog?: string;
};
