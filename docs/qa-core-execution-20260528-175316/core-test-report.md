# Core Test Report

- Base URL: `http://127.0.0.1:3001`
- Run ID: `20260528-175316`
- Passed: `8`
- Failed: `2`
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
| TC07 API request simulation | failed | Mock API response was not shown on API page | `screenshots/tc07.png` |
| TC08 Execution simulation | passed | Execution modal completes and publishes execution-finished event. | `screenshots/tc08_execution_flow.png` |
| TC09 AI assistant XSS probe | failed | TimeoutError: Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("button[type='submit']")
    - locator resolved to <button type="submit" class="p-2 rounded-xl accent-btn shrink-0 cursor-pointer">…</button>
  - attempting click action
    2 × waiting for element to be visible, enabled and stable
      - element is not stable
    - retrying click action
    - waiting 20ms
    2 × waiting for element to be visible, enabled and stable
      - element is not stable
    - retrying click action
      - waiting 100ms
    58 × waiting for element to be visible, enabled and stable
       - element is visible, enabled and stable
       - scrolling into view if needed
       - done scrolling
       - <div class="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity duration-300"></div> from <div class="fixed inset-0 z-[999] flex items-center justify-center pointer-events-auto">…</div> subtree intercepts pointer events
     - retrying click action
       - waiting 500ms
 | `screenshots/tc09.png` |
| TC10 Mobile horizontal overflow | passed | Mobile layout stays within acceptable width: {'scrollWidth': 390, 'innerWidth': 390} | `screenshots/tc10_mobile_overflow.png` |

## Console Errors

- error: Invalid DOM property `%s`. Did you mean `%s`? paint-order paintOrder
- error: Invalid DOM property `%s`. Did you mean `%s`? paint-order paintOrder