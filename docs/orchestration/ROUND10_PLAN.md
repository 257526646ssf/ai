# Round 10 Plan - 报告中心后端收口

## 本轮目标
- 在不新增生产依赖、不改变前端视觉风格的前提下，把报告中心从占位能力推进为可验收的后端快照链路。
- 对齐需求文档第九章与技术方案 4.20：报告聚合层、报告快照层、正式报告和轻量结论共用同一份聚合上下文。

## 范围
- `POST /api/v2/reports/comprehensive`
  - 聚合 Project、RequirementItem、TestCase、Execution、Defect、ApiExecution、AutoExecution、PerfResult 等事实数据。
  - 生成稳定的 `scope_snapshot`、`data_snapshot`、`source_refs_json`。
- `POST /api/v2/perf-plans/{planId}/generate-report`
  - 基于 PerfPlan 和最新 PerfResult 生成性能报告快照。
- `GET /api/v2/reports/{reportId}/download`
  - 支持 `format=markdown|html|json`。
  - 返回 `filename`、`content`、`mime_type`、`format`，不再标记 placeholder。
- `POST /api/v2/reports/lightweight-conclusions`
  - 有 `project_id` 时复用报告聚合上下文生成轻量结论。
  - 支持 `save=true` 时保存为轻量报告记录。
  - 缺少 `project_id` 时保留兼容降级，不破坏已有前端调用。

## 非目标
- 不引入 PDF/Word 导出依赖。
- 不引入对象存储。
- 不引入 Celery/Redis。
- 不做前端视觉改动。

## Worker 分配
- `reporting_aggregator_engineer_round10`
  - 负责 `backend/aitest_platform/services/reporting.py` 和必要的报告相关路由接入。
  - 不修改测试文件。
- `qa_reporting_engineer_round10`
  - 只新增 `backend/tests/test_round10_reporting.py`。
  - 不修改实现代码。

## 验收标准
- Round10 合同测试通过。
- 全量后端测试通过。
- 报告快照中可以追溯到需求项、用例、执行、缺陷及接口/自动化/性能结果。
- 响应与快照不泄露 `api_key`、`token`、`cookie`、`password`、`secret`、`authorization`、`git_auth` 等敏感字段。
