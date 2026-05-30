# R32 第二轮总验收报告

## 轮次定位

R32 是第二轮总验收，不新增业务能力，目标是基于当前工作区和远程分支状态，完成全量验证、边界核对、最终交付报告和完成审计。

## 验收结论

- 第二轮 R20-R31 的已实施能力在当前工作区和远程分支上均有提交与验收记录支撑。
- 后端编译通过，后端全量测试通过，重点合同回归在隔离 SQLite 下通过。
- 前端构建通过，核心页面浏览器导航通过，未出现 `console.error`、`pageerror` 或 React ErrorBoundary。
- 下载与导出链路满足当前支持边界：CSV、Markdown、JSON、XLSX 为真实输出；PDF、Word、XMind 保持 unsupported 或 HTML/Markdown 替代，不返回假文件。
- R31 deferred / unsupported 边界仍然成立：PostgreSQL/pgvector、Celery/Redis、MinIO/S3、真实密钥加密存储、Alembic 未实施。

## 核心证据

- 后端编译：`python -m compileall backend/aitest_platform` 通过。
- 后端全量：`cd backend; python -m pytest -q` 通过。
- 重点合同回归：在独立 `AITEST_DATABASE_PATH` 下执行 `test_round27...` 到 `test_round31...` 组合通过，避免默认 SQLite 历史数据干扰。
- 前端构建：`npm run build` 通过；仅有 Vite chunk size warning。
- 接口证据：
  - `/api/v2/system/schema-status` 200
  - `/api/v2/system/runtime-dependencies` 200
  - `/api/v2/system/backup-status` 200
  - `/api/v2/system/storage-summary` 200
  - `/api/v2/system/infra-status` 200
  - `/api/v2/system/cleanup` dry-run 200，`mode=dry_run`
  - `/api/v2/test-cases/export?format=pdf` 返回结构化 `415`，无假文件字段
- 浏览器证据：使用 Python Playwright + system Chrome；因本机 `8000` 被外部 PID `4588` 占用，本轮验收使用 `8001` 后端和 `VITE_API_BASE_URL=http://127.0.0.1:8001/api/v2` 前端。
  - `测试用例库` 页面可见 `CSV`、`Markdown`、`JSON`、`XLSX`
  - `用例执行` 页面可见 `用例执行`
  - `接口测试` 页面可见 `接口测试中心`
  - `自动化中心` 页面可见 `自动化中心`
  - `性能测试` 页面可见 `性能测试`
  - `测试报告` 页面可见 `测试报告中心`
  - `系统设置` 页面可见 `CLEANUP`、`后端存储占用`
  - `console.error=0`，`pageerror=0`

## 安全与边界

- secrets 扫描未发现真实 API key、token、cookie、凭证泄露；命中的 fake secret 仅存在于测试文件和少量说明文档中。
- 导出内容保持递归脱敏，XLSX/CSV 公式注入已中和。
- 自动化和性能 artifact ZIP 对越界文件写入 skipped metadata，不打包越界内容。
- R29 真实 cleanup 未执行；仅验证了 dry-run 和确认门，因为 dry-run 显示会影响 849 个 artifact 文件。
- R31 `infra-status` 仅返回安全摘要，不泄露数据库绝对路径、host、用户名、密码或库名。

## 未实施边界

- PostgreSQL / pgvector：deferred / unsupported unless explicitly approved
- Celery / Redis：deferred / unsupported unless explicitly approved
- MinIO / S3：deferred / unsupported unless explicitly approved
- 真实密钥加密存储：deferred / unsupported unless explicitly approved
- Alembic 正式迁移链：deferred / unsupported unless explicitly approved
- PDF / Word / XMind 真实服务端生成：未实施，当前走 unsupported 或 HTML/Markdown 替代
- docx/pdf/xlsx/xmind 深度导入解析：未实施，当前只建立硬边界
- 真实 JMeter / 真实外部 LLM / 分布式异步任务：未纳入第二轮交付

## 文档修正

- 已修正 R31 文档中的事实错误：R31 并非“只改文档”，实际新增了只读 `infra-status` 接口和 `test_round31_infra_decisions.py`，但未新增生产依赖，也未实施生产基础设施。

