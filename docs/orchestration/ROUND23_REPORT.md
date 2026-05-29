# Round 23 Report

## 名称
- R23：用例评审与质量规则。

## 范围
- 后端新增 deterministic 用例质量规则服务，补齐单条评审、批量评审、项目级质量摘要、人工评审意见保存，以及旧入口复用。
- 前端 TestCases 页面接入项目级质量摘要、单条质量评审、批量评审、评审意见保存、质量分展示和评审操作。
- QA 覆盖完整项目链路、质量规则、旧入口兼容和 secret redaction。

## 实现
- 后端新增 `backend/aitest_platform/services/test_case_quality.py`，提供 deterministic 用例质量规则服务。
- 规则覆盖缺步骤、缺预期、预期不可断言/过短、标题过短、缺 source anchors、优先级不一致、重复/相似、不可执行、同需求 happy path 覆盖弱。
- 新增/增强接口：`POST /test-cases/{caseId}/quality-review`、`POST /test-cases/review-batch`、`GET /projects/{projectId}/test-case-quality-summary`、`POST /test-cases/{caseId}/review-opinions`。
- 旧入口 `rule-validate` 和 `ai-review` 复用新规则服务。
- R23 不调用真实 LLM，响应 provider flags false，并做脱敏。
- TestCases 页面新增项目级质量摘要区。
- TestCases 页面接入单条质量评审、批量评审、评审意见保存。
- 表格增加质量分和单条评审操作。
- 所有评审返回 array/object/string/null 归一化，避免 R22 类似 `.slice` 崩溃。

## QA
- 新增 `backend/tests/test_round23_testcase_quality.py`。
- 覆盖完整项目链路、好/坏/重复/优先级不一致用例、质量评审、批量评审、项目摘要、人工意见、旧入口、secret redaction。

## 验证
- `python -m compileall backend\aitest_platform`：通过。
- `python -m pytest backend\tests\test_round23_testcase_quality.py -q`：5 passed。
- `python -m pytest backend\tests\test_round14_requirement_testcase_integration.py backend\tests\test_round22_requirement_closure.py -q`：9 passed。
- `cd backend; python -m pytest -q`：全量通过。
- `npm run build`：通过，仅 Vite chunk size warning。
- Headless Chrome CDP 烟测通过：R23 专用项目进入测试用例库，质量摘要可见，批量评审/单条评审按钮可见，批量评审后结果可见，`window.__r23Errors` 为空。

## 残余风险
- 规则评分是 deterministic 启发式，阈值后续可按产品验收口径微调。
- 人工评审意见保存到操作日志/状态字段，没有新增正式 Review 表。
- 浏览器烟测使用本地临时 smoke 数据。
- 真实 LLM 默认关闭。

## 下一步
- 进入 R24：执行与缺陷闭环。
