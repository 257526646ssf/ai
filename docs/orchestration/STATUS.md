# 后端实现状态

## 阶段
- 当前阶段：截至 2026-05-30，Round 31 已完成；生产基础设施决策门已收口，下一步进入 R32 第二轮总验收。
- 日期说明：第二轮路线图中的旧时间窗口如与实际完成时间冲突，以各 Round 报告、验收记录和提交/测试证据为准。
- 目标：在不改变前端视觉风格的前提下，实现需求文档与技术实现方案中的后端基础能力。
- 主线程职责：拆解、派工、验收、进度统一；产品实现代码由子任务完成。

## 第一轮范围
- P0：FastAPI 后端骨架。
- P0：SQLite 本地持久化，保留 PostgreSQL 迁移空间。
- P0：核心主链实体：Project、RequirementDocument、RequirementItem、TestPoint、TestCase、Execution、Defect、Report。
- P0：`/api/v2` 基础接口可运行，可被前端后续替换 mock 数据。
- P1：GenerationJob 模拟任务与 SSE 事件占位。
- P1：系统备份/恢复、操作日志、搜索与接口测试/自动化/性能模块占位入口。

## Worker 分配
- backend_data_engineer：已交付 SQLite/ORM/repository/seed。
- backend_api_engineer：已交付 FastAPI `/api/v2`，并完成 P0 SQLite 集成与 P1 DB/store 薄适配。
- devops_qa_engineer：已交付后端运行文档与 P0 contract tests。

## 主线程验收结果
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest`：`6 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：105。
- P0 主链 smoke：project -> lib -> document -> parse -> extract -> confirm -> points -> cases -> execution -> report -> backup 通过。
- P1 入口 smoke：DB project -> api-test-lib -> auto-project -> perf-plan 通过。
- 追加验证：requirement brain analyze、traceability refresh、split、DB soft delete 均通过 smoke。

## 残余风险
- 第一轮未接真实 LLM、LangGraph、Celery/Redis、真实浏览器执行、JMeter CLI。
- P1 模块资源本体仍主要使用内存 store，占位数据重启后不持久化。
- 本机 FastAPI/Starlette 版本存在兼容补丁，后续统一依赖版本后可移除。
- 测试和 smoke 会生成或复用 `backend/data/aitest.sqlite3`。

## 第二轮范围
- P0：把接口测试、自动化、性能、报告模板、LLM 配置、Prompt 模板从内存 store 迁移到 SQLite。
- P0：保留占位执行，但执行结果必须结构化落库，可在重启后查询。
- P0：补充 Round 2 contract tests，覆盖新增持久化链路。
- P1：搜索和操作日志优先读取 SQLite 数据。
- 非目标：真实外部 API 调用、真实 LLM、真实 JMeter、真实 Playwright 自动化执行、前端视觉重构。

## 第二轮 Worker 分配
- backend_data_engineer_round2：进行中，agent `019e6ee6-ba9f-70f2-9fcb-38793538e7a5`，负责 P1 数据模型与 repository。
- backend_api_engineer_round2：进行中，agent `019e6ee7-00c0-76b3-9f26-c7cb8b68f812`，负责 P1 API 路由接库与响应契约。
- qa_contract_engineer_round2：进行中，agent `019e6ee7-352a-7530-ae91-d3ec38b9140d`，负责 Round 2 验收测试和文档同步。

## 第二轮接续说明
- 上一批 Round 2 worker 会话中断后返回 `not_found`，但已落入部分模型/API 文件改动。
- 主线程已验证当前基线：`compileall` 通过、`pytest` 为 `6 passed, 2 warnings`、OpenAPI `/api/v2` path 为 105。
- 已重新派发窄范围收尾任务：
  - backend_data_engineer_round2b：已交付，agent `019e6eeb-4a37-7fb2-ba4a-e3c90de7a013`。
  - backend_api_engineer_round2b：已交付，agent `019e6eeb-8c43-70f3-83bc-2db7bda63601`。
  - qa_contract_engineer_round2b：已交付，agent `019e6eeb-c6ed-78f1-9043-9ce7e96bcedf`。

## 第二轮主线程验收结果
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest`：`11 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：105。
- Round 2 contract tests 覆盖接口测试、自动化、性能、配置、安全脱敏、日志和搜索。
- 主线程手工 smoke 通过：
  - project -> api-test-lib -> import-documents -> apis/import -> api cases -> executions -> environment -> scenario -> schedule
  - project -> auto-project -> candidates -> framework -> case files -> execution -> events -> download metadata
  - project -> perf-plan -> generated plan -> script -> result -> performance report -> quick test
  - report-template、llm-config、prompt-template、operation-logs、search

## 第二轮残余风险
- 生成/执行仍是确定性占位，不调用真实外部 API、LLM、JMeter、Playwright。
- `auto-candidates/screen`、`perf/quick-tests` 使用轻量 `round2_resource` SQLite 表持久化，不是专用 ORM model。
- LLM API key 目前保存为掩码/引用，不是真正加密存储。
- 当前项目不是 git 仓库，无法提供提交级 diff。

## 第三轮范围
- P0：接入 OpenAI-compatible LLM client，支持本地 `/v1` base URL。
- P0：`/api/v2/llm-configs/{configId}/test` 可在启用真实 LLM 时调用模型服务并记录 usage。
- P0：`/api/v2/chat` 可在启用真实 LLM 时返回真实模型回复，失败时安全降级。
- P0：密钥只通过环境变量或运行时传入，不写入代码、文档、数据库明文、日志或响应。
- P0：补充 Round 3 LLM contract/security tests。
- 非目标：把所有需求拆解/测试点/用例生成一次性改成真实 LLM；真实 JMeter/Playwright 执行；前端视觉改造。

## 第三轮 Worker 分配
- llm_integration_engineer_round3：已交付，agent `019e6eff-a73e-7a70-8db2-50accb58f8ee`，负责 LLM client 与 API 接入。
- qa_security_engineer_round3：已交付，agent `019e6eff-da94-7b62-a1ba-c4a4f8087fbf`，负责 LLM 集成测试、安全脱敏测试和文档同步。

## 第三轮主线程验收结果
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest`：`16 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：105。
- 主线程 disabled smoke：`llm-config test` 和 `chat` 在 `AITEST_ENABLE_REAL_LLM=false` 时不触网，返回 `skipped`，并记录 usage。
- 安全扫描：项目文件中未出现用户提供的真实 key 前缀。

## 第三轮残余风险
- 主线程未把真实 API key 注入命令行做 live smoke，避免密钥进入命令记录；真实连通性需通过环境变量临时设置后验证。
- enabled path 已由 mock contract tests 覆盖，不同 OpenAI-compatible 服务响应细节仍可能需要小适配。
- 真实 LLM 只接入 `llm-config test` 和 `chat`，需求拆解/测试点/用例生成仍是占位。

## 第四轮范围
- P0：将真实 LLM 接入主链生成：
  - `POST /api/v2/requirement-documents/{documentId}/extract-items`
  - `POST /api/v2/requirement-items/{itemId}/generate-test-points`
  - `POST /api/v2/requirement-items/{itemId}/generate-test-cases`
