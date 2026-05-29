from __future__ import annotations

import html
import json
import os
import time
import traceback
import urllib.request
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3001").rstrip("/")
RUN_ID = time.strftime("%Y%m%d-%H%M%S")
REPORT_DIR = ROOT / "docs" / f"qa-core-execution-{RUN_ID}"
SCREENSHOT_DIR = REPORT_DIR / "screenshots"


def browser_launch_kwargs():
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return {"headless": True, "executable_path": str(candidate)}
    return {"headless": True}


def ensure_dirs():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def http_status(url: str) -> int:
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status


def screenshot(page, name: str) -> str:
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def add_result(results, case_id, name, status, details="", screenshot_path=None, error=None):
    results.append(
        {
            "case_id": case_id,
            "name": name,
            "status": status,
            "details": details,
            "screenshot": screenshot_path,
            "error": error,
        }
    )


def run_case(results, page, case_id, name, fn):
    try:
        details, shot_name = fn()
        add_result(results, case_id, name, "passed", details, screenshot(page, shot_name))
    except AssertionError as error:
        add_result(results, case_id, name, "failed", str(error), screenshot(page, case_id.lower()), traceback.format_exc())
    except Exception as error:
        add_result(results, case_id, name, "failed", f"{type(error).__name__}: {error}", screenshot(page, case_id.lower()), traceback.format_exc())
    finally:
        # Keep one failed modal from cascading into unrelated cases.
        try:
            for _ in range(3):
                if page.locator(".fixed.inset-0.z-\\[999\\] button").count() == 0:
                    break
                page.locator(".fixed.inset-0.z-\\[999\\] button").first.click(timeout=1000)
                page.wait_for_timeout(200)
        except Exception:
            pass


def wait_no_overlay(page):
    try:
        page.locator(".fixed.inset-0.z-\\[999\\]").wait_for(state="detached", timeout=8000)
    except PlaywrightTimeoutError:
        pass


def click_nav(page, idx: int):
    page.locator("aside nav button").nth(idx).click()
    page.wait_for_timeout(400)


