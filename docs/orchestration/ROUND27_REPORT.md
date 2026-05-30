# Round 27 Report

## 名称
- R27：性能测试增强。

## 日期
- 验收日期：2026-05-30。
- 说明：第二轮路线图中的旧时间窗口如与实际完成时间冲突，以本报告、`ACCEPTANCE.md` 验收记录和提交/测试证据为准。

## 范围
- 后端补齐性能执行停止/中止接口、阈值判定、历史对比、项目 `performance-trend` 聚合。
- JMeter 参数编辑会体现在生成/下载脚本中。
- `generate-report` 增加风险建议，并对报告快照做递归脱敏。
- 前端 Performance 页面接完整 results、阈值判定、历史比对、7 日趋势、JMeter 参数表单、停止执行和报告建议展示。
- 去掉 Performance 页面中影响判断的关键静态假数据。

## 实现
- 增强后端文件：
  - `backend/aitest_platform/api/router.py`
  - `backend/aitest_platform/services/perf_runner.py`
  - `backend/aitest_platform/services/reporting.py`
  - `backend/aitest_platform/services/exporting.py`
- 新增后端服务：
  - `backend/aitest_platform/services/perf_analysis.py`
- 性能结果增加阈值判定输出，覆盖 P95、错误率、吞吐等核心指标口径。
- 性能历史对比基于已有结果生成本次与上一轮/历史记录的变化摘要。
- 项目级 `performance-trend` 支持聚合近 7 日趋势，用于前端趋势展示。
- JMeter 模板参数支持编辑，并在下载脚本中体现配置结果。
- 性能报告生成时补充风险/建议，并递归脱敏嵌套数据，避免 token、cookie、secret、Authorization 等敏感字段回显。

## 前端
- `src/pages/Performance.jsx` 接入完整 results 列表，不再依赖关键静态假数据。
- 展示阈值判定、历史比对、7 日趋势 P95。
- 新增 JMeter 参数/模板参数表单，并与脚本生成、下载链路对齐。
- 支持停止执行操作。
- 报告页展示报告建议和风险建议。

## QA
- 新增 `backend/tests/test_round27_performance_enhancement.py`。
- 覆盖性能停止/中止、阈值判定、历史比对、趋势聚合、JMeter 参数落脚本、报告风险建议和递归脱敏等 R27 契约。

## 验证
- `python -m compileall backend/aitest_platform`：passed。
- R27 定向测试：`backend/tests/test_round27_performance_enhancement.py`，10 passed。
- 合同组合回归：passed。
- 后端全量：`pytest -q` passed。
- 前端构建：`npm run build` passed。
- 真实 Chrome Playwright 烟测：passed；`console.error=0`，`pageerror=0`。
- 浏览器关键词命中：阈值判定、性能历史比对、7日趋势 P95、JMeter 参数/模板参数、停止执行、报告建议/风险建议。

## 残余风险
- 真实 JMeter 执行仍依赖本机 JMeter CLI、目标系统可达性和测试环境容量。
- 阈值与风险建议为当前规则化口径，后续可按项目 SLA 或团队准出标准继续调参。
- 历史比对和 7 日趋势依赖已落库的性能结果，冷启动或样本很少时只能展示有限趋势。
- 本轮未引入 Celery/Redis、对象存储、正式迁移或生产级密钥管理。

## 下一步
- 进入 R28：报告中心增强。
- 优先补模板管理闭环、报告下钻、风险项转待办、Markdown/HTML 强化。
- PDF/Word 若没有新增依赖批准，继续以 HTML/Markdown 作为生产级替代输出。