- P0：disabled 或 LLM 失败时继续安全降级到确定性占位。
- P0：生成结果必须结构化解析、校验、写入 SQLite，并记录 `GenerationJob` 与 `LlmUsage`。
- P0：新增 Round 4 contract tests，覆盖 disabled fallback、enabled mock LLM、坏 JSON 降级、secret redaction。
- 非目标：真实 API 调试、真实 Playwright/JMeter 执行、Celery/Redis。

## 第四轮 Worker 分配
- llm_main_chain_engineer_round4：已交付，agent `019e6f11-be8f-7421-bb85-21130b560014`，负责主链 LLM 生成实现。
- qa_main_chain_llm_round4：已交付，agent `019e6f12-016e-7e72-b107-9ed68807cf2a`，负责 Round 4 契约和安全测试。

## 第四轮主线程验收结果
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest`：`25 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：106。
- 主线程 disabled smoke：document parse -> extract-items -> generate-test-points -> generate-test-cases 通过，生成 1 个需求项、2 个测试点、2 个测试用例。
- 安全扫描：文本文件中未发现非测试用的 `agt_codex_` 风格 key；smoke 响应未回显 fake key/token。
- Round 4 contract/security tests 覆盖 disabled fallback、enabled mock LLM JSON、坏 JSON/provider error 降级、usage 统计和 secret redaction。

## 第四轮残余风险
- 主线程仍未把用户真实 API key 注入命令行做 live smoke，避免密钥进入命令记录；真实服务差异后续需用本地环境变量手动验证。
- 主链 LLM 已接入三条核心生成接口，但 LangGraph 多轮编排、SSE 生成细节、Celery/Redis 异步任务仍未接入。
- 真实外部 API 调试、真实 Playwright 自动化执行、真实 JMeter 执行仍未完成。
- LLM API key 仍采用环境变量读取和数据库掩码引用，尚未做正式密钥管理或加密存储。

## 第五轮范围
- P0：实现真实 API 调试与接口用例执行器。
- P0：`/api/v2/apis/debug` 支持通过 `httpx` 发起真实请求并返回响应快照和断言结果。
- P0：`/api/v2/api-test-cases/{caseId}/execute` 在存在环境或 base URL 时真实执行，缺环境时保持 placeholder 兼容。
- P0：`/api/v2/api-test-cases/batch-executions` 复用真实执行器并汇总结果。
- P0：请求/响应/错误/日志必须脱敏，网络异常不得导致 500。
- 非目标：Playwright/JMeter 执行器、Celery/Redis 调度、正式迁移。

## 第五轮 Worker 分配
- api_execution_engineer_round5：已交付，agent `019e6f22-b96a-7c30-bb6f-c6becc8eb30c`，负责真实 API runner 实现。
- qa_api_execution_round5：已交付，agent `019e6f22-f495-7080-9e6d-34e9b9bf50cb`，负责 Round 5 契约和安全测试。

## 第五轮主线程验收结果
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest tests/test_round5_api_runner.py -q`：8 个用例通过。
- `cd backend; python -m pytest`：`33 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：106。
- 主线程本地 HTTP smoke：临时 SQLite + 本机 HTTPServer，`apis/debug` 和 `api-test-cases/{caseId}/execute` 均真实请求成功，HTTP 201 断言通过。
- 追加修复：`GET /llm-configs` 同 `sort_order` 下改为新记录优先，避免默认持久库历史数据导致第一页看不到新建配置。

## 第五轮残余风险
- 当前真实执行器支持基础 HTTP 请求和轻量断言，但未实现完整 OpenAPI/Postman/curl 导入解析。
- 场景执行仍未实现跨步骤变量提取和数据传递。
- 调度器仍是配置入口，没有真实定时执行。
- Playwright 自动化执行器、JMeter 性能执行器、Celery/Redis 异步任务仍未完成。

## 第六轮范围
- P0：自动化项目执行从 deterministic placeholder 推进到本地 runner。
- P0：性能测试执行支持 JMeter CLI 路径，缺工具时结构化 error，不抛 500。
- P0：API 场景执行按节点顺序执行 case，并支持基础变量注入/提取。
- P0：新增 Round 6 contract tests，覆盖成功、失败、超时/缺工具、安全脱敏与兼容 fallback。
- 非目标：引入新生产依赖、真实 Celery/Redis 集群、完整 OpenAPI/Postman/curl 导入。

## 第六轮 Worker 分配
- auto_runner_engineer_round6：已交付，负责 `services/auto_runner.py`、`router.py` 自动化执行区。
- perf_runner_engineer_round6：已交付，负责 `services/perf_runner.py`、`router.py` 性能执行区。
- api_scenario_engineer_round6：已交付，负责 API 场景顺序执行与变量传递。
- qa_execution_round6：已交付，负责 Round 6 契约/安全测试。

## 第六轮主线程验收结果
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest tests/test_round6_execution_runners.py -q`：9 个用例通过。
- `cd backend; python -m pytest -o addopts='' -q`：`42 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：105。
- 安全扫描：仅发现测试和文档中明确标注的 fake secret；未发现用户真实 key。
- Round 6 contract/security tests 覆盖自动化本地 runner、JMeter runner、API scenario 变量注入/提取、缺资产 fallback、缺工具/超时/失败降级、secret redaction。

## 第六轮残余风险
- 自动化 runner 当前执行 persisted Python/pytest case files；完整 Playwright trace、失败截图和浏览器 artifacts 尚未打包。
- JMeter runner 已支持 CLI/JTL 摘要解析；JMeter HTML report 打包尚未实现。
- API scenario 已支持基础顺序执行、`{{variable}}` 注入和 JSONPath 提取；复杂数据映射、条件分支、循环、并发场景尚未实现。
- 调度器仍是配置和手动触发入口，尚未实现真实本地队列或 Celery/Redis 定时执行。
- 当前 Codex 会话目录曾切到 `D:\codex-project\最新版ai测试平台`，但完整项目和本轮实现位于 `D:\codex-project\新ui-前端`；后续交付需继续以完整项目目录为准。

## 第七轮范围
- P0：OpenAPI JSON、Postman Collection JSON、curl 命令可导入为 `ApiEndpoint`，可按需生成 `ApiTestCase`。
- P0：导入链路对 secret 做脱敏，非法格式返回结构化错误，不抛 500。
- P0：API schedule 支持本地手动执行和 due-scan 触发，执行结果落库并更新 `last_run_at`、`last_result`。
- P0：新增 Round 7 contract/security tests。
- 非目标：新增生产依赖、完整 YAML 解析、Celery/Redis 分布式调度、前端视觉重构。

## 第七轮 Worker 分配
- api_import_engineer_round7：已交付，agent `019e6f82-825a-7421-8a61-d23fcd8e3a55`，负责 `services/api_importer.py` 与 import 路由区块。
- schedule_runner_engineer_round7：已交付，agent `019e6f82-dce0-7b01-b322-c38763e6d0d9`，负责 `services/schedule_runner.py` 与 schedules 路由区块。
- qa_contract_engineer_round7：已交付，agent `019e6f83-1ea0-7e40-a1e6-4fe776f020fa`，负责 `backend/tests/test_round7_import_schedule.py`。

