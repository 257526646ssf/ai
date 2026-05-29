# Round 26 Report

## 名称
- R26：自动化中心增强。

## 范围
- 后端补齐候选筛选/选择、文件 CRUD、执行详情、artifact 列表与预览路由。
- `generate-cases` 支持候选选择，Playwright 模板增强。
- 前端 `src/pages/Automation.jsx` 增加候选筛选、case file 在线编辑/dirty/save/reset、Playwright 模板配置、按 `case_file_ids` 执行、执行详情日志/evidence、artifact preview。
- QA 覆盖候选筛选/过滤、候选选择影响生成、Playwright 模板增强、在线文件查看/保存/非法路径、按文件执行与详情、artifact 列表/预览、artifact ZIP 回归安全。

## 实现
- 新增后端服务：
  - `backend/aitest_platform/services/auto_center.py`
- 增强后端文件：
  - `backend/aitest_platform/api/router.py`
  - `backend/aitest_platform/services/exporting.py`
- `generate-cases` 支持候选选择，生成链路可以按用户选定候选收敛用例来源。
- 自动化文件支持受控 CRUD，非法路径会被拒绝，避免越界读取或写入。
- 执行详情补齐日志、evidence、artifact 列表与预览入口。
- Playwright 模板增强，便于从自动化中心生成更贴近项目配置的脚手架。
- `exporting.py` 对文本类 artifact ZIP 内容做脱敏，保留 artifact ZIP 回归安全。

## 前端
- `src/pages/Automation.jsx` 新增候选筛选与候选选择交互。
- 自动化 case file 支持在线查看、编辑、dirty 状态提示、保存和 reset。
- 新增 Playwright 模板配置入口。
- 执行入口支持按 `case_file_ids` 选择文件执行。
- 执行详情展示日志与 evidence。
- artifact preview 支持文本类预览；trace/zip 不展开执行。

## QA
- 新增 `backend/tests/test_round26_automation_center.py`。
- 覆盖候选筛选/过滤、候选选择影响生成、Playwright 模板增强、在线文件查看/保存/非法路径、按文件执行与详情、artifact 列表/预览、artifact ZIP 回归安全。

## 验证
- `python -m pytest backend/tests/test_round26_automation_center.py -q`：7 passed。
- `cd backend; python -m compileall aitest_platform`：passed，exit code 0。
- R26 组合回归：`python -m pytest tests/test_round6_execution_runners.py tests/test_round8_artifacts.py tests/test_round11_exports.py tests/test_round13_frontend_integration.py tests/test_round25_api_testing_enhancement.py tests/test_round26_automation_center.py -q` passed，40 passed，仅 FastAPI deprecation warning。
- Full backend：`python -m pytest -q` passed，exit code 0，仅 FastAPI deprecation warning。
- Root `npm run build`：passed，仅 Vite chunk >500k warning。
- API smoke passed：候选筛选/过滤、文件保存、artifact preview 均返回合理结果。
- 浏览器最终复验 passed：Automation 页面打开；console.error=0；pageerror=0；`/case-files` 请求数 0；`/case-files` 404 为 0；`/auto-projects/693/files?page=1&pageSize=200` 返回 200；R26 DOM 可见关键词 8/8：候选筛选、在线文件、保存、Playwright、trace、Artifacts、预览、执行日志。
- 进程清理：8000/3000 已停止并复查无监听。

## 残余风险
- Vite chunk warning。
- Playwright 真实执行依赖本机环境。
- trace/zip 预览不展开执行。
- 浏览器深层写操作主要由 API smoke 和后端契约测试覆盖。

## 下一步
- 进入 R27：性能测试增强。
