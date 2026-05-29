# Backend V1 Round 4 Report

## 交付摘要
- 将真实 LLM 能力从配置测试和 Chat 扩展到核心主链三条生成接口。
- 新增结构化生成服务，负责 prompt、JSON 提取、字段归一、数量限制和默认值补齐。
- `extract-items`、`generate-test-points`、`generate-test-cases` 在 enabled mode 可消费 LLM JSON 并写入 SQLite。
- disabled、缺配置、provider error、坏 JSON、空结构化结果会安全降级到 deterministic placeholder。
- 新增 Round 4 contract/security tests，并补强 `agt_codex_...` 风格 key 的错误文本脱敏。
- 前端视觉和 `src/` 未改动。

## 关键文件
- `backend/aitest_platform/services/structured_generation.py`
- `backend/aitest_platform/services/llm_client.py`
- `backend/aitest_platform/api/router.py`
- `backend/tests/test_round4_main_chain_llm.py`
- `backend/README.md`
- `docs/orchestration/ACCEPTANCE.md`
- `docs/orchestration/STATUS.md`

## 主线程验收
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest`：`25 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：106。
- Disabled smoke：document parse -> extract-items -> generate-test-points -> generate-test-cases 通过。
- Smoke 结果：1 个 RequirementItem、2 个 TestPoint、2 个 TestCase，fake key/token 未出现在响应中。
- 文本扫描：未发现非测试用 `agt_codex_` 风格 key。

## 安全结果
- API key 仍只通过 `AITEST_LLM_API_KEY` 读取，不写入数据库明文。
- LLM provider 错误、响应 payload、GenerationJob payload 和 operation log 均走脱敏边界。
- Round 4 测试只使用 fake secrets，不使用用户真实 key。

## 残余风险
- 未用用户真实 key 做 live smoke，避免密钥进入命令记录；真实连通性需在本地环境变量中手动验证。
- LangGraph 多轮编排、SSE 生成详情、Celery/Redis 异步执行仍未接入。
- 真实 API 调试、Playwright 自动化执行、JMeter 性能执行仍是后续轮次范围。
- 正式迁移和密钥管理还未落地。