## 第七轮主线程验收结果
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest tests/test_round7_import_schedule.py -q`：5 个用例通过。
- `cd backend; python -m pytest -o addopts='' -q`：`47 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：107。
- 安全扫描：仅发现测试和文档中明确标注的 fake secret；未发现用户真实 key。
- 主线程追加修复：
  - `postman_collection` / `openapi_json` / `curl_command` 等别名进入正确解析分支。
  - `collection` 字段可作为 Postman 文档来源。
  - Postman 嵌套目录名不再并入 endpoint `name`。
  - `run-due` 支持 `lib_id/libId` 过滤，并返回紧凑 executed 结果，避免默认持久库历史 schedule 污染测试。

## 第七轮残余风险
- OpenAPI YAML 未解析；当前只支持 JSON/dict/JSON string，符合本轮“不新增依赖”约束。
- Postman prerequest/test scripts 尚未转换为断言或前后置脚本。
- `run-due` 仍是轻量 due-scan，不是完整 cron parser 或后台常驻调度器。
- 后端剩余较大项：完整执行证据打包、正式迁移/Alembic、正式密钥管理、生产级异步队列。

## 第八轮范围
- P0：自动化 runner 持久化运行日志和执行证据 artifacts 元数据。
- P0：性能 runner 持久化 JMX/JTL/stdout/stderr，并支持可选 JMeter HTML report。
- P0：新增 Round 8 contract/security tests。
- 非目标：对象存储、Celery/Redis、Alembic、前端视觉重构。

## 第八轮 Worker 分配
- auto_artifact_engineer_round8：已交付，agent `019e6f8c-e77b-79d3-af36-0467d4930869`，负责 `services/auto_runner.py` 与自动化执行返回兼容。
- perf_artifact_engineer_round8：已交付，agent `019e6f8d-1e7d-7493-9915-837f0035ffcb`，负责 `services/perf_runner.py`。
- qa_artifact_engineer_round8：已交付，agent `019e6f8d-5ab3-7992-bb6e-04331852c4fd`，负责 `backend/tests/test_round8_artifacts.py`。

## 第八轮主线程验收结果
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest tests/test_round8_artifacts.py -q`：4 个用例通过。
- `cd backend; python -m pytest -o addopts='' -q`：`51 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：107。
- 安全扫描：仅发现测试和文档中明确标注的 fake secret；未发现用户真实 key。
- 自动化 runner 现可持久化 runner log、截图、trace、video、Junit/XML、HTML、log 等 evidence。
- 性能 runner 现可持久化 `plan.jmx`、`result.jtl`、stdout/stderr，并可选生成 JMeter HTML report。

## 第八轮残余风险
- 二进制 artifacts 只做文件名和元数据脱敏，不解析内部二进制内容。
- 真实 JMeter HTML dashboard 的目录结构依赖本机 JMeter 版本；当前实现按标准 `jmeter -g result.jtl -o report` 并做失败降级。
- 对象存储、后台异步执行和正式迁移链路仍未接入。

## 第九轮范围
- P0：`/system/restore` 支持 dry-run/preview 与安全 merge restore。
- P0：`/system/restore` 的 overwrite 模式必须显式确认，不允许误清库。
- P0：`/system/schema-status` 提供 SQLite 表/列状态自检。
- P0：新增 Round 9 contract/security tests。
- 非目标：正式 Alembic、生产清库恢复、恢复所有复杂主链依赖对象。

## 第九轮 Worker 分配
- restore_engineer_round9：已交付，agent `019e6f94-2ab3-7362-acb8-2abe684ef783`，负责恢复服务与 `/system/restore` 接入。
- schema_status_engineer_round9：已交付，agent `019e6f94-7441-7a73-8e60-b1bf748b548a`，负责 schema status 自检服务与路由。
- qa_restore_engineer_round9：已交付，agent `019e6f94-acb7-73d3-bfff-e3d4550a6f3b`，负责 `backend/tests/test_round9_restore_schema.py`。

## 第九轮主线程验收结果
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest tests/test_round9_restore_schema.py -q`：5 个用例通过。
- `cd backend; python -m pytest -o addopts='' -q`：`56 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：108。
- 安全扫描：仅发现测试和文档中明确标注的 fake secret；未发现用户真实 key。
- 主线程追加修复：`/system/restore` dry-run 返回增加 `summary` 兼容别名，保留 `tables` 结构。

## 第九轮残余风险
- overwrite 模式本轮只加确认门槛并复用 merge 逻辑，未执行真实清库恢复。
- 恢复范围仍限定为 Round9 指定表；复杂执行/报告/缺陷等深依赖对象暂未全量恢复。
- schema-status 是 introspection 自检，不是正式 Alembic migration。

## 第十轮范围
- P0：报告中心增加统一 Reporting Aggregator，综合聚合需求项、用例、执行、缺陷、接口、自动化和性能结果。
- P0：`/reports/comprehensive` 生成稳定快照，写入 `scope_snapshot`、`data_snapshot`、`source_refs_json`。
- P0：`/perf-plans/{planId}/generate-report` 基于 PerfPlan 和最新 PerfResult 生成性能报告快照。
- P0：`/reports/{reportId}/download` 支持 Markdown / HTML / JSON 下载内容。
- P0：`/reports/lightweight-conclusions` 复用同一聚合上下文生成轻量结论，并支持可选保存。
- P0：新增 Round 10 contract/security tests。
- 非目标：PDF/Word 导出依赖、对象存储、Celery/Redis、前端视觉重构。

## 第十轮 Worker 分配
- reporting_aggregator_engineer_round10：进行中，agent `019e6ff8-ff12-7b52-bb03-0e1983b432f8`，负责报告聚合服务与报告相关路由。
- qa_reporting_engineer_round10：进行中，agent `019e6ff9-39c6-7ac0-baf3-aa2120fe4799`，负责 `backend/tests/test_round10_reporting.py`。

## 第十轮主线程验收结果
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest tests/test_round10_reporting.py -q`：7 个用例通过。
- `cd backend; python -m pytest -o addopts='' -q`：`63 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：108。
- 安全扫描：仅发现测试和文档中的 fake secret、文档说明和脱敏正则；未发现用户真实 key。
- 报告聚合、快照、下载和轻量结论链路验收通过。

## 第十轮残余风险
- 报告总结仍为规则化生成，未接入真实 LLM 分章节总结。
- HTML 导出为轻量 HTML，不是 PDF/Word 级模板导出。
- 自动化 artifacts 只聚合元数据，不解析二进制内容。

## 第十一轮范围
- P0：测试用例支持 Markdown / CSV / JSON 导出。
- P0：缺陷列表支持 Markdown / CSV / JSON 导出。
- P0：自动化项目下载从 placeholder 推进为可解码 ZIP 包。
- P0：性能计划支持下载 JMX 脚本与性能结果摘要/原始数据引用。
- P0：新增 Round 11 contract/security tests。
- 非目标：PDF/Word、真实 Excel `.xlsx`、对象存储、前端视觉重构。

## 第十一轮 Worker 分配
- export_download_engineer_round11：进行中，agent `019e7005-6461-7f00-b966-91180312367b`，负责导出服务与导出相关路由。
- qa_export_engineer_round11：进行中，agent `019e7005-8f89-74b1-a12a-199a89ada5fe`，负责 Round11 合同/安全测试。

