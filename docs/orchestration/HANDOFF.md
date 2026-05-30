# Worker 交接契约

## 文档依据
- `00-AI测试平台需求文档.md`
- `02-技术实现方案.md`

## 后端目录约定
- 后端代码放在 `backend/`
- Python 包名建议：`aitest_platform`
- API 前缀：`/api/v2`
- 默认数据库：`backend/data/aitest.sqlite3`

## 统一响应格式
```json
{
  "code": 0,
  "message": "ok",
  "data": {},
  "trace_id": "uuid"
}
```

## 第一轮实体边界
- Project
- RequirementLib
- RequirementDocument
- RequirementItem
- TestPoint
- TestCase
- GenerationJob
- TestRound
- Execution
- Defect
- ApiTestLib / ApiEndpoint / ApiEnvironment / ApiScenario
- AutoProject
- PerfPlan
- Report / ReportTemplate
- LlmConfig / PromptTemplate
- OperationLog

## 第一轮接口边界
- 必须覆盖文档技术方案中的核心 `/api/v2` 清单的可运行子集。
- 暂不要求真实 LLM、真实浏览器执行、真实 JMeter 执行。
- 生成、执行、导出类接口可返回结构化模拟结果，但必须写入或读取统一数据层。

## 文件所有权
- backend_data_engineer：`backend/aitest_platform/db/**`、`backend/aitest_platform/models.py`、`backend/aitest_platform/repositories.py`、`backend/aitest_platform/seed.py`
- backend_api_engineer：`backend/aitest_platform/main.py`、`backend/aitest_platform/schemas.py`、`backend/aitest_platform/api/**`
- devops_qa_engineer：`backend/pyproject.toml`、`backend/README.md`、`backend/.env.example`、`backend/tests/**`

## 协作规则
- 你不是唯一 worker，不要回滚他人改动。
- 如需改动他人文件，先在最终报告中说明原因和风险。
- 每个 worker 必须给出：改动文件、测试命令、完成度评分、风险。

## 第二轮交接
- 数据层优先补齐 P1 模型与 repository，API 层可以在数据层模型存在后接入。
- API 层不得继续为第二轮范围内资源写入内存 store。
- QA 层不得修改实现代码；测试可以先按契约写，若实现未到位应明确失败点。
- 所有新接口仍用现有 `WritePayload` 宽松输入即可，除非局部需要明确 schema。
- 占位执行必须是确定性的、结构化的、可查询的，不允许只返回临时字符串。
- Secrets 规则：`api_key`、token、cookie、git_auth 等字段不得原样返回或写入日志。

## 第三轮交接
- 用户提供了本地 OpenAI-compatible `/v1` 服务地址和 API key；API key 不得进入任何文件。
- 实现只读取环境变量或运行时配置：
  - `AITEST_LLM_BASE_URL`
  - `AITEST_LLM_API_KEY`
  - `AITEST_ENABLE_REAL_LLM`
- 默认 `AITEST_ENABLE_REAL_LLM=false`，避免测试和本地启动误触真实调用。
- QA 使用 mock/monkeypatch 覆盖 enabled path，不使用用户真实 key。

## 第四轮交接
- 主链 LLM 生成只接 `extract-items`、`generate-test-points`、`generate-test-cases`。
- 复用第三轮 LLM client，测试继续使用 monkeypatch/mock，不使用用户真实 key。
- 生成失败必须回落到现有 repository placeholder 方法。
- 不要把 prompt 原文中的敏感上下文写入日志；`GenerationJob.input_payload` 只保留类型、id、mode、fallback reason 等摘要。

## 第四轮完成状态
- 主链三条生成接口已支持 enabled mock LLM JSON，结果会结构化写入 SQLite。
- disabled、missing config、provider error、bad JSON 会降级到 repository placeholder。
- `GenerationJob` 会记录 source/fallback/usage 摘要；`LlmUsage` 会记录 requirement_extract、test_point_generation、test_case_generation。
- OpenAI-compatible real key 仍只允许通过环境变量提供，禁止写入文件、日志、测试或文档。

## 第五轮候选范围
- 真实 API 调试执行器：导入 OpenAPI/curl 后可真实发起请求、断言响应、落库执行证据。
- 真实 Playwright 自动化执行器：从自动化项目/用例文件触发浏览器执行、收集截图/trace/日志。
- 真实 JMeter 或轻量性能执行器：生成脚本后可运行、解析结果、生成性能报告。
- 正式任务调度与迁移：Celery/Redis 或本地队列、Alembic、密钥管理。

## 第五轮完成状态
- `/apis/debug` 已支持真实 httpx 请求、响应快照、断言结果和错误降级。
- `/api-test-cases/{caseId}/execute` 已支持 environment/base URL 真实执行并写入 `ApiExecution`。
- `/api-test-cases/batch-executions` 已复用同一 runner。
- 没有 environment/base URL 时保留 Round 2 placeholder fallback。
- Round 5 已补充 secret redaction 测试和本地 HTTP smoke。

## 第六轮候选范围
- Playwright 自动化执行器：从 AutoProject/AutoCaseFile 触发本地 Playwright，保存 stdout、失败截图和 artifacts。
- API 场景执行增强：跨步骤变量提取、数据映射、依赖顺序执行。
- JMeter 性能执行器：运行 JMX、解析 JTL、落库 PerfResult。
- 后端工程化：Alembic 迁移、正式密钥管理、本地队列或 Celery/Redis。

## 第六轮交接
- 自动化、性能、API 场景 worker 都可能改 `router.py`，必须只改自己负责的路由区块，不回滚他人改动。
- runner 服务放在 `backend/aitest_platform/services/`，避免把复杂执行逻辑塞进 router。
- 所有 runner 都必须限制 timeout、输出长度，并对 secret 做脱敏。
- 默认保持旧 placeholder 兼容，只有存在可执行资产或请求明确真实执行时进入真实 runner。

