# 第一轮验收标准

## P0 验收
- [x] 后端可导入并启动 FastAPI app。
- [x] `GET /api/v2/projects` 返回统一响应。
- [x] 可创建 Project、RequirementLib、RequirementDocument。
- [x] RequirementDocument 可进入 parse/extract/confirm 主链占位流程。
- [x] RequirementItem 可生成 TestPoint。
- [x] RequirementItem 可生成 TestCase。
- [x] TestCase 可创建 Execution 或批量 Execution。
- [x] Report 可基于项目生成占位快照。
- [x] 系统备份接口可导出 JSON 快照。
- [x] 核心数据写入 SQLite 后可读回。

## P1 验收
- [x] GenerationJob 有查询和事件流占位。
- [x] 接口测试、自动化、性能模块有基础占位入口。
- [x] SQLite 创建的 Project 可进入 P1 占位模块，不再因为 DB/store 混用误 404。
- [x] OpenAPI 文档能展示核心路由。

## 非目标
- [ ] 真实 LLM 调用。
- [ ] 真实 Celery/Redis 异步执行。
- [ ] 真实 JMeter CLI 执行。
- [ ] 前端视觉重构。

## 已执行验证
- `python -m compileall backend\aitest_platform`
- `cd backend; python -m pytest`
- OpenAPI `/api/v2` path 数量检查：105。
- 主线程手工 smoke：
  - project -> lib -> document -> parse -> extract -> confirm -> points -> cases -> execution -> report -> backup
  - project -> api-test-lib -> auto-project -> perf-plan
  - requirement brain analyze、traceability refresh、split、DB soft delete

## 第二轮验收
- [x] 接口测试库、接口、接口用例、环境、场景、计划任务、执行结果写入 SQLite。
- [x] 自动化项目、框架文件、自动化用例文件、自动化执行结果写入 SQLite。
- [x] 性能方案、脚本占位、执行结果、性能报告写入 SQLite。
- [x] ReportTemplate、LlmConfig、PromptTemplate 使用 SQLite CRUD。
- [x] LLM 配置响应不回显真实 `api_key`。
- [x] `GET /api/v2/system/operation-logs` 可读取 SQLite 操作日志。
- [x] `GET /api/v2/search` 可搜索 SQLite 主链和第二轮资产。
- [x] Round 2 contract tests 通过。

## Round 2 Contract Test Evidence
- Added `backend/tests/test_round2_persistence.py`.
- Covers API testing, automation, performance, configuration, secret redaction, operation logs, and search contracts.
- Command to verify: `cd backend; python -m pytest`.
- 2026-05-28 interim result: `8 passed, 3 failed, 2 warnings`; this exposed DB/store mixed-read gaps.
- 2026-05-28 final result: `11 passed, 2 warnings`.
- Main-thread smoke additionally covered import-documents, schedule toggle, candidate screen, git pull/push skip responses, perf quick tests, and search result types.

## 第三轮验收
- [x] LLM client 支持 OpenAI-compatible `/v1/models` 和 `/v1/chat/completions`。
- [x] `POST /api/v2/llm-configs/{configId}/test` 在 disabled mode 不触网，在 enabled mode 可调用 client。
- [x] `POST /api/v2/chat` 在 disabled mode 安全降级，在 enabled mode 可返回模型回复。
- [x] LLM usage 统计会记录 test/chat 调用。
- [x] API key 不出现在响应、日志、测试输出或备份数据中。
- [x] Round 3 contract/security tests 通过。

## Round 3 Contract Test Evidence
- Added `backend/tests/test_round3_llm_integration.py`.
- Covers disabled no-network mode, enabled mock-client mode, chat fallback, mock model reply, usage growth, and secret redaction.
- Uses only fake test secret `sk-round3-test-secret`; no real API key is written to tests or docs.
- Command to verify: `cd backend; python -m pytest`.
- 2026-05-28 final result: `16 passed, 2 warnings`.
- Main-thread smoke additionally verified disabled `llm-config test` + `chat` with fake secret and local `/v1` base URL.

## 第四轮验收
- [x] `extract-items` enabled mode 可消费 LLM JSON 并写入 RequirementItem。
- [x] `generate-test-points` enabled mode 可消费 LLM JSON 并写入 TestPoint。
- [x] `generate-test-cases` enabled mode 可消费 LLM JSON 并写入 TestCase。
- [x] disabled/missing config/provider error/bad JSON 时安全降级，不中断主链。
- [x] LLM usage 记录 requirement_extract、test_point_generation、test_case_generation。
- [x] API key 不出现在响应、日志、GenerationJob payload 或测试输出中。
- [x] Round 4 contract/security tests 通过。

## Round 4 Contract Test Evidence
- Added `backend/tests/test_round4_main_chain_llm.py`.
- Covers disabled no-network placeholder persistence for `extract-items`, `generate-test-points`, and `generate-test-cases`.
- Covers enabled mock LLM JSON contracts for RequirementItem, TestPoint, and TestCase persistence, provider bad JSON/error fallback, usage module growth, and secret redaction.
- Uses only fake test secret `sk-round4-test-secret`; no real API key is written to tests or docs.
- Command to verify: `cd backend; python -m pytest`.
- 2026-05-28 interim result: `20 passed, 5 failed, 2 warnings`; this exposed missing main-chain LLM consumption and request secret echo.
- 2026-05-28 final result: `25 passed, 2 warnings`.
- Main-thread smoke additionally verified disabled fallback chain and OpenAPI path count 106.

## 第五轮验收
- [x] `apis/debug` 可通过 httpx 发起真实请求并返回响应快照。
- [x] API case execute 可基于 environment/base URL 真实执行并写入 ApiExecution。
- [x] batch executions 复用真实执行器并返回逐条结果。
- [x] status_code 断言失败会返回 failed 执行记录，而不是 HTTP 500。
- [x] timeout/request error 会返回 error 执行记录，并记录脱敏错误。
- [x] 没有 environment/base URL 时保留 placeholder fallback。
- [x] 请求、响应、错误、日志和 execution payload 不泄露 Authorization、api_key、token、cookie。
- [x] Round 5 contract/security tests 通过。

## Round 5 Contract Test Evidence
- Added `backend/tests/test_round5_api_runner.py`.
- Covers debug real runner, single case execution, failed assertion, timeout/request error, batch execution, secret redaction, and placeholder fallback.
- Command to verify: `cd backend; python -m pytest tests/test_round5_api_runner.py -q`.
- 2026-05-28 final Round 5 result: 8 tests passed.
- 2026-05-28 full backend result: `33 passed, 2 warnings`.
- Main-thread smoke additionally verified a real local HTTP request without monkeypatch.

## 第六轮验收
- [x] 自动化项目可执行生成的本地 case files，并落库 AutoExecution。
- [x] 自动化执行失败/超时返回 failed/error，不导致 HTTP 500。
- [x] 性能计划可通过 JMeter runner 执行或在缺工具时返回结构化 error。
- [x] API scenario 可按节点顺序执行关联 API case。
- [x] API scenario 支持基础变量注入与 JSON 字段提取。
- [x] 执行日志、artifacts、错误信息不泄露 token/cookie/secret/password。
- [x] 缺少可执行资产时保留 placeholder fallback。
- [x] Round 6 contract/security tests 通过。

## Round 6 Contract Test Evidence
- Added `backend/tests/test_round6_execution_runners.py`.
- Covers auto runner success/fallback/failure/timeout, perf runner JMeter success/missing tool/error, API scenario ordered execution with extraction/injection, stop-on-failure, and secret redaction.
- Command to verify: `cd backend; python -m pytest tests/test_round6_execution_runners.py -q`.
- 2026-05-29 final Round 6 result: 9 tests passed.
- 2026-05-29 full backend result: `42 passed, 2 warnings`.
- OpenAPI `/api/v2` path count: 105.

## 第七轮验收
- [x] OpenAPI JSON 可导入为 ApiEndpoint，并可按需生成 ApiTestCase。
- [x] Postman Collection JSON 可递归导入嵌套 item。
- [x] curl 命令可解析 method、path、query、headers、body。
- [x] 导入链路不泄露 Authorization、api_key、token、cookie、secret、password。
- [x] API schedule 可手动 run，执行结果落库并更新 `last_run_at`、`last_result`。
- [x] `run-due` 只执行 enabled 且 due 的 schedule，并支持 `lib_id` 缩小扫描范围。
- [x] Round 7 contract/security tests 通过。

## Round 7 Contract Test Evidence
- Added `backend/tests/test_round7_import_schedule.py`.
- Covers OpenAPI JSON import with case generation, Postman nested collection import, curl import, schedule manual run, run-due filtering, and secret redaction.
- Command to verify: `cd backend; python -m pytest tests/test_round7_import_schedule.py -q`.
- 2026-05-29 final Round 7 result: 5 tests passed.
- 2026-05-29 full backend result: `47 passed, 2 warnings`.
- OpenAPI `/api/v2` path count: 107.

## 第八轮验收
- [x] 自动化 runner 可将 runner log 持久化为 artifact。
- [x] 自动化 runner 可采集截图、trace、Junit/XML、HTML、log 等 evidence 元数据。
- [x] 性能 runner 可持久化 JMX、JTL、stdout、stderr。
- [x] 性能 runner 可在 mock JMeter 下生成并返回 HTML report evidence。
- [x] artifacts、error_details、logs 不泄露 fake secret。
- [x] Round 8 contract/security tests 通过。

## Round 8 Contract Test Evidence
- Added `backend/tests/test_round8_artifacts.py`.
- Covers auto runner artifact persistence, JMeter artifact persistence, optional HTML report, error-path redaction, and path containment under `artifact_root`.
- Command to verify: `cd backend; python -m pytest tests/test_round8_artifacts.py -q`.
- 2026-05-29 final Round 8 result: 4 tests passed.
- 2026-05-29 full backend result: `51 passed, 2 warnings`.
- OpenAPI `/api/v2` path count: 107.

## 第九轮验收
- [x] `/system/restore` 支持 dry-run/preview，不写库。
- [x] `/system/restore` 支持安全 merge restore。
- [x] overwrite 模式没有 `confirm_text="RESTORE"` 时会拒绝执行。
- [x] restore 响应和读回列表不泄露 fake secret。
- [x] `/system/schema-status` 返回结构化 schema 自检结果，不暴露完整本机路径。
- [x] Round 9 contract/security tests 通过。

## Round 9 Contract Test Evidence
- Added `backend/tests/test_round9_restore_schema.py`.
- Covers schema-status, restore dry-run, restore merge, overwrite guard, and secret redaction.
- Command to verify: `cd backend; python -m pytest tests/test_round9_restore_schema.py -q`.
- 2026-05-29 final Round 9 result: 5 tests passed.
- 2026-05-29 full backend result: `56 passed, 2 warnings`.
- OpenAPI `/api/v2` path count: 108.

