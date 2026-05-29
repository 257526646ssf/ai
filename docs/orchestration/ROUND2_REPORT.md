# Backend V1 Round 2 Report

## 交付摘要
- 将接口测试、自动化、性能、报告模板、LLM 配置、Prompt 模板等第二轮资产接入 SQLite。
- 新增 Round 2 contract tests，覆盖持久化读回、安全脱敏、日志和搜索。
- 保持 `/api/v2` 路由兼容，OpenAPI path 数保持 105。
- 前端视觉和 `src/` 未改动。

## 关键文件
- `backend/aitest_platform/models.py`
- `backend/aitest_platform/repositories.py`
- `backend/aitest_platform/db/session.py`
- `backend/aitest_platform/api/router.py`
- `backend/tests/test_round2_persistence.py`
- `backend/README.md`
- `docs/orchestration/ACCEPTANCE.md`

## 主线程验收
- `python -m compileall backend\aitest_platform`：通过。
- `cd backend; python -m pytest`：`11 passed, 2 warnings`。
- OpenAPI `/api/v2` path 数：105。
- 手工 smoke：
  - API testing：project -> api lib -> imported endpoints -> api cases -> executions -> environment -> scenario -> schedule。
  - Automation：project -> auto project -> candidate screen -> framework -> case files -> execution -> events -> download metadata。
  - Performance：project -> perf plan -> structured plan -> JMX placeholder script -> result -> report -> quick test。
  - Config/system：report template、LLM config、Prompt template、operation logs、search。

## 已修复的问题
- API environment/scenario/schedule 不能读取 SQLite 创建的 API test lib。
- 自动化 `generate-cases` 不返回持久化 case file。
- `search` 搜不到 SQLite 中的第二轮 API test lib。
- LLM config 响应中可能暴露用户提交的 `api_key`。

## 残余风险
- 真实 LLM、真实外部 API 调试、真实 Playwright/JMeter 执行仍未接入。
- `auto-candidates/screen` 和 `perf/quick-tests` 采用轻量 `round2_resource` SQLite 表，而非专用 ORM 表。
- API key 目前仅做掩码/引用保存，未做真实加密。
- 现有 SQLite 兼容补列逻辑适合本地开发，正式迁移建议引入 Alembic 或等价迁移机制。