## 第六轮完成状态
- 自动化 runner 已可执行 persisted Python/pytest case files，并将 summary、logs、artifacts 写入 `AutoExecution`。
- JMeter runner 已可运行 JMX、解析基础 JTL 摘要并写入 `PerfResult`；缺工具/超时/执行失败走结构化 error。
- API scenario runner 已可按节点顺序执行 case，支持基础变量注入、`$.body.xxx` 提取和 `stop_on_failure`。
- `/api/v2/search` 已修复为 SQLite 查询侧过滤，避免默认持久库历史数据污染搜索结果。
- Round 6 主线程验收：`42 passed, 2 warnings`，OpenAPI `/api/v2` path 数 105。

## 第七轮候选范围
- OpenAPI/Postman/curl 导入解析：把真实接口文档导入为 `ApiEndpoint`/`ApiTestCase`，保持无新增依赖优先。
- 本地调度闭环：在不引入 Celery/Redis 的前提下，先实现 SQLite-backed 手动/一次性/轮询式任务执行记录。
- 执行证据增强：自动化失败截图/trace、JMeter HTML report、API scenario 更完整 artifacts。
- 密钥管理设计：继续禁止真实 key 写入文档/测试/日志；如需本地加密或凭证库，应单独决策。

## 第七轮交接
- 导入 worker 只改 import 相关路由：`/api-test-libs/{libId}/import-documents` 和 `/api-test-libs/{libId}/apis/import`；复杂解析放到 `services/api_importer.py`。
- 调度 worker 只改 schedules 相关路由：`/api-schedules/{scheduleId}/run`、`/api-schedules/run-due` 和必要 helper；执行逻辑放到 `services/schedule_runner.py`。
- QA worker 尽量只新增 `backend/tests/test_round7_import_schedule.py`，不要修改实现代码。
- 三个 worker 都要继续遵守 secret redaction；测试只能使用 fake secret。

## 第七轮完成状态
- `services/api_importer.py` 已支持 OpenAPI/Swagger JSON、Postman Collection JSON、curl 和旧手工 payload。
- `/api-test-libs/{libId}/import-documents` 与 `/api-test-libs/{libId}/apis/import` 已接入解析器，并可按 `generate_cases/create_cases/create_test_cases` 生成 ApiTestCase。
- `services/schedule_runner.py` 已支持 schedule 手动 run 与 `run-due` due-scan；case/scenario 执行结果落库并更新 `last_run_at`、`last_result`。
- 主线程已修复 Round7 集成测试发现的 postman 别名、collection 字段、Postman name、run-due lib 过滤和响应过宽问题。
- Round 7 主线程验收：`47 passed, 2 warnings`，OpenAPI `/api/v2` path 数 107。

## 第八轮候选范围
- 执行证据增强：自动化 runner 采集并返回截图、trace、pytest/junit 等 artifacts；JMeter runner 可选生成 HTML report。
- 工程化增强：无新依赖版本的 schema/migration 状态记录；如要正式 Alembic，需要单独确认新增依赖。
- 密钥管理增强：本地 secret reference registry 或加密存储设计；继续禁止真实 key 写入文档/测试/日志。

## 第八轮交接
- 自动化 artifacts worker 只改 `services/auto_runner.py` 和必要的自动化执行兼容字段，不碰性能 runner。
- 性能 artifacts worker 只改 `services/perf_runner.py` 和必要 README，不碰自动化 runner。
- QA worker 只新增 `backend/tests/test_round8_artifacts.py`，用 fake secret 验证脱敏。
- artifacts 默认落在 `backend/data/artifacts/`，测试可用临时路径或 monkeypatch，避免污染真实工作区。

## 第八轮完成状态
- 自动化 runner 已支持 `artifact_root`，默认落盘到 `backend/data/artifacts/auto/<run_id>/`。
- 自动化 evidence 包含 `kind/path/relative_path/size_bytes/source`，支持 screenshot、trace、video、junit/xml、html、log。
- 性能 runner 已支持 `artifact_root`，默认落盘到 `backend/data/artifacts/perf/<run_id>/`。
- 性能 evidence 包含 jmx、jtl、stdout、stderr、html_report，`raw_data_path` 指向持久化 JTL。
- Round 8 主线程验收：`51 passed, 2 warnings`，OpenAPI `/api/v2` path 数 107。

## 第九轮候选范围
- 系统恢复：把 `/system/restore` 从 dry-run 推进为安全 merge restore，支持版本检查、预览、确认字段、防止误覆盖。
- schema/migration 状态：不引入 Alembic 的前提下提供 schema version/status endpoint；如需正式 Alembic 需单独确认依赖。
- 密钥引用 registry：继续不存真实 key，补充 hash/ref 管理和响应脱敏一致性。

## 第九轮交接
- restore worker 只改 `services/restore_service.py`、`schemas.py` 的 restore payload 兼容和 `/system/restore` 路由。
- schema worker 只改 `services/schema_status.py` 和 `/system/schema-status` 路由。
- QA worker 只新增 `backend/tests/test_round9_restore_schema.py`。
- 禁止在测试或文档中写真实 key；只能使用 fake secret 并验证脱敏。
- 不允许在实现或测试中执行清空真实数据库的操作；overwrite 仅通过临时测试库/受控 TestClient 行为验证确认门槛。

## 第九轮完成状态
- `/system/restore` 已支持 dry-run/preview、安全 merge restore、overwrite 确认门槛和脱敏 summary。
- `services/restore_service.py` 可恢复 Round9 范围内的项目、API 测试、自动化、性能和配置类资产。
- `/system/schema-status` 已提供 SQLAlchemy metadata 与当前 DB introspection 对比结果。
- Round 9 主线程验收：`56 passed, 2 warnings`，OpenAPI `/api/v2` path 数 108。

## 剩余需决策项
- 正式 Alembic migration：需要新增依赖/迁移目录与版本策略，建议单独确认后做。
- Celery/Redis：会改变运行形态和依赖，需要确认本地单机还是服务化部署。
- 真实密钥加密存储：需要确认本地密钥来源、加密方案和恢复策略。
- 完整对象存储：MinIO/S3 需要部署配置，当前 artifacts 先落本地目录。

## 第十轮候选范围
- 报告聚合层：实现文档 4.20 要求的统一 Reporting Aggregator，不再由报告端点临时拼接占位文案。
- 报告快照层：生成报告时冻结 `scope_snapshot`、`data_snapshot`、`source_refs_json`，避免历史报告随实时数据漂移。
- 报告输出层：先支持 Markdown / HTML / JSON，不新增 PDF/Word 依赖。
- 轻量结论：复用正式报告聚合上下文，保证轻量结论与正式报告口径一致。