## 第十一轮主线程验收结果
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest tests/test_round11_exports.py -q`：7 个用例通过。
- `cd backend; python -m pytest -o addopts='' -q`：`71 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：112。
- 安全扫描：仅发现测试和文档中的 fake secret、文档说明和脱敏正则；未发现用户真实 key。
- 用例/缺陷导出、自动化 ZIP 下载、性能脚本/结果下载验收通过。

## 第十一轮残余风险
- Excel `.xlsx`、PDF、Word 仍未实现，需要确认是否允许新增导出依赖。
- 自动化 ZIP 是即时本地打包，尚未接对象存储或持久下载文件。
- 性能结果下载目前是 JSON 摘要和本地原始路径引用，尚未流式输出 JTL/CSV 真实附件。

## 第十二轮范围
- P0：`/system/recycle-bin` 列出数据库软删除对象，不再只看内存 store。
- P0：`/system/recycle-bin/{id}/restore` 支持恢复 `type:id` 形式的数据库回收站对象，并保留旧兼容。
- P0：用户偏好接口使用 SQLite 持久化。
- P0：最近活动接口使用 SQLite 持久化。
- P0：新增 Round 12 contract/security tests。
- 非目标：清空全部数据、组织级用户系统、新表迁移、新依赖。

## 第十二轮主线程验收结果
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest tests/test_round12_system_state.py -q`：3 个用例通过。
- `cd backend; python -m pytest -o addopts='' -q`：`74 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：115。
- 安全扫描：仅发现测试和文档中的 fake secret、文档说明和脱敏正则；未发现用户真实 key。
- DB 回收站、用户偏好、最近活动验收通过。

## 第十二轮残余风险
- 回收站恢复只覆盖已有软删除模型，不做级联依赖修复。
- 用户偏好和最近活动复用 `round2_resource`，不是正式独立表。
- 清空所有数据/恢复出厂设置属于破坏性操作，仍需用户明确确认后才能实现。

## 第十三轮范围
- P0：新增前端 API client，统一连接后端 `/api/v2`。
- P0：后端支持本地 Vite CORS，并修复统一响应 `Content-Length` 复用问题。
- P0：Dashboard 接入默认项目、项目大盘、最近活动。
- P0：Reports 接入报告列表、综合报告生成、报告下载、轻量结论生成/归档。
- P0：Settings 接入 schema-status、runtime settings preference、system backup。
- P0：浏览器真实验证三页主流程。
- 非目标：前端视觉重构、PDF/Word/Excel `.xlsx` 导出、Celery/Redis、正式 Alembic。

## 第十三轮主线程验收结果
- `npm run build`：通过，Vite 仅提示 chunk size warning。
- `cd backend; python -m pytest tests/test_round13_frontend_integration.py -q`：3 个用例通过。
- `cd backend; python -m pytest -q`：全量通过，保留 FastAPI 依赖 deprecation warnings。
- 浏览器验证通过：
  - Dashboard 显示后端连接状态和项目大盘数据，无 console error。
  - Reports 可读取/生成后端报告，详情页可下载 HTML。
  - Settings 可读取 schema 状态，保存配置并创建后端备份。

## 第十三轮残余风险
- Requirements、TestCases、Execution、ApiTesting、Automation、Performance、LlmConfig 仍有较多 mock 数据，下一轮继续分批接入。
- Reports 详情页主体仍有部分静态分析块，本轮只接入列表、生成、下载和轻量结论链路。
- 默认项目来源临时使用第一页项目，后续应接正式当前项目上下文。
- `dist` 由构建生成，后续提交时应按项目策略决定是否纳入版本管理。

## 第十四轮范围
- P0：Requirements 接入后端需求库、需求文档、需求项和测试点生成主链。
- P0：TestCases 接入后端测试用例列表、需求项批量生成和导出。
- P0：后端补齐前端所需的需求库详情和项目级用例过滤接口。
- P0：浏览器真实验证需求库和测试用例库主流程。
- 非目标：前端视觉重构、Excel `.xlsx`、PDF/Word、正式项目选择器、Celery/Redis。

## 第十四轮主线程验收结果
- `npm run build`：通过，Vite 仅提示 chunk size warning。
- `python -m pytest backend/tests/test_round14_requirement_testcase_integration.py -q`：2 个用例通过。
- `cd backend; python -m pytest -q`：全量通过，保留 2 个 FastAPI 依赖 deprecation warnings。
- OpenAPI `/api/v2` path 数：118。
- 浏览器验证通过：
  - Requirements 可新建需求库并导入需求文档，无 console error。
  - TestCases 可批量生成后端测试用例并导出 CSV，无 console error。
  - 截图证据位于 `docs/orchestration/artifacts/round14-requirements.png` 和 `docs/orchestration/artifacts/round14-testcases.png`。

## 第十四轮残余风险
- Requirements / TestCases 仍保留部分演示分析块，核心后端主链已接入。
- 当前项目上下文仍为前端自动选择，后续应补全局项目选择器。
- 测试用例导出使用 CSV / Markdown / JSON，未实现真实 `.xlsx`。
- Execution、ApiTesting、Automation、Performance、LlmConfig 仍待继续接后端。

## 第十五轮范围
- P0：Execution 接入后端测试用例、执行统计、执行历史、缺陷列表和测试轮次。
- P0：后端新增 `GET /api/v2/projects/{projectId}/test-rounds`，支持项目级轮次分页和状态过滤。
- P0：“批量执行”创建测试轮次并写入执行记录，失败记录生成缺陷。
- P0：“重跑失败”写入新的通过记录并刷新执行状态。
- P0：“导出缺陷列表”调用后端 CSV 导出。
- P0：浏览器真实验证 Execution 主流程。
- 非目标：真实浏览器自动化 runner、正式全局项目选择器、AI 修复闭环、前端视觉重构。

## 第十五轮主线程验收结果
- `npm run build`：通过，Vite 仅提示 chunk size warning。
- `cd backend; python -m pytest tests/test_round15_execution_integration.py -q`：1 个用例通过。
- `cd backend; python -m pytest -q`：全量通过，保留 2 个 FastAPI 依赖 deprecation warnings。
- OpenAPI `/api/v2` path 数：119。
- 浏览器验证通过：
  - Execution 自动选择已有后端测试用例的项目，无 console error。
  - “批量执行”创建测试轮次、写入执行记录并生成缺陷。
  - “重跑失败”写入通过结果并刷新列表。
  - “历史与缺陷记录”展示轮次、通过率、缺陷网格和关联测试用例。
  - “导出缺陷列表”触发 CSV 下载提示。
  - 截图证据位于 `docs/orchestration/artifacts/round15-execution-list.png` 和 `docs/orchestration/artifacts/round15-execution-history.png`。

## 第十五轮残余风险
- Execution 仍使用前端自动选择项目，只是已优先选择有测试用例的项目；正式全局项目上下文仍待补。
- “关联现有缺陷”“智能新建缺陷”“AI 修复方案”仍为演示交互。
- 执行结果为前端触发的确定性模拟执行，未接真实浏览器/接口自动化 runner。
- 历史趋势图仍保留静态曲线，后续可接测试轮次统计。

