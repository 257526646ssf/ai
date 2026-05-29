# Backend V1 Round 2 Plan

## 目标
将第一轮仍在内存 store 中的 P1 模块资源迁移到 SQLite，使后端在重启后仍能保留接口测试、自动化、性能、报告模板、LLM 配置和 Prompt 模板等资产。

## 范围
- 接口测试：
  - `ApiTestLib`
  - `ApiEndpoint`
  - `ApiTestCase`
  - `ApiEnvironment`
  - `ApiScenario`
  - `ApiSchedule`
  - `ApiExecution`
- 自动化中心：
  - `AutoProject`
  - `AutoCaseFile`
  - `AutoExecution`
- 性能测试：
  - `PerfPlan`
  - `PerfResult`
- 配置与系统：
  - `ReportTemplate`
  - `LlmConfig`
  - `LlmUsage`
  - `PromptTemplate`
  - `OperationLog`
  - `BackupSnapshot`

## 接口原则
- API prefix 继续使用 `/api/v2`。
- 统一响应继续保持 `{ code, message, data, trace_id }`。
- 不调用真实 LLM、真实外部 API、真实 JMeter、真实 Playwright。
- API key 只能保存引用或掩码，任何响应、日志、测试断言都不能回显真实 key。
- 生成、执行、导出类接口可以返回结构化占位结果，但必须落库或读取统一数据层。

## 验收
- `python -m compileall backend\aitest_platform`
- `cd backend; python -m pytest`
- OpenAPI `/api/v2` path 数不低于第一轮的 105。
- 手工 smoke：
  - project -> api-test-lib -> endpoint -> api case -> api execution -> environment -> scenario -> schedule
  - project -> auto-project -> framework -> auto case file -> auto execution -> download metadata
  - project -> perf-plan -> generated plan -> generated script -> perf result -> perf report
  - report-template CRUD
  - llm-config create/update/test/statistics
  - prompt-template update/test

## 延后
- Alembic 迁移。
- 真正加密 API key。
- 真实网络请求调试。
- 真实自动化框架 ZIP 打包。
- 真实 JMeter 执行。
