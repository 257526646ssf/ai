from __future__ import annotations

import re
from typing import Any


VARIABLE_PATTERN = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*}}")
SENSITIVE_KEY_PARTS = ("authorization", "api_key", "api-key", "apikey", "token", "cookie", "secret", "password")
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)(authorization|api[_-]?key|token|cookie|secret|password)(\s*[:=]\s*)(Bearer\s+)?[^\s,;}\"]+"
)


def sanitize_runtime_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if is_sensitive_key(key):
                clean[key] = "***"
            else:
                clean[key] = sanitize_runtime_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_runtime_payload(item) for item in value]
    if isinstance(value, str):
        return SENSITIVE_TEXT_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}***", value)
    return value


def is_sensitive_key(key: Any) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def resolve_runtime_variables(environment: Any | None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = payload or {}
    variables: dict[str, Any] = {}
    if environment is not None and isinstance(getattr(environment, "variables", None), dict):
        variables.update(getattr(environment, "variables") or {})
    if isinstance(data.get("variables"), dict):
        variables.update(data["variables"])
    runtime_variables = data.get("runtime_variables") if "runtime_variables" in data else data.get("runtimeVariables")
    if isinstance(runtime_variables, dict):
        variables.update(runtime_variables)
    return variables


def merge_headers(environment: Any | None, case_headers: Any, override_headers: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for source in (
        getattr(environment, "headers", None) if environment is not None else None,
        case_headers,
        override_headers,
    ):
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            _set_header(merged, str(key), value)
    return merged


def build_case_request_payload(
    case: Any,
    endpoint: Any,
    environment: Any | None,
    overrides: dict[str, Any] | None = None,
    *,
    include_raw_response: bool = False,
) -> dict[str, Any]:
    data = overrides or {}
    variables = resolve_runtime_variables(environment, data)
    headers = merge_headers(environment, getattr(case, "request_headers", None) or {}, data.get("headers") or {})
    assertions = data.get("assertions") or getattr(case, "assertions", None) or [
        {"type": "status_code", "expected": getattr(case, "expected_status", 200)}
    ]
    raw_payload = {
        "method": data.get("method") or getattr(endpoint, "method", "GET"),
        "url": data.get("url"),
        "base_url": data.get("base_url") or data.get("baseUrl") or (getattr(environment, "base_url", None) if environment else None),
        "path": data.get("path") or getattr(endpoint, "path", "/"),
        "headers": headers,
        "query": data.get("query") or data.get("params") or getattr(case, "request_query", None) or {},
        "body": data["body"] if "body" in data else getattr(case, "request_body", None),
        "content_type": data.get("content_type") or data.get("contentType") or getattr(case, "content_type", "application/json"),
        "timeout_ms": data.get("timeout_ms") or data.get("timeoutMs"),
        "assertions": assertions,
        "pre_script": data.get("pre_script") if "pre_script" in data else getattr(case, "pre_script", None),
        "post_script": data.get("post_script") if "post_script" in data else getattr(case, "post_script", None),
        "_runtime_variables": variables,
    }
    if include_raw_response:
        raw_payload["_include_raw_response"] = True
    resolved_payload, missing_variables = inject_runtime_values(raw_payload, variables)
    resolved_payload["_runtime_context"] = runtime_context_snapshot(variables, missing_variables)
    return resolved_payload


def inject_runtime_values(value: Any, variables: dict[str, Any]) -> tuple[Any, list[dict[str, str]]]:
    missing: list[dict[str, str]] = []
    resolved = _inject(value, variables, "$", missing)
    return resolved, _dedupe_missing(missing)


def runtime_context_snapshot(variables: dict[str, Any], missing_variables: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return sanitize_runtime_payload(
        {
            "variables": variables,
            "missing_variables": missing_variables or [],
        }
    )


def attach_runtime_context(result: dict[str, Any], runtime_context: dict[str, Any] | None) -> dict[str, Any]:
    if not runtime_context:
        return result
    request_snapshot = result.get("request_snapshot")
    if isinstance(request_snapshot, dict):
        request_snapshot["runtime_context"] = sanitize_runtime_payload(runtime_context)
    if runtime_context.get("missing_variables"):
        result["missing_variables"] = sanitize_runtime_payload(runtime_context["missing_variables"])
    return result


def redact_sensitive_variable_values(value: Any, variables: dict[str, Any]) -> Any:
    secret_values = [str(item) for key, item in variables.items() if _is_sensitive_variable(key, item)]
    if isinstance(value, dict):
        return {key: redact_sensitive_variable_values(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_variable_values(item, variables) for item in value]
    if isinstance(value, str):
        redacted = value
        for secret in secret_values:
            redacted = redacted.replace(secret, "***")
        return redacted
    return value


def _set_header(headers: dict[str, Any], key: str, value: Any) -> None:
    lowered = key.lower()
    for existing in list(headers.keys()):
        if existing.lower() == lowered:
            del headers[existing]
    headers[key] = value


def _inject(value: Any, variables: dict[str, Any], path: str, missing: list[dict[str, str]]) -> Any:
    if isinstance(value, dict):
        return {key: _inject(item, variables, f"{path}.{key}", missing) for key, item in value.items()}
    if isinstance(value, list):
        return [_inject(item, variables, f"{path}[{index}]", missing) for index, item in enumerate(value)]
    if not isinstance(value, str):
        return value
    matches = list(VARIABLE_PATTERN.finditer(value))
    if not matches:
        return value
    if len(matches) == 1 and matches[0].span() == (0, len(value)):
        name = matches[0].group(1)
        if name in variables:
            return variables[name]
        missing.append({"name": name, "path": path})
        return value

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            missing.append({"name": name, "path": path})
            return match.group(0)
        return str(variables[name])

    return VARIABLE_PATTERN.sub(replace, value)


def _dedupe_missing(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for item in items:
        key = (item.get("name", ""), item.get("path", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _is_sensitive_variable(key: Any, value: Any) -> bool:
    if not isinstance(value, str) or len(value) < 3:
        return False
    return is_sensitive_key(key)
