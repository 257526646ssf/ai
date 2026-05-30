# R31 生产基础设施决策门报告

## 轮次定位

R31 是生产基础设施决策门，不是生产依赖实施轮次。本轮仅更新文档和决策口径，未新增代码、测试、数据库迁移、运行时服务或生产依赖。

## 决策结论

- R32 总验收继续以 SQLite 本地优先作为支持目标。
- 当前默认数据库仍为 `backend/data/aitest.sqlite3`。
- 当前 artifacts 仍默认使用本地目录 `backend/data/artifacts/`。
- PostgreSQL/pgvector、Celery/Redis、MinIO/S3、真实密钥加密存储、Alembic 均为 deferred / unsupported unless explicitly approved。
- 任何 deferred 项进入实施前，必须先补独立技术方案、依赖变更说明、迁移/回滚策略、验证命令和安全边界。

## 保护性状态

- 未把未实施的生产依赖写成已完成能力。
- 未写入 secrets、token、cookie、API key、私钥或真实凭证。
- 未改变当前本地运行方式。
- 未修改代码或测试。
- 未执行 commit 或 push。

## 验证

- 文档一致性检查：R31 状态已同步到 `DECISIONS.md`、`STATUS.md`、`HANDOFF.md`、`ACCEPTANCE.md`、`SECOND_ROUND_ROADMAP.md` 和 `backend/README.md`。
- 格式检查：`git diff --check` 通过；仅出现 Git 行尾转换提示，无 whitespace error。
- 本轮不运行后端测试、前端构建或浏览器烟测，原因是 R31 不包含代码、测试或运行时行为改动。

## 风险

- SQLite 本地优先仍不等同生产级多用户数据库能力。
- 本地 artifacts 仍不提供对象存储的远程共享、生命周期管理和预签名下载能力。
- 当前密钥策略仍是环境变量/运行时传入与脱敏，不支持平台内真实密钥加密托管。
- 当前 schema 状态自检不等同正式 Alembic 迁移链。
- 后续如直接引入 deferred 项而不先过方案评审，可能导致部署复杂度、数据迁移风险和安全边界不清晰。

## R32 前证据缺口

- R32 需要在 SQLite 本地优先模式下重新跑完整后端回归。
- R32 需要重新跑前端构建。
- R32 需要覆盖核心浏览器流程和真实下载链路。
- R32 需要执行 secrets 扫描或等价的敏感信息检查。
- R32 需要核对最终文档是否仍未把 deferred 生产依赖写成已实施能力。
- R32 需要确认当前分支和远程状态，但不得在未获授权时 commit/push。
