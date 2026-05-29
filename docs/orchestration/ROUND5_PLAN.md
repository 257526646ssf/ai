# Backend V1 Round 5 Plan

## 目标
把接口测试模块从占位执行推进到真实 HTTP 调试和接口用例执行，形成可落库、可断言、可追溯的接口执行证据。

## 范围
- `POST /api/v2/apis/debug`
- `POST /api/v2/api-test-cases/{caseId}/execute`
- `POST /api/v2/api-test-cases/batch-executions`

## 设计原则
- 使用现有依赖 `httpx`，不新增生产依赖。
- 默认 timeout 5 秒，允许调用方覆盖，但限制在 0.1 到 30 秒之间。
- 有 active/specified environment 或 payload base URL 时真实请求；没有环境/base URL 时保留 deterministic placeholder，避免破坏既有前端和 Round 2 测试。
- 请求快照、响应快照、断言结果、耗时、错误信息必须写入 `ApiExecution`。
- 支持最小断言集：`status_code` 必须有；可扩展 body/header/json path 断言。
- 网络异常、超时、断言失败都返回结构化执行结果，不抛 500。
- 所有 secret 类字段和值必须脱敏。

## 验收
- `python -m compileall backend\aitest_platform`
- `cd backend; python -m pytest`
- Round 5 tests 覆盖：
  - debug 真实 runner
  - 单用例真实执行通过
  - 断言失败
  - timeout/request error
  - batch execution
  - secret redaction
  - no environment placeholder fallback

## 延后
- OpenAPI/Postman/curl 更完整导入解析。
- 复杂 pytest-style assertion engine。
- 场景依赖变量提取和跨步骤数据传递。
- 调度器真实定时运行。
