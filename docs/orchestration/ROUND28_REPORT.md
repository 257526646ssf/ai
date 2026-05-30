# Round 28 Report

## 名称
- R28：报告中心增强。

## 日期
- 验收日期：2026-05-30。
- 说明：第二轮路线图中的旧时间窗口如与实际完成时间冲突，以本报告、`ACCEPTANCE.md` 验收记录和提交/测试证据为准。

## 范围
- 后端补齐 report-templates CRUD 校验与默认唯一约束。
- 综合报告按 `template_id` 和 `scope` 生成，并冻结模板、章节和 scope 快照。
- 报告列表支持过滤、排序；报告支持 drilldown；报告风险支持独立读取。
- 风险项可转待办，todo 列表和状态可查询/更新。
- Markdown/HTML 输出强化，HTML 输出做 escape，报告快照和嵌套数据继续递归脱敏。
- PDF/Word/docx 暂不引入新依赖，返回 unsupported 结构化响应。
- 轻量结论支持 `daily_report`、`test_submission_feedback`、`release_advice`、`risk_list`。
- 前端 Reports 页移除 fallback/static AI 意见、固定默认报告和假分享，改为接真实报告列表、模板管理、筛选排序、下钻、风险转待办、下载和轻量结论类型。

## 实现
- 增强后端文件：
  - `backend/aitest_platform/api/router.py`
  - `backend/aitest_platform/models.py`
  - `backend/aitest_platform/services/reporting.py`
- 前端增强：
  - `src/pages/Reports.jsx`
- 报告模板管理完成创建、读取、更新、删除、校验和默认模板唯一性控制。
- 综合报告生成会冻结所用模板、章节定义和 scope，避免历史报告随模板或实时筛选漂移。
- 报告列表支持按项目、类型、状态等条件过滤，并支持排序口径。
- drilldown 和 risks 为报告详情提供可追溯入口，风险项可转换为待办并进入 todo 列表/状态流转。
- Markdown/HTML 输出强化，并保持敏感字段递归脱敏；HTML 输出避免原始内容直接注入。
- PDF、Word、docx 输出在未引入生产依赖前返回结构化 unsupported，不伪装成功。

## 前端
- Reports 页已移除静态 fallback AI 意见、固定默认报告和假分享入口。
- 报告列表、模板管理、筛选排序、报告下钻、下钻明细、风险转待办和下载均接入真实后端能力。
- 轻量结论入口覆盖日报、提测反馈、上线建议和风险清单。
- 模板管理支持查看、新建模板等核心路径。

## QA
- 新增 `backend/tests/test_round28_report_center_enhancement.py`。
- 定向测试覆盖 report-templates CRUD 与默认唯一、综合报告模板/scope 冻结、列表过滤排序、drilldown、risks、风险转待办、todo 状态、Markdown/HTML 输出、unsupported PDF/Word/docx、递归脱敏和轻量结论类型。

## 验证
- `python -m compileall backend/aitest_platform`：passed。
- R28 定向测试：`backend/tests/test_round28_report_center_enhancement.py`，13 passed。
- 合同组合回归：passed。
- 后端全量：`pytest -q` passed。
- 前端构建：`npm run build` passed。
- 真实 Chrome Playwright 报告中心烟测：passed；`console.error=0`，`pageerror=0`。
- 浏览器入口命中：风险转待办、Markdown、HTML、日报、提测反馈、上线建议、风险清单、管理报告模板/新建模板、查看下钻/下钻明细。
- 端口已清理。

## 残余风险
- PDF/Word/docx 仍为 unsupported 结构化返回，未引入新导出依赖。
- 报告下钻、风险和待办流转已覆盖核心路径，后续仍可按产品口径扩展更细的权限、审计和团队协作规则。
- 轻量结论为当前报告聚合口径下的规则化输出；真实 LLM 仍按既有开关和安全约束处理。

## 下一步
- 进入 R29：数据工厂与数据管理。
- R29 只应推进已排期的数据生成、执行测试数据建议、自动备份提醒、存储空间统计和按模块清理安全门，不应顺带夸大 R30-R32 未完成能力。
