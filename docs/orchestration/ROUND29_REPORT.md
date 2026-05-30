# Round 29 Report

## 名称
- R29：数据工厂与数据管理。

## 日期
- 验收日期：2026-05-30。
- 说明：第二轮路线图中的旧时间窗口如与实际完成时间冲突，以本报告、`ACCEPTANCE.md` 验收记录和实际测试证据为准。

## 范围
- 后端补齐接口参数测试数据生成。
- 后端补齐测试用例维度的测试数据建议。
- 后端补齐系统备份状态、存储空间统计和模块化清理安全门。
- 前端 Settings 接入存储统计、备份提醒、清理 dry-run 和确认执行。
- 前端 ApiTesting 增加生成测试数据入口。
- 前端 Execution 增加准备测试数据入口和空态。

## 实现
- 新增/增强后端能力：
  - `POST /data-factory/api-parameters/generate`
  - `GET /test-cases/{caseId}/test-data-suggestions`
  - `GET /system/backup-status`
  - `GET /system/storage-summary`
  - `POST /system/cleanup`
- 清理接口已加入 dry-run、安全确认文本 `CLEANUP`、模块白名单、路径根目录限制和响应脱敏。
- Settings 页已接入存储统计、备份提醒、清理预览和确认执行流程。
- ApiTesting 页已增加接口参数测试数据生成入口。
- Execution 页已增加准备测试数据入口，并处理没有可准备数据时的空态。

## QA
- 新增 `backend/tests/test_round29_data_factory_management.py`。
- 定向测试覆盖数据生成、测试数据建议、备份状态、存储统计、清理 dry-run/确认门、模块白名单、路径边界和响应脱敏等 R29 范围。

## 验证
- R29 定向测试复验：`backend/tests/test_round29_data_factory_management.py`，5 passed。
- 后端实现阶段曾记录 R29 定向 8 passed；当前以文件实际测试复验结果 5 passed 为准。
- 合同回归组合：passed。
- 后端全量：passed。
- 前端构建：`npm run build` passed。
- 浏览器复验：passed；Settings cleanup dry-run 返回 200，payload 包含 `execution_history`、`api_execution_history`、`artifacts`，`console.error=0`，`pageerror=0`。
- 未执行真实清理：dry-run 显示会影响 849 个 artifact 文件，出于安全边界仅验证 dry-run 和确认门能力。
- 端口说明：本机 8000 被既有 `python -m http.server 8000` PID 4588 占用，验收使用 8001，未触碰非本次启动进程。

## 残余风险
- 真实清理未在本轮执行，原因是 dry-run 预估影响 849 个 artifact 文件；后续如需执行必须由用户明确确认清理范围和确认文本。
- 数据生成与建议能力按当前本地规则和现有数据口径输出，不等同外部真实数据平台或真实 LLM 生成。
- 存储统计和备份提醒以本地 SQLite/artifacts 文件布局为当前依据，后续若引入对象存储或生产备份系统需重新校准口径。

## 下一步
- 进入 R30：文件与导出格式增强。
- R30-R32 仍为未完成排期，不应把文件/导出格式增强、生产基础设施决策或第二轮总验收写成已完成。
