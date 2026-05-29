# Backend V1 Round 5 Report

## 交付摘要
- 新增真实 API runner，使用现有 `httpx` 执行接口调试和接口用例。
- `POST /api/v2/apis/debug` 支持真实请求、响应快照、断言结果和错误降级。
- `POST /api/v2/api-test-cases/{caseId}/execute` 在有 environment/base URL 时真实执行并写入 `ApiExecution`。
- `POST /api/v2/api-test-cases/batch-executions` 复用同一执行逻辑。
- 支持 `status_code`、`body_contains`、`json_path_equals`、`header_equals` 断言。
- 保留无 environment/base URL 时的 deterministic placeholder，兼容 Round 2。
- 修复 `GET /llm-configs` 默认持久库历史数据过多时新建配置不在第一页的问题。
- 前端视觉和 `src/` 未改动。

## 关键文件
- `backend/aitest_platform/services/api_runner.py`
- `backend/aitest_platform/api/router.py`
- `backend/tests/test_round5_api_runner.py`
- `docs/orchestration/ACCEPTANCE.md`
- `docs/orchestration/STATUS.md`

## 主线程验收
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest tests/test_round5_api_runner.py -q`：8 个 Round 5 用例通过。
- `cd backend; python -m pytest`：`33 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：106。
- 本地 HTTP smoke：临时 SQLite + 本机 HTTPServer，`apis/debug` 和 `api-test-cases/{caseId}/execute` 均真实请求成功，HTTP 201 断言通过。

## 安全结果
- 请求快照、响应快照、断言结果和错误信息会脱敏 Authorization、api_key、token、cookie、secret、password。
- timeout 默认 5 秒，限制在 0.1 到 30 秒之间。
- 响应 body 入库有长度限制，避免巨大响应直接写入执行记录。

## 残余风险
- 尚未实现 OpenAPI/Postman/curl 的完整导入解析。
- API 场景执行仍缺跨步骤变量提取和数据传递。
- 自动化执行器、JMeter 执行器和异步任务调度仍未完成。
