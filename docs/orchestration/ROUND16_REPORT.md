# Round 16 Report

## Scope
- ApiTesting: 接入后端接口库列表、Swagger/OpenAPI 导入、接口 debug、接口用例批量执行。
- LlmConfig: 接入 `/llm-configs` 列表、创建、更新、停用和连接测试；前端只保存环境变量引用，不保存明文 Key。
- Automation: 接入自动化项目列表、项目创建、框架生成、用例生成、执行结果和 Git pull skip 入口。
- Performance: 接入性能方案列表、方案创建、计划生成、脚本生成、执行、报告生成和结果导出入口。

## Implementation
- `src/pages/ApiTesting.jsx`
  - 自动扫描后端项目，优先选择存在接口库的项目。
  - “同步 Swagger” 创建接口库并导入 OpenAPI schema。
  - “运行” 调用 `/apis/debug`，展示真实后端响应快照。
  - “批量执行物理断言” 调用 `/api-test-cases/batch-executions`。
- `src/pages/LlmConfig.jsx`
  - 从 `/llm-configs` 加载模型路由表。
  - 保存、设为默认、停用、新增节点均使用后端接口。
  - 连接测试调用 `/llm-configs/{id}/test`，真实 LLM 关闭时显示后端降级状态。
- `src/pages/Automation.jsx`
  - 从 `/projects/{projectId}/auto-projects` 加载自动化项目。
  - 构建运行串联 `generate-framework`、`generate-cases`、`execute`。
  - 新建向导完成后创建后端自动化项目并生成初始脚手架。
- `src/pages/Performance.jsx`
  - 从 `/projects/{projectId}/perf-plans` 加载性能方案并读取最新结果。
  - 执行串联 `generate-plan`、`generate-script`、`execute`、`generate-report`。
  - 报告页使用最新 `PerfResult` 摘要数据，导出入口指向后端结果下载。

## Verification
- `npm run build`: passed；仅保留 Vite chunk size warning。
- `cd backend; python -m pytest -q`: passed，80 tests；保留 2 个 FastAPI dependency deprecation warnings。
- Browser smoke passed without console errors:
  - ApiTesting: Swagger 同步、进入工作台、debug 运行、批量执行物理断言。
  - LlmConfig: 后端配置加载、连接测试、保存配置。
  - Automation: 后端项目加载、构建运行、执行结果页。
  - Performance: 后端方案加载、执行、报告页。

## Browser Evidence
- `docs/orchestration/artifacts/round16-api-list.png`
- `docs/orchestration/artifacts/round16-api-workbench.png`
- `docs/orchestration/artifacts/round16-llm-list.png`
- `docs/orchestration/artifacts/round16-llm-diagnostic.png`
- `docs/orchestration/artifacts/round16-automation-list.png`
- `docs/orchestration/artifacts/round16-automation-result.png`
- `docs/orchestration/artifacts/round16-performance-list.png`
- `docs/orchestration/artifacts/round16-performance-report.png`

## Residual Risks
- 四个页面仍保留部分视觉演示区块，核心按钮和主数据链路已接后端。
- 项目上下文仍由页面扫描自动选择；正式产品仍应补全全局项目选择器。
- Automation 默认执行后端生成的确定性占位用例，尚未接真实浏览器自动化 runner。
- Performance 默认走后端确定性占位压测，真实 JMeter runner 只在请求显式启用或有工具链时进入。
- LLM 真实调用默认关闭；连接测试会返回后端 disabled/fallback 状态，真实连通需要本地环境变量开启。