## 第十轮验收
- [x] `/reports/comprehensive` 使用统一 Reporting Aggregator 聚合报告事实数据。
- [x] 报告记录包含稳定 `scope_snapshot`、`data_snapshot`、`source_refs_json`。
- [x] 综合报告可追溯到需求项、用例、执行、缺陷、接口、自动化和性能结果。
- [x] `/perf-plans/{planId}/generate-report` 基于 PerfPlan 和最新 PerfResult 生成快照。
- [x] `/reports/{reportId}/download` 支持 Markdown、HTML、JSON 三种输出格式。
- [x] `/reports/lightweight-conclusions` 复用同一聚合上下文，并支持 `save=true` 保存报告记录。
- [x] 报告响应和快照不泄露 fake secret。
- [x] Round 10 contract/security tests 通过。

## Round 10 Contract Test Evidence
- Added `backend/tests/test_round10_reporting.py`.
- Covers comprehensive report aggregation, report download formats, lightweight conclusion save path, performance report metrics, and secret redaction.
- Command to verify: `cd backend; python -m pytest tests/test_round10_reporting.py -q`.
- 2026-05-29 final Round 10 result: 7 tests passed.
- 2026-05-29 full backend result: `63 passed, 2 warnings`.
- OpenAPI `/api/v2` path count: 108.

## 第十一轮验收
- [x] 测试用例支持 Markdown / CSV / JSON 导出。
- [x] 测试用例导出支持项目、需求项、选中 ID、类型过滤。
- [x] 缺陷列表支持 Markdown / CSV / JSON 导出。
- [x] 缺陷导出支持项目和状态过滤。
- [x] 自动化项目下载返回可解码 ZIP 包，并保留旧 `download_url` 兼容字段。
- [x] 性能计划支持 JMX 脚本下载。
- [x] 性能结果支持 JSON 下载和原始数据路径可用性说明。
- [x] 导出响应和导出内容不泄露 fake secret。
- [x] Round 11 contract/security tests 通过。

## Round 11 Contract Test Evidence
- Added `backend/tests/test_round11_exports.py`.
- Covers test case export, defect export, automation ZIP download, performance script/result download, and secret redaction.
- Command to verify: `cd backend; python -m pytest tests/test_round11_exports.py -q`.
- 2026-05-29 final Round 11 result: 7 tests passed.
- 2026-05-29 full backend result: `71 passed, 2 warnings`.
- OpenAPI `/api/v2` path count: 112.

## 第十二轮验收
- [x] `/system/recycle-bin` 可列出数据库软删除对象。
- [x] `/system/recycle-bin/{id}/restore` 可恢复 `type:id` 形式的数据库回收站对象。
- [x] 回收站保留旧内存 store 兼容。
- [x] 用户偏好可持久化到 SQLite。
- [x] 最近活动可持久化到 SQLite，并支持项目过滤。
- [x] 系统状态响应不泄露 fake secret。
- [x] Round 12 contract/security tests 通过。

## Round 12 Contract Test Evidence
- Added `backend/tests/test_round12_system_state.py`.
- Covers DB recycle bin list/restore, user preferences, recent activities, and secret redaction.
- Command to verify: `cd backend; python -m pytest tests/test_round12_system_state.py -q`.
- 2026-05-29 final Round 12 result: 3 tests passed.
- 2026-05-29 full backend result: `74 passed, 2 warnings`.
- OpenAPI `/api/v2` path count: 115.

## 第十三轮验收
- [x] 前端可通过统一 API client 访问 `/api/v2` 并解包统一响应。
- [x] 后端本地 CORS 支持 `127.0.0.1:3000` / `localhost:3000`。
- [x] 统一响应不会复用旧 `Content-Length`，真实 Uvicorn 浏览器请求不再报错。
- [x] Dashboard 可读取默认项目与项目大盘数据，后端不可用时保留演示降级。
- [x] Reports 可读取后端报告、生成综合报告、下载报告、生成/归档轻量结论。
- [x] Settings 可读取 schema 状态、保存运行参数、创建系统备份快照。
- [x] 浏览器验证三页主流程无 console error。

## Round 13 Contract Test Evidence
- Added `backend/tests/test_round13_frontend_integration.py`.
- Covers local frontend CORS, unified response `Content-Length`, Dashboard/Settings frontend-facing contracts.
- Command to verify: `cd backend; python -m pytest tests/test_round13_frontend_integration.py -q`.
- 2026-05-29 final Round 13 result: 3 tests passed.
- 2026-05-29 frontend result: `npm run build` passed, with only Vite chunk size warning.
- 2026-05-29 full backend result: all tests passed with 2 FastAPI dependency warnings.
- Browser evidence: Dashboard backend sync, Reports generate/download, Settings save/backup all passed without console errors.

## 第十四轮验收
- [x] `GET /api/v2/requirement-libs/{libId}/documents` 可为前端返回需求库文档列表。
- [x] `GET /api/v2/requirement-libs/{libId}/requirement-items` 可为前端返回需求库需求项列表。
- [x] `GET /api/v2/projects/{projectId}/test-cases` 支持项目、需求库、需求项过滤。
- [x] Requirements 可读取后端需求库，并触发新建需求库、导入需求文档、解析/提取需求项、生成测试点。
- [x] TestCases 可读取后端测试用例，并触发批量生成和 CSV / Markdown 导出。
- [x] 浏览器验证需求库和测试用例库主流程无 console error。

## Round 14 Contract Test Evidence
- Added `backend/tests/test_round14_requirement_testcase_integration.py`.
- Covers requirement lib frontend-facing document/item lists, project-level test case list filtering, and export payload integration.
- Command to verify: `python -m pytest backend/tests/test_round14_requirement_testcase_integration.py -q`.
- 2026-05-29 final Round 14 result: 2 tests passed.
- 2026-05-29 frontend result: `npm run build` passed, with only Vite chunk size warning.
- 2026-05-29 full backend result: all tests passed with 2 FastAPI dependency warnings.
- OpenAPI `/api/v2` path count: 118.
- Browser evidence: Requirements create/import and TestCases generate/export passed without console errors.

