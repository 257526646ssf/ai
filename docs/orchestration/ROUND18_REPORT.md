# Round 18 Report

## Scope
- 全局项目上下文继续下沉到 Dashboard / Requirements / TestCases / Execution / Reports / Settings，并移除这些页面各自扫描第一个项目的旧策略。
- Dashboard / Reports 的关键判断数据改为优先使用后端 dashboard/report snapshot，而不是固定演示数字。
- 后端新增 runtime dependencies 自检，前端展示 Playwright / JMeter 依赖状态并在缺依赖时给出明确提示。
- Performance 新增性能执行 artifacts ZIP 受控下载入口，可包含 JMeter JMX/JTL/stdout/stderr/HTML report 目录。

## Implementation
- `backend/aitest_platform/api/router.py` 扩展 `/projects/{projectId}/dashboard`，新增 API、自动化、性能、报告和状态分布统计；新增 `/system/runtime-dependencies` 与 `/perf-results/{resultId}/artifacts/download`。
- `backend/aitest_platform/services/auto_runner.py` 新增非侵入式 Playwright/pytest/Node/npx 依赖状态检查。
- `backend/aitest_platform/services/perf_runner.py` 新增 JMeter CLI 路径解析状态检查。
- `backend/aitest_platform/services/exporting.py` 新增性能结果 artifacts ZIP 打包。
- `src/pages/*.jsx` 相关页面改用 `useProjectContext`，并让 Dashboard / Reports 使用后端统计生成风险、缺陷、通过率和待办提示。
- `src/pages/Automation.jsx` 与 `src/pages/Performance.jsx` 展示运行依赖状态，Performance 增加 artifacts 下载按钮。

## Verification
- `python -m compileall backend\aitest_platform`: passed。
- `npm run build`: passed，仅保留 Vite chunk size warning。
- `python -m pytest backend\tests\test_round13_frontend_integration.py backend\tests\test_round11_exports.py -q`: passed，11 tests，保留 2 个 FastAPI deprecation warnings。

## Residual Risks
- 正式 Alembic migration、Celery/Redis 异步队列和真实密钥加密存储仍属于生产基础设施决策项，会引入依赖、运行拓扑或迁移策略变化；当前轮未擅自引入。
- 历史趋势图仍有部分静态曲线形态，已优先替换影响决策的汇总数字、风险项和下载/执行入口。
