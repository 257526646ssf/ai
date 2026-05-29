# Round 14 Report：Requirements / TestCases 前后端集成

## 完成内容
- 后端新增需求库详情只读接口，可按需求库读取文档列表和需求项列表。
- 后端新增项目级测试用例列表接口，支持按需求库和需求项过滤。
- Requirements 页面接入后端项目和需求库，可新建需求库、导入演示需求文档、触发解析与需求项提取、为当前需求项生成测试点。
- TestCases 页面接入后端项目/需求库/需求项上下文，可读取真实测试用例、调用后端生成用例、导出 CSV / Markdown。
- 新增 Round14 契约测试，覆盖前端所需的新增接口与导出联动。
- 使用真实 Chrome headless 验证需求库和测试用例库主流程，保留截图证据。

## 验证结果
- `npm run build`：通过，Vite 仅提示 chunk size warning。
- `python -m pytest backend/tests/test_round14_requirement_testcase_integration.py -q`：2 个用例通过。
- `cd backend; python -m pytest -q`：全量通过，保留 2 个 FastAPI 依赖 deprecation warnings。
- OpenAPI `/api/v2` path 数：118。
- 浏览器 smoke：
  - Requirements：进入需求库页，新建需求库，导入需求文档，页面无 console error。
  - TestCases：进入测试用例库，批量生成后端测试用例，CSV 导出成功，页面无 console error。
  - 截图证据：
    - `docs/orchestration/artifacts/round14-requirements.png`
    - `docs/orchestration/artifacts/round14-testcases.png`

## 主线程评分
- 完成度：94/100。
- 接受状态：接受，进入下一轮可继续扩大页面集成范围。

## 残余风险
- Requirements / TestCases 仍保留部分演示型静态分析内容，核心 CRUD / 生成 / 导出主链已接后端。
- 当前项目上下文仍由前端自动取项目列表，不是正式用户选择器；持久库中历史测试项目较多时，后续应补一个全局当前项目状态。
- 测试用例导出当前按后端已有 Markdown / CSV / JSON 能力落地，未实现真实 `.xlsx`。
- Execution、ApiTesting、Automation、Performance、LlmConfig 仍需继续分批接入后端。