## 第十六轮范围
- P0：ApiTesting 接入后端接口库、OpenAPI 导入、接口 debug 和接口用例批量执行主链路。
- P0：LlmConfig 接入后端 LLM 配置列表、保存、设默认、停用和连接测试。
- P0：Automation 接入后端自动化项目、框架生成、用例生成和执行结果。
- P0：Performance 接入后端性能方案、计划生成、脚本生成、执行、报告生成和结果下载入口。
- P0：浏览器真实验收四个页面主流按钮链路。
- 非目标：视觉重构、正式全局项目选择器、真实外部 LLM 调用、真实 Playwright/JMeter 执行强制启用。

## 第十六轮主线程验收结果
- `npm run build`：通过，Vite 仅提示 chunk size warning。
- `cd backend; python -m pytest -q`：通过，80 tests，保留 2 个 FastAPI 依赖 deprecation warnings。
- 浏览器验证通过且无 console error：
  - ApiTesting：Swagger 同步、进入工作台、debug 运行、批量执行物理断言。
  - LlmConfig：配置加载、连接测试、保存配置。
  - Automation：项目加载、构建运行、执行结果页。
  - Performance：方案加载、执行、报告页。
- 截图证据位于 `docs/orchestration/artifacts/round16-*.png`。

## 第十六轮残余风险
- ApiTesting / LlmConfig / Automation / Performance 仍保留部分演示型分析区块，但核心数据与操作主链路已接后端。
- 项目上下文仍由页面扫描自动选择，后续应补正式全局项目选择器。
- Automation 默认执行后端确定性占位用例；真实浏览器自动化 runner 尚未在前端强制启用。
- Performance 默认执行后端确定性占位压测；真实 JMeter runner 仍取决于工具链和请求模式。
- LLM 真实调用默认关闭，连接测试会展示 disabled/fallback 状态；真实连通需本地环境变量开启。

## 第十七轮范围
- P0：新增全局项目选择器，替代 ApiTesting / Automation / Performance 的自动扫描项目策略。
- P0：ApiTesting 环境、场景编排、计划任务页面接后端运行链路。
- P0：Automation 区分真实 runner、Playwright runner、占位 runner，并支持执行 artifacts 下载。
- P0：Performance 补齐 JMX 下载、结果 JSON/HTML 导出、真实 JMeter 执行开关。

## 第十七轮验收结果
- `python -m compileall backend\aitest_platform`：通过。
- `npm run build`：通过，仅保留 Vite chunk size warning。
- `python -m pytest backend\tests\test_round11_exports.py -q`：8 passed，2 warnings。
- `cd backend; python -m pytest -q`：通过，2 warnings。

## 第十七轮残余风险
- 真实 Playwright runner 依赖本机 Node/Playwright 环境；缺依赖时返回结构化失败。
- 真实 JMeter runner 依赖 JMeter CLI；缺工具时返回结构化 error。
- 旧页面仍有部分静态演示图表，后续需继续替换为后端统计。

## 第十八轮范围
- P0：将全局项目选择器下沉到 Dashboard / Requirements / TestCases / Execution / Reports / Settings。
- P0：去除 ApiTesting / Automation / Performance 的项目扫描 fallback，统一以全局项目为准。
- P0：扩展 dashboard 后端统计，并替换 Dashboard / Reports 中影响判断的静态数字、风险项和待办。
- P0：新增 runtime dependencies 自检，前端展示 Playwright / JMeter 依赖状态。
- P0：为 JMeter HTML report / 性能 artifacts 提供受控 ZIP 下载入口。

## 第十八轮验收结果
- `python -m compileall backend\aitest_platform`：通过。
- `npm run build`：通过，仅保留 Vite chunk size warning。
- `python -m pytest backend\tests\test_round13_frontend_integration.py backend\tests\test_round11_exports.py -q`：11 passed，2 warnings。

## 第十八轮残余风险
- 正式 Alembic migration、Celery/Redis 异步队列、真实密钥加密存储仍属于生产基础设施决策项；本轮未擅自新增依赖或改变部署拓扑。
- 历史趋势图还有部分静态曲线形态，但关键汇总数字、风险项、准出提示、runner 状态和下载入口已接后端事实。

## 第十九轮范围
- P0：Dashboard 日报/周报摘要改为后端事实聚合，不再返回固定占位文案。
- P0：AI 助手前端优先调用 `/api/v2/chat`，携带当前全局项目和页面上下文。
- P0：`/chat` 在真实 LLM 未启用时基于当前项目事实生成降级回复，覆盖风险、待办、准出和报告摘要类问题。
- P0：新增 Round 19 合同测试覆盖摘要和聊天 fallback。

## 第十九轮验收结果
- `python -m compileall backend\aitest_platform`：通过。
- `python -m pytest backend\tests\test_round19_dashboard_chat.py -q`：2 passed，2 warnings。
- `npm run build`：通过，仅保留 Vite chunk size warning。
- `cd backend; python -m pytest -q`：全量通过，仅保留 2 个 FastAPI 依赖 deprecation warnings。
- 浏览器烟测通过：Vite 首页 200，Headless Edge 可渲染 React DOM，并展示 `测试大脑 AI 助手` 与 `后端分析链路`。

## 第十九轮残余风险
- 真实 LLM 调用仍默认关闭，需本地环境变量启用并注入运行时密钥。
- 正式 Alembic migration、Celery/Redis 异步队列、真实密钥加密存储仍是生产基础设施决策项。
- Dashboard 历史趋势图仍有部分静态曲线形态；关键摘要、风险、待办和 AI 助手回复已接后端事实。

## 第二轮总攻排期
- 已创建长期 goal：作为第二轮总攻，基于需求文档和技术实现方案梳理 AI 测试平台剩余任务，制定可执行排期，并按排期逐项完成剩余功能、验证、提交并推送到 GitHub。
- 排期文档：`docs/orchestration/SECOND_ROUND_ROADMAP.md`。
- 第二轮从 R20 开始，不再按零散补丁推进。
- R20 立即开工范围：Dashboard 关键静态图表替换为后端事实统计，Topbar LLM 状态接后端配置与运行时状态。

## 第二轮 R20 完成状态
- `backend/aitest_platform/api/router.py` 已扩展 Dashboard 后端事实统计：`execution_trend`、`requirement_coverage`、`module_heatmap`。
- `/api/v2/system/llm-status` 已新增非侵入式 LLM 状态接口，读取配置、运行时开关和 usage，且不调用 provider、不返回密钥。
- `src/pages/Dashboard.jsx` 已把执行趋势、需求覆盖率、模块热力图从静态演示数据替换为后端字段，并保留稳定空态。
- `src/components/Topbar.jsx` 已读取后端 LLM 状态；`src/App.jsx` 已向 Topbar 透传 `setActiveTab`，点击可进入 LLM 配置页。
- `backend/tests/test_round20_dashboard_topbar.py` 已覆盖空项目结构、有事实数据聚合、LLM 未配置/已配置脱敏响应。
- `docs/orchestration/ROUND20_REPORT.md` 已记录实现、验证和残余风险。
- Round 20 主线程验收：`python -m compileall backend\aitest_platform` 通过；`python -m pytest backend\tests\test_round20_dashboard_topbar.py -q` 4 passed；QA 子线程全量后端测试通过；`npm run build` 通过；Headless Chrome CDP 烟测 Dashboard/Topbar 通过且无 JS error。

