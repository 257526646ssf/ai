# Round 15 Plan：Execution 前后端集成

## 目标
- 保持现有 Execution 页面视觉和布局，只替换核心 mock 链路。
- 将执行页接入后端执行记录、执行统计、缺陷列表、测试用例和测试轮次。
- 打通最小主链：测试用例 -> 创建执行轮次 -> 批量写入执行记录 -> 失败生成缺陷 -> 前端刷新统计和缺陷。

## 范围
- 后端：
  - 新增 `GET /api/v2/projects/{projectId}/test-rounds` 项目级轮次列表。
  - 复用已有 `/executions`、`/executions/batch`、`/executions/history`、`/executions/statistics`、`/defects`、`/defects/export`。
  - 新增 Round15 契约测试覆盖执行轮次、批量执行、统计、缺陷读回。
- 前端：
  - `src/pages/Execution.jsx` 加载默认项目、执行统计、执行历史、缺陷、后端测试用例。
  - “批量执行”创建轮次并写入执行记录。
  - “重跑失败”将失败/阻塞记录重新写入通过记录。
  - “导出缺陷列表”下载 CSV。

## 非目标
- 不重做 UI。
- 不实现真实浏览器自动化执行器的新能力。
- 不新增生产依赖。
- 不处理正式全局项目选择器。
- 不改动真实密钥存储策略。
