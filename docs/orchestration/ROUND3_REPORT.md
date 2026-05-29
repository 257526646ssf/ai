# Backend V1 Round 3 Report

## 交付摘要
- 新增 OpenAI-compatible LLM client，支持 `/models` 与 `/chat/completions`。
- `POST /api/v2/llm-configs/{configId}/test` 接入真实 LLM client，并保留 disabled/fallback 路径。
- `POST /api/v2/chat` 接入真实 LLM client，并保留安全占位回复。
- 新增 Round 3 LLM contract/security tests。
- 前端视觉和 `src/` 未改动。

## 关键文件
- `backend/aitest_platform/services/llm_client.py`
- `backend/aitest_platform/api/router.py`
- `backend/tests/test_round3_llm_integration.py`
- `backend/.env.example`
- `backend/README.md`
- `docs/orchestration/ACCEPTANCE.md`

## 主线程验收
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest`：`16 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：105。
- Disabled smoke：`AITEST_ENABLE_REAL_LLM=false` 时，`llm-config test` 与 `chat` 不触网，返回 `skipped`，并记录 usage。
- 文件扫描：未发现用户真实 key 前缀。

## 安全结果
- API key 只通过 `AITEST_LLM_API_KEY` 读取。
- `.env.example` 只保留空变量，不包含真实值。
- 响应、错误、usage、日志和测试输出均不应包含原始 key、Authorization、token、cookie。

## 残余风险
- 主线程未将用户真实 key 注入命令行执行 live smoke，避免密钥进入命令记录。
- enabled path 已通过 mock tests 覆盖，真实服务响应差异后续可能需要微调。
- 当前只把真实 LLM 接入 LLM 配置测试和 Chat；需求拆解、测试点、用例生成仍未接真实 LLM。
