# Round 22 Report

## 名称
- R22：需求库解析与确认闭环。

## 范围
- 后端增强 TXT/Markdown 需求文档解析、需求项确认闭环和需求大脑摘要能力。
- 前端 Requirements 页面接入解析块、source anchors、需求项编辑确认、暂不入库、拆分、合并、粒度质检、需求大脑和追溯刷新。
- 补齐 R22 定向契约测试、回归验证、前端构建和 Headless Chrome CDP 烟测证据。

## 实现
- 后端实现 TXT/Markdown 多 block 解析，重 parse 会替换旧 blocks。
- fallback extract 基于 blocks 生成多条可追溯需求项，保留 source anchors / source_refs。
- split / merge / shelve / quality-check / brain analyze / get / traceability refresh 均接入 DB 化闭环。
- 闭环响应做脱敏处理，不回显 token、cookie、Authorization、secret。
- 前端 Requirements 页面展示解析块和 source anchors。
- 需求项编辑保存、确认、暂不入库、拆分、合并、粒度质检、需求大脑、追溯刷新已接后端。
- 前端支持多选合并。
- brain / source_refs 等返回形状已归一化，修复浏览器烟测中 `source_refs.slice is not a function` 崩溃。

## 测试
- 新增 `backend/tests/test_round22_requirement_closure.py`。
- 覆盖 parse / extract / edit / confirm / shelve / split / merge / quality / brain / traceability / redaction。

## 验证
- `python -m compileall backend\aitest_platform`：通过。
- `python -m pytest backend\tests\test_round22_requirement_closure.py -q`：7 passed。
- `python -m pytest backend\tests\test_p0_acceptance.py backend\tests\test_round4_main_chain_llm.py backend\tests\test_round14_requirement_testcase_integration.py -q`：17 passed。
- `cd backend; python -m pytest -q`：全量通过。
- `npm run build`：通过，仅 Vite chunk size warning。
- Headless Chrome CDP 烟测通过：R22 专用项目进入需求库工作台，source anchors 可见，合并/质检/追溯/暂不入库/拆分按钮可见，点击质检和需求大脑结果可见，`window.__r22Errors` 为空。

## 残余风险
- 解析仍为规则化 TXT/Markdown，不覆盖 docx/pdf/xlsx 深解析。
- 真实 LLM 默认关闭，需求大脑是 DB deterministic 摘要。
- split/merge lineage 用状态和响应表达，未新增正式血缘表。
- 浏览器烟测使用本地临时 smoke 数据。

## 下一步
- 进入 R23：用例评审与质量规则。
