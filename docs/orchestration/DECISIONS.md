# 决策记录

## 已确认
- D1：第一轮以后端为主，不重做前端视觉。
- D2：正式接口前缀使用 `/api/v2`。
- D3：本地优先模式先用 SQLite；PostgreSQL 仅保留后续评估空间，正式接入需单独批准。
- D4：AI、LangGraph、Celery/Redis 在第一轮用可替换占位实现，避免阻塞主链 API。
- D5：前端现有 mock 页面暂不大改，后续通过 API client 逐步接入。

## 待验证
- V1 是否需要真实 OpenAI/兼容模型调用，还是先保留本地模拟。
- 是否要把 backend 作为独立 Python 包发布，还是随前端项目一起运行。

## R31 生产基础设施决策矩阵

R31 是生产基础设施决策门，不是生产依赖实施轮次。本轮未新增 PostgreSQL、pgvector、Celery、Redis、MinIO、S3、Alembic 或密钥加密存储相关生产依赖，也未改变当前 SQLite + 本地 artifacts 的默认运行方式。

| 决策项 | R31 状态 | 原因 | 当前边界 | 触发条件 | 迁移准备 |
|---|---|---|---|---|---|
| SQLite 本地优先 | R32 支持目标 | 当前功能、测试和本地验收都围绕单机本地运行闭环；继续保持最低部署成本和离线可测性。 | 默认数据库仍为 `backend/data/aitest.sqlite3`；R32 总验收应覆盖当前 SQLite 路径下的核心流程、导出和本地 artifacts。 | R32 全量验收、打包交付或本地试用需要稳定复现时继续使用 SQLite。 | 保持 SQLAlchemy 模型边界；避免写入 PostgreSQL 专属 SQL；记录 schema 状态和备份/恢复口径。 |
| PostgreSQL | deferred / unsupported unless explicitly approved | 会引入部署、连接池、数据迁移、备份和环境配置成本；当前没有生产并发、远程部署或多用户数据隔离证据要求。 | 当前不提供 PostgreSQL 运行保证；不在 README 或状态文档中宣称已支持生产 PostgreSQL。 | 明确要求服务化部署、多用户并发、远程数据库、备份恢复 SLA 或 SQLite 已无法满足数据量/并发时。 | 先补数据库 URL 配置矩阵、迁移脚本方案、SQLite 到 PostgreSQL 数据迁移演练、回滚策略和连接池超时策略。 |
| pgvector | deferred / unsupported unless explicitly approved | 当前搜索和摘要仍是本地规则/SQLite 口径；尚未确认向量检索产品需求、embedding provider、索引规模和隐私边界。 | 不提供向量索引、embedding 存储或相似度搜索生产能力。 | 明确需要语义检索、需求/用例相似度召回、知识库 RAG，并确认 embedding 模型与数据合规要求时。 | 先设计 embedding 表、索引更新策略、重新建索引流程、数据脱敏规则和离线 fallback。 |
| Celery/Redis | deferred / unsupported unless explicitly approved | 会改变任务执行拓扑，引入 worker 生命周期、队列幂等、重试、任务取消、结果一致性和 Redis 运维成本。 | 当前执行仍为本地同步/轻量 runner；不承诺分布式异步队列。 | 真实长任务、并发执行、后台定时任务、跨进程任务恢复或 UI 需要稳定异步进度时。 | 先定义任务状态机、幂等 key、超时/重试/取消策略、任务结果表、worker 健康检查和本地无 Redis fallback。 |
| MinIO/S3 | deferred / unsupported unless explicitly approved | 当前 artifacts 可落本地目录并已做路径边界；对象存储会引入 bucket、凭证、生命周期、下载签名和网络失败处理。 | 当前 artifacts 默认在 `backend/data/artifacts/`；不承诺对象存储上传、预签名下载或远程保留策略。 | artifacts 超出本地磁盘、需要多人共享、远程下载、生命周期清理或生产备份时。 | 先定义 storage adapter 接口、bucket/path 规则、对象元数据、上传失败补偿、清理策略和本地文件兼容层。 |
| 真实密钥加密存储 | deferred / unsupported unless explicitly approved | 当前安全边界是环境变量/运行时传入 + 响应脱敏；真实加密存储需要密钥来源、轮换、恢复、审计和误删处理。 | 不把真实 API key、token、cookie、Git 凭证写入代码、文档、日志或数据库明文；现有 `api_key_ref` 仅作为引用/掩码口径。 | 需要在平台内保存真实 provider key、团队共享凭证、审计凭证访问或多租户密钥隔离时。 | 先确认 KMS/本地 master key 来源、加密算法、轮换/撤销流程、备份恢复、审计日志和密钥引用 schema。 |
| Alembic 正式迁移 | deferred / unsupported unless explicitly approved | 当前 schema 主要由 SQLAlchemy metadata 和本地 schema-status 自检支撑；Alembic 会引入迁移目录、版本管理和升级/回滚流程。 | 当前不提供正式迁移链；不承诺跨版本自动升级生产库。 | 开始长期保留用户数据、接入 PostgreSQL、发布多版本安装包或需要可回滚 schema 变更时。 | 先建立 baseline revision、迁移命名规范、SQLite/PostgreSQL 双库演练、备份前置检查和 downgrade/失败恢复策略。 |

## R31 保护性结论

- R31 明确继续采用本地优先边界：SQLite + 本地 artifacts 是 R32 总验收的支持目标。
- PostgreSQL/pgvector、Celery/Redis、MinIO/S3、真实密钥加密存储、Alembic 均保持 deferred / unsupported unless explicitly approved。
- 后续如果批准任一 deferred 项，必须先补独立方案、依赖清单、迁移/回滚策略、验证命令和安全边界，再进入实施轮次。
