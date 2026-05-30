# 第二轮总攻排期

## 目标

从 2026-05-29 开始，第二轮不再按零散补丁推进，而是按需求文档和技术实现方案中未完成的能力分阶段收口。

目标口径：
- 优先完成能在当前本地仓库直接实现、验证、提交和推送的任务。
- 生产基础设施项按默认本地优先方案推进；如果会引入 Redis、PostgreSQL、MinIO/S3 或真实密钥加密依赖，必须作为决策门单独记录。
- 每个工作包必须有测试、构建或浏览器烟测证据。
- 每个工作包完成后更新 `STATUS.md`、`HANDOFF.md`、`ACCEPTANCE.md` 或新增对应报告。

日期口径：
- 当前真实日期为 2026-05-30；R20-R29 实际完成节奏早于原排期窗口。
- 旧路线图日期如与实际完成时间冲突，以对应 Round 报告、验收记录和提交/测试证据为准。

## 默认策略

- 默认运行模式：继续保持本地优先，SQLite + 本地 artifacts。
- 默认后端契约：继续使用 `/api/v2`。
- 默认安全策略：不保存真实明文 API key、token、cookie、Git 凭证。
- 默认交付方式：小步提交，每个工作包一个或多个可验证 commit，推送到 `origin/new-ui-frontend`。
- 默认验收命令：
  - `python -m compileall backend\aitest_platform`
  - `python -m pytest -q` 或相关定向测试
  - `npm run build`
  - 必要时执行本地浏览器烟测

## 工作包排期

| 阶段 | 时间窗口 | 优先级 | 工作包 | 验收标准 |
|---|---:|---:|---|---|
| R20 | 2026-05-29 ~ 2026-05-30 | P0 | 消灭关键静态数据 | Dashboard 趋势、覆盖率、热力图、最近活动优先接后端统计；Topbar LLM 状态接后端配置与用量状态；新增测试覆盖前端所需契约。 |
| R21 | 2026-05-30 ~ 2026-05-31 | P0 | AI 助手与 Prompt 闭环 | 支持复制回复、保存常用 Prompt、最近操作回溯；AI 助手能基于当前页面/项目生成测试点、澄清问题、缺陷备注草稿。 |
| R22 | 2026-05-31 ~ 2026-06-03 | P0 | 需求库解析与确认闭环 | 支持 TXT/Markdown 基础解析增强，补需求项编辑、合并、拆分、暂不入库、粒度质检、来源锚点；需求大脑输出可追溯摘要和风险。 |
| R23 | 2026-06-03 ~ 2026-06-05 | P0 | 用例评审与质量规则 | 补 AI/规则评审、查漏、查重、不可执行检查、优先级检查、预期结果检查、质量评分、评审意见保存。 |
| R24 | 2026-06-05 ~ 2026-06-07 | P0 | 执行与缺陷闭环 | 补失败/阻塞模板、缺陷标题/复现步骤/严重级别建议、关联/解除用例、复测提醒、失败/阻塞筛选、真实趋势统计。 |
| R25 | 2026-06-07 ~ 2026-06-10 | P0 | 接口测试增强 | 支持 OpenAPI YAML/HAR 基础解析，补保存调试为用例、环境变量优先级、场景变量映射增强、Mock 服务基础能力、前后置脚本受控执行。 |
| R26 | 2026-06-10 ~ 2026-06-12 | P0 | 自动化中心增强 | 补候选筛选、在线文件编辑、代码保存、Playwright 模板增强、执行日志/截图/trace 展示、Artifacts 预览。 |
| R27 | 2026-05-30 已验收；原窗口 2026-06-12 ~ 2026-06-14 | P0 | 性能测试增强 | 已完成：中止/停止执行接口、阈值判定、历史对比、JMeter 模板参数编辑、性能趋势聚合、报告风险建议。验收证据见 `ROUND27_REPORT.md`。 |
| R28 | 2026-05-30 已验收 | P0 | 报告中心增强 | 已完成：report-templates CRUD 校验与默认唯一、综合报告模板/scope 冻结、报告列表过滤排序、下钻、风险转待办、Markdown/HTML 强化、unsupported PDF/Word/docx 结构化返回、轻量结论类型。验收证据见 `ROUND28_REPORT.md`。 |
| R29 | 2026-05-30 已验收 | P1 | 数据工厂与数据管理 | 已完成：接口参数测试数据生成、执行测试数据建议、备份状态提醒、存储空间统计、清理 dry-run/确认门、模块白名单、路径根目录限制和响应脱敏。验收证据见 `ROUND29_REPORT.md`。 |
| R30 | 2026-05-30 已验收 | P1 | 文件与导出格式增强 | 已完成：统一 unsupported contract；无依赖 XLSX 导出 test-cases/defects；公式注入中和；二进制 docx/pdf/xlsx/xmind 导入硬边界；自动化/性能 artifact ZIP canonical path 校验、越界 skipped metadata 和文本脱敏；前端移除假下载并支持 TestCases CSV/Markdown/JSON/XLSX。PDF/Word/XMind 未做真实服务端生成。验收证据见 `ROUND30_REPORT.md`。 |
| R31 | 2026-05-30 已完成 | 决策门 | 生产基础设施决策 | 已完成：明确 SQLite 本地优先为 R32 支持目标；PostgreSQL/pgvector、Celery/Redis、MinIO/S3、真实密钥加密存储、Alembic 均 deferred / unsupported unless explicitly approved。未新增生产依赖。验收证据见 `ROUND31_REPORT.md`。 |
| R32 | 2026-05-30 已验收 | P0 | 第二轮总验收 | 已完成：后端编译、后端全量 pytest、R27-R31 重点合同回归、前端构建、核心浏览器导航、接口状态自检、unsupported 导出边界、R31 文档事实修正与最终交付报告。验收证据见 `ROUND32_REPORT.md`。 |
| R33 | 2026-05-31 已验收 | P1 | 二进制文档导入与正式导出 | 已完成：`PDF / DOCX / XMind` 真实服务端导出；`docx / pdf / xlsx / xmind` 深度导入解析；前端相关入口接入真实链路。验收证据见 `ROUND33_REPORT.md`。 |

