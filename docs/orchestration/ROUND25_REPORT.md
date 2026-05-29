# Round 25 Report

## 名称
- R25：接口测试增强。

## 范围
- 后端补齐 OpenAPI YAML 轻量解析、HAR 基础解析、debug `save_as_case` 保存为 `ApiTestCase`、API runtime context 统一变量/header 优先级、scenario `data_mappings.extract` 增强、Mock 服务基础能力，以及受控 pre/post script allowlist DSL。
- 前端 `src/pages/ApiTesting.jsx` 增加 JSON/YAML/HAR 导入面板、真实 debug 表单、保存为接口用例、环境变量/运行覆盖、场景变量映射、Mock 服务 UI、pre/post script UI。
- QA 覆盖 YAML/HAR、debug save、变量优先级、scenario mapping、mock、allowlist/danger script。

## 实现
- 新增后端服务：
  - `backend/aitest_platform/services/api_runtime_context.py`
  - `backend/aitest_platform/services/api_mock_service.py`
  - `backend/aitest_platform/services/api_script_runner.py`
- 增强后端文件：
  - `backend/aitest_platform/services/api_importer.py`
  - `backend/aitest_platform/services/api_runner.py`
  - `backend/aitest_platform/services/api_scenario_runner.py`
  - `backend/aitest_platform/api/router.py`
- OpenAPI YAML 解析保持轻量实现，不新增 `PyYAML` 生产依赖。
- HAR 解析支持基础 request 提取，用于导入接口资产。
- debug 链路支持 `save_as_case`，可将调试请求保存为接口用例。
- API runtime context 统一处理环境变量、运行覆盖和 header 优先级，供 debug、case execute、scenario runner 复用。
- scenario `data_mappings.extract` 增强变量提取和传递能力。
- Mock 服务提供本地平台基础 mock 能力，不作为完整代理网关。
- pre/post script 使用受控 allowlist DSL，避免执行任意代码。

## 前端
- `src/pages/ApiTesting.jsx` 新增 JSON/YAML/HAR 导入面板。
- debug 表单改为真实请求调试入口，并支持保存为接口用例。
- 增加环境变量、运行覆盖、场景变量映射配置入口。
- 增加 Mock 服务 UI。
- 增加 pre/post script UI，与后端 allowlist DSL 对齐。

## QA
- 新增 `backend/tests/test_round25_api_testing_enhancement.py`。
- 覆盖 OpenAPI YAML/HAR 导入、debug save、变量优先级、scenario mapping、Mock 服务、allowlist script 与 danger script 拒绝。

## 验证
- `cd backend; python -m compileall aitest_platform`：passed，exit code 0。
- `cd backend; python -m pytest tests/test_round5_api_runner.py tests/test_round6_execution_runners.py tests/test_round7_import_schedule.py tests/test_round25_api_testing_enhancement.py -q`：passed，exit code 0，仅 FastAPI `HTTP_422_UNPROCESSABLE_ENTITY` deprecation warning。
- `cd backend; python -m pytest -q`：完整后端回归 passed，exit code 0，仅 FastAPI deprecation warning。
- 根目录 `npm run build`：passed，exit code 0，仅 Vite chunk > 500 kB warning。
- API 冒烟使用临时 SQLite 且已删除：OpenAPI YAML import imported=1，path `/r25/smoke/users`，expected status 206；HAR import imported=1，path `/r25/smoke/orders`，expected status 202；Mock create/list/dispatch 命中 matched=true，status 207；debug save_as_case status 200，saved_case_id=3。
- 浏览器冒烟：`http://127.0.0.1:3000/` 进入 ApiTesting/workbench，R25 UI 关键词可见 5 个：OpenAPI YAML、HAR、环境变量、本次运行覆盖、Mock 服务；console.error=0，pageerror=0。
- 进程和临时 DB 已清理，8000/3000 无监听。

## 残余风险
- YAML 为轻量解析，不覆盖完整 YAML 规范。
- 脚本能力为 allowlist DSL，不支持任意代码执行。
- Mock 服务是本地平台基础 mock，不是完整代理网关。
- Vite 仍保留 chunk > 500 kB warning。
- 浏览器只做轻量加载/可见性/console smoke，深层 UI 写操作主要由 API 冒烟覆盖。

## 下一步
- 进入 R26：自动化中心增强。
