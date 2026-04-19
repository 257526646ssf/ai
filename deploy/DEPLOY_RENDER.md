# Render 部署指南（可访问成品）

## 1. 前置
- 代码在 GitHub 仓库（Render 需要连接仓库）
- 你有 Render 账号
- 已准备 `OPENAI_API_KEY`

## 2. 一键创建服务
1. 在 Render Dashboard 选择 **Blueprints**
2. 连接本仓库并选择根目录 `render.yaml`
3. 点击创建，Render 会自动创建：
   - `ai-test-agent-api`
   - `ai-test-agent-web`
   - `ai-test-agent-ai`
   - `ai-test-agent-runner`
   - `ai-test-agent-demo-site`
   - `ai-test-agent-redis`
   - `ai-test-agent-db`

## 3. 配置环境变量（首次部署后）
在 Render 控制台中设置：
- `ai-test-agent-ai`
  - `OPENAI_API_KEY=<你的key>`

- `ai-test-agent-api`
  - `AI_SERVICE_URL=https://<ai-service-domain>`
  - `RUNNER_URL=https://<runner-service-domain>`

- `ai-test-agent-web`
  - `VITE_API_BASE_URL=https://<api-service-domain>`

## 4. 健康检查
- API: `https://<api-domain>/api/v1/health`
- AI: `https://<ai-domain>/health`
- Runner: `https://<runner-domain>/health`
- Demo Site: `https://<demo-site-domain>/health`

## 5. 演示链路验证
先拿 API token：
1. `POST https://<api-domain>/api/v1/auth/login`
2. body: `{ "userId": "demo-owner", "role": "owner" }`

然后在本地执行（将 API 地址换成线上）：
1. `set API_BASE_URL=https://<api-domain>/api/v1`
2. `set DEMO_BASE_URL=https://<demo-site-domain>`
3. `corepack pnpm demo:seed`
4. `corepack pnpm demo:e2e`

若 `demo:e2e` 输出 `"status": "passed"`，说明成品可访问且主链路可用。
