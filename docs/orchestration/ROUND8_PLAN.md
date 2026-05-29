# Backend V1 Round 8 Plan

## 目标
补强执行证据链路，让自动化和性能执行结果能稳定回溯到日志、截图、trace、JTL、HTML 报告等 artifacts。继续不改前端视觉、不新增生产依赖、不写入真实密钥。

## 范围
- `services/auto_runner.py`
- `services/perf_runner.py`
- `POST /api/v2/auto-projects/{autoProjectId}/execute`
- `POST /api/v2/perf-plans/{planId}/execute`

## 设计原则
- 使用 Python 标准库持久化 artifacts 到 `backend/data/artifacts/...`。
- 自动化 runner 采集测试运行后产生的 `png/jpg/webp`、`trace.zip`、`mp4/webm`、`junit/xml`、`html`、runner log 等证据元数据。
- JMeter runner 持久化 `plan.jmx`、`result.jtl`、stdout/stderr，并在 payload 显式 `generate_html_report=true` 时尝试生成 JMeter HTML report。
- artifacts 中只返回相对安全的文件元数据和本地路径，不返回真实 secret；文件内容和日志摘要必须脱敏。
- 缺少证据文件时仍保留当前结构化结果，不得导致 500。
- 不引入 MinIO/S3；对象存储留作后续部署增强。

## Worker 分配
- auto_artifact_engineer_round8：负责自动化 runner artifacts 采集和路由结果兼容。
- perf_artifact_engineer_round8：负责 JMeter artifacts/JTL/HTML report 持久化。
- qa_artifact_engineer_round8：负责 Round 8 契约/安全测试。

## 验收
- `python -m compileall backend\aitest_platform`
- `cd backend; python -m pytest tests/test_round8_artifacts.py -q`
- `cd backend; python -m pytest -o addopts='' -q`

## 延后
- Playwright 原生启动器和 Midscene fallback。
- 对象存储 MinIO/S3。
- Celery/Redis 分布式异步执行。
- Alembic 正式迁移链路。