## 必须完成清单

### P0：第二轮必须收口
- Dashboard 关键图表和风险/待办全部由后端事实驱动。
- Topbar LLM 状态由后端配置和运行时状态驱动。
- AI 助手具备项目上下文、Prompt 保存、最近操作、结果转测试资产能力。
- 需求项编辑、合并、拆分、暂不入库、粒度质检闭环。
- 用例评审、质量评分、查漏查重、不可执行检查闭环。
- 执行失败、阻塞、缺陷、复测、趋势闭环。
- 接口测试保存调试为用例、环境变量、场景链路、Mock 基础能力。
- 自动化文件在线编辑和执行 artifacts 预览。
- 性能阈值判定、历史对比、中止执行和趋势。
- 报告下钻、风险项转待办、模板闭环。

### P1：第二轮尽量完成
- 测试数据工厂。
- 自动备份提醒、存储空间统计、按模块清理。
- Excel/PDF/Word/XMind 导出。
- OpenAPI YAML、HAR、Markdown/TXT 解析增强。

### 决策门：不静默硬上
- Alembic 正式迁移。
- PostgreSQL + pgvector。
- Celery/Redis。
- MinIO/S3。
- 真实密钥加密存储。
- Midscene 或其他视觉执行增强依赖。

## 每个阶段完成定义

每个阶段必须满足：
- 后端新增或调整能力有定向测试。
- 前端核心路径至少通过 `npm run build`。
- 涉及页面主流程时执行浏览器烟测。
- 不提交真实 secrets。
- 文档记录本阶段完成内容、验证命令、残余风险。
- 提交并推送到 GitHub 远程 `new-ui-frontend`。

## 当前下一步

立即进入 R32：第二轮总验收。
- R31 生产基础设施决策门已完成；本轮未新增生产依赖，未实施 PostgreSQL/Redis/MinIO/Alembic 或真实密钥加密存储。
- R32 仍未开始，等待全量验收、前端构建、核心浏览器流程、导出下载、secrets 检查和最终交付报告。
- 继续保持脱敏、本地优先和结构化失败约束。

## 当前进展