## 第十五轮验收
- [x] `GET /api/v2/projects/{projectId}/test-rounds` 可返回项目级测试轮次列表，支持分页和状态过滤。
- [x] 批量执行可创建测试轮次并写入执行记录。
- [x] 失败执行记录可生成缺陷并被缺陷列表读回。
- [x] 执行统计和执行历史可按项目读取。
- [x] Execution 页面可读取后端测试用例、轮次、执行统计、执行历史和缺陷列表。
- [x] Execution 页面可触发批量执行、重跑失败和缺陷 CSV 导出。
- [x] 浏览器验证 Execution 主流程无 console error。

## Round 15 Contract Test Evidence
- Added `backend/tests/test_round15_execution_integration.py`.
- Covers project test-round list, batch execution, test round counters, execution history, statistics, defect generation, and defect readback.
- Command to verify: `cd backend; python -m pytest tests/test_round15_execution_integration.py -q`.
- 2026-05-29 final Round 15 result: 1 test passed.
- 2026-05-29 frontend result: `npm run build` passed, with only Vite chunk size warning.
- 2026-05-29 full backend result: all tests passed with 2 FastAPI dependency warnings.
- OpenAPI `/api/v2` path count: 119.
- Browser evidence: Execution batch execution, rerun failed, defect history, and CSV export passed without console errors.

## 第十六轮验收
- [x] ApiTesting 页面可读取后端接口库并触发 Swagger/OpenAPI 导入。
- [x] ApiTesting 工作台可调用 `/apis/debug` 并展示后端响应快照。
- [x] ApiTesting 可调用 `/api-test-cases/batch-executions` 批量执行接口用例。
- [x] LlmConfig 页面可读取、保存、新增、设默认和停用后端 LLM 配置。
- [x] LlmConfig 连接测试调用 `/llm-configs/{id}/test`，且不保存或回显明文 API Key。
- [x] Automation 页面可读取/创建后端自动化项目，并触发框架生成、用例生成、执行结果。
- [x] Performance 页面可读取/创建后端性能方案，并触发计划生成、脚本生成、执行和报告生成。
- [x] 浏览器验证 ApiTesting / LlmConfig / Automation / Performance 主链路无 console error。

## Round 16 Evidence
- `npm run build`: passed, with only Vite chunk size warning.
- `cd backend; python -m pytest -q`: passed, 80 tests, with 2 FastAPI dependency warnings.
- Browser screenshots:
  - `docs/orchestration/artifacts/round16-api-list.png`
  - `docs/orchestration/artifacts/round16-api-workbench.png`
  - `docs/orchestration/artifacts/round16-llm-list.png`
  - `docs/orchestration/artifacts/round16-llm-diagnostic.png`
  - `docs/orchestration/artifacts/round16-automation-list.png`
  - `docs/orchestration/artifacts/round16-automation-result.png`
  - `docs/orchestration/artifacts/round16-performance-list.png`
  - `docs/orchestration/artifacts/round16-performance-report.png`

## 第十七轮验收
- [x] 顶栏提供全局项目选择器，并持久化当前项目上下文。
- [x] ApiTesting 环境、场景、计划任务可走后端创建、执行和回写链路。
- [x] Automation 可切换真实本地 runner、Playwright runner、占位 runner，并可下载工程 ZIP 与执行 artifacts ZIP。
- [x] Performance 可下载 JMX，导出 JSON/HTML 结果，并可显式启用真实 JMeter 与 HTML report。
- [x] 自动化 artifacts 下载和性能 HTML 导出有后端契约测试覆盖。

## Round 17 Evidence
- `python -m compileall backend\aitest_platform`: passed.
- `npm run build`: passed, with only Vite chunk size warning.
- `python -m pytest backend\tests\test_round11_exports.py -q`: passed, 8 tests, with 2 FastAPI dependency warnings.
- `cd backend; python -m pytest -q`: passed, with 2 FastAPI dependency warnings.

## 第十八轮验收
- [x] Dashboard / Requirements / TestCases / Execution / Reports / Settings 均使用全局项目上下文。
- [x] ApiTesting / Automation / Performance 不再自行扫描项目列表选择项目。
- [x] Dashboard 后端契约返回 API、自动化、性能、报告和状态分布统计。
- [x] Reports 详情页按后端报告 snapshot 展示通过率、缺陷分布、风险项和准出建议。
- [x] `/system/runtime-dependencies` 返回 Playwright / JMeter 运行依赖状态，前端有可见提示。
- [x] `/perf-results/{resultId}/artifacts/download` 返回可解码 ZIP，至少包含 `manifest.json`。

## Round 18 Evidence
- `python -m compileall backend\aitest_platform`: passed.
- `npm run build`: passed, with only Vite chunk size warning.
- `python -m pytest backend\tests\test_round13_frontend_integration.py backend\tests\test_round11_exports.py -q`: passed, 11 tests, with 2 FastAPI dependency warnings.

## 第十九轮验收
- [x] `/projects/{projectId}/dashboard/daily-summary` 基于后端项目事实生成日报摘要，不再返回固定占位文案。
- [x] `/projects/{projectId}/dashboard/weekly-summary` 基于后端项目事实生成周报摘要，不再返回固定占位文案。
- [x] `/chat` 在真实 LLM 未启用时可读取 `project_id` 上下文，并返回包含当前项目事实的风险/待办/准出分析。
- [x] AI 助手前端优先调用后端 `/chat`，并携带当前全局项目与页面上下文。
- [x] AI 助手本地兜底不再包含固定 Bearer 示例或固定执行编号式模拟结论。

