# Round 13 Plan：前后端第一批真实集成

## 目标
- 在不改变前端视觉风格的前提下，把已完成的后端能力接入前端核心页面。
- 优先接入 Dashboard、Reports、SettingsPage 三个页面，验证浏览器真实可用。
- 修复真实浏览器暴露的后端响应/CORS/交互问题。

## 范围
- P0：新增前端 `fetch` API client，统一解包 `/api/v2` 响应。
- P0：后端允许本地 Vite 前端跨域访问。
- P0：Dashboard 读取默认项目、项目大盘和最近活动。
- P0：Reports 读取后端报告、生成综合报告、下载报告、生成/归档轻量结论。
- P0：Settings 读取 schema 状态，持久化运行参数，调用后端备份。
- P0：补 Round 13 contract tests，覆盖 CORS、统一响应 `Content-Length`、前端依赖的系统契约。

## 非目标
- 不重做前端视觉风格。
- 不新增生产依赖。
- 不实现 PDF/Word/Excel `.xlsx` 导出。
- 不接入 Celery/Redis、对象存储、正式 Alembic。

## 验收标准
- `npm run build` 通过。
- `cd backend; python -m pytest tests/test_round13_frontend_integration.py -q` 通过。
- `cd backend; python -m pytest -q` 通过。
- 浏览器验证 Dashboard、Reports、Settings 无 console error。
- 浏览器验证 Reports 可生成并下载后端报告，Settings 可保存配置并创建备份。
