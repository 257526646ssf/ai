import express from "express";
import { runExecution } from "./executor";
import type { RunRequest } from "./types";

const app = express();
app.use(express.json({ limit: "2mb" }));

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

app.post("/run", async (req, res) => {
  const payload = req.body as RunRequest;
  try {
    const result = await runExecution(payload);
    res.json(result);
  } catch (error) {
    res.status(500).json({
      message: "Runner failed",
      error: error instanceof Error ? error.message : "unknown error",
    });
  }
});

const port = Number(process.env.RUNNER_PORT || 8100);
app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`Runner listening on ${port}`);
});
