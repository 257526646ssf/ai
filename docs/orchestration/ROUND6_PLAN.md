# Backend V1 Round 6 Plan

## 目标
把自动化、性能和 API 场景从“结构化占位结果”推进到可实际触发本地执行的后端能力。

## 范围
- `POST /api/v2/auto-projects/{autoProjectId}/execute`
- `GET /api/v2/auto-executions/{executionId}/events`
- `POST /api/v2/perf-plans/{planId}/execute`
- `POST /api/v2/api-scenarios/{scenarioId}/execute`

## 设计原则
- 不新增生产依赖；自动化 runner 优先执行项目内已生成的 Python/pytest 文件，若文件使用 Playwright 且本机已安装则自然运行。
- JMeter runner 使用本机 `jmeter` CLI；缺工具、超时、脚本错误时返回结构化 `error`，不抛 500。
- 保留兼容 fallback：没有 case files/JMX/明确真实执行条件时仍可返回 deterministic placeholder。
- 所有执行都要落库，包含 summary、artifacts、log excerpt、duration、错误信息。
- stdout/stderr、命令、路径、环境变量和错误信息要脱敏并限制长度。
- API scenario 使用 Round 5 API runner，按节点顺序执行关联 case，支持 `{{variable}}` 基础注入和响应 JSON 字段提取。

## 验收
- `python -m compileall backend\aitest_platform`
- `cd backend; python -m pytest`
- Round 6 tests 覆盖：
  - auto runner 成功/失败/超时或脚本错误
  - perf runner JMeter mock 成功/缺工具错误
  - API scenario 顺序执行、变量注入/提取
  - secret redaction
  - 兼容 fallback

## 延后
- 真实 Celery/Redis 异步调度。
- 完整 Playwright trace/screenshot 采集。
- 完整 JMeter HTML report 打包。
- 完整 OpenAPI/Postman/curl 导入解析。
