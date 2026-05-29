# 第二轮总攻排期

## 目标

从 2026-05-29 开始，第二轮不再按零散补丁推进，而是按需求文档和技术实现方案中未完成的能力分阶段收口。

目标口径：
- 优先完成能在当前本地仓库直接实现、验证、提交和推送的任务。
- 生产基础设施项按默认本地优先方案推进；如果会引入 Redis、PostgreSQL、MinIO/S3 或真实密钥加密依赖，必须作为决策门单独记录。
- 每个工作包必须有测试、构建或浏览器烟测证据。
- 每个工作包完成后更新 `STATUS.md`、`HANDOFF.md`、`ACCEPTANCE.md` 或新增对应报告。

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
| R27 | 2026-06-12 ~ 2026-06-14 | P0 | 性能测试增强 | 补中止执行接口、阈值判定、历史对比、JMeter 模板参数编辑、性能趋势聚合、报告风险建议。 |
| R28 | 2026-06-14 ~ 2026-06-16 | P0 | 报告中心增强 | 补模板管理闭环、报告下钻、风险项转待办、Markdown/HTML 强化；PDF/Word 若无新增依赖批准，先提供 HTML/Markdown 生产级替代。 |
| R29 | 2026-06-16 ~ 2026-06-17 | P1 | 数据工厂与数据管理 | 补接口参数测试数据生成、执行测试数据建议、自动备份提醒、存储空间统计、按模块清理安全门。 |
| R30 | 2026-06-17 ~ 2026-06-20 | P1 | 文件与导出格式增强 | 评估并实现 `.xlsx`、PDF、Word、XMind 的本地安全导出；若依赖未批准，保留 Markdown/CSV/HTML/ZIP 完整替代。 |
| R31 | 2026-06-20 ~ 2026-06-24 | 决策门 | 生产基础设施 | Alembic、PostgreSQL/pgvector、Celery/Redis、MinIO/S3、真实密钥加密存储。默认不静默引入，需在 `DECISIONS.md` 明确选择后实施。 |
| R32 | 2026-06-24 ~ 2026-06-26 | P0 | 第二轮总验收 | 全量测试、前端构建、核心浏览器流程、导出下载、secrets 扫描、远程分支校验、最终交付报告。 |

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

立即进入 R22：
- 增强 TXT/Markdown 需求解析与来源锚点。
- 补齐需求项编辑、合并、拆分、暂不入库和粒度质检闭环。
- 让需求大脑输出可追溯摘要与风险，继续保持真实 LLM 默认关闭和脱敏约束。

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