## Round 19 Evidence
- Added `backend/tests/test_round19_dashboard_chat.py`.
- Covers dashboard daily/weekly quality summaries and chat fallback with backend project facts.
- `python -m compileall backend\aitest_platform`: passed.
- `python -m pytest backend\tests\test_round19_dashboard_chat.py -q`: passed, 2 tests, with 2 FastAPI dependency warnings.
- `npm run build`: passed, with only Vite chunk size warning.
- `cd backend; python -m pytest -q`: passed, with 2 FastAPI dependency warnings.
- Browser smoke: Vite returned HTTP 200, Headless Edge rendered React DOM and the AI assistant backend-link status.

## 第二十轮验收
- [x] `/projects/{projectId}/dashboard` 返回最近 14 天 `execution_trend`，按日统计 passed / failed / blocked / other / total / pass_rate。
- [x] `/projects/{projectId}/dashboard` 返回 `requirement_coverage`，基于 RequirementItem / TestPoint / TestCase 统计 covered / partial / uncovered。
- [x] `/projects/{projectId}/dashboard` 返回 `module_heatmap`，按模块聚合需求、用例、执行、缺陷。
- [x] `/system/llm-status` 返回 LLM 配置、运行时开关、模型名和 usage 统计，不调用外部 provider。
- [x] `/system/llm-status` 不返回 `api_key`、`api_key_ref` 或真实密钥值。
- [x] Dashboard 执行趋势、需求覆盖率、模块热力图均使用后端字段，空数据时稳定渲染。
- [x] Topbar LLM 状态从后端读取，默认真实 LLM 关闭时显示“未启用”，点击可跳转 LLM 配置页。
- [x] 浏览器烟测确认 Dashboard/Topbar 实际 React DOM 渲染，无 JS error。

## Round 20 Evidence
- Added `backend/tests/test_round20_dashboard_topbar.py`.
- Covers empty dashboard structures, fact-backed coverage/trend/heatmap, unconfigured LLM status, configured LLM status, and secret redaction.
- `python -m compileall backend\aitest_platform`: passed.
- `python -m pytest backend\tests\test_round20_dashboard_topbar.py -q`: passed, 4 tests, with FastAPI dependency warnings.
- QA subagent full backend regression: `cd backend; python -m pytest -q` passed, with FastAPI dependency warnings.
- `npm run build`: passed, with only Vite chunk size warning.
- Headless Chrome CDP smoke: rendered `LLM 状态 / 未启用 / round20-model`, `执行趋势`, `需求覆盖率`, `模块使用热力图`; no JS console error or browser error log.

## 第二十一轮验收
- [x] R21 名称为 AI 助手与 Prompt 闭环。
- [x] `POST /api/v2/prompt-templates` 可新增 Prompt 模板。
- [x] `DELETE /api/v2/prompt-templates/{templateId}` 可删除自定义 Prompt 模板，内置模板不可删除。
- [x] `POST /api/v2/prompt-templates/{templateId}/test` 支持测试渲染，并兼容 `variables` 嵌套与 flat payload。
- [x] `GET /api/v2/assistant/context` 可返回 AI 助手上下文。
- [x] `POST /api/v2/assistant/drafts` 可生成测试点、澄清问题、缺陷备注草稿。
- [x] `/chat` fallback 会追加 assistant context 摘要。
- [x] R21 所有后端响应不调用真实 provider 且做敏感信息脱敏。
- [x] AI 助手可复制整条回复、读取/保存常用 Prompt、展示最近操作、把最近操作带入输入框。
- [x] AI 助手可生成测试点/澄清问题/缺陷备注草稿。
- [x] LLM 配置页新增 Prompt 模板管理面板，支持加载/新增/编辑/测试渲染/删除自定义模板。
- [x] 前端 `/assistant/drafts` 已发送 `message: prompt`。
- [x] 最近操作 normalize 已兼容 `recent_activities.list` 与 `operation_logs.list`。

## Round 21 Evidence
- Added `backend/tests/test_round21_ai_prompt.py`.
- `python -m compileall backend\aitest_platform`: passed.
- `python -m pytest backend\tests\test_round21_ai_prompt.py -q`: passed, 4 tests.
- `python -m pytest backend\tests\test_round19_dashboard_chat.py backend\tests\test_round20_dashboard_topbar.py -q`: passed, 6 tests.
- `cd backend; python -m pytest -q`: passed.
- `npm run build`: passed, with only Vite chunk size warning.
- Headless Chrome CDP smoke: confirmed LLM 配置页 Prompt 面板、AI 助手常用 Prompt/最近操作/三类草稿按钮、生成测试点草稿；`window.__r21Errors` 为空。
- Residual risks: real LLM remains disabled by default; Prompt templates are basic CRUD/test rendering only; recent activities/operation logs are summary context rather than full audit replay; structured drafts are deterministic rules fallback.

## 第二十二轮验收
- [x] R22 名称为需求库解析与确认闭环。
- [x] 后端支持 TXT/Markdown 多 block 解析，重 parse 替换旧 blocks。
- [x] fallback extract 基于 blocks 生成多条可追溯需求项。
- [x] split / merge / shelve / quality-check / brain analyze / get / traceability refresh 均为 DB 化闭环。
- [x] 闭环响应脱敏，不回显 token / cookie / Authorization / secret。
- [x] Requirements 页面展示解析块和 source anchors。
- [x] 需求项编辑保存、确认、暂不入库、拆分、合并、粒度质检、需求大脑、追溯刷新已接后端。
- [x] Requirements 页面支持多选合并。
- [x] brain / source_refs 等返回形状已归一化，浏览器烟测中 `source_refs.slice is not a function` 崩溃已修复。
- [x] R22 定向测试覆盖 parse / extract / edit / confirm / shelve / split / merge / quality / brain / traceability / redaction。

