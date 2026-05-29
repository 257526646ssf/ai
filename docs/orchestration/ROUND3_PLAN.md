# Backend V1 Round 3 Plan

## 目标
接入用户提供的本地 OpenAI-compatible `/v1` 服务，让后端具备真实 LLM 调用能力，同时保持本地优先、安全脱敏和失败降级。

## 输入
- Base URL：用户提供的本地 `/v1` 地址。
- API Key：用户已提供，但必须视为敏感信息。

## 安全规则
- 不得把 API Key 写入 `.env.example`、文档、测试、SQLite 明文字段、日志或响应。
- 运行时优先读取 `AITEST_LLM_BASE_URL`、`AITEST_LLM_API_KEY`、`AITEST_ENABLE_REAL_LLM`。
- `LlmConfig.api_key_ref` 只保存掩码或引用，不保存真实 key。
- 所有异常信息必须脱敏，不包含 Authorization header、token、cookie、api_key。

## 范围
- 新增 OpenAI-compatible LLM client：
  - `GET /models`
  - `POST /chat/completions`
  - timeout、错误分类、安全降级
- API 接入：
  - `POST /api/v2/llm-configs/{configId}/test`
  - `POST /api/v2/chat`
  - LLM usage 记录
- 测试：
  - disabled mode 不触网并返回 skipped/fallback
  - enabled mode 使用 mock transport/monkeypatch，不调用真实服务
  - secret redaction
  - usage statistics 增长

## 验收
- `python -m compileall backend\aitest_platform`
- `cd backend; python -m pytest`
- OpenAPI `/api/v2` path 数不低于 105。
- 主线程手工 smoke：
  - 未启用真实 LLM：`llm-config test` 和 `chat` 安全降级。
  - 启用真实 LLM 且设置环境变量：可连接本地 `/v1` 服务，返回模型结果或明确的脱敏错误。

## 延后
- 需求拆解、测试点生成、用例生成的全链路真实 LLM 改造。
- API key 加密存储。
- 多模型路由、重试退避队列、流式 SSE 输出。
