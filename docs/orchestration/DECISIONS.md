# 决策记录

## 已确认
- D1：第一轮以后端为主，不重做前端视觉。
- D2：正式接口前缀使用 `/api/v2`。
- D3：本地优先模式先用 SQLite；数据模型保持可迁移到 PostgreSQL。
- D4：AI、LangGraph、Celery/Redis 在第一轮用可替换占位实现，避免阻塞主链 API。
- D5：前端现有 mock 页面暂不大改，后续通过 API client 逐步接入。

## 待验证
- V1 是否需要真实 OpenAI/兼容模型调用，还是先保留本地模拟。
- 是否要把 backend 作为独立 Python 包发布，还是随前端项目一起运行。

