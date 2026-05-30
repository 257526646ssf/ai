# Round 30 Report

## 名称
- R30：文件与导出格式增强。

## 日期
- 验收日期：2026-05-30。
- 说明：第二轮路线图中的旧时间窗口如与实际完成时间冲突，以本报告、`ACCEPTANCE.md` 验收记录和实际测试证据为准。

## 范围
- 后端统一 unsupported 导出契约。
- 后端在不新增生产依赖的前提下支持 test-cases/defects 的 XLSX 导出。
- 后端对 CSV/XLSX 单元格内容做公式注入中和。
- 后端对 docx/pdf/xlsx/xmind 导入建立二进制格式硬边界。
- 后端对自动化/性能 artifact ZIP 做 canonical path 校验、越界条目 skipped metadata 记录和文本脱敏。
- 前端移除假下载/假成功，并把可用格式和 unsupported 提示接到真实后端契约。

## 实现
- TestCases 支持 CSV、Markdown、JSON、XLSX 四种真实下载。
- PDF、Word、XMind 未开放真实服务端生成；前端展示未开放提示，后端返回统一 unsupported 结构化响应，不返回假文件字段。
- Reports 和 Performance 使用 HTML/Markdown 作为当前可下载替代格式。
- 统一下载 helper 处理 unsupported、空内容和真实文件下载，避免假成功。
- 自动化/性能 artifact ZIP 只打包 canonical path 校验通过的文件；越界文件进入 skipped metadata；文本类内容继续脱敏。
- 本轮未新增生产依赖；XLSX 导出采用无依赖 workbook 生成路径。

## QA
- 新增 `backend/tests/test_round30_file_export_formats.py`。
- 定向测试覆盖 unsupported contract、test-cases/defects XLSX、公式注入中和、二进制导入硬边界、artifact ZIP path containment、skipped metadata 和文本脱敏。

## 验证
- `python -m compileall backend\aitest_platform`：通过。
- R30 定向测试：36 passed。
- 合同回归组合：64 passed。
- 后端全量：通过。
- 前端构建：`npm run build` 通过。
- 真实 Chrome 烟测：通过；TestCases 四种真实下载均可用，XLSX 为真实 ZIP workbook，unsupported 不返回假文件字段，artifact 越界条目进入 skipped，`console.error=0`，`pageerror=0`。
- 端口说明：本机 8000 被既有 PID 4588 占用，验收使用 8001，未触碰非本次启动进程。

## 残余风险
- PDF、Word、XMind 未做真实服务端生成；后续如需真实生成，需要先决策依赖、格式口径和安全边界。
- XLSX 为当前无依赖实现，覆盖本轮 test-cases/defects 导出场景，不等同完整 Excel 模板/样式系统。
- docx/pdf/xlsx/xmind 导入在本轮建立硬边界，不做深度解析。

## 下一步
- 进入 R31：生产基础设施决策。
- R31-R32 仍为未完成排期；不得把 Alembic、PostgreSQL/pgvector、Celery/Redis、MinIO/S3、真实密钥加密存储或第二轮总验收写成已完成。