## Round 22 Evidence
- Added `backend/tests/test_round22_requirement_closure.py`.
- `python -m compileall backend\aitest_platform`: passed.
- `python -m pytest backend\tests\test_round22_requirement_closure.py -q`: 7 passed.
- `python -m pytest backend\tests\test_p0_acceptance.py backend\tests\test_round4_main_chain_llm.py backend\tests\test_round14_requirement_testcase_integration.py -q`: 17 passed.
- `cd backend; python -m pytest -q`: full suite passed.
- `npm run build`: passed, with only Vite chunk size warning.
- Headless Chrome CDP smoke: R22 专用项目进入需求库工作台，source anchors 可见，合并/质检/追溯/暂不入库/拆分按钮可见，点击质检和需求大脑结果可见，`window.__r22Errors` 为空。
- Residual risks: 解析仍为规则化 TXT/Markdown，不覆盖 docx/pdf/xlsx 深解析；真实 LLM 默认关闭，需求大脑是 DB deterministic 摘要；split/merge lineage 用状态和响应表达，未新增正式血缘表；浏览器烟测使用本地临时 smoke 数据。

## 第二十三轮验收
- [x] R23 名称为用例评审与质量规则。
- [x] 后端新增 deterministic 用例质量规则服务 `backend/aitest_platform/services/test_case_quality.py`。
- [x] 质量规则覆盖缺步骤、缺预期、预期不可断言/过短、标题过短、缺 source anchors、优先级不一致、重复/相似、不可执行、同需求 happy path 覆盖弱。
- [x] 新增/增强 `POST /test-cases/{caseId}/quality-review`、`POST /test-cases/review-batch`、`GET /projects/{projectId}/test-case-quality-summary`、`POST /test-cases/{caseId}/review-opinions`。
- [x] 旧入口 `rule-validate` 和 `ai-review` 复用新规则服务。
- [x] R23 不调用真实 LLM，响应 provider flags false，并做脱敏。
- [x] TestCases 页面新增项目级质量摘要区。
- [x] TestCases 页面接入单条质量评审、批量评审、评审意见保存。
- [x] TestCases 表格增加质量分和单条评审操作。
- [x] 所有评审返回 array/object/string/null 归一化，避免 R22 类似 `.slice` 崩溃。
- [x] R23 定向测试覆盖完整项目链路、好/坏/重复/优先级不一致用例、质量评审、批量评审、项目摘要、人工意见、旧入口、secret redaction。

## Round 23 Evidence
- Added `backend/tests/test_round23_testcase_quality.py`.
- `python -m compileall backend\aitest_platform`: passed.
- `python -m pytest backend\tests\test_round23_testcase_quality.py -q`: 5 passed.
- `python -m pytest backend\tests\test_round14_requirement_testcase_integration.py backend\tests\test_round22_requirement_closure.py -q`: 9 passed.
- `cd backend; python -m pytest -q`: full suite passed.
- `npm run build`: passed, with only Vite chunk size warning.
- Headless Chrome CDP smoke: R23 专用项目进入测试用例库，质量摘要可见，批量评审/单条评审按钮可见，批量评审后结果可见，`window.__r23Errors` 为空。
- Residual risks: 规则评分是 deterministic 启发式，阈值后续可按产品验收口径微调；人工评审意见保存到操作日志/状态字段，没有新增正式 Review 表；浏览器烟测使用本地临时 smoke 数据；真实 LLM 默认关闭。

## 第二十四轮验收
- [x] R24 名称为执行与缺陷闭环。
- [x] 后端新增 deterministic execution defect loop service `backend/aitest_platform/services/execution_defect_loop.py`。
- [x] 新增 `GET /executions/templates`、`POST /executions/{executionId}/defect-suggestion`、`POST /executions/{executionId}/create-defect`、`POST /defects/{defectId}/link-case`、`POST /defects/{defectId}/unlink-case`、`POST /defects/{defectId}/retest-reminder`、`GET /projects/{projectId}/execution-trend`、`GET /projects/{projectId}/defect-loop-summary`。
- [x] 增强 batch/statistics/defects patch/copy-text。
- [x] `defect-suggestion` 返回 top-level `steps_to_reproduce`。
- [x] `copy-text` 使用中文标签“复现/实际/预期/复测建议”。
- [x] R24 不接真实 LLM，并注意敏感信息脱敏。
- [x] `src/pages/Execution.jsx` 接入 templates、trend、defect loop summary、suggestion/create/link/unlink/retest/status/copy。
- [x] 批量摘要显示 `created_defects` / `failed` / `blocked` / `skipped`。
- [x] 历史趋势优先后端数据。
- [x] 前端做了 shape normalization。
- [x] R24 定向测试覆盖项目链路、模板、建议、创建缺陷、关联/解除、复测提醒、趋势、摘要、统计、筛选/patch/copy、批量摘要、脱敏。
- [x] 脱敏从整段替换改为片段级脱敏，`Round 11 defect ... sk-*` 普通标题不再被误伤。
- [x] Round9 restore merge 测试改为分页查找以适配脏库。
- [x] API 验收确认实际前缀为 `/api/v2`，`/api/v2/executions/templates` 返回 200。
- [x] 浏览器轻量验收确认首页可加载并包含 `用例执行` 入口，未发现明显 JS runtime error。

