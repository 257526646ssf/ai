# Round 13 Report：前后端第一批真实集成

## 完成内容
- 新增 `src/lib/api.js`，提供 `/api/v2` base URL、统一响应解包、超时取消、文本下载工具。
- 后端 `main.py` 增加本地开发 CORS，并修复统一响应复用旧 `Content-Length` 导致 Uvicorn 报错的问题。
- Dashboard 已优先加载后端默认项目、项目大盘和最近活动，失败时保留演示数据降级。
- Reports 已接入后端报告列表、综合报告生成、Markdown/HTML/JSON 下载、轻量结论生成/归档。
- Settings 已接入 schema-status、runtime settings preference、system backup。
- 修复 `TiltCard` 在真实交互控件上触发 3D hit-test 不稳定的问题；设置页快照动作卡改为普通 `theme-card`，保留视觉但确保按钮可点击。

## 验证结果
- `npm run build`：通过，Vite 仅提示 chunk size warning。
- `cd backend; python -m pytest tests/test_round13_frontend_integration.py -q`：3 个用例通过。
- `cd backend; python -m pytest -q`：全量通过，保留 FastAPI 依赖 deprecation warnings。
- 浏览器验证：
  - Dashboard 显示后端连接状态和项目大盘数据，无 console error。
  - Reports 可从后端读取报告，生成综合报告，进入详情并下载 HTML。
  - Settings 可读取 schema 状态，保存 runtime settings，并创建后端备份快照。

## 主线程评分
- 完成度：93/100。
- 接受状态：接受，进入下一轮可继续扩大页面集成范围。

## 残余风险
- 前端项目仍有大量页面使用 mock 数据，下一轮应继续接 Requirements、TestCases、Execution、ApiTesting。
- Reports 详情页主体内容仍有静态展示块，本轮只把列表、生成、下载、结论主链接入后端。
- 默认项目来源目前是 `GET /projects?page=1&pageSize=1`，后续应接正式项目选择上下文。
- chunk size warning 未处理，属于构建优化项，不影响本轮功能验收。