## 第二轮 R20 残余风险
- LLM 状态接口默认不探测外部 provider，真实连通性仍通过 LLM 配置页连接测试验证。
- Topbar 目前挂载时读取一次 LLM 状态，配置变更后的自动刷新可在 R21/R后续体验优化中处理。
- Dashboard 新聚合未做大数据量性能压测；当前本地 SQLite、契约测试和浏览器烟测均通过。

## 第二轮 R21 完成状态
- R21 名称：AI 助手与 Prompt 闭环。
- 后端新增/增强 `POST /api/v2/prompt-templates`、`DELETE /api/v2/prompt-templates/{templateId}`、`POST /api/v2/prompt-templates/{templateId}/test`、`GET /api/v2/assistant/context`、`POST /api/v2/assistant/drafts`；Prompt 模板测试渲染兼容 `variables` 嵌套与 flat payload。
- `/chat` fallback 会追加 assistant context 摘要；R21 所有响应不调用真实 provider 且做敏感信息脱敏。
- 前端 AI 助手已支持复制整条回复、读取/保存常用 Prompt、展示最近操作、把最近操作带入输入框，并生成测试点/澄清问题/缺陷备注草稿。
- LLM 配置页新增 Prompt 模板管理面板，支持加载/新增/编辑/测试渲染/删除自定义模板，内置模板不可删除。
- QA 修复：前端 `/assistant/drafts` 已发送 `message: prompt`；最近操作 normalize 已兼容 `recent_activities.list` 与 `operation_logs.list`。
- `docs/orchestration/ROUND21_REPORT.md` 已记录实现、验证和残余风险。
- Round 21 主线程验收：`python -m compileall backend\aitest_platform` 通过；`python -m pytest backend\tests\test_round21_ai_prompt.py -q` 4 passed；`python -m pytest backend\tests\test_round19_dashboard_chat.py backend\tests\test_round20_dashboard_topbar.py -q` 6 passed；`cd backend; python -m pytest -q` 通过；`npm run build` 通过，仅 Vite chunk size warning；Headless Chrome CDP 烟测通过且 `window.__r21Errors` 为空。

## 第二轮 R21 残余风险
- 真实 LLM 仍默认关闭。
- Prompt 模板只是基础 CRUD/测试渲染，尚未做收藏排序/团队级模板权限。
- 最近操作/operation logs 是摘要上下文，不是全量审计回放。
- 结构化草稿为 deterministic rules fallback，不等同真实 LLM 资产生成。
- 下一步进入 R22：需求库解析与确认闭环。

## 第二轮 R22 完成状态
- R22 名称：需求库解析与确认闭环。
- 后端实现：TXT/Markdown 多 block 解析，重 parse 替换旧 blocks；fallback extract 基于 blocks 生成多条可追溯需求项；DB 化 split/merge/shelve/quality-check/brain analyze/get/traceability refresh；闭环响应脱敏，不回显 token/cookie/Authorization/secret。
- 前端实现：Requirements 页面展示解析块/source anchors；需求项编辑保存、确认、暂不入库、拆分、合并、粒度质检、需求大脑、追溯刷新接后端；多选合并；brain/source_refs 等返回形状归一化，修复浏览器烟测中 `source_refs.slice is not a function` 崩溃。
- 测试：新增 `backend/tests/test_round22_requirement_closure.py`，覆盖 parse/extract/edit/confirm/shelve/split/merge/quality/brain/traceability/redaction。
- 验证：`python -m compileall backend\aitest_platform` 通过；`python -m pytest backend\tests\test_round22_requirement_closure.py -q` 7 passed；`python -m pytest backend\tests\test_p0_acceptance.py backend\tests\test_round4_main_chain_llm.py backend\tests\test_round14_requirement_testcase_integration.py -q` 17 passed；`cd backend; python -m pytest -q` 全量通过；`npm run build` 通过，仅 Vite chunk size warning；Headless Chrome CDP 烟测通过，R22 专用项目进入需求库工作台，source anchors 可见，合并/质检/追溯/暂不入库/拆分按钮可见，点击质检和需求大脑结果可见，`window.__r22Errors` 为空。
- 残余风险：解析仍为规则化 TXT/Markdown，不覆盖 docx/pdf/xlsx 深解析；真实 LLM 默认关闭，需求大脑是 DB deterministic 摘要；split/merge lineage 用状态和响应表达，未新增正式血缘表；浏览器烟测使用本地临时 smoke 数据。
- 下一步进入 R23：用例评审与质量规则。

## 第二轮 R23 完成状态
- R23 名称：用例评审与质量规则。
- 后端实现：新增 deterministic 用例质量规则服务 `backend/aitest_platform/services/test_case_quality.py`；规则覆盖缺步骤、缺预期、预期不可断言/过短、标题过短、缺 source anchors、优先级不一致、重复/相似、不可执行、同需求 happy path 覆盖弱；新增/增强接口 `POST /test-cases/{caseId}/quality-review`、`POST /test-cases/review-batch`、`GET /projects/{projectId}/test-case-quality-summary`、`POST /test-cases/{caseId}/review-opinions`；旧入口 `rule-validate` 和 `ai-review` 复用新规则服务；不调用真实 LLM，响应 provider flags false，并做脱敏。
- 前端实现：TestCases 页面新增项目级质量摘要区；接入单条质量评审、批量评审、评审意见保存；表格增加质量分和单条评审操作；所有评审返回 array/object/string/null 归一化，避免 R22 类似 `.slice` 崩溃。
- QA：新增 `backend/tests/test_round23_testcase_quality.py`，覆盖完整项目链路、好/坏/重复/优先级不一致用例、质量评审、批量评审、项目摘要、人工意见、旧入口、secret redaction。
- 验证：`python -m compileall backend\aitest_platform` 通过；`python -m pytest backend\tests\test_round23_testcase_quality.py -q` 5 passed；`python -m pytest backend\tests\test_round14_requirement_testcase_integration.py backend\tests\test_round22_requirement_closure.py -q` 9 passed；`cd backend; python -m pytest -q` 全量通过；`npm run build` 通过，仅 Vite chunk size warning；Headless Chrome CDP 烟测通过：R23 专用项目进入测试用例库，质量摘要可见，批量评审/单条评审按钮可见，批量评审后结果可见，`window.__r23Errors` 为空。
- 残余风险：规则评分是 deterministic 启发式，阈值后续可按产品验收口径微调；人工评审意见保存到操作日志/状态字段，没有新增正式 Review 表；浏览器烟测使用本地临时 smoke 数据；真实 LLM 默认关闭。
- 下一步进入 R24：执行与缺陷闭环。

