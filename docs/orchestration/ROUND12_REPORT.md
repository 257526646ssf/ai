# Round 12 Report - 系统状态与回收站收口

## 本轮交付
- 新增 `services/system_state.py`，统一处理 DB 回收站、用户偏好、最近活动和系统状态脱敏。
- `/system/recycle-bin` 现在可列出数据库软删除对象，并保留旧内存 store 兼容。
- `/system/recycle-bin/{id}/restore` 支持恢复 `type:id` 形式的数据库回收站对象。
- 新增 `/system/preferences`、`/system/preferences/{prefKey}`，使用 `round2_resource` 持久化用户偏好。
- 新增 `/system/recent-activities`，使用 `round2_resource` 持久化最近活动。
- 收窄 `run-due` compact response 字段，避免无关数字污染调度验收结果。
- 新增 Round 12 system-state 合同和安全测试。

## 关键文件
- `backend/aitest_platform/services/system_state.py`
- `backend/aitest_platform/services/schedule_runner.py`
- `backend/aitest_platform/api/router.py`
- `backend/tests/test_round12_system_state.py`

## 主线程验收
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest tests/test_round12_system_state.py -q`：3 passed。
- `cd backend; python -m pytest tests/test_round7_import_schedule.py::test_run_due_executes_only_enabled_due_schedule_and_skips_disabled -q`：1 passed。
- `cd backend; python -m pytest -o addopts='' -q`：74 passed, 2 warnings。
- OpenAPI `/api/v2` path 数：115。
- Secret scan：只发现测试/文档中的 fake secret、文档说明和脱敏正则，未发现用户真实 key。

## 验收结论
- Round 12 接受，完成度 94/100。
- 系统回收站和本地用户状态已从占位推进为 SQLite 持久能力。

## 残余风险
- 回收站恢复只覆盖已有软删除模型，不执行级联恢复或跨对象依赖修复。
- 用户偏好和最近活动复用 `round2_resource`，不是正式独立表。
- 未实现清空所有数据/恢复出厂设置；该操作具有破坏性，需要用户单独确认。
