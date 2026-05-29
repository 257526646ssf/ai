# Backend V1 Round 1 Report

## 交付摘要
- 新增 `backend/` 后端工程，提供 FastAPI `/api/v2` API。
- 新增 SQLite + SQLAlchemy 本地数据层，默认数据库为 `backend/data/aitest.sqlite3`。
- 建立项目、需求文档、需求项、测试点、测试用例、执行、缺陷、报告、备份的 P0 主链。
- 保留接口测试、自动化、性能、LLM 配置等 P1 占位入口，便于前端后续逐步替换 mock。
- 前端视觉风格未重构。

## 关键文件
- `backend/aitest_platform/main.py`
- `backend/aitest_platform/api/router.py`
- `backend/aitest_platform/models.py`
- `backend/aitest_platform/repositories.py`
- `backend/aitest_platform/db/session.py`
- `backend/tests/test_p0_acceptance.py`
- `backend/README.md`

## 主线程发现并修复的问题
- `POST /api/v2/reports/comprehensive` 原先返回嵌套对象，已改为顶层 report 资源对象，满足创建接口契约。
- P0 切到 SQLite 后，P1 占位接口仍检查内存 store 中的 project，导致 DB project 无法创建 api-test-lib/auto-project/perf-plan；已增加薄适配。
- `DELETE /api/v2/requirement-items/{itemId}` 原先打到内存 store，已改为数字 id 走 SQLite soft delete。

## 验证结果
- 编译：通过。
- 后端 contract tests：`6 passed, 2 warnings`。
- OpenAPI：105 个 `/api/v2` path。
- 手工 smoke：P0 主链与 P1 入口均通过。

## 下一轮建议
- 将 P1 模块资源从内存 store 逐步迁移到 SQLite。
- 接入真实 LLM 配置读取、调用审计、失败降级和 token 用量统计。
- 建立前端 API client，把当前 mock 数据按页面分批替换为 `/api/v2`。
- 统一 Python 依赖版本，移除 FastAPI/Starlette 兼容补丁。