## 第二轮 R24 完成状态
- R24 名称：执行与缺陷闭环。
- 后端实现：新增 deterministic execution defect loop service `backend/aitest_platform/services/execution_defect_loop.py`；新增 `GET /executions/templates`、`POST /executions/{executionId}/defect-suggestion`、`POST /executions/{executionId}/create-defect`、`POST /defects/{defectId}/link-case`、`POST /defects/{defectId}/unlink-case`、`POST /defects/{defectId}/retest-reminder`、`GET /projects/{projectId}/execution-trend`、`GET /projects/{projectId}/defect-loop-summary`；增强 batch/statistics/defects patch/copy-text；`defect-suggestion` 返回 top-level `steps_to_reproduce`；`copy-text` 使用中文标签“复现/实际/预期/复测建议”；不接真实 LLM，并注意敏感信息脱敏。
- 前端实现：`src/pages/Execution.jsx` 接入 templates、trend、defect loop summary、suggestion/create/link/unlink/retest/status/copy；批量摘要显示 `created_defects` / `failed` / `blocked` / `skipped`；历史趋势优先后端数据；做了 shape normalization。
- QA：新增 `backend/tests/test_round24_execution_defect_loop.py`，覆盖项目链路、模板、建议、创建缺陷、关联/解除、复测提醒、趋势、摘要、统计、筛选/patch/copy、批量摘要、脱敏。
- 验证：`python -m compileall backend\aitest_platform` 通过；`python -m pytest backend\tests\test_round24_execution_defect_loop.py -q` 8 passed；`python -m pytest backend\tests\test_round15_execution_history.py backend\tests\test_round23_testcase_quality.py -q` 6 passed；`npm run build` 通过；`python -m pytest -q` 完整后端回归通过，退出码 0。
- API 验收：项目实际前缀为 `/api/v2`；裸 `/executions/templates` 和 `/api/executions/templates` 返回 404 是前缀不匹配，`/api/v2/executions/templates` 返回 200。
- 浏览器轻量验收：`http://127.0.0.1:3000/` 可加载，页面入口包含 `用例执行`；QA 收集到 `console.error` / `pageerror` 无明显 JS runtime error。
- 残余风险：扩展缺陷字段通过 `Defect.remark` 的 R24 JSON prefix 存储，避免 schema 迁移；建议和复测为 deterministic 规则，非真实 LLM；冒烟使用临时数据；趋势聚合基于本地 SQLite。
- 下一步进入 R25：接口测试增强。

## 第二轮 R25 完成状态
- R25 名称：接口测试增强。
- 后端实现：OpenAPI YAML 轻量解析（不新增 PyYAML 依赖）、HAR 基础解析、debug `save_as_case` 保存为 `ApiTestCase`、API runtime context 统一变量/header 优先级、scenario `data_mappings.extract` 增强、Mock 服务基础能力、受控 pre/post script allowlist DSL。
- 后端新增服务：`backend/aitest_platform/services/api_runtime_context.py`、`backend/aitest_platform/services/api_mock_service.py`、`backend/aitest_platform/services/api_script_runner.py`。
- 后端增强：`backend/aitest_platform/services/api_importer.py`、`backend/aitest_platform/services/api_runner.py`、`backend/aitest_platform/services/api_scenario_runner.py`、`backend/aitest_platform/api/router.py`。
- 前端实现：`src/pages/ApiTesting.jsx` 新增 JSON/YAML/HAR 导入面板、真实 debug 表单、保存为接口用例、环境变量/运行覆盖、场景变量映射、Mock 服务 UI、pre/post script UI。
- QA：新增 `backend/tests/test_round25_api_testing_enhancement.py`，覆盖 YAML/HAR、debug save、变量优先级、scenario mapping、mock、allowlist/danger script。
- 验证：`cd backend; python -m compileall aitest_platform` passed，exit code 0；R5/R6/R7/R25 定向回归 passed，exit code 0，仅 FastAPI `HTTP_422_UNPROCESSABLE_ENTITY` deprecation warning；`cd backend; python -m pytest -q` 完整后端回归 passed，exit code 0，仅 FastAPI deprecation warning；根目录 `npm run build` passed，exit code 0，仅 Vite chunk > 500 kB warning。
- API/浏览器冒烟：临时 SQLite 已删除；OpenAPI YAML import imported=1 path `/r25/smoke/users` expected status 206；HAR import imported=1 path `/r25/smoke/orders` expected status 202；Mock create/list/dispatch matched=true status 207；debug save_as_case status 200 saved_case_id=3；`http://127.0.0.1:3000/` 进入 ApiTesting/workbench，R25 UI 关键词可见 5 个：OpenAPI YAML、HAR、环境变量、本次运行覆盖、Mock 服务；console.error=0，pageerror=0；进程和临时 DB 已清理，8000/3000 无监听。
- 残余风险：YAML 为轻量解析非完整 YAML 规范；脚本为 allowlist DSL 非任意代码；Mock 服务为本地平台基础 mock 非完整代理网关；Vite 仍有 chunk > 500 kB warning；浏览器只做轻量加载/可见性/console smoke，深层 UI 写操作主要由 API 冒烟覆盖。
- 下一步进入 R26：自动化中心增强。

## 第二轮 R26 完成状态
- R26 名称：自动化中心增强。
- 后端实现：候选筛选/选择、文件 CRUD、执行详情、artifact 列表与预览路由；`generate-cases` 支持候选选择；Playwright 模板增强；新增 `backend/aitest_platform/services/auto_center.py`；`exporting.py` 对文本类 artifact ZIP 内容脱敏。
- 前端实现：`src/pages/Automation.jsx` 新增候选筛选、case file 在线编辑/dirty/save/reset、Playwright 模板配置、按 `case_file_ids` 执行、执行详情日志/evidence、artifact preview。
- QA：新增 `backend/tests/test_round26_automation_center.py`，覆盖候选筛选/过滤、候选选择影响生成、Playwright 模板增强、在线文件查看/保存/非法路径、按文件执行与详情、artifact 列表/预览、artifact ZIP 回归安全。
- 验证：`cd backend; python -m compileall aitest_platform` passed，exit code 0；R26 组合回归 `python -m pytest tests/test_round6_execution_runners.py tests/test_round8_artifacts.py tests/test_round11_exports.py tests/test_round13_frontend_integration.py tests/test_round25_api_testing_enhancement.py tests/test_round26_automation_center.py -q` passed，40 passed，仅 FastAPI deprecation warning；full backend `python -m pytest -q` passed，exit code 0，仅 FastAPI deprecation warning；`npm run build` passed，仅 Vite chunk >500k warning。
- API/浏览器冒烟：API smoke passed，候选筛选/过滤、文件保存、artifact preview 均返回合理结果；浏览器最终复验 Automation 页面打开，console.error=0，pageerror=0，`/case-files` 请求数 0，`/case-files` 404 为 0，`/auto-projects/693/files?page=1&pageSize=200` 返回 200，R26 DOM 可见关键词 8/8：候选筛选、在线文件、保存、Playwright、trace、Artifacts、预览、执行日志；进程清理后 8000/3000 已停止并复查无监听。
- 残余风险：Vite chunk warning；Playwright 真实执行依赖本机环境；trace/zip 预览不展开执行；浏览器深层写操作主要由 API smoke 和后端契约测试覆盖。
- R26 验收证据见 `docs/orchestration/ROUND26_REPORT.md`。

