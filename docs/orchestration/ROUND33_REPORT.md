# R33 二进制文档导入与正式导出报告

## 轮次定位

R33 是对第二轮后续边界的定向补强，不涉及 PostgreSQL、Celery、MinIO、Alembic 或真实密钥托管等生产基础设施决策项。本轮只收口两项能力：

- `PDF / DOCX / XMind` 真实服务端导出
- `docx / pdf / xlsx / xmind` 深度导入解析

## 实现结果

- 后端新增 `office_formats.py`，以 stdlib 方式实现：
  - `DOCX` 最小 OOXML 导出与解析
  - `PDF` 最小文本导出与文本型内容提取
  - `XMind` 最小 zip/content.json 导出与解析
  - `XLSX` 深度导入解析
- 导出链路已覆盖：
  - `test-cases / defects / reports / performance`
  - `requirement-documents / requirement-items`
- 导入链路已覆盖：
  - `requirement-documents`
  - `api-test-libs/{id}/import-documents`
  - `api-test-libs/{id}/apis/import`
- 旧 `.doc` 和泛化 `binary` 仍保持 unsupported，不假装解析成功。

## 前端接入

- `TestCases`：PDF / Word / XMind 不再提示未开放，改为真实下载。
- `Reports` / `Performance`：PDF / Word 改为真实下载或真实错误。
- `Requirements`：新增真实“导出需求”菜单，支持 `Markdown / JSON / PDF / DOCX / XMind`。
- `Requirements` / `ApiTesting`：支持文件选择后读取 `content_base64` 并提交 `docx / pdf / xlsx / xmind` 导入请求。
- 统一下载继续走 `apiDownload` / `downloadExportedFile`，不返回假成功。

## 验证

- `python -m compileall backend/aitest_platform`：通过
- `cd backend; python -m pytest tests/test_round30_file_export_formats.py -q`：通过
- `cd backend; python -m pytest tests/test_round28_report_center_enhancement.py tests/test_round11_exports.py tests/test_round10_reporting.py -q`：通过
- `cd backend; python -m pytest -q`：通过
- `npm run build`：通过

### Live API smoke

- 需求导入：
  - `docx`：create / parse / extract 200
  - `xlsx`：create / parse / extract 200
  - `xmind`：create / parse / extract 200
- 需求导出：
  - `pdf / docx / xmind`：200，返回真实 `content_base64`
- API 导入：
  - `docx`：200，能落 `apis` 与 `test_cases`
  - `xmind`：200，能落 `apis` 与 `test_cases`

### 浏览器烟测

- `console.error=0`
- `pageerror=0`
- `TestCases` 可见 `CSV / Markdown / JSON / XLSX / PDF / Word / XMind`
- `Requirements` 已接真实导出逻辑与二进制文件导入
- `ApiTesting` 已接真实二进制文件导入
- `Reports` / `Performance` 已接真实 PDF / Word 下载链路

## 安全边界

- 导出内容保持递归脱敏。
- `XLSX / CSV` 继续保留公式注入中和。
- 二进制解析仍走受控路径，不因为“支持了格式”就放宽脱敏或路径校验。
- 对空白或文本不足的 PDF，不再一律 unsupported；需求导入会给出 OCR/文本不足提示，API 导入维持结构化失败，不伪成功。

## 仍未实施

- PostgreSQL / pgvector
- Celery / Redis
- MinIO / S3
- 真实密钥加密存储
- Alembic 正式迁移链
- 真实对象存储和生产级异步队列