## Round 24 Evidence
- Added `backend/tests/test_round24_execution_defect_loop.py`.
- `python -m compileall backend\aitest_platform`: passed.
- `python -m pytest backend\tests\test_round24_execution_defect_loop.py -q`: previously passed; after adding the redaction false-positive regression test, R24 targeted suite is 9 passed.
- `python -m pytest backend\tests\test_round15_execution_history.py backend\tests\test_round23_testcase_quality.py -q`: 6 passed.
- `npm run build`: passed.
- `python -m pytest tests/test_round9_restore_schema.py::test_restore_merge_restores_project_api_assets_and_lists_can_read_them -q`: 1 passed.
- `python -m pytest tests/test_round11_exports.py tests/test_round24_execution_defect_loop.py -q`: 17 passed.
- `python -m pytest -q`: full backend regression passed, exit code 0.
- API acceptance: actual project prefix is `/api/v2`; bare `/executions/templates` and `/api/executions/templates` return 404 due to prefix mismatch; `/api/v2/executions/templates` returns 200.
- Browser light smoke: `http://127.0.0.1:3000/` loads and includes `用例执行`; QA-collected `console.error` / `pageerror` has no obvious JS runtime error. Deep interaction was affected by script Chinese encoding / Playwright lag and is not used as complete interaction evidence.
- Residual risks: 深层浏览器交互仅轻量验证；扩展缺陷字段仍通过 `Defect.remark` 的 R24 JSON prefix 存储；建议/复测为 deterministic 规则，非真实 LLM；本地服务仍为原有 8000/3000 dev 进程。

## 第二十五轮验收
- [x] R25 名称为接口测试增强。
- [x] OpenAPI YAML 支持轻量解析，且不新增 PyYAML 生产依赖。
- [x] HAR 支持基础解析并导入接口资产。
- [x] debug 支持 `save_as_case` 保存为 `ApiTestCase`。
- [x] API runtime context 统一处理环境变量、运行覆盖和 header 优先级。
- [x] scenario `data_mappings.extract` 已增强变量提取和传递。
- [x] Mock 服务提供本地平台基础 mock 能力。
- [x] pre/post script 使用受控 allowlist DSL，danger script 会被拒绝。
- [x] `src/pages/ApiTesting.jsx` 新增 JSON/YAML/HAR 导入面板、真实 debug 表单、保存为接口用例、环境变量/运行覆盖、场景变量映射、Mock 服务 UI、pre/post script UI。
- [x] R25 定向测试覆盖 YAML/HAR、debug save、变量优先级、scenario mapping、mock、allowlist/danger script。
- [x] 完整后端回归、API 冒烟、浏览器轻量 smoke 和清理检查均已由 QA worker 回填通过。

## Round 25 Evidence
- Added `backend/tests/test_round25_api_testing_enhancement.py`.
- Added backend services `backend/aitest_platform/services/api_runtime_context.py`, `backend/aitest_platform/services/api_mock_service.py`, and `backend/aitest_platform/services/api_script_runner.py`.
- Enhanced `backend/aitest_platform/services/api_importer.py`, `backend/aitest_platform/services/api_runner.py`, `backend/aitest_platform/services/api_scenario_runner.py`, and `backend/aitest_platform/api/router.py`.
- `cd backend; python -m compileall aitest_platform`: passed, exit code 0.
- `cd backend; python -m pytest tests/test_round5_api_runner.py tests/test_round6_execution_runners.py tests/test_round7_import_schedule.py tests/test_round25_api_testing_enhancement.py -q`: passed, exit code 0, with only FastAPI `HTTP_422_UNPROCESSABLE_ENTITY` deprecation warning.
- `cd backend; python -m pytest -q`: full backend regression passed, exit code 0, with only FastAPI deprecation warning.
- Root `npm run build`: passed, exit code 0, with only Vite chunk > 500 kB warning.
- API smoke used temporary SQLite and the DB was deleted: OpenAPI YAML import imported=1 path `/r25/smoke/users` expected status 206; HAR import imported=1 path `/r25/smoke/orders` expected status 202; Mock create/list/dispatch matched=true status 207; debug save_as_case status 200 saved_case_id=3.
- Browser smoke: `http://127.0.0.1:3000/` entered ApiTesting/workbench; 5 R25 UI keywords were visible: OpenAPI YAML, HAR, 环境变量, 本次运行覆盖, Mock 服务; console.error=0 and pageerror=0.
- Cleanup: temporary processes and DB were cleaned; ports 8000/3000 had no listeners.
- Residual risks: Vite chunk > 500 kB warning remains; browser coverage is limited to light load/visibility/console smoke, and deeper UI writes are mainly covered by API smoke.

## 第二十六轮验收
- [x] R26 名称为自动化中心增强。
- [x] 后端支持候选筛选/选择。
- [x] 后端支持自动化文件 CRUD。
- [x] 后端支持执行详情、artifact 列表与预览路由。
- [x] `generate-cases` 支持候选选择。
- [x] Playwright 模板已增强。
- [x] 新增后端服务 `backend/aitest_platform/services/auto_center.py`。
- [x] `backend/aitest_platform/services/exporting.py` 对文本类 artifact ZIP 内容脱敏。
- [x] `src/pages/Automation.jsx` 新增候选筛选、case file 在线编辑/dirty/save/reset、Playwright 模板配置、按 `case_file_ids` 执行、执行详情日志/evidence、artifact preview。
- [x] R26 定向测试覆盖候选筛选/过滤、候选选择影响生成、Playwright 模板增强、在线文件查看/保存/非法路径、按文件执行与详情、artifact 列表/预览、artifact ZIP 回归安全。
- [x] 最终完整后端回归、API 冒烟、浏览器最终复验均已由 QA worker 回填通过。

