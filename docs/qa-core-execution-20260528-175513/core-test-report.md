# Core Test Report

- Base URL: `http://127.0.0.1:3001`
- Run ID: `20260528-175513`
- Passed: `9`
- Failed: `1`
- Console errors: `2`
- Failed requests: `0`

| Case | Status | Details | Screenshot |
| --- | --- | --- | --- |
| TC01 Root document loads | passed | Root document responds with HTTP 200. | `screenshots/tc01_http_root.png` |
| TC02 React boot smoke | passed | React app mounted with sidebar and main content. | `screenshots/tc02_app_boot.png` |
| TC03 Sidebar navigation | passed | Visited 10 sidebar destinations. Header samples: ['平台首页\n/\nDashboard\n风格选择: 01 基础雅致版\nLLM 状态\n已连接\nOpenAI GPT-4o\n张明\n测试负责人', '需求库\n/\n需求库\n风格选择: 01 基础雅致版\nLLM 状态\n已连接\nOpenAI GPT-4o\n张明\n测试负责人', '测试用例库\n/\n测试用例库\n风格选择: 01 基础雅致版\nLLM 状态\n已连接\nOpenAI GPT-4o\n张明\n测试负责人'] | `screenshots/tc03_navigation.png` |
| TC04 Theme dropdown | passed | Theme dropdown switches dashboard theme to dark. | `screenshots/tc04_theme_switch.png` |
| TC05 Requirement upload modal | passed | Upload requirement modal opens and closes. | `screenshots/tc05_modal_upload.png` |
| TC06 AI case generation mutation | passed | AI generation modal inserts generated test cases into TestCases state. | `screenshots/tc06_generate_cases.png` |
| TC07 API request simulation | passed | API workbench run shows the mocked response body. | `screenshots/tc07_api_response.png` |
| TC08 Execution simulation | passed | Execution modal completes and publishes execution-finished event. | `screenshots/tc08_execution_flow.png` |
| TC09 AI assistant XSS probe | failed | User message HTML executed through dangerouslySetInnerHTML | `screenshots/tc09.png` |
| TC10 Mobile horizontal overflow | passed | Mobile layout stays within acceptable width: {'scrollWidth': 390, 'innerWidth': 390} | `screenshots/tc10_mobile_overflow.png` |

## Console Errors

- error: Invalid DOM property `%s`. Did you mean `%s`? paint-order paintOrder
- error: Invalid DOM property `%s`. Did you mean `%s`? paint-order paintOrder