# Round 19 Report

## 范围
- P0：将 Dashboard 日报/周报摘要从固定占位文案改为后端事实聚合输出。
- P0：将前端 AI 助手从纯本地模拟改为优先调用 `/api/v2/chat`。
- P0：当真实 LLM 未启用时，`/chat` 使用当前项目的后端事实数据生成可追溯降级回复，而不是泛化占位回复。
- P0：补充 Round 19 合同测试，覆盖日报/周报摘要和 AI 助手项目事实 fallback。

## 实现
- `backend/aitest_platform/api/router.py`
  - 新增 `_period_quality_summary`，复用 Reporting Aggregator 的 `build_aggregation_context` 生成日报/周报摘要。
  - `/projects/{projectId}/dashboard/daily-summary` 与 `/weekly-summary` 返回 metrics、risk_level、risk_items、next_actions、source_refs。
  - `/chat` 在 fallback 路径中读取 `project_id` 上下文，并基于项目事实生成风险、待办、准出或报告类回复。
- `src/components/AiAssistant.jsx`
  - 引入 `apiPost` 与 `useProjectContext`。
  - 发送消息时携带 active tab、当前项目和最近消息，优先调用后端 `/chat`。
  - 后端不可用时保留本地兜底回复，但不再内置固定执行编号或 Bearer 示例。
- `backend/tests/test_round19_dashboard_chat.py`
  - 覆盖日报/周报不再返回占位摘要。
  - 覆盖 `/chat` fallback 能返回当前项目名称、通过率和项目事实上下文。

## 验证
- `python -m compileall backend\aitest_platform`：通过。
- `python -m pytest backend\tests\test_round19_dashboard_chat.py -q`：2 passed，2 warnings。
- `npm run build`：通过，仅保留 Vite chunk size warning。
- `cd backend; python -m pytest -q`：全量通过，仅保留 2 个 FastAPI 依赖 deprecation warnings。
- `git diff --check`：通过，仅有 Windows LF/CRLF 提示。
- secrets 扫描：仅命中既有 fake test secret、脱敏代码和 CSS `mask-composite`，未发现真实凭证。
- 浏览器烟测：`http://localhost:3000/` 返回 200，Headless Edge 可渲染 React DOM，并出现 `测试大脑 AI 助手` 与 `后端分析链路`。

## 残余风险
- 真实 LLM 调用仍默认关闭，需通过本地环境变量启用并提供运行时密钥。
- 正式 Alembic migration、Celery/Redis 异步队列、真实密钥加密存储仍属于生产基础设施决策项，未在本轮擅自改变依赖或部署拓扑。
- Dashboard 历史趋势图仍有部分静态曲线形态；关键摘要、风险、待办、报告和助手回复已优先接后端事实。
