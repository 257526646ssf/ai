from __future__ import annotations

import time
import re
from typing import Any
from urllib.parse import urljoin

import httpx

from aitest_platform.services.api_script_runner import run_api_script

SENSITIVE_KEY_PARTS = ("authorization", "api_key", "api-key", "apikey", "token", "cookie", "secret", "password")
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)(authorization|api[_-]?key|token|cookie|secret|password)(\s*[:=]\s*)(Bearer\s+)?[^\s,;}\"]+"
)
DEFAULT_TIMEOUT_MS = 5000
MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 30000
MAX_RESPONSE_BODY_CHARS = 65536


def clamp_timeout_ms(value: Any = None) -> int:
    if value is None:
        return DEFAULT_TIMEOUT_MS
    try:
        timeout_ms = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_MS
    return max(MIN_TIMEOUT_MS, min(MAX_TIMEOUT_MS, timeout_ms))


def sanitize_api_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                clean[key] = "***"
            else:
                clean[key] = sanitize_api_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_api_payload(item) for item in value]
    if isinstance(value, str):
        return SENSITIVE_TEXT_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}***", value)
    return value


def build_api_url(data: dict[str, Any]) -> str:
    direct_url = data.get("url")
    if direct_url:
        url = str(direct_url).strip()
    else:
        base_url = str(data.get("base_url") or data.get("baseUrl") or "").strip()
        path = str(data.get("path") or "/").strip() or "/"
        if not base_url:
            raise ValueError("url or base_url is required")
        url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("url must start with http:// or https://")
    return url


def run_api_request(data: dict[str, Any]) -> dict[str, Any]:
    timeout_ms = clamp_timeout_ms(data.get("timeout_ms") or data.get("timeoutMs"))
    method = str(data.get("method") or "GET").upper()
    headers = dict(data.get("headers") or {})
    query = data.get("query") or data.get("params") or {}
    body = data.get("body")
    content_type = data.get("content_type") or data.get("contentType")
    if content_type and body is not None and not any(key.lower() == "content-type" for key in headers):
        headers["Content-Type"] = str(content_type)
    started = time.perf_counter()
    script_results: dict[str, Any] = {}
    runtime_variables = data.get("_runtime_variables") if isinstance(data.get("_runtime_variables"), dict) else {}
    request_context = {"headers": headers, "query": query, "body": body}
    pre_script_result = run_api_script(
        data.get("pre_script"),
        phase="pre",
        request=request_context,
        variables=runtime_variables,
    )
    if data.get("pre_script") not in (None, "", [], {}):
        script_results["pre"] = pre_script_result
    if pre_script_result.get("errors"):
        duration_ms = max(1, int((time.perf_counter() - started) * 1000))
        request_snapshot = sanitize_api_payload(
            {
                "method": method,
                "url": data.get("url") or data.get("base_url") or data.get("baseUrl") or data.get("path"),
                "headers": headers,
                "query": query,
                "body": body,
                "content_type": content_type,
                "timeout_ms": timeout_ms,
                "script_results": script_results,
            }
        )
        return {
            "status": "error",
            "request_snapshot": request_snapshot,
            "response_snapshot": None,
            "assertion_results": [],
            "duration_ms": duration_ms,
            "error_message": "pre_script_failed",
            "script_results": script_results,
        }
    headers = dict(request_context.get("headers") or {})
    query = request_context.get("query") or {}
    body = request_context.get("body")
    request_snapshot = sanitize_api_payload(
        {
            "method": method,
            "url": data.get("url") or data.get("base_url") or data.get("baseUrl") or data.get("path"),
            "headers": headers,
            "query": query,
            "body": body,
            "content_type": content_type,
            "timeout_ms": timeout_ms,
            "script_results": script_results,
        }
    )
    try:
        url = build_api_url(data)
        request_snapshot["url"] = sanitize_api_payload(url)
        request_kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": headers,
            "params": query,
            "timeout": timeout_ms / 1000,
        }
        if body is not None:
            if isinstance(body, (dict, list)) and str(content_type or "application/json").lower().find("json") >= 0:
                request_kwargs["json"] = body
            else:
                request_kwargs["content"] = body if isinstance(body, (str, bytes)) else str(body)

        with httpx.Client(follow_redirects=False) as client:
            response = client.request(**request_kwargs)
        duration_ms = max(1, int((time.perf_counter() - started) * 1000))
        body_text = _limited_response_text(response)
        response_body = _response_body_value(response, body_text)
        raw_response_snapshot = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response_body,
            "body_truncated": len(response.text) > MAX_RESPONSE_BODY_CHARS,
            "content_type": response.headers.get("content-type"),
        }
        response_snapshot = sanitize_api_payload(raw_response_snapshot)
        assertions = data.get("assertions") or []
        if not assertions and data.get("expected_status") is not None:
            assertions = [{"type": "status_code", "expected": data.get("expected_status")}]
        assertion_results = evaluate_assertions(assertions, response, body_text)
        post_script_result = run_api_script(
            data.get("post_script"),
            phase="post",
            request={"headers": headers, "query": query, "body": body},
            response=raw_response_snapshot,
            variables=runtime_variables,
        )
        if data.get("post_script") not in (None, "", [], {}):
            script_results["post"] = post_script_result
            assertion_results.extend(post_script_result.get("assertion_results") or [])
        status = "passed" if all(item["passed"] for item in assertion_results) else "failed"
        if post_script_result.get("errors"):
            status = "error"
        result = {
            "status": status,
            "request_snapshot": request_snapshot,
            "response_snapshot": response_snapshot,
            "assertion_results": assertion_results,
            "duration_ms": duration_ms,
            "error_message": "post_script_failed" if post_script_result.get("errors") else None,
            "script_results": sanitize_api_payload(script_results),
        }
        if post_script_result.get("variables"):
            result["variables"] = sanitize_api_payload(post_script_result["variables"])
        if script_results:
            if isinstance(result["request_snapshot"], dict):
                result["request_snapshot"]["script_results"] = sanitize_api_payload(script_results)
            if isinstance(result["response_snapshot"], dict):
                result["response_snapshot"]["script_results"] = sanitize_api_payload(script_results)
        if data.get("_include_raw_response"):
            result["_raw_response_snapshot"] = raw_response_snapshot
        return result
    except (httpx.HTTPError, ValueError) as exc:
        duration_ms = max(1, int((time.perf_counter() - started) * 1000))
        return {
            "status": "error",
            "request_snapshot": request_snapshot,
            "response_snapshot": None,
            "assertion_results": [],
            "duration_ms": duration_ms,
            "error_message": _safe_error_message(exc),
            "script_results": sanitize_api_payload(script_results),
        }


