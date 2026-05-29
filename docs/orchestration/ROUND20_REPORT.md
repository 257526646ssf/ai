# Round 20 Report

## 范围
- Dashboard 剩余关键静态图表改为后端事实驱动：执行趋势、需求覆盖率、模块热力图。
- Topbar LLM 状态改为读取后端配置与运行时状态，不再固定显示 `已连接 / OpenAI GPT-4o`。
- 新增后端契约测试覆盖 Dashboard 图表字段和 LLM 状态脱敏。

## 实现
- `GET /api/v2/projects/{projectId}/dashboard` 新增：
  - `execution_trend`：最近 14 天按日统计 passed / failed / blocked / other / total / pass_rate。
  - `requirement_coverage`：基于 RequirementItem / TestPoint / TestCase 计算 covered / partial / uncovered。
  - `module_heatmap`：按 RequirementItem.module 聚合需求、用例、执行、缺陷。
- `GET /api/v2/system/llm-status` 新增：
  - 读取默认启用 LLM 配置、运行时开关、模型配置和 usage 统计。
  - 不调用外部 provider，返回 `provider_call_performed=false`。
  - 不返回 `api_key`、`api_key_ref` 或真实密钥值。
- `Dashboard.jsx` 使用后端字段渲染执行趋势图、覆盖率环和模块热力图，空数据保持稳定空态。
- `Topbar.jsx` 使用 `/system/llm-status` 展示 loading / error / 未配置 / 未启用 / 已就绪 / 降级状态；点击状态入口进入 LLM 配置页。

## 验证
- `python -m compileall backend\aitest_platform`：通过。
- `python -m pytest backend\tests\test_round20_dashboard_topbar.py -q`：4 passed，保留 FastAPI deprecation warnings。
- QA 子线程全量验证：`cd backend; python -m pytest -q` 通过，保留 FastAPI deprecation warnings。
- `npm run build`：通过，保留 Vite chunk size warning。
- Headless Chrome CDP 烟测：
  - Vite 首页可渲染 React DOM。
  - Topbar 显示 `LLM 状态 / 未启用 / round20-model`。
  - Dashboard 渲染 `执行趋势`、`需求覆盖率`、`模块使用热力图`。
  - 未捕获 JS console error 或 browser error log。

## 子线程分工
- 后端子线程 Euler：Dashboard 聚合字段、LLM 状态接口、Round20 后端契约测试。
- 前端子线程 Erdos：Dashboard 图表绑定、Topbar LLM 状态绑定、App 传参。
- QA 子线程 Lovelace：独立 diff 审查、后端全量测试、前端构建和风险复核。

## 残余风险
- `/system/llm-status` 不做真实 provider 连通探测，避免默认触发外部调用；真实连通性仍通过 LLM 配置页的连接测试验证。
- Topbar 当前在组件挂载时读取一次状态；配置页保存后自动刷新属于后续体验优化。
- Dashboard 新增聚合未做大数据量性能压测；当前本地 SQLite 场景和契约测试通过。