- R20 已完成并验收：Dashboard 执行趋势、需求覆盖率、模块热力图已改为后端事实驱动，Topbar LLM 状态已接 `/system/llm-status`。
- R20 验收证据：`docs/orchestration/ROUND20_REPORT.md`。
- R21 已完成并验收：AI 助手与 Prompt 闭环已落地，后端补齐 Prompt 模板 CRUD/测试渲染、assistant context、assistant drafts 和 `/chat` fallback context 摘要；前端补齐常用 Prompt、最近操作、复制回复、三类草稿按钮和 LLM 配置页 Prompt 模板管理面板。
- R21 验收证据：`docs/orchestration/ROUND21_REPORT.md`。
- 下一步进入 R22：需求库解析与确认闭环。

## 当前进展补充
- R22 已完成并验收：需求库解析与确认闭环已落地。
- 后端完成 TXT/Markdown 多 block 解析、重 parse 替换旧 blocks、基于 blocks 的 fallback extract 多需求项生成、DB 化 split/merge/shelve/quality-check/brain analyze/get/traceability refresh，并确保闭环响应脱敏，不回显 token/cookie/Authorization/secret。
- 前端 Requirements 页面已展示解析块/source anchors，需求项编辑保存、确认、暂不入库、拆分、合并、多选合并、粒度质检、需求大脑、追溯刷新已接后端；brain/source_refs 返回形状已归一化，修复 `source_refs.slice is not a function` 崩溃。
- R22 验收证据见 `docs/orchestration/ROUND22_REPORT.md`：R22 定向测试 7 passed，P0/R4/R14 回归 17 passed，后端全量 pytest 通过，`npm run build` 通过且仅 Vite chunk size warning，Headless Chrome CDP 烟测通过且 `window.__r22Errors` 为空。
- R22 残余风险：规则化 TXT/Markdown 解析未覆盖 docx/pdf/xlsx 深解析；真实 LLM 默认关闭，需求大脑是 DB deterministic 摘要；split/merge lineage 未新增正式血缘表；浏览器烟测使用本地临时 smoke 数据。
- 下一步进入 R23：用例评审与质量规则。

## 当前进展补充：R23
- R23 已完成并验收：用例评审与质量规则已落地。
- 后端新增 deterministic 用例质量规则服务 `backend/aitest_platform/services/test_case_quality.py`；规则覆盖缺步骤、缺预期、预期不可断言/过短、标题过短、缺 source anchors、优先级不一致、重复/相似、不可执行、同需求 happy path 覆盖弱；新增/增强 `POST /test-cases/{caseId}/quality-review`、`POST /test-cases/review-batch`、`GET /projects/{projectId}/test-case-quality-summary`、`POST /test-cases/{caseId}/review-opinions`；旧入口 `rule-validate` 和 `ai-review` 复用新规则服务；不调用真实 LLM，响应 provider flags false，并做脱敏。
- 前端 TestCases 页面新增项目级质量摘要区；接入单条质量评审、批量评审、评审意见保存；表格增加质量分和单条评审操作；所有评审返回 array/object/string/null 归一化，避免 R22 类似 `.slice` 崩溃。
- R23 验收证据见 `docs/orchestration/ROUND23_REPORT.md`：R23 定向测试 5 passed，R14/R22 回归 9 passed，后端全量 pytest 通过，`npm run build` 通过且仅 Vite chunk size warning，Headless Chrome CDP 烟测通过且 `window.__r23Errors` 为空。
- R23 残余风险：规则评分是 deterministic 启发式，阈值后续可按产品验收口径微调；人工评审意见保存到操作日志/状态字段，没有新增正式 Review 表；浏览器烟测使用本地临时 smoke 数据；真实 LLM 默认关闭。
- 下一步进入 R24：执行与缺陷闭环。

