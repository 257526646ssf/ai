# Backend V1 Round 9 Plan

## 目标
把系统备份/恢复从 dry-run 推进到安全、可预览、可合并的本地恢复闭环，并提供 schema/status 自检能力。

## 范围
- `POST /api/v2/system/restore`
- `GET /api/v2/system/schema-status`
- 备份数据版本/兼容性检查

## 设计原则
- 默认 `mode=merge`，禁止默认清库。
- `dry_run=true` 或 `preview=true` 时只返回统计和兼容性检查，不写数据库。
- `mode=overwrite` 必须携带确认字段，例如 `confirm_text="RESTORE"`，否则返回 400。
- 本轮优先恢复安全且依赖少的配置/二级资产表：Project、ApiTestLib、ApiEndpoint、ApiTestCase、ApiEnvironment、ApiScenario、ApiSchedule、AutoProject、AutoCaseFile、PerfPlan、ReportTemplate、PromptTemplate。
- 避免恢复真实密钥；`llm_configs` 只恢复脱敏配置，不恢复明文 API key。
- 所有恢复结果和错误信息都必须脱敏。
- 不引入 Alembic；schema-status 使用 SQLAlchemy metadata + SQLite introspection。

## Worker 分配
- restore_engineer_round9：负责恢复服务与 `/system/restore` 接入。
- schema_status_engineer_round9：负责 schema status 自检服务与路由。
- qa_restore_engineer_round9：负责 Round 9 契约/安全测试。

## 验收
- `python -m compileall backend\aitest_platform`
- `cd backend; python -m pytest tests/test_round9_restore_schema.py -q`
- `cd backend; python -m pytest -o addopts='' -q`

## 延后
- Alembic 正式迁移。
- 清库式 overwrite 的生产操作流程。
- 完整恢复所有主链复杂依赖对象。
