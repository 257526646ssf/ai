# AI Test Agent Monorepo

## Workspace Layout
- `apps/web`: React frontend MVP (projects, cases, execution, report).
- `apps/api`: NestJS backend with Prisma + BullMQ.
- `services/ai`: FastAPI AI service with OpenAI adapter layer.
- `services/runner`: Playwright execution service.
- `packages/shared`: Shared schemas (`TestCaseSchema`, `ExecutionEventSchema`, `FailureCategory`).

## Quick Start
1. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.
2. Start infra and services:
   - `docker compose up --build`
3. For local non-docker dev:
   - `pnpm install`
   - `pnpm dev`

## Demo Scripts
- One-click seed demo project + testcase:
  - `corepack pnpm demo:seed`
- One-click run end-to-end demo execution:
  - `corepack pnpm demo:e2e`

Both scripts expect API + runner + demo-site to be reachable.

## Production Deploy
- Render Blueprint file: `render.yaml`
- Deploy guide: `deploy/DEPLOY_RENDER.md`

## API Highlights
- `POST /api/v1/auth/login`
- `POST /api/v1/projects`
- `POST /api/v1/projects/:id/assets`
- `POST /api/v1/projects/:id/test-cases`
- `POST /api/v1/projects/:id/test-cases/generate`
- `GET /api/v1/jobs/:jobId`
- `POST /api/v1/test-cases/:tcId/execute`
- `GET /api/v1/executions/:execId`
- `GET /api/v1/executions/:execId/results`
- `GET /api/v1/executions/:execId/report`

## Notes
- First release focuses on minimal end-to-end loop.
- `OPENAI_API_KEY` is optional in local mode; AI service falls back to deterministic mock output.
