# Round 12 Plan - 系统状态与回收站收口

## 本轮目标
- 在不新增生产依赖、不改变前端视觉风格的前提下，补齐系统类本地状态能力。
- 把回收站从内存占位推进为可查看、可恢复数据库软删除对象。
- 用现有 SQLite `round2_resource` 保存用户偏好和最近活动。

## 范围
- DB 回收站
  - `GET /system/recycle-bin` 返回软删除的 Project、RequirementLib、RequirementItem、TestCase、ApiTestLib、ApiEndpoint、ApiTestCase、ApiEnvironment、ApiSchedule、AutoProject、AutoCaseFile、PerfPlan 等对象。
  - `POST /system/recycle-bin/{id}/restore` 支持恢复 `type:id` 形式的回收站对象，并保留旧内存 store 兼容。
- 用户偏好
  - 支持保存、读取、列表化用户偏好。
  - 使用 `round2_resource` 持久化，不新增表。
- 最近活动
  - 支持记录和读取最近活动，用于继续上次位置。
  - 使用 `round2_resource` 持久化，不新增表。

## 非目标
- 不实现清空所有数据/恢复出厂设置。
- 不实现组织级用户系统。
- 不引入新表迁移或新依赖。

## 验收标准
- Round12 合同测试通过。
- 全量后端测试通过。
- 系统状态响应不泄露 `api_key`、`token`、`cookie`、`password`、`secret`、`authorization`、`git_auth` 等敏感字段。
