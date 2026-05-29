# Backend V1 Round 9 Report

## 目标
把系统备份/恢复从 dry-run 推进到安全、可预览、可合并的本地恢复闭环，并提供 schema/status 自检能力。

## 完成内容
- 新增 `services/restore_service.py`，`POST /api/v2/system/restore` 支持 dry-run、preview、merge restore。
- overwrite 模式必须携带 `confirm_text="RESTORE"`，本轮不做默认清库。
- 支持恢复 Round9 范围内的 Project、API 测试资产、自动化资产、性能方案、报告模板、Prompt 模板。
- `llm_configs` 只恢复安全字段，强制不恢复明文 API key。
- 新增 `services/schema_status.py` 与 `GET /api/v2/system/schema-status`。
- schema-status 只返回数据库类型和文件存在状态，不暴露完整本机路径。

## 主线程集成修复
- dry-run 返回增加 `summary` 兼容别名，保留 `tables` 详细结构，满足契约测试与后续调用方两种读取方式。

## 验收证据
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest tests/test_round9_restore_schema.py -q`：5 个用例通过。
- `cd backend; python -m pytest -o addopts='' -q`：`56 passed, 2 warnings in 9.16s`。
- OpenAPI `/api/v2` path 数：108。
- Secret scan：只发现测试/文档中的 fake secret 字符串，未发现用户真实 key。

## 质量评分
- Restore service：92/100。安全 merge/dry-run 可用；完整 overwrite 清库与复杂依赖恢复延后。
- Schema status：95/100。metadata introspection 可用；正式 Alembic 延后。
- QA 覆盖：94/100。恢复、保护门槛、脱敏和 schema status 均覆盖。
- 综合：93/100。

## 剩余建议
- Alembic、Celery/Redis、真实密钥加密、MinIO/S3 都属于依赖或运行形态变更，建议在下一决策点确认后再推进。
