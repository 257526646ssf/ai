# Round 14 Plan：Requirements / TestCases 前后端集成

## 目标
- 继续保持现有前端视觉风格，只替换高价值 mock 链路。
- Requirements 页面接入后端项目、需求库、需求文档、需求项和测试点生成主链。
- TestCases 页面接入后端需求项测试用例列表、批量生成和导出。
- 后端补齐前端所需的只读聚合接口，避免前端绕远路拼装数据。

## 范围
- 后端新增：
  - `GET /api/v2/requirement-libs/{libId}/documents`
  - `GET /api/v2/requirement-libs/{libId}/requirement-items`
  - `GET /api/v2/projects/{projectId}/test-cases`
- 前端新增：
  - Requirements 读取后端需求库，支持创建需求库、导入并解析需求文档、生成测试点。
  - TestCases 读取后端测试用例，支持按当前需求项批量生成，支持 CSV / Markdown 导出。
- 验证：
  - Round14 后端契约测试。
  - 后端全量测试。
  - 前端生产构建。
  - 真实浏览器主流程 smoke。

## 非目标
- 不重做前端视觉体系。
- 不新增 Excel `.xlsx` / PDF / Word 导出依赖。
- 不接入 Celery/Redis 或正式 Alembic。
- 不在文档、代码、日志中写入真实 LLM key。