## 当前进展补充：R24
- R24 已完成文档收口：执行与缺陷闭环已落地。
- 后端新增 deterministic execution defect loop service `backend/aitest_platform/services/execution_defect_loop.py`；新增 `GET /executions/templates`、`POST /executions/{executionId}/defect-suggestion`、`POST /executions/{executionId}/create-defect`、`POST /defects/{defectId}/link-case`、`POST /defects/{defectId}/unlink-case`、`POST /defects/{defectId}/retest-reminder`、`GET /projects/{projectId}/execution-trend`、`GET /projects/{projectId}/defect-loop-summary`；增强 batch/statistics/defects patch/copy-text；`defect-suggestion` 返回 top-level `steps_to_reproduce`；`copy-text` 使用中文标签“复现/实际/预期/复测建议”；不接真实 LLM，并注意敏感信息脱敏。
- 前端 `src/pages/Execution.jsx` 已接入 templates、trend、defect loop summary、suggestion/create/link/unlink/retest/status/copy；批量摘要显示 `created_defects` / `failed` / `blocked` / `skipped`；历史趋势优先后端数据；做了 shape normalization。
- R24 回归修复：脱敏从整段替换改为片段级脱敏，修复 `Round 11 defect ... sk-*` 普通标题被误伤；Round9 restore merge 测试改为分页查找以适配脏库。
- R24 验收证据见 `docs/orchestration/ROUND24_REPORT.md`：`python -m compileall backend\aitest_platform` 通过；R24 定向测试先前通过，补充脱敏不误伤测试后为 9 passed；R15/R23 回归 6 passed；`npm run build` 通过；`python -m pytest tests/test_round9_restore_schema.py::test_restore_merge_restores_project_api_assets_and_lists_can_read_them -q` 1 passed；`python -m pytest tests/test_round11_exports.py tests/test_round24_execution_defect_loop.py -q` 17 passed；`python -m pytest -q` 完整后端回归通过，退出码 0。
- R24 API 与浏览器验收：项目实际前缀为 `/api/v2`，裸 `/executions/templates` 和 `/api/executions/templates` 返回 404 是前缀不匹配，`/api/v2/executions/templates` 返回 200；`http://127.0.0.1:3000/` 可加载，页面入口包含 `用例执行`，QA 收集到 `console.error` / `pageerror` 无明显 JS runtime error；深层交互曾受脚本中文编码/Playwright 卡顿影响，未作为完整交互验收证据。
- R24 残余风险：深层浏览器交互仅轻量验证；扩展缺陷字段仍通过 `Defect.remark` 的 R24 JSON prefix 存储；建议/复测为 deterministic 规则，非真实 LLM；本地服务仍为原有 8000/3000 dev 进程。
- 下一步进入 R25：接口测试增强。

## 当前进展补充：R25
- R25 已完成文档收口：接口测试增强已落地。
- 后端完成 OpenAPI YAML 轻量解析（不新增 PyYAML 依赖）、HAR 基础解析、debug `save_as_case` 保存为 `ApiTestCase`、API runtime context 统一变量/header 优先级、scenario `data_mappings.extract` 增强、Mock 服务基础能力、受控 pre/post script allowlist DSL。
- 新增服务 `backend/aitest_platform/services/api_runtime_context.py`、`backend/aitest_platform/services/api_mock_service.py`、`backend/aitest_platform/services/api_script_runner.py`；增强 `backend/aitest_platform/services/api_importer.py`、`backend/aitest_platform/services/api_runner.py`、`backend/aitest_platform/services/api_scenario_runner.py`、`backend/aitest_platform/api/router.py`。
- 前端 `src/pages/ApiTesting.jsx` 已新增 JSON/YAML/HAR 导入面板、真实 debug 表单、保存为接口用例、环境变量/运行覆盖、场景变量映射、Mock 服务 UI、pre/post script UI。
- R25 验收证据见 `docs/orchestration/ROUND25_REPORT.md`：`cd backend; python -m compileall aitest_platform` passed，exit code 0；R5/R6/R7/R25 定向回归 passed，exit code 0，仅 FastAPI `HTTP_422_UNPROCESSABLE_ENTITY` deprecation warning；`cd backend; python -m pytest -q` 完整后端回归 passed，exit code 0，仅 FastAPI deprecation warning；根目录 `npm run build` passed，exit code 0，仅 Vite chunk > 500 kB warning。
- R25 冒烟事实：临时 SQLite 已删除；OpenAPI YAML import imported=1 path `/r25/smoke/users` expected status 206；HAR import imported=1 path `/r25/smoke/orders` expected status 202；Mock create/list/dispatch matched=true status 207；debug save_as_case status 200 saved_case_id=3；浏览器进入 `http://127.0.0.1:3000/` 的 ApiTesting/workbench，OpenAPI YAML、HAR、环境变量、本次运行覆盖、Mock 服务 5 个关键词可见，console.error=0，pageerror=0；进程和临时 DB 已清理，8000/3000 无监听。
- R25 残余风险：YAML 为轻量解析非完整 YAML 规范；脚本为 allowlist DSL 非任意代码；Mock 服务为本地平台基础 mock 非完整代理网关；Vite 仍有 chunk > 500 kB warning；浏览器只做轻量加载/可见性/console smoke，深层 UI 写操作主要由 API 冒烟覆盖。
- 下一步进入 R26：自动化中心增强。