## Round 26 Evidence
- Added `backend/tests/test_round26_automation_center.py`.
- Added backend service `backend/aitest_platform/services/auto_center.py`.
- Enhanced `backend/aitest_platform/api/router.py`, `backend/aitest_platform/services/exporting.py`, and `src/pages/Automation.jsx`.
- `python -m pytest backend/tests/test_round26_automation_center.py -q`: 7 passed.
- `cd backend; python -m compileall aitest_platform`: passed, exit code 0.
- R26 combination regression: `python -m pytest tests/test_round6_execution_runners.py tests/test_round8_artifacts.py tests/test_round11_exports.py tests/test_round13_frontend_integration.py tests/test_round25_api_testing_enhancement.py tests/test_round26_automation_center.py -q`: 40 passed, with only FastAPI deprecation warning.
- Full backend `python -m pytest -q`: passed, exit code 0, with only FastAPI deprecation warning.
- Root `npm run build`: passed, with only Vite chunk >500k warning.
- API smoke: passed; candidate filter/filtering, file save, and artifact preview returned reasonable results.
- Browser final smoke: Automation page opened; console.error=0; pageerror=0; `/case-files` request count 0; `/case-files` 404 count 0; `/auto-projects/693/files?page=1&pageSize=200` returned 200; R26 DOM visible keywords 8/8: 候选筛选、在线文件、保存、Playwright、trace、Artifacts、预览、执行日志.
- Cleanup: ports 8000/3000 were stopped and rechecked with no listeners.
- Residual risks: Vite chunk warning; Playwright 真实执行依赖本机环境；trace/zip 预览不展开执行；浏览器深层写操作主要由 API smoke 和后端契约测试覆盖。

## 第二十七轮验收
- [x] R27 名称为性能测试增强。
- [x] 后端支持性能执行停止/中止接口。
- [x] 后端支持性能阈值判定。
- [x] 后端支持性能历史对比。
- [x] 后端支持项目 `performance-trend` 聚合。
- [x] JMeter 参数编辑会体现在生成/下载脚本中。
- [x] `generate-report` 增加风险建议。
- [x] 报告快照和嵌套数据支持递归脱敏，不回显 token / cookie / Authorization / secret。
- [x] `src/pages/Performance.jsx` 接完整 results、阈值判定、历史比对、7 日趋势、JMeter 参数表单、停止执行和报告风险/建议展示。
- [x] Performance 页面已去掉影响判断的关键静态假数据。
- [x] R27 定向测试覆盖停止/中止、阈值判定、历史对比、趋势聚合、JMeter 参数、报告建议和递归脱敏。
- [x] 完整后端回归、合同组合回归、前端构建和真实 Chrome Playwright 烟测均已验证通过。

## Round 27 Evidence
- Added `backend/tests/test_round27_performance_enhancement.py`.
- Added backend service `backend/aitest_platform/services/perf_analysis.py`.
- Enhanced `backend/aitest_platform/api/router.py`, `backend/aitest_platform/services/perf_runner.py`, `backend/aitest_platform/services/reporting.py`, `backend/aitest_platform/services/exporting.py`, and `src/pages/Performance.jsx`.
- `python -m compileall backend/aitest_platform`: passed.
- `python -m pytest backend/tests/test_round27_performance_enhancement.py -q`: 10 passed.
- Contract combination regression: passed.
- Full backend `pytest -q`: passed.
- Root `npm run build`: passed.
- Real Chrome Playwright smoke: passed; console.error=0; pageerror=0; visible keywords included 阈值判定、性能历史比对、7日趋势 P95、JMeter 参数/模板参数、停止执行、报告建议/风险建议.
- Residual risks: 真实 JMeter 执行依赖本机工具和目标环境；阈值/风险建议为当前规则口径，后续可按项目 SLA 调整；趋势依赖已落库样本。

## 第二十八轮验收
- [x] R28 名称为报告中心增强。
- [x] report-templates 支持 CRUD 校验与默认唯一。
- [x] 综合报告可按 `template_id` 和 `scope` 生成，并冻结模板、章节和 scope。
- [x] 报告列表支持过滤和排序。
- [x] report drilldown 已可查询。
- [x] report risks 已可查询。
- [x] 风险项支持转待办，todo 列表和状态可查询/更新。
- [x] Markdown/HTML 输出已强化，HTML 输出做 escape。
- [x] 报告快照和嵌套数据继续递归脱敏，不回显 token / cookie / Authorization / secret。
- [x] PDF/Word/docx 在未引入新依赖时返回 unsupported 结构化响应。
- [x] 轻量结论支持 `daily_report`、`test_submission_feedback`、`release_advice`、`risk_list`。
- [x] Reports 页已移除 fallback/static AI 意见、固定默认报告和假分享。
- [x] Reports 页已接真实报告列表、模板管理、筛选排序、下钻、风险转待办、下载和轻量结论类型。
- [x] R28 定向测试、合同组合回归、完整后端回归、前端构建和真实 Chrome Playwright 报告中心烟测均已验证通过。

## Round 28 Evidence
- Added `backend/tests/test_round28_report_center_enhancement.py`.
- Enhanced `backend/aitest_platform/api/router.py`, `backend/aitest_platform/models.py`, `backend/aitest_platform/services/reporting.py`, and `src/pages/Reports.jsx`.
- `python -m compileall backend/aitest_platform`: passed.
- `python -m pytest backend/tests/test_round28_report_center_enhancement.py -q`: 13 passed.
- Contract combination regression: passed.
- Full backend `pytest -q`: passed.
- Root `npm run build`: passed.
- Real Chrome Playwright report center smoke: passed; console.error=0; pageerror=0.
- Browser smoke hit entries for 风险转待办、Markdown、HTML、日报、提测反馈、上线建议、风险清单、管理报告模板/新建模板、查看下钻/下钻明细.
- Cleanup: ports were cleaned.
- Residual risks: PDF/Word/docx remain unsupported structured responses until an export dependency decision is made; lightweight conclusions follow the current report aggregation rules.
