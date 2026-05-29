# Round 11 Plan - 导出与下载后端收口

## 本轮目标
- 在不新增生产依赖、不改变前端视觉风格的前提下，补齐文档中高频导出/下载能力。
- 优先实现可本地生成的 Markdown / CSV / JSON / ZIP，暂不实现 PDF、Word、真实 Excel `.xlsx`。

## 范围
- 测试用例导出
  - 支持按项目、需求项、选中 ID、用例类型导出。
  - 支持 `markdown`、`csv`、`json` 格式。
- 缺陷列表导出
  - 支持按项目和状态过滤。
  - 支持 `markdown`、`csv`、`json` 格式。
- 自动化项目下载
  - 将框架文件和用例文件打包为 ZIP。
  - 返回 `filename`、`mime_type`、`content_base64`、`files`，不再标记 placeholder。
- 性能脚本/结果下载
  - 支持下载 JMX 脚本。
  - 支持下载最新或指定 PerfResult 的原始数据路径/摘要，缺少文件时结构化降级。

## 非目标
- 不实现 PDF/Word。
- 不新增 Excel `.xlsx` 依赖；Excel 诉求先由 CSV 覆盖。
- 不引入对象存储。
- 不改前端视觉。

## Worker 分配
- `export_download_engineer_round11`
  - 负责导出服务和相关路由实现。
- `qa_export_engineer_round11`
  - 只新增 Round11 合同/安全测试。

## 验收标准
- 新增 Round11 tests 通过。
- 全量后端测试通过。
- 导出内容可解码/可读。
- 导出响应不泄露 `api_key`、`token`、`cookie`、`password`、`secret`、`authorization`、`git_auth` 等敏感字段。
