# Round 17 Report

## Scope
- 全局项目选择器：在 Topbar 增加项目下拉，统一保存当前项目上下文。
- ApiTesting：环境、场景编排、计划任务接入后端运行链路。
- Automation：区分真实本地 runner、Playwright runner、占位 runner，并支持工程 ZIP 与执行 artifacts 下载。
- Performance：补齐 JMX 下载、结果 JSON/HTML 导出、真实 JMeter 执行模式开关与 HTML report 开关。

## Implementation
- `src/lib/projectContext.jsx` 新增全局项目上下文，统一加载 `/projects` 并持久化选中项目。
- `src/components/Topbar.jsx` 接入项目选择器。
- `src/pages/ApiTesting.jsx` 改为优先使用全局项目，并调用后端 environment / scenario / schedule 接口创建、执行、回写结果。
- `src/pages/Automation.jsx` 增加 runner 模式选择、执行 artifacts 展示和下载入口。
- `src/pages/Performance.jsx` 增加真实 JMeter 与 HTML report 开关，并通过后端下载 JMX、JSON、HTML。
- `backend/aitest_platform/api/router.py` 增加自动化 artifacts 下载端点，并按项目 framework 生成 Playwright / pytest 文件。
- `backend/aitest_platform/services/auto_runner.py` 增加 Playwright runner 命令分支。
- `backend/aitest_platform/services/exporting.py` 增加自动化执行 artifacts ZIP 与性能结果 HTML 导出。

## Verification
- `npm run build`: passed；保留 Vite chunk size warning。
- `python -m pytest backend\tests\test_round11_exports.py -q`: passed，8 tests，保留 2 个 FastAPI deprecation warnings。
- `cd backend; python -m pytest -q`: passed，保留 2 个 FastAPI deprecation warnings。
- `python -m compileall backend\aitest_platform`: passed。

## Residual Risks
- 真实 Playwright runner 依赖本机或执行环境已安装 `npx` 与 Playwright 依赖；缺失时会返回结构化失败，不抛 500。
- 真实 JMeter runner 依赖 JMeter CLI；缺失时会走后端结构化 error。
- 浏览器视觉冒烟未在本轮使用 in-app Browser 执行，已用生产构建覆盖语法与打包风险。
