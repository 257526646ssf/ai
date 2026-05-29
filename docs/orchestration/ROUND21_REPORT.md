# Round 21 Report

## 名称
- R21：AI 助手与 Prompt 闭环。

## 范围
- 后端补齐 Prompt 模板 CRUD、测试渲染、AI 助手上下文和结构化草稿接口。
- 前端增强 AI 助手常用 Prompt、最近操作、整条回复复制和三类草稿生成入口。
- LLM 配置页新增 Prompt 模板管理面板，支持自定义模板全流程管理。

## 实现
- 后端新增/增强：`POST /api/v2/prompt-templates`、`DELETE /api/v2/prompt-templates/{templateId}`、`POST /api/v2/prompt-templates/{templateId}/test`、`GET /api/v2/assistant/context`、`POST /api/v2/assistant/drafts`。
- `POST /api/v2/prompt-templates/{templateId}/test` 兼容 `variables` 嵌套与 flat payload。
- `/chat` fallback 会追加 assistant context 摘要。
- 所有响应不调用真实 provider 且做敏感信息脱敏。
- 前端 AI 助手可复制整条回复、读取/保存常用 Prompt、展示最近操作、把最近操作带入输入框，并生成测试点/澄清问题/缺陷备注草稿。
- LLM 配置页新增 Prompt 模板管理面板，支持加载/新增/编辑/测试渲染/删除自定义模板；内置模板不可删除。

## QA 修复
- 前端 `/assistant/drafts` 已发送 `message: prompt`。
- 最近操作 normalize 已兼容 `recent_activities.list` 与 `operation_logs.list`。

## 验证
- `python -m compileall backend\aitest_platform`：通过。
- `python -m pytest backend\tests\test_round21_ai_prompt.py -q`：4 passed。
- `python -m pytest backend\tests\test_round19_dashboard_chat.py backend\tests\test_round20_dashboard_topbar.py -q`：6 passed。
- `cd backend; python -m pytest -q`：通过。
- `npm run build`：通过，仅 Vite chunk size warning。
- Headless Chrome CDP 烟测通过：确认 LLM 配置页 Prompt 面板、AI 助手常用 Prompt/最近操作/三类草稿按钮、生成测试点草稿，`window.__r21Errors` 为空。

## 残余风险
- 真实 LLM 仍默认关闭。
- Prompt 模板只是基础 CRUD/测试渲染，尚未做收藏排序/团队级模板权限。
- 最近操作/operation logs 是摘要上下文，不是全量审计回放。
- 结构化草稿为 deterministic rules fallback，不等同真实 LLM 资产生成。

## 下一步
- 进入 R22：需求库解析与确认闭环。
