# Backend V1 Round 7 Plan

## 目标
补齐接口测试链路的“真实导入 -> 可执行用例 -> 调度触发”闭环，继续不改前端视觉风格、不新增生产依赖、不写入真实密钥。

## 范围
- `POST /api/v2/api-test-libs/{libId}/import-documents`
- `POST /api/v2/api-test-libs/{libId}/apis/import`
- `POST /api/v2/api-schedules/{scheduleId}/run`
- `POST /api/v2/api-schedules/run-due`

## 设计原则
- OpenAPI/Postman/curl 解析优先使用 Python 标准库；YAML 只在本机已有解析能力时支持，否则返回结构化 validation error。
- 导入结果必须写入 SQLite `ApiEndpoint`，并在 payload 明确要求时生成 `ApiTestCase`。
- 导入时必须脱敏 headers/body/query 中的 Authorization、api_key、token、cookie、secret、password。
- 调度执行先实现本地同步触发和 due-scan，不引入 Celery/Redis；执行结果必须落库 `ApiExecution`，并更新 `ApiSchedule.last_run_at`、`last_result`。
- 缺少 environment/base URL 时继续保持 placeholder fallback，不因调度或导入错误导致 500。
- Worker 写入范围必须隔离；`router.py` 修改仅限各自负责区块。

## Worker 分配
- api_import_engineer_round7：负责导入解析服务与 import 路由区块。
- schedule_runner_engineer_round7：负责调度执行服务与 schedules 路由区块。
- qa_contract_engineer_round7：负责 Round 7 契约/安全测试，尽量只新增测试文件。

## 验收
- `python -m compileall backend\aitest_platform`
- `cd backend; python -m pytest tests/test_round7_import_schedule.py -q`
- `cd backend; python -m pytest -o addopts='' -q`
- Round 7 tests 覆盖：
  - OpenAPI JSON 导入 endpoint，并按需生成 ApiTestCase。
  - Postman Collection JSON 导入嵌套 item。
  - curl 命令导入 method/header/body/path/query。
  - 导入 secret redaction。
  - schedule manual run 执行 case/scenario 并更新 last_result。
  - run-due 只执行 enabled 且 due 的 schedule。

## 延后
- 完整 YAML OpenAPI 解析。
- Celery/Redis 分布式调度。
- 可视化调度队列和后台常驻 worker。
- 更完整的 Postman prerequest/test script 转换。
