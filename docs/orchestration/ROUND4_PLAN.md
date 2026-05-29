# Backend V1 Round 4 Plan

## 目标
把真实 LLM 从配置测试和 Chat 扩展到核心主链，让需求文档可以生成结构化需求项，需求项可以生成测试点和测试用例。

## 范围
- `POST /api/v2/requirement-documents/{documentId}/extract-items`
- `POST /api/v2/requirement-items/{itemId}/generate-test-points`
- `POST /api/v2/requirement-items/{itemId}/generate-test-cases`

## 设计原则
- 默认 `AITEST_ENABLE_REAL_LLM=false`，离线测试不触网。
- enabled mode 调用 OpenAI-compatible `/chat/completions`。
- LLM 必须输出 JSON；后端必须做结构化解析、字段白名单、默认值补齐和数量限制。
- 解析失败、服务失败、缺配置时，安全降级到现有 deterministic placeholder。
- 生成结果必须写入 SQLite，并返回 `GenerationJob`、items/points/cases。
- 记录 `LlmUsage`，但响应、日志和 job payload 不得包含 API key、Authorization、token、cookie。

## 建议 Schema
- requirement items：
  - `title`
  - `summary`
  - `module`
  - `actor`
  - `goal`
  - `business_rules`
  - `exceptions`
  - `permissions`
  - `non_functional`
  - `priority`
  - `confidence`
- test points：
  - `title`
  - `point_type`
  - `target`
  - `priority`
  - `suggested_method`
  - `note`
- test cases：
  - `test_point_id`
  - `title`
  - `case_type`
  - `precondition`
  - `steps`
  - `expected_result`
  - `priority`
  - `tags`

## 验收
- `python -m compileall backend\aitest_platform`
- `cd backend; python -m pytest`
- Round 4 mock-enabled tests 通过：
  - LLM JSON 生成需求项
  - LLM JSON 生成测试点
  - LLM JSON 生成测试用例
  - 坏 JSON / provider error 降级
  - secret redaction

## 延后
- LangGraph 多轮生成编排。
- SSE 流式生成详情。
- 真实 live smoke。
- API 调试、Playwright、JMeter 执行器。