## 第二轮 R27 完成状态
- R27 名称：性能测试增强。
- 后端实现：性能停止/中止接口、阈值判定、历史对比、项目 `performance-trend` 聚合；JMeter 参数编辑会体现在生成/下载脚本中；`generate-report` 增加风险建议并递归脱敏。
- 后端新增服务：`backend/aitest_platform/services/perf_analysis.py`。
- 后端增强：`backend/aitest_platform/api/router.py`、`backend/aitest_platform/services/perf_runner.py`、`backend/aitest_platform/services/reporting.py`、`backend/aitest_platform/services/exporting.py`。
- 前端实现：`src/pages/Performance.jsx` 接完整 results、阈值判定、历史比对、7 日趋势、JMeter 参数表单、停止执行、报告风险/建议展示，并去掉关键静态假数据。
- QA：新增 `backend/tests/test_round27_performance_enhancement.py`，覆盖停止/中止、阈值判定、历史对比、趋势聚合、JMeter 参数、报告建议和递归脱敏。
- 验证：`python -m compileall backend/aitest_platform` passed；R27 定向 10 passed；合同组合回归 passed；后端全量 `pytest -q` passed；`npm run build` passed；真实 Chrome Playwright 烟测 passed，`console.error=0`，`pageerror=0`。
- 浏览器关键词命中：阈值判定、性能历史比对、7日趋势 P95、JMeter 参数/模板参数、停止执行、报告建议/风险建议。
- 残余风险：真实 JMeter 执行依赖本机工具和目标环境；阈值/风险建议为当前规则口径，后续可按项目 SLA 调整；趋势依赖已落库样本。
- R27 验收证据见 `docs/orchestration/ROUND27_REPORT.md`。
- 下一步已进入并完成 R28：报告中心增强。

## 第二轮 R28 完成状态
- R28 名称：报告中心增强。
- 后端实现：report-templates CRUD 校验与默认唯一；综合报告按 `template_id`/`scope` 生成并冻结模板、章节、scope；报告列表过滤排序；report drilldown；report risks；风险转待办与 todo 列表/状态；Markdown/HTML 强化与 HTML escape/递归脱敏；PDF/Word/docx unsupported 结构化返回；轻量结论支持 `daily_report`、`test_submission_feedback`、`release_advice`、`risk_list`。
- 前端实现：Reports 页移除 fallback/static AI 意见、固定默认报告和假分享；接真实报告列表、模板管理、筛选排序、下钻、风险转待办、下载和轻量结论类型。
- QA：新增 `backend/tests/test_round28_report_center_enhancement.py`，13 passed。
- 验证：`python -m compileall backend/aitest_platform` passed；R28 定向 13 passed；合同组合回归 passed；后端全量 `pytest -q` passed；`npm run build` passed；真实 Chrome Playwright 报告中心烟测 passed，`console.error=0`，`pageerror=0`。
- 浏览器关键词/入口命中：风险转待办、Markdown、HTML、日报、提测反馈、上线建议、风险清单、管理报告模板/新建模板、查看下钻/下钻明细。
- 端口已清理。
- 残余风险：PDF/Word/docx 仍为 unsupported 结构化返回，未引入新导出依赖；轻量结论仍按当前报告聚合口径输出。
- R28 验收证据见 `docs/orchestration/ROUND28_REPORT.md`。
- 下一步已进入并完成 R29：数据工厂与数据管理。

## 第二轮 R29 完成状态
- R29 名称：数据工厂与数据管理。
- 后端实现：`POST /data-factory/api-parameters/generate`、`GET /test-cases/{caseId}/test-data-suggestions`、`GET /system/backup-status`、`GET /system/storage-summary`、`POST /system/cleanup`。
- 清理接口已具备 dry-run、安全确认文本 `CLEANUP`、模块白名单、路径根目录限制和响应脱敏。
- 前端实现：Settings 接存储统计、备份提醒、清理 dry-run 与确认执行；ApiTesting 增加生成测试数据入口；Execution 增加准备测试数据入口和空态。
- QA：新增 `backend/tests/test_round29_data_factory_management.py`，当前复验 5 passed；后端实现阶段曾记录 8 passed，当前以文件实际测试为准。
- 验证：R29 定向测试复验 5 passed；合同回归组合 passed；后端全量 passed；`npm run build` passed；浏览器复验 passed，Settings cleanup dry-run 200，payload 包含 `execution_history`、`api_execution_history`、`artifacts`，`console.error=0`，`pageerror=0`。
- 真实清理未执行：dry-run 显示会影响 849 个 artifact 文件，出于安全边界仅验证 dry-run 和确认门能力。
- 端口说明：本机 8000 被既有 `python -m http.server 8000` PID 4588 占用，验收使用 8001，未触碰非本次启动进程。
- R29 验收证据见 `docs/orchestration/ROUND29_REPORT.md`。
- 下一步已进入并完成 R30：文件与导出格式增强。

## 第二轮 R30 完成状态
- R30 名称：文件与导出格式增强。
- 后端实现：统一 unsupported contract；无依赖 XLSX 导出 test-cases/defects；公式注入中和；二进制 docx/pdf/xlsx/xmind 导入硬边界；自动化/性能 artifact ZIP canonical path 校验、越界 skipped metadata 和文本脱敏。
- 前端实现：移除假下载/假成功；TestCases 支持 CSV、Markdown、JSON、XLSX；PDF、Word、XMind 未开放真实服务端生成并展示未开放提示；Reports/Performance 使用 HTML/Markdown 替代；统一下载 helper 处理 unsupported、空内容和真实下载。
- QA：新增 `backend/tests/test_round30_file_export_formats.py`，R30 定向 36 passed。
- 验证：`python -m compileall backend\aitest_platform` 通过；R30 定向 36 passed；合同回归组合 64 passed；后端全量通过；`npm run build` 通过；真实 Chrome 烟测通过，TestCases 四种真实下载、XLSX 真实 ZIP workbook、unsupported 不返回假文件字段、artifact 越界 skipped，`console.error=0`，`pageerror=0`。
- 端口说明：本机 8000 被既有 PID 4588 占用，验收使用 8001，未触碰外部进程。
- R30 验收证据见 `docs/orchestration/ROUND30_REPORT.md`。
- 残余风险：PDF/Word/XMind 未做真实服务端生成；本轮未新增生产依赖；docx/pdf/xlsx/xmind 导入只建立硬边界，不做深度解析。
- R30 后进入 R31：生产基础设施决策门；当前已完成 R31 文档收口，R32 仍未开始。

## 第二轮 R31 完成状态
- R31 名称：生产基础设施决策门。
- 本轮性质：只做决策记录和文档同步，不实施生产基础设施，不新增代码、测试、数据库迁移、运行时服务或生产依赖。
- 决策结论：R32 总验收继续以 SQLite 本地优先作为支持目标；当前默认数据库仍为 `backend/data/aitest.sqlite3`，artifacts 仍默认使用本地目录 `backend/data/artifacts/`。
- deferred / unsupported unless explicitly approved：PostgreSQL/pgvector、Celery/Redis、MinIO/S3、真实密钥加密存储、Alembic。
- 原因：这些能力会引入部署、迁移、运维、安全和回滚复杂度；当前第二轮验收目标仍可在本地优先边界内完成。
- 已同步文档：`docs/orchestration/DECISIONS.md` 增加 R31 决策矩阵；新增 `docs/orchestration/ROUND31_REPORT.md`；同步 `STATUS.md`、`HANDOFF.md`、`ACCEPTANCE.md`、`SECOND_ROUND_ROADMAP.md` 和 `backend/README.md`。
- 保护性状态：未写入 secrets；未把 deferred 生产依赖写成已完成；未 commit/push。
- 验证：`git diff --check` 通过；仅出现 Git 行尾转换提示，无 whitespace error。
- 下一步进入 R32：第二轮总验收。R32 尚未开始，不能标记为完成。