## 第十轮交接
- reporting worker 可新增 `services/reporting.py`，并小范围修改报告相关路由：`/reports/comprehensive`、`/perf-plans/{planId}/generate-report`、`/reports/{reportId}/download`、`/reports/lightweight-conclusions`。
- QA worker 只新增 `backend/tests/test_round10_reporting.py`，不修改实现代码。
- 不允许写入真实密钥；测试只能使用 fake secret，并验证脱敏。
- 不引入新生产依赖；PDF/Word、对象存储、Celery/Redis 继续作为决策项保留。

## 第十轮完成状态
- `services/reporting.py` 已实现统一 Reporting Aggregator。
- `/reports/comprehensive` 已生成包含 `scope_snapshot`、`data_snapshot`、`source_refs_json` 的综合报告快照。
- `/perf-plans/{planId}/generate-report` 已基于最新 PerfResult 生成性能报告快照。
- `/reports/{reportId}/download` 已支持 Markdown / HTML / JSON 输出。
- `/reports/lightweight-conclusions` 已复用聚合上下文，并支持 `save=true` 保存报告。
- Round 10 主线程验收：`63 passed, 2 warnings`，OpenAPI `/api/v2` path 数 108。

## 第十一轮候选范围
- 用例导出：Markdown / CSV / JSON，支持项目、需求项、选中 IDs、类型过滤。
- 缺陷导出：Markdown / CSV / JSON，支持项目和状态过滤。
- 自动化项目下载：将 framework files 和 case files 打包为 ZIP，返回 base64 内容和文件清单。
- 性能下载：下载 JMX 脚本和性能结果摘要/原始数据引用。

## 第十一轮交接
- export worker 可新增 `services/exporting.py`，并小范围修改导出/下载相关路由。
- QA worker 只新增 `backend/tests/test_round11_exports.py`，不修改实现代码。
- 不允许写入真实密钥；测试只能使用 fake secret 并验证导出内容脱敏。
- 不引入新依赖；`.xlsx`、PDF、Word、对象存储继续作为决策项保留。

## 第十一轮完成状态
- `services/exporting.py` 已统一实现 Markdown / CSV / JSON 导出、ZIP 打包和脱敏。
- `/test-cases/export` 已支持项目、需求项、用例 IDs、用例类型过滤。
- `/defects/export` 已支持项目和状态过滤。
- `/auto-projects/{autoProjectId}/download` 已返回可解码 ZIP，并保留 `download_url` 兼容字段。
- `/perf-plans/{planId}/download-script` 已支持 JMX 下载。
- `/perf-plans/{planId}/results/{resultId}/download` 已支持性能结果 JSON 下载和原始路径可用性说明。
- Round 11 主线程验收：`71 passed, 2 warnings`，OpenAPI `/api/v2` path 数 112。

## 第十二轮候选范围
- DB 回收站：列出和恢复数据库软删除对象，替代纯内存占位。
- 用户偏好：保存继续上次位置等本地偏好。
- 最近活动：保存最近访问的项目、需求、用例、报告等入口。

## 第十二轮完成状态
- `services/system_state.py` 已实现 DB 回收站、用户偏好、最近活动和脱敏。
- `/system/recycle-bin` 已合并数据库软删除对象与旧内存 store 对象。
- `/system/recycle-bin/{id}/restore` 已支持 `type:id` 数据库对象恢复。
- `/system/preferences` 与 `/system/preferences/{prefKey}` 已使用 `round2_resource` 持久化用户偏好。
- `/system/recent-activities` 已使用 `round2_resource` 持久化最近活动。
- `run-due` compact response 已收窄字段，避免历史测试被无关数字污染。
- Round 12 主线程验收：`74 passed, 2 warnings`，OpenAPI `/api/v2` path 数 115。

## 第十三轮候选范围
- 前端第一批集成：Dashboard、Reports、SettingsPage 先替换高价值 mock 链路。
- 后端浏览器联通：本地 CORS、统一响应 headers、真实 Uvicorn 请求验证。
- 交互稳定性：有真实后端动作的按钮必须能在浏览器中稳定点击。

## 第十三轮完成状态
- `src/lib/api.js` 已新增前端 API client，默认 `http://127.0.0.1:8000/api/v2`，可用 `VITE_API_BASE_URL` 覆盖。
- `backend/aitest_platform/main.py` 已增加本地 CORS，并修复旧 `Content-Length` 复用。
- `src/pages/Dashboard.jsx` 已接默认项目、dashboard、recent activities，并保留离线降级。
- `src/pages/Reports.jsx` 已接报告列表、综合报告生成、报告下载、轻量结论生成/归档。
- `src/pages/SettingsPage.jsx` 已接 schema-status、runtime settings preference、system backup。
- `src/components/TiltCard.jsx` 已避免交互控件触发 3D hover 更新；Settings 快照动作卡改为普通 `theme-card`，确保点击稳定。
- Round 13 主线程验收：`npm run build` 通过；Round13 tests 通过；后端全量测试通过；浏览器验证 Dashboard/Reports/Settings 主流程通过。

## 下一轮建议范围
- Requirements：需求库/文档/需求项列表接后端 CRUD 与生成主链。
- TestCases：测试用例列表、导出、详情接后端。
- Execution：执行计划/执行记录/缺陷联动接后端。
- ApiTesting：接口库、导入、debug、case execute、scenario run 接后端。
- LlmConfig：配置列表与 test/chat 已有后端能力，可继续替换 mock。

## 第十四轮候选范围
- Requirements：需求库/文档/需求项列表接后端 CRUD 与生成主链。
- TestCases：测试用例列表、生成、导出接后端。
- 后端补齐前端缺失的列表型聚合接口，避免前端绕行多个资源端点。