## 当前进展补充：R26
- R26 已完成文档收口：自动化中心增强已落地。
- 后端完成候选筛选/选择、文件 CRUD、执行详情、artifact 列表与预览路由；`generate-cases` 支持候选选择；Playwright 模板增强；新增 `backend/aitest_platform/services/auto_center.py`；`backend/aitest_platform/services/exporting.py` 对文本类 artifact ZIP 内容脱敏。
- 前端 `src/pages/Automation.jsx` 已新增候选筛选、case file 在线编辑/dirty/save/reset、Playwright 模板配置、按 `case_file_ids` 执行、执行详情日志/evidence、artifact preview。
- R26 验收证据见 `docs/orchestration/ROUND26_REPORT.md`：`cd backend; python -m compileall aitest_platform` passed，exit code 0；R26 组合回归 40 passed，仅 FastAPI deprecation warning；full backend `python -m pytest -q` passed，exit code 0，仅 FastAPI deprecation warning；`npm run build` passed，仅 Vite chunk >500k warning。
- R26 冒烟事实：API smoke passed，候选筛选/过滤、文件保存、artifact preview 均返回合理结果；浏览器最终复验 Automation 页面打开，console.error=0，pageerror=0，`/case-files` 请求数 0，`/case-files` 404 为 0，`/auto-projects/693/files?page=1&pageSize=200` 返回 200，R26 DOM 可见关键词 8/8：候选筛选、在线文件、保存、Playwright、trace、Artifacts、预览、执行日志；8000/3000 已停止并复查无监听。
- R26 残余风险：Vite chunk warning；Playwright 真实执行依赖本机环境；trace/zip 预览不展开执行；浏览器深层写操作主要由 API smoke 和后端契约测试覆盖。
- 下一步已进入并完成 R27：性能测试增强。

## 当前进展补充：R27
- R27 已完成文档收口：性能测试增强已落地并验收。
- 后端完成性能停止/中止接口、阈值判定、历史对比、项目 `performance-trend` 聚合；JMeter 参数编辑会体现在生成/下载脚本中；`generate-report` 已增加风险建议并递归脱敏。
- 新增 `backend/aitest_platform/services/perf_analysis.py`；增强 `backend/aitest_platform/api/router.py`、`backend/aitest_platform/services/perf_runner.py`、`backend/aitest_platform/services/reporting.py`、`backend/aitest_platform/services/exporting.py`。
- 前端 `src/pages/Performance.jsx` 已接完整 results、阈值判定、历史比对、7 日趋势、JMeter 参数表单、停止执行、报告风险/建议展示，并去掉关键静态假数据。
- R27 验收证据见 `docs/orchestration/ROUND27_REPORT.md`：`python -m compileall backend/aitest_platform` passed；R27 定向 10 passed；合同组合回归 passed；后端全量 `pytest -q` passed；`npm run build` passed；真实 Chrome Playwright 烟测 passed，`console.error=0`，`pageerror=0`。
- R27 浏览器关键词命中：阈值判定、性能历史比对、7日趋势 P95、JMeter 参数/模板参数、停止执行、报告建议/风险建议。
- R27 残余风险：真实 JMeter 执行依赖本机工具和目标环境；阈值/风险建议为当前规则口径，后续可按项目 SLA 调整；趋势依赖已落库样本。
- 下一步已进入并完成 R28：报告中心增强。

