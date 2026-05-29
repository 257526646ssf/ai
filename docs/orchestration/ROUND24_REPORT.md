# Round 24 Report

## 名称
- R24：执行与缺陷闭环。

## 范围
- 后端新增 deterministic execution defect loop service，补齐失败/阻塞模板、缺陷建议、缺陷创建、关联/解除用例、复测提醒、执行趋势和缺陷闭环摘要。
- 前端 Execution 页面接入模板、趋势、缺陷闭环摘要、建议生成、缺陷创建、关联/解除、复测提醒、状态更新和复制文本。
- QA 覆盖执行到缺陷闭环的项目链路、统计、筛选、批量摘要和敏感信息脱敏。

## 实现
- 后端新增 `backend/aitest_platform/services/execution_defect_loop.py`，提供 deterministic execution defect loop service。
- 新增端点：`GET /executions/templates`、`POST /executions/{executionId}/defect-suggestion`、`POST /executions/{executionId}/create-defect`、`POST /defects/{defectId}/link-case`、`POST /defects/{defectId}/unlink-case`、`POST /defects/{defectId}/retest-reminder`、`GET /projects/{projectId}/execution-trend`、`GET /projects/{projectId}/defect-loop-summary`。
- 增强 batch、statistics、defects patch 和 copy-text 链路；批量摘要包含 `created_defects` / `failed` / `blocked` / `skipped`。
- `defect-suggestion` 返回 top-level `steps_to_reproduce`，便于前端和测试稳定消费。
- `copy-text` 使用中文标签“复现/实际/预期/复测建议”。
- R24 不接真实 LLM；缺陷建议和复测提醒均为确定性规则，并注意敏感信息脱敏。
- 前端 `src/pages/Execution.jsx` 接入 templates、trend、defect loop summary、suggestion/create/link/unlink/retest/status/copy。
- 前端批量摘要显示 `created_defects` / `failed` / `blocked` / `skipped`；历史趋势优先使用后端数据。
- 前端做了 shape normalization，兼容后端返回 array/object/string/null 等形态，避免 UI 因返回形状波动崩溃。

## QA
- 新增 `backend/tests/test_round24_execution_defect_loop.py`。
- 覆盖项目链路、模板、建议、创建缺陷、关联/解除、复测提醒、趋势、摘要、统计、筛选/patch/copy、批量摘要、脱敏。

## 验证
- `python -m compileall backend\aitest_platform`：通过。
- `python -m pytest backend\tests\test_round24_execution_defect_loop.py -q`：8 passed。
- `python -m pytest backend\tests\test_round15_execution_history.py backend\tests\test_round23_testcase_quality.py -q`：6 passed。
- `npm run build`：通过。
- `python -m pytest -q`：完整后端回归通过，退出码 0。
- API 验收：项目实际前缀为 `/api/v2`；裸 `/executions/templates` 和 `/api/executions/templates` 返回 404 是前缀不匹配，`/api/v2/executions/templates` 返回 200。
- 浏览器轻量验收：`http://127.0.0.1:3000/` 可加载，页面入口包含 `用例执行`；QA 收集到 `console.error` / `pageerror` 无明显 JS runtime error；深层交互曾受脚本中文编码/Playwright 卡顿影响，未作为完整交互验收证据。

## 残余风险
- 扩展缺陷字段通过 `Defect.remark` 的 R24 JSON prefix 存储，避免 schema 迁移。
- 建议和复测为 deterministic 规则，非真实 LLM。
- 冒烟使用临时数据。
- 趋势聚合基于本地 SQLite。

## 下一步
- 进入 R25：接口测试增强。