def evaluate_assertions(assertions: list[Any], response: httpx.Response, body_text: str) -> list[dict[str, Any]]:
    normalized = [item for item in assertions if isinstance(item, dict)]
    if not normalized:
        normalized = [{"type": "status_code", "expected": 200}]
    json_body = _json_body(response)
    results: list[dict[str, Any]] = []
    for assertion in normalized:
        assertion_type = assertion.get("type") or assertion.get("name")
        if assertion_type == "status_code":
            expected = assertion.get("expected", assertion.get("value", assertion.get("status_code")))
            expected_code = _safe_int(expected)
            passed = expected_code is not None and response.status_code == expected_code
            actual: Any = response.status_code
            expected = expected_code if expected_code is not None else expected
        elif assertion_type == "body_contains":
            expected = str(assertion.get("expected", assertion.get("value", assertion.get("contains", ""))))
            passed = expected in body_text
            actual = body_text[:500]
        elif assertion_type == "header_equals":
            header_name = str(assertion.get("header") or assertion.get("header_name") or "")
            expected = str(assertion.get("expected", assertion.get("value", "")))
            actual = response.headers.get(header_name)
            passed = actual == expected
        elif assertion_type == "json_path_equals":
            path = str(assertion.get("path") or assertion.get("json_path") or "")
            expected = assertion.get("expected", assertion.get("value"))
            actual = _json_path_get(json_body, path)
            passed = actual == expected
        else:
            expected = assertion.get("expected")
            actual = None
            passed = False
        results.append(
            sanitize_api_payload(
                {
                    "type": assertion_type or "unknown",
                    "passed": bool(passed),
                    "expected": expected,
                    "actual": actual,
                }
            )
        )
    return results


def _limited_response_text(response: httpx.Response) -> str:
    return response.text[:MAX_RESPONSE_BODY_CHARS]


def _response_body_value(response: httpx.Response, body_text: str) -> Any:
    if len(response.text) > MAX_RESPONSE_BODY_CHARS:
        return body_text
    content_type = response.headers.get("content-type", "")
    if "json" in content_type.lower():
        try:
            return response.json()
        except ValueError:
            return body_text
    if body_text.lstrip().startswith(("{", "[")):
        try:
            return response.json()
        except ValueError:
            return body_text
    return body_text


def _json_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _json_path_get(value: Any, path: str) -> Any:
    if not path:
        return value
    parts = path[2:].split(".") if path.startswith("$.") else path.strip(".").split(".")
    current = value
    for part in parts:
        if part == "":
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def _safe_error_message(exc: Exception) -> str:
    return str(sanitize_api_payload({"error": str(exc)})["error"])[:1000]


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