## 当前进展补充：R28
- R28 已完成文档收口：报告中心增强已落地并验收。
- 后端完成 report-templates CRUD 校验与默认唯一；综合报告按 `template_id`/`scope` 生成并冻结模板、章节、scope；报告列表过滤排序；report drilldown；report risks；风险转待办与 todo 列表/状态；Markdown/HTML 强化与 HTML escape/递归脱敏；PDF/Word/docx unsupported 结构化返回；轻量结论支持 `daily_report`、`test_submission_feedback`、`release_advice`、`risk_list`。
- 前端 Reports 页已移除 fallback/static AI 意见、固定默认报告和假分享；已接真实报告列表、模板管理、筛选排序、下钻、风险转待办、下载和轻量结论类型。
- R28 验收证据见 `docs/orchestration/ROUND28_REPORT.md`：`python -m compileall backend/aitest_platform` passed；R28 定向 13 passed；合同组合回归 passed；后端全量 `pytest -q` passed；`npm run build` passed；真实 Chrome Playwright 报告中心烟测 passed，`console.error=0`，`pageerror=0`。
- R28 浏览器入口命中：风险转待办、Markdown、HTML、日报、提测反馈、上线建议、风险清单、管理报告模板/新建模板、查看下钻/下钻明细。
- R28 残余风险：PDF/Word/docx 仍为 unsupported 结构化返回，未引入新导出依赖；轻量结论仍按当前报告聚合口径输出。
- 下一步已进入并完成 R29：数据工厂与数据管理。

## 当前进展补充：R29
- R29 已完成文档收口：数据工厂与数据管理已落地并验收。
- 后端完成 `POST /data-factory/api-parameters/generate`、`GET /test-cases/{caseId}/test-data-suggestions`、`GET /system/backup-status`、`GET /system/storage-summary`、`POST /system/cleanup`；清理接口支持 dry-run、安全确认文本 `CLEANUP`、模块白名单、路径根目录限制和响应脱敏。
- 前端 Settings 已接存储统计、备份提醒、清理 dry-run 与确认执行；ApiTesting 已有生成测试数据入口；Execution 已有准备测试数据入口和空态。
- R29 验收证据见 `docs/orchestration/ROUND29_REPORT.md`：R29 定向测试复验 5 passed，合同回归组合 passed，后端全量 passed，`npm run build` passed，浏览器复验 passed，Settings cleanup dry-run 200，`console.error=0`，`pageerror=0`。
- 真实清理未执行：dry-run 显示会影响 849 个 artifact 文件，出于安全边界仅验证 dry-run 和确认门能力。
- 端口说明：本机 8000 被既有 `python -m http.server 8000` PID 4588 占用，验收使用 8001，未触碰非本次启动进程。
- 下一步已进入并完成 R30：文件与导出格式增强。

## 当前进展补充：R30
- R30 已完成文档收口：文件与导出格式增强已落地并验收。
- 后端完成统一 unsupported contract、无依赖 XLSX 导出 test-cases/defects、公式注入中和、二进制 docx/pdf/xlsx/xmind 导入硬边界、自动化/性能 artifact ZIP canonical path 校验、越界 skipped metadata 和文本脱敏。
- 前端移除假下载/假成功；TestCases 支持 CSV、Markdown、JSON、XLSX 四种真实下载；PDF、Word、XMind 未开放真实服务端生成并提示未开放；Reports/Performance 使用 HTML/Markdown 替代；统一下载 helper 处理 unsupported、空内容和真实下载。
- R30 验收证据见 `docs/orchestration/ROUND30_REPORT.md`：`python -m compileall backend\aitest_platform` 通过；R30 定向 36 passed；合同回归组合 64 passed；后端全量通过；`npm run build` 通过；真实 Chrome 烟测通过，`console.error=0`，`pageerror=0`。
- R30 冒烟事实：TestCases 四种真实下载均可用；XLSX 为真实 ZIP workbook；unsupported 不返回假文件字段；artifact 越界条目进入 skipped metadata。
- R30 残余风险：PDF/Word/XMind 未做真实服务端生成；本轮未新增生产依赖；docx/pdf/xlsx/xmind 导入只建立硬边界，不做深度解析。
- R31 生产基础设施决策门已完成；下一步进入 R32：第二轮总验收。R32 保持未完成排期。

## 当前进展补充：R31
- R31 已完成文档收口：生产基础设施决策门已落地到 `DECISIONS.md` 和 `ROUND31_REPORT.md`。
- 本轮未新增生产依赖、未实施生产基础设施；新增了只读 `infra-status` 接口和 R31 契约测试，用于固定当前 supported/deferred/unsupported 边界。
- R32 支持目标继续是 SQLite 本地优先；PostgreSQL/pgvector、Celery/Redis、MinIO/S3、真实密钥加密存储、Alembic 均保持 deferred / unsupported unless explicitly approved。
- R32 已完成第二轮总验收；后续若继续推进，只剩 deferred / unsupported 边界对应的独立实施项。