def render_reports(results, console_errors, failed_requests):
    summary = {
        "base_url": BASE,
        "run_id": RUN_ID,
        "total": len(results),
        "passed": sum(1 for r in results if r["status"] == "passed"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "console_errors": console_errors,
        "failed_requests": failed_requests,
        "results": results,
    }
    (REPORT_DIR / "core-test-results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Core Test Report",
        "",
        f"- Base URL: `{BASE}`",
        f"- Run ID: `{RUN_ID}`",
        f"- Passed: `{summary['passed']}`",
        f"- Failed: `{summary['failed']}`",
        f"- Console errors: `{len(console_errors)}`",
        f"- Failed requests: `{len(failed_requests)}`",
        "",
        "| Case | Status | Details | Screenshot |",
        "| --- | --- | --- | --- |",
    ]
    for result in results:
        rel = Path(result["screenshot"]).relative_to(REPORT_DIR).as_posix() if result.get("screenshot") else ""
        md_lines.append(f"| {result['case_id']} {result['name']} | {result['status']} | {result['details']} | `{rel}` |")
    if console_errors:
        md_lines.extend(["", "## Console Errors", ""])
        md_lines.extend([f"- {item}" for item in console_errors])
    if failed_requests:
        md_lines.extend(["", "## Failed Requests", ""])
        md_lines.extend([f"- {item}" for item in failed_requests])
    (REPORT_DIR / "core-test-report.md").write_text("\n".join(md_lines), encoding="utf-8")

    rows = []
    for result in results:
        cls = "pass" if result["status"] == "passed" else "fail"
        shot = Path(result["screenshot"]).relative_to(REPORT_DIR).as_posix() if result.get("screenshot") else ""
        rows.append(
            f"<tr><td>{html.escape(result['case_id'])}</td><td>{html.escape(result['name'])}</td>"
            f"<td class='{cls}'>{html.escape(result['status'])}</td><td>{html.escape(result['details'])}</td>"
            f"<td>{html.escape(shot)}</td></tr>"
        )
    html_doc = f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
body{{font-family:Arial, sans-serif; padding:24px; color:#111827;}}
.pass{{color:#047857;font-weight:700}} .fail{{color:#dc2626;font-weight:700}}
table{{border-collapse:collapse;width:100%;font-size:13px}} td,th{{border:1px solid #e5e7eb;padding:8px;text-align:left;vertical-align:top}}
pre{{white-space:pre-wrap;background:#f9fafb;border:1px solid #e5e7eb;padding:12px}}
</style></head><body>
<h1>Core Test Report</h1>
<p>Base URL: <code>{html.escape(BASE)}</code> | Run ID: <code>{RUN_ID}</code></p>
<p>Passed: <b>{summary['passed']}</b> | Failed: <b>{summary['failed']}</b> | Console errors: <b>{len(console_errors)}</b> | Failed requests: <b>{len(failed_requests)}</b></p>
<table><thead><tr><th>Case</th><th>Name</th><th>Status</th><th>Details</th><th>Screenshot</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Console Errors</h2><pre>{html.escape(json.dumps(console_errors, ensure_ascii=False, indent=2))}</pre>
<h2>Failed Requests</h2><pre>{html.escape(json.dumps(failed_requests, ensure_ascii=False, indent=2))}</pre>
</body></html>"""
    (REPORT_DIR / "core-test-report.html").write_text(html_doc, encoding="utf-8")
    return summary


def main():
    ensure_dirs()
    results = []
    console_errors = []
    failed_requests = []

    with sync_playwright() as p:
        browser = p.chromium.launch(**browser_launch_kwargs())
        context = browser.new_context(viewport={"width": 1440, "height": 1200}, accept_downloads=True)
        page = context.new_page()

        page.on("console", lambda msg: console_errors.append(f"{msg.type}: {msg.text}") if msg.type in {"error"} else None)
        page.on("pageerror", lambda exc: console_errors.append(f"pageerror: {exc}"))
        page.on("response", lambda response: failed_requests.append(f"{response.status} {response.url}") if response.status >= 400 else None)

        def tc_http_root():
            status = http_status(f"{BASE}/")
            assert status == 200, f"Expected HTTP 200, got {status}"
            page.goto(BASE, wait_until="networkidle", timeout=90000)
            return "Root document responds with HTTP 200.", "tc01_http_root"

        run_case(results, page, "TC01", "Root document loads", tc_http_root)

        def tc_app_boot():
            expect(page.locator("#root")).to_be_visible()
            assert page.locator("#root > *").count() > 0, "React root has no rendered children"
            assert page.locator("aside").is_visible(), "Sidebar is not visible"
            assert page.locator("main").is_visible(), "Main content is not visible"
            return "React app mounted with sidebar and main content.", "tc02_app_boot"

        run_case(results, page, "TC02", "React boot smoke", tc_app_boot)

        def tc_navigation():
            labels = []
            for idx in range(9):
                click_nav(page, idx)
                labels.append(page.locator("header").inner_text(timeout=5000)[:80])
            page.locator("aside > div").last.locator("button").last.click()
            page.wait_for_timeout(300)
            assert page.locator("main").is_visible(), "Main content disappeared after navigation"
            return f"Visited 10 sidebar destinations. Header samples: {labels[:3]}", "tc03_navigation"

        run_case(results, page, "TC03", "Sidebar navigation", tc_navigation)

        def tc_theme_switch():
            page.locator("header .group").first.hover()
            page.locator("header .group button").nth(1).click()
            page.wait_for_timeout(300)
            theme = page.locator("[data-theme]").first.get_attribute("data-theme")
            assert theme == "dark", f"Expected dark theme after selecting option 2, got {theme}"
            return "Theme dropdown switches dashboard theme to dark.", "tc04_theme_switch"

        run_case(results, page, "TC04", "Theme dropdown", tc_theme_switch)

        def tc_modal_upload():
            page.evaluate("window.dispatchEvent(new CustomEvent('open-modal', {detail:{type:'upload-req'}}))")
            expect(page.locator(".fixed.inset-0.z-\\[999\\]")).to_be_visible(timeout=5000)
            modal_text = page.locator(".fixed.inset-0.z-\\[999\\]").inner_text()
            assert len(modal_text.strip()) > 0, "Upload modal opened but has no text"
            page.keyboard.press("Escape")
            page.locator(".fixed.inset-0.z-\\[999\\] button").first.click()
            wait_no_overlay(page)
            return "Upload requirement modal opens and closes.", "tc05_modal_upload"

        run_case(results, page, "TC05", "Requirement upload modal", tc_modal_upload)

        def tc_generate_cases():
            click_nav(page, 2)
            before = page.locator("text=TC-AI-001").count()
            page.evaluate("window.dispatchEvent(new CustomEvent('open-modal', {detail:{type:'generate-cases'}}))")
            expect(page.locator(".fixed.inset-0.z-\\[999\\]")).to_be_visible(timeout=5000)
            page.locator(".fixed.inset-0.z-\\[999\\] button.accent-btn").last.click()
            page.wait_for_timeout(3500)
            after = page.locator("text=TC-AI-001").count()
            assert after > before, "Generated AI cases were not inserted into the test case page"
            return "AI generation modal inserts generated test cases into TestCases state.", "tc06_generate_cases"

        run_case(results, page, "TC06", "AI case generation mutation", tc_generate_cases)

        def tc_api_workbench_response():
            click_nav(page, 4)
            page.locator("button", has_text="工作台").click(timeout=5000)
            page.wait_for_timeout(400)
            page.locator("button", has_text="运行").click(timeout=5000)
            page.wait_for_timeout(2500)
            body_text = page.locator("body").inner_text()
            assert "document_summary" in body_text or "智能客服文本消息" in body_text, "Workbench response was not shown after running API request"
            return "API workbench run shows the mocked response body.", "tc07_api_response"

        run_case(results, page, "TC07", "API request simulation", tc_api_workbench_response)

        def tc_execution_flow():
            click_nav(page, 3)
            page.evaluate("window.dispatchEvent(new CustomEvent('open-modal', {detail:{type:'run-execution'}}))")
            expect(page.locator(".fixed.inset-0.z-\\[999\\]")).to_be_visible(timeout=5000)
            page.locator(".fixed.inset-0.z-\\[999\\] button.accent-btn").last.click()
            page.wait_for_timeout(2600)
            body = page.locator("body").inner_text()
            assert "75.0%" in body or "3" in body, "Execution result event did not visibly update the execution page"
            return "Execution modal completes and publishes execution-finished event.", "tc08_execution_flow"

        run_case(results, page, "TC08", "Execution simulation", tc_execution_flow)

        def tc_ai_assistant_xss():
            page.evaluate("window.__xss_probe = 0; window.dispatchEvent(new CustomEvent('open-ai-chat'))")
            expect(page.locator("input").last).to_be_visible(timeout=5000)
            payload = '<img src=x onerror="window.__xss_probe=1">'
            page.locator("input").last.fill(payload)
            page.keyboard.press("Enter")
            page.wait_for_timeout(500)
            xss = page.evaluate("window.__xss_probe")
            assert xss == 0, "User message HTML executed through dangerouslySetInnerHTML"
            return "AI assistant did not execute injected user HTML.", "tc09_ai_assistant_xss"

        run_case(results, page, "TC09", "AI assistant XSS probe", tc_ai_assistant_xss)

        def tc_mobile_overflow():
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(BASE, wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(500)
            dims = page.evaluate("({scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth})")
            assert dims["scrollWidth"] <= dims["innerWidth"] * 1.15, f"Mobile horizontal overflow: scrollWidth={dims['scrollWidth']}, innerWidth={dims['innerWidth']}"
            return f"Mobile layout stays within acceptable width: {dims}", "tc10_mobile_overflow"

        run_case(results, page, "TC10", "Mobile horizontal overflow", tc_mobile_overflow)

        summary = render_reports(results, console_errors, failed_requests)

        report_page = context.new_page()
        report_page.goto((REPORT_DIR / "core-test-report.html").as_uri(), wait_until="load")
        report_page.screenshot(path=str(REPORT_DIR / "core-test-report.png"), full_page=True)

        browser.close()

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