## 第十四轮完成状态
- `backend/aitest_platform/api/router.py` 已新增需求库文档列表、需求库需求项列表、项目级测试用例列表接口。
- `backend/tests/test_round14_requirement_testcase_integration.py` 已覆盖新增接口和导出集成契约。
- `src/pages/Requirements.jsx` 已接入后端需求库加载、新建需求库、导入需求文档、解析提取需求项、生成测试点。
- `src/pages/TestCases.jsx` 已接入后端测试用例加载、需求项用例生成、CSV / Markdown 导出。
- Round 14 主线程验收：`npm run build` 通过；Round14 tests 通过；后端全量测试通过；浏览器验证 Requirements/TestCases 主流程通过；OpenAPI `/api/v2` path 数 118。

## 下一轮建议范围
- Execution：执行计划、执行记录、缺陷联动接后端，并验证手工/自动执行入口。
- ApiTesting：接口库、导入、debug、case execute、scenario run 接后端。
- LlmConfig：配置列表、启停、测试连接、chat smoke 接后端。
- Automation / Performance：继续替换剩余 mock 操作和报告下载入口。

## 第十五轮完成状态
- `backend/aitest_platform/api/router.py` 已新增 `GET /api/v2/projects/{projectId}/test-rounds` 项目级轮次列表。
- `backend/tests/test_round15_execution_integration.py` 已覆盖轮次、批量执行、执行统计、执行历史和失败生成缺陷。
- `src/pages/Execution.jsx` 已接入后端测试用例、执行统计、执行历史、缺陷、轮次、批量执行、重跑失败和缺陷 CSV 导出。
- Execution 项目选择已从固定第一个项目改为优先选择近期项目中有测试用例的项目，避免本地历史空项目导致真实链路不可用。
- Round 15 主线程验收：`npm run build` 通过；Round15 tests 通过；后端全量测试通过；浏览器验证 Execution 主流程通过；OpenAPI `/api/v2` path 数 119。

## 下一轮建议范围
- ApiTesting：接口库、导入、debug、case execute、scenario run 接后端。
- LlmConfig：配置列表、启停、测试连接、chat smoke 接后端。
- Automation：自动化项目、框架生成、用例文件、执行结果与 artifacts 入口继续替换 mock。
- Performance：性能计划、执行结果、报告下载入口继续替换 mock。
- Execution 增强：正式项目选择器、真实 runner、缺陷关联/新建闭环、真实趋势图。

## 第十六轮完成状态
- `src/pages/ApiTesting.jsx` 已接入后端接口库扫描、Swagger/OpenAPI 导入、`/apis/debug` 和 `/api-test-cases/batch-executions`。
- `src/pages/LlmConfig.jsx` 已接入 `/llm-configs` 列表、保存、设默认、停用、新增和 `/llm-configs/{id}/test`；前端只保存环境变量引用，不保存明文 Key。
- `src/pages/Automation.jsx` 已接入自动化项目列表、项目创建、框架生成、用例生成、执行和 Git pull skip 入口。
- `src/pages/Performance.jsx` 已接入性能方案列表、计划生成、脚本生成、执行、报告生成和结果下载入口。
- `docs/orchestration/ROUND16_REPORT.md` 已记录实现、验证、截图和残余风险。
- Round 16 主线程验收：`npm run build` 通过；`cd backend; python -m pytest -q` 通过，80 tests；浏览器验证四页主链路无 console error。

## 下一轮建议范围
- 补正式全局项目选择器，替代各页面自动扫描项目的临时策略。
- 将 ApiTesting 的环境、场景编排、计划任务页面继续接后端运行链路。
- 将 Automation 前端执行入口进一步区分占位 runner 与真实 Playwright runner，并展示 artifacts 下载。
- 将 Performance 前端补齐 JMX 下载、结果 JSON/HTML 导出和真实 JMeter 执行模式开关。
- 继续减少四页剩余静态演示区块，优先替换会影响用户决策的数据。

## 第十七轮完成状态
- `src/lib/projectContext.jsx` 与 `src/components/Topbar.jsx` 已新增全局项目选择器，页面优先使用当前选中项目。
- `src/pages/ApiTesting.jsx` 已接入环境、场景、计划任务后端链路，可创建环境、编排 scenario、执行 scenario 并运行 schedule。
- `src/pages/Automation.jsx` 已支持真实本地 runner / Playwright runner / 占位 runner 切换，展示 runner mode 与 artifacts，并可下载工程 ZIP 和执行 artifacts ZIP。
- `src/pages/Performance.jsx` 已支持真实 JMeter 开关、HTML report 开关、JMX 下载、JSON/HTML 结果导出。
- `backend/aitest_platform/api/router.py`、`services/auto_runner.py`、`services/exporting.py` 已补齐 Playwright 文件生成、Playwright runner 分支、自动化 artifacts 下载和性能 HTML 导出。
- `docs/orchestration/ROUND17_REPORT.md` 已记录实现、验证和残余风险。
- Round 17 主线程验收：`python -m compileall backend\aitest_platform` 通过；`npm run build` 通过；`python -m pytest backend\tests\test_round11_exports.py -q` 通过；`cd backend; python -m pytest -q` 通过。

## 下一轮建议范围
- 将全局项目选择器进一步下沉到 Requirements / TestCases / Execution / Reports / Settings，消除旧页面各自选择项目的差异。
- 为真实 Playwright runner 增加依赖安装状态检测和更明确的前端错误提示。
- 为 JMeter HTML report 提供静态文件预览或受控下载入口，而不仅是结果 HTML 摘要导出。
- 继续减少历史演示数据区块，优先替换图表和风险列表为后端真实统计。

## 第十八轮完成状态
- Dashboard / Requirements / TestCases / Execution / Reports / Settings 已统一使用 `useProjectContext`，不再各自读取 `/projects` 后选第一个项目。
- ApiTesting / Automation / Performance 已去除无全局项目时的项目扫描 fallback，页面以全局选择器为唯一项目来源。
- `/projects/{projectId}/dashboard` 已扩展 API、自动化、性能、报告和状态分布统计，Dashboard 的关键指标、风险待办和执行概览优先取后端数据。
- Reports 详情页已用后端报告 snapshot 生成通过率、缺陷分布、风险项和准出提示。
- `/system/runtime-dependencies` 已提供 Playwright/pytest/Node/npx/JMeter 非侵入式依赖检查；Automation / Performance 前端展示状态并在缺依赖时提示。
- `/perf-results/{resultId}/artifacts/download` 已提供性能执行 artifacts ZIP 受控下载，Performance 报告页增加 Artifacts 下载入口。
- `docs/orchestration/ROUND18_REPORT.md` 已记录实现、验证和残余风险。
- Round 18 主线程验收：`python -m compileall backend\aitest_platform` 通过；`npm run build` 通过；`python -m pytest backend\tests\test_round13_frontend_integration.py backend\tests\test_round11_exports.py -q` 通过。

## 剩余需决策项
- 正式 Alembic migration、Celery/Redis 异步队列、真实密钥加密存储会改变依赖、运行拓扑或迁移策略，未在本轮擅自引入；当前系统继续使用已有 schema-status、自检、脱敏和结构化 runner 降级能力。

## 第十九轮完成状态
- Dashboard 日报/周报摘要接口已从固定占位文案改为 Reporting Aggregator 事实聚合输出，返回 metrics、risk_level、risk_items、next_actions 和 source_refs。
- `src/components/AiAssistant.jsx` 已从纯本地模拟改为优先调用 `/api/v2/chat`，并携带当前全局项目、页面和最近消息上下文。
- `/chat` 在真实 LLM 未启用或不可用时，会基于当前项目后端事实生成风险、待办、准出或报告类降级回复。
- 已移除 AI 助手内置的固定 Bearer 示例与固定执行编号式模拟结论。
- `backend/tests/test_round19_dashboard_chat.py` 已覆盖日报/周报摘要和项目事实型 chat fallback。
- `docs/orchestration/ROUND19_REPORT.md` 已记录实现、验证和残余风险。
- Round 19 主线程验收：`python -m compileall backend\aitest_platform` 通过；`python -m pytest backend\tests\test_round19_dashboard_chat.py -q` 通过；`npm run build` 通过；`cd backend; python -m pytest -q` 全量通过；Headless Edge 烟测可渲染 AI 助手后端链路状态。

## 剩余需决策项
- 正式 Alembic migration、Celery/Redis 异步队列、真实密钥加密存储仍会改变依赖、运行拓扑或迁移策略，建议单独确认部署方案后再做。

## 第二轮总攻
- 长期 goal 已创建，目标是把需求文档和技术实现方案中的剩余任务按第二轮排期逐项完成、验证、提交并推送。
- 总排期已落地到 `docs/orchestration/SECOND_ROUND_ROADMAP.md`。
- 第二轮工作包从 R20 到 R32，优先完成当前本地仓库可直接交付的 P0/P1 项。
- R20 下一步：Dashboard 剩余关键静态图表接后端事实统计，Topbar LLM 状态接后端配置和运行时状态。

## R20 完成交接
- Dashboard 后端契约已新增 `execution_trend`、`requirement_coverage`、`module_heatmap`，前端已消费这些字段并保留空态。
- Topbar 已从 `/system/llm-status` 读取 LLM 配置与运行时状态，默认真实 LLM 关闭时显示“未启用”，不会再固定显示 `OpenAI GPT-4o`。
- `/system/llm-status` 不调用外部 provider，响应中只包含配置布尔态、脱敏文本和 usage 统计，不返回 `api_key` 或 `api_key_ref`。
- R20 验收证据见 `docs/orchestration/ROUND20_REPORT.md`；定向测试、前端构建、后端全量测试和 Headless Chrome CDP 烟测均通过。

## R21 预备交接
- 只读探索子线程 Nietzsche 已完成 R21 预研：AI 助手已有 `/chat` 后端调用、项目上下文和本地兜底；缺口集中在常用 Prompt 保存、最近操作回溯、整条回复复制、结构化资产入口和后端契约测试。
- 建议 R21 worker 拆分：
  - 后端契约 worker：`backend/aitest_platform/api/router.py`、`backend/tests/test_round21_ai_prompt.py`，负责 Prompt create/delete/favorite、chat context 扩展、recent/operation 回溯契约。
  - AI 助手 worker：`src/components/AiAssistant.jsx`，负责整条回复复制、常用 Prompt 入口、最近操作入口、结构化行动按钮。
  - Prompt 管理 worker：`src/pages/LlmConfig.jsx`，必要时新增 `src/components/PromptTemplatePanel.jsx`，只做配置页 PromptTemplate 管理。
  - QA/文档 worker：`docs/orchestration/ACCEPTANCE.md`、`docs/orchestration/HANDOFF.md`、`docs/orchestration/ROUND21_REPORT.md`，负责验收记录和烟测清单。
- R21 仍不得默认启用真实 LLM，不得保存或输出真实 `.env`、API key、token、cookie、Authorization。

## R21 完成交接
- R21 名称：AI 助手与 Prompt 闭环。
- 后端新增/增强 `POST /api/v2/prompt-templates`、`DELETE /api/v2/prompt-templates/{templateId}`、`POST /api/v2/prompt-templates/{templateId}/test`、`GET /api/v2/assistant/context`、`POST /api/v2/assistant/drafts`。
- `POST /api/v2/prompt-templates/{templateId}/test` 兼容 `variables` 嵌套与 flat payload；`/chat` fallback 会追加 assistant context 摘要；所有响应不调用真实 provider 且做敏感信息脱敏。
- AI 助手已支持复制整条回复、读取/保存常用 Prompt、展示最近操作、把最近操作带入输入框，并生成测试点/澄清问题/缺陷备注草稿。
- LLM 配置页 Prompt 模板管理面板已支持加载、新增、编辑、测试渲染、删除自定义模板；内置模板不可删除。
- QA 修复已落地：前端 `/assistant/drafts` 发送 `message: prompt`；最近操作 normalize 兼容 `recent_activities.list` 与 `operation_logs.list`。
- R21 验收证据见 `docs/orchestration/ROUND21_REPORT.md`；后端定向测试、R19/R20 回归、后端全量测试、前端构建和 Headless Chrome CDP 烟测均通过。
- R21 残余风险：真实 LLM 仍默认关闭；Prompt 模板尚未做收藏排序/团队级模板权限；最近操作/operation logs 是摘要上下文；结构化草稿为 deterministic rules fallback。

## R22 预备交接
- 下一步进入 R22：需求库解析与确认闭环。
- R22 应优先围绕 TXT/Markdown 基础解析增强、需求项编辑/合并/拆分/暂不入库、粒度质检、来源锚点和需求大脑可追溯摘要继续拆分子线程。

## R22 完成交接
- R22 名称：需求库解析与确认闭环。
- 后端实现 TXT/Markdown 多 block 解析，重 parse 会替换旧 blocks；fallback extract 基于 blocks 生成多条可追溯需求项；split/merge/shelve/quality-check/brain analyze/get/traceability refresh 已 DB 化。
- 闭环响应已脱敏，不回显 token、cookie、Authorization、secret。
- Requirements 页面展示解析块和 source anchors；需求项编辑保存、确认、暂不入库、拆分、合并、粒度质检、需求大脑、追溯刷新已接后端，支持多选合并。
- 前端已归一化 brain/source_refs 等返回形状，修复浏览器烟测中 `source_refs.slice is not a function` 崩溃。
- R22 验收证据见 `docs/orchestration/ROUND22_REPORT.md`；定向测试 `backend/tests/test_round22_requirement_closure.py` 覆盖 parse/extract/edit/confirm/shelve/split/merge/quality/brain/traceability/redaction。
- 验证结果：`python -m compileall backend\aitest_platform` 通过；R22 定向测试 7 passed；P0/R4/R14 回归 17 passed；后端全量 pytest 通过；`npm run build` 通过且仅 Vite chunk size warning；Headless Chrome CDP R22 烟测通过，`window.__r22Errors` 为空。
- R22 残余风险：解析仍为规则化 TXT/Markdown，不覆盖 docx/pdf/xlsx 深解析；真实 LLM 默认关闭，需求大脑是 DB deterministic 摘要；split/merge lineage 用状态和响应表达，未新增正式血缘表；浏览器烟测使用本地临时 smoke 数据。
- 下一步进入 R23：用例评审与质量规则。

## R23 完成交接
- R23 名称：用例评审与质量规则。
- 后端实现：新增 deterministic 用例质量规则服务 `backend/aitest_platform/services/test_case_quality.py`；规则覆盖缺步骤、缺预期、预期不可断言/过短、标题过短、缺 source anchors、优先级不一致、重复/相似、不可执行、同需求 happy path 覆盖弱；新增/增强接口 `POST /test-cases/{caseId}/quality-review`、`POST /test-cases/review-batch`、`GET /projects/{projectId}/test-case-quality-summary`、`POST /test-cases/{caseId}/review-opinions`；旧入口 `rule-validate` 和 `ai-review` 复用新规则服务；不调用真实 LLM，响应 provider flags false，并做脱敏。
- 前端实现：TestCases 页面新增项目级质量摘要区；接入单条质量评审、批量评审、评审意见保存；表格增加质量分和单条评审操作；所有评审返回 array/object/string/null 归一化，避免 R22 类似 `.slice` 崩溃。
- R23 验收证据见 `docs/orchestration/ROUND23_REPORT.md`；定向测试 `backend/tests/test_round23_testcase_quality.py` 覆盖完整项目链路、好/坏/重复/优先级不一致用例、质量评审、批量评审、项目摘要、人工意见、旧入口、secret redaction。
- 验证结果：`python -m compileall backend\aitest_platform` 通过；R23 定向测试 5 passed；R14/R22 回归 9 passed；后端全量 pytest 通过；`npm run build` 通过且仅 Vite chunk size warning；Headless Chrome CDP R23 烟测通过，`window.__r23Errors` 为空。
- R23 残余风险：规则评分是 deterministic 启发式，阈值后续可按产品验收口径微调；人工评审意见保存到操作日志/状态字段，没有新增正式 Review 表；浏览器烟测使用本地临时 smoke 数据；真实 LLM 默认关闭。
- 下一步进入 R24：执行与缺陷闭环。

## R24 完成交接
- R24 名称：执行与缺陷闭环。
- 后端新增 deterministic execution defect loop service `backend/aitest_platform/services/execution_defect_loop.py`；新增 `GET /executions/templates`、`POST /executions/{executionId}/defect-suggestion`、`POST /executions/{executionId}/create-defect`、`POST /defects/{defectId}/link-case`、`POST /defects/{defectId}/unlink-case`、`POST /defects/{defectId}/retest-reminder`、`GET /projects/{projectId}/execution-trend`、`GET /projects/{projectId}/defect-loop-summary`。
- 后端增强 batch/statistics/defects patch/copy-text；`defect-suggestion` 返回 top-level `steps_to_reproduce`；`copy-text` 使用中文标签“复现/实际/预期/复测建议”；不接真实 LLM，并注意敏感信息脱敏。
- `src/pages/Execution.jsx` 已接入 templates、trend、defect loop summary、suggestion/create/link/unlink/retest/status/copy；批量摘要显示 `created_defects` / `failed` / `blocked` / `skipped`；历史趋势优先后端数据；返回形状已做 normalization。
- R24 验收证据见 `docs/orchestration/ROUND24_REPORT.md`；定向测试 `backend/tests/test_round24_execution_defect_loop.py` 覆盖项目链路、模板、建议、创建缺陷、关联/解除、复测提醒、趋势、摘要、统计、筛选/patch/copy、批量摘要、脱敏。
- 验证结果：`python -m compileall backend\aitest_platform` 通过；R24 定向测试 8 passed；R15/R23 回归 6 passed；`npm run build` 通过；`python -m pytest -q` 完整后端回归通过，退出码 0。
- API 验收：项目实际前缀为 `/api/v2`；裸 `/executions/templates` 和 `/api/executions/templates` 返回 404 是前缀不匹配，`/api/v2/executions/templates` 返回 200。
- 浏览器轻量验收：`http://127.0.0.1:3000/` 可加载，页面入口包含 `用例执行`；QA 收集到 `console.error` / `pageerror` 无明显 JS runtime error。
- R24 残余风险：扩展缺陷字段通过 `Defect.remark` 的 R24 JSON prefix 存储，避免 schema 迁移；建议和复测为 deterministic 规则，非真实 LLM；冒烟使用临时数据；趋势聚合基于本地 SQLite。
- 下一步进入 R25：接口测试增强。

## R25 完成交接
- R25 名称：接口测试增强。
- 后端完成 OpenAPI YAML 轻量解析（不新增 PyYAML 依赖）、HAR 基础解析、debug `save_as_case` 保存为 `ApiTestCase`、API runtime context 统一变量/header 优先级、scenario `data_mappings.extract` 增强、Mock 服务基础能力、受控 pre/post script allowlist DSL。
- 新增服务：`backend/aitest_platform/services/api_runtime_context.py`、`backend/aitest_platform/services/api_mock_service.py`、`backend/aitest_platform/services/api_script_runner.py`。
- 增强文件：`backend/aitest_platform/services/api_importer.py`、`backend/aitest_platform/services/api_runner.py`、`backend/aitest_platform/services/api_scenario_runner.py`、`backend/aitest_platform/api/router.py`。
- `src/pages/ApiTesting.jsx` 已新增 JSON/YAML/HAR 导入面板、真实 debug 表单、保存为接口用例、环境变量/运行覆盖、场景变量映射、Mock 服务 UI、pre/post script UI。
- R25 验收证据见 `docs/orchestration/ROUND25_REPORT.md`；定向测试 `backend/tests/test_round25_api_testing_enhancement.py` 覆盖 YAML/HAR、debug save、变量优先级、scenario mapping、mock、allowlist/danger script。
- 验证结果：`cd backend; python -m compileall aitest_platform` passed，exit code 0；R5/R6/R7/R25 定向回归 passed，exit code 0，仅 FastAPI `HTTP_422_UNPROCESSABLE_ENTITY` deprecation warning；`cd backend; python -m pytest -q` 完整后端回归 passed，exit code 0，仅 FastAPI deprecation warning；根目录 `npm run build` passed，exit code 0，仅 Vite chunk > 500 kB warning。
- QA 冒烟：临时 SQLite 已删除；OpenAPI YAML import imported=1 path `/r25/smoke/users` expected status 206；HAR import imported=1 path `/r25/smoke/orders` expected status 202；Mock create/list/dispatch matched=true status 207；debug save_as_case status 200 saved_case_id=3。浏览器进入 `http://127.0.0.1:3000/` 的 ApiTesting/workbench，OpenAPI YAML、HAR、环境变量、本次运行覆盖、Mock 服务 5 个关键词可见，console.error=0，pageerror=0；进程和临时 DB 已清理，8000/3000 无监听。
- R25 残余风险：YAML 为轻量解析非完整 YAML 规范；脚本为 allowlist DSL 非任意代码；Mock 服务为本地平台基础 mock 非完整代理网关；Vite 仍有 chunk > 500 kB warning；浏览器只做轻量加载/可见性/console smoke，深层 UI 写操作主要由 API 冒烟覆盖。
- 下一步进入 R26：自动化中心增强。

## R26 预备交接
- R26 名称：自动化中心增强。
- 建议优先围绕候选筛选、在线文件编辑、代码保存、Playwright 模板增强、执行日志/截图/trace 展示、Artifacts 预览继续拆分 worker。
- 继续保持本地优先、结构化失败、敏感信息脱敏和不静默新增生产依赖的约束。

## R26 完成交接
- R26 名称：自动化中心增强。
- 后端完成候选筛选/选择、文件 CRUD、执行详情、artifact 列表与预览路由；`generate-cases` 支持候选选择；Playwright 模板增强；新增 `backend/aitest_platform/services/auto_center.py`；`backend/aitest_platform/services/exporting.py` 对文本类 artifact ZIP 内容脱敏。
- 前端 `src/pages/Automation.jsx` 已新增候选筛选、case file 在线编辑/dirty/save/reset、Playwright 模板配置、按 `case_file_ids` 执行、执行详情日志/evidence、artifact preview。
- R26 验收证据见 `docs/orchestration/ROUND26_REPORT.md`；定向测试 `backend/tests/test_round26_automation_center.py` 覆盖候选筛选/过滤、候选选择影响生成、Playwright 模板增强、在线文件查看/保存/非法路径、按文件执行与详情、artifact 列表/预览、artifact ZIP 回归安全。
- 最终 QA 回填：`cd backend; python -m compileall aitest_platform` passed，exit code 0；R26 组合回归 `python -m pytest tests/test_round6_execution_runners.py tests/test_round8_artifacts.py tests/test_round11_exports.py tests/test_round13_frontend_integration.py tests/test_round25_api_testing_enhancement.py tests/test_round26_automation_center.py -q` passed，40 passed，仅 FastAPI deprecation warning；full backend `python -m pytest -q` passed，exit code 0，仅 FastAPI deprecation warning；`npm run build` passed，仅 Vite chunk >500k warning。
- API smoke passed：候选筛选/过滤、文件保存、artifact preview 均返回合理结果。
- 浏览器最终复验 passed：Automation 页面打开；console.error=0；pageerror=0；`/case-files` 请求数 0；`/case-files` 404 为 0；`/auto-projects/693/files?page=1&pageSize=200` 返回 200；R26 DOM 可见关键词 8/8：候选筛选、在线文件、保存、Playwright、trace、Artifacts、预览、执行日志。
- 进程清理：8000/3000 已停止并复查无监听。
- R26 残余风险：Vite chunk warning；Playwright 真实执行依赖本机环境；trace/zip 预览不展开执行；浏览器深层写操作主要由 API smoke 和后端契约测试覆盖。

## R27 完成交接
- R27 名称：性能测试增强。
- 后端已完成性能停止/中止接口、阈值判定、历史对比、项目 `performance-trend` 聚合；JMeter 参数编辑会体现在生成/下载脚本中；`generate-report` 已增加风险建议并递归脱敏。
- 新增服务：`backend/aitest_platform/services/perf_analysis.py`。
- 增强文件：`backend/aitest_platform/api/router.py`、`backend/aitest_platform/services/perf_runner.py`、`backend/aitest_platform/services/reporting.py`、`backend/aitest_platform/services/exporting.py`。
- 前端 `src/pages/Performance.jsx` 已接完整 results、阈值判定、历史比对、7 日趋势、JMeter 参数表单、停止执行、报告风险/建议展示，并去掉关键静态假数据。
- R27 验收证据见 `docs/orchestration/ROUND27_REPORT.md`；定向测试 `backend/tests/test_round27_performance_enhancement.py` 为 10 passed。
- 验证结果：`python -m compileall backend/aitest_platform` passed；合同组合回归 passed；后端全量 `pytest -q` passed；`npm run build` passed；真实 Chrome Playwright 烟测 passed，`console.error=0`，`pageerror=0`。
- 浏览器关键词命中：阈值判定、性能历史比对、7日趋势 P95、JMeter 参数/模板参数、停止执行、报告建议/风险建议。
- R27 残余风险：真实 JMeter 执行依赖本机工具和目标环境；阈值/风险建议为当前规则口径，后续可按项目 SLA 调整；趋势依赖已落库样本。

## R28 完成交接
- R28 名称：报告中心增强。
- 后端已完成 report-templates CRUD 校验与默认唯一；综合报告按 `template_id`/`scope` 生成并冻结模板、章节、scope；报告列表过滤排序；report drilldown；report risks；风险转待办与 todo 列表/状态；Markdown/HTML 强化与 HTML escape/递归脱敏；PDF/Word/docx unsupported 结构化返回；轻量结论支持 `daily_report`、`test_submission_feedback`、`release_advice`、`risk_list`。
- 前端 Reports 页已移除 fallback/static AI 意见、固定默认报告和假分享；已接真实报告列表、模板管理、筛选排序、下钻、风险转待办、下载和轻量结论类型。
- R28 验收证据见 `docs/orchestration/ROUND28_REPORT.md`；定向测试 `backend/tests/test_round28_report_center_enhancement.py` 为 13 passed。
- 验证结果：`python -m compileall backend/aitest_platform` passed；合同组合回归 passed；后端全量 `pytest -q` passed；`npm run build` passed；真实 Chrome Playwright 报告中心烟测 passed，`console.error=0`，`pageerror=0`。
- 浏览器入口命中：风险转待办、Markdown、HTML、日报、提测反馈、上线建议、风险清单、管理报告模板/新建模板、查看下钻/下钻明细。
- 端口已清理。
- R28 残余风险：PDF/Word/docx 仍为 unsupported 结构化返回，未引入新导出依赖；轻量结论仍按当前报告聚合口径输出。

## R29 预备交接
- 下一步进入 R29：数据工厂与数据管理。
- 建议优先围绕接口参数测试数据生成、执行测试数据建议、自动备份提醒、存储空间统计和按模块清理安全门继续拆分 worker。
- R29-R32 仍为未完成排期；不得把 R30 文件格式增强、R31 生产基础设施或 R32 总验收写成已完成。

## R29 完成交接
- R29 名称：数据工厂与数据管理。
- 后端已完成 `POST /data-factory/api-parameters/generate`、`GET /test-cases/{caseId}/test-data-suggestions`、`GET /system/backup-status`、`GET /system/storage-summary`、`POST /system/cleanup`。
- 清理能力已具备 dry-run、安全确认文本 `CLEANUP`、模块白名单、路径根目录限制和响应脱敏。
- 前端 Settings 已接入存储统计、备份提醒、清理 dry-run 与确认执行；ApiTesting 已增加生成测试数据入口；Execution 已增加准备测试数据入口和空态。
- R29 验收证据见 `docs/orchestration/ROUND29_REPORT.md`；定向测试 `backend/tests/test_round29_data_factory_management.py` 当前复验为 5 passed，后端实现阶段曾记录 8 passed，当前以文件实际测试为准。
- 验证结果：R29 定向测试 passed；合同回归组合 passed；后端全量 passed；`npm run build` passed；浏览器复验 passed，Settings cleanup dry-run 返回 200，payload 包含 `execution_history`、`api_execution_history`、`artifacts`，`console.error=0`，`pageerror=0`。
- 真实清理未执行：dry-run 显示会影响 849 个 artifact 文件，出于安全边界仅验证 dry-run 和确认门能力。
- 端口说明：本机 8000 被既有 `python -m http.server 8000` PID 4588 占用，验收使用 8001，未触碰非本次启动进程。
- R29 残余风险：数据生成与建议按当前本地规则和现有数据口径输出；存储统计和备份提醒基于当前本地 SQLite/artifacts 文件布局。

## R30 预备交接
- R30 已完成并验收，预备交接关闭。

## R30 完成交接
- R30 名称：文件与导出格式增强。
- 后端已完成统一 unsupported contract、无依赖 XLSX 导出 test-cases/defects、公式注入中和、二进制 docx/pdf/xlsx/xmind 导入硬边界。
- 后端已完成自动化/性能 artifact ZIP canonical path 校验；越界文件不进入 ZIP，记录为 skipped metadata；文本类 artifact 内容继续脱敏。
- 前端已移除假下载/假成功；TestCases 支持 CSV、Markdown、JSON、XLSX 四种真实下载；PDF、Word、XMind 未开放真实服务端生成并提示未开放；Reports/Performance 使用 HTML/Markdown 替代；统一下载 helper 处理 unsupported、空内容和真实文件下载。
- R30 验收证据见 `docs/orchestration/ROUND30_REPORT.md`；定向测试 `backend/tests/test_round30_file_export_formats.py` 为 36 passed。
- 验证结果：`python -m compileall backend\aitest_platform` 通过；R30 定向 36 passed；合同回归组合 64 passed；后端全量通过；`npm run build` 通过；真实 Chrome 烟测通过，TestCases 四种真实下载、XLSX 真实 ZIP workbook、unsupported 不返回假文件字段、artifact 越界 skipped，`console.error=0`，`pageerror=0`。
- 端口说明：本机 8000 被既有 PID 4588 占用，验收使用 8001，未触碰外部进程。
- R30 残余风险：PDF/Word/XMind 未做真实服务端生成；本轮未新增生产依赖；docx/pdf/xlsx/xmind 导入只建立硬边界，不做深度解析。

## R31 预备交接
- 下一步进入 R31：生产基础设施决策。
- R31 应只做 Alembic、PostgreSQL/pgvector、Celery/Redis、MinIO/S3、真实密钥加密存储等生产基础设施的决策与取舍记录；不得静默引入新依赖或把决策项写成已实施。
- R31-R32 仍为未完成排期；不得把第二轮总验收写成已完成。
