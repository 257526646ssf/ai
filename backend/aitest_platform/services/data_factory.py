from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aitest_platform.models import ApiEndpoint, ApiTestCase, TestCase


MAX_GENERATION_COUNT = 50
SUPPORTED_MODES = ("normal", "boundary", "invalid", "empty", "special")
SUPPORTED_TARGETS = ("body", "query", "variables")
RESERVED_EMAIL_DOMAINS = ("example.com", "example.org", "example.net", "example.test", "invalid.test")
SENSITIVE_KEY_PARTS = ("authorization", "api_key", "api-key", "apikey", "token", "cookie", "secret", "password", "git_auth")
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)(authorization|api[_-]?key|api-key|apikey|token|cookie|secret|password)(\s*[:=]\s*)(Bearer\s+)?[^\s,;}\"']+"
)
AUTH_VALUE_RE = re.compile(r"(?i)\b(?:bearer|basic)\s+[^\s,;}\"']+")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
PHONE_RE = re.compile(r"\b(?:\+?86[- ]?)?1[3-9]\d{9}\b")
CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


class DataFactoryError(ValueError):
    pass


class DataFactoryNotFoundError(DataFactoryError):
    pass


def test_data_suggestions(session: Session, case_id: Any) -> dict[str, Any]:
    if not str(case_id).isdigit():
        raise DataFactoryError("case_id must be an integer")
    case = session.get(TestCase, int(case_id))
    if case is None or case.is_deleted:
        raise DataFactoryNotFoundError(f"TestCase({case_id}) not found")

    text = _case_text(case)
    clean_text = str(redact_payload(text))
    key_values = _extract_key_values(clean_text)
    identifiers = _identifier_candidates(clean_text, key_values)
    variables = [_variable_suggestion(name, key_values.get(name), index) for index, name in enumerate(identifiers)]
    precondition_data = [
        {
            "name": item["name"],
            "value": item["example_value"],
            "source": "case_text",
        }
        for item in variables
        if item["name"] in key_values or item["name"] in {"warehouse_zone", "loyalty_tier"}
    ]
    missing_dependencies = [
        {
            "name": item["name"],
            "type": "variable",
            "required": item["required"],
            "reason": "referenced by test case steps or expectations",
        }
        for item in variables
        if item["name"] not in key_values
    ]
    preparation_steps = [
        {
            "order": index + 1,
            "action": f"prepare {item['name']}",
            "data": {item["name"]: item["example_value"]},
        }
        for index, item in enumerate(variables[:8])
    ]
    accounts = [
        {
            "name": "synthetic_test_account",
            "role": "qa_user",
            "data": {
                "email": "qa.user@example.com",
                "warehouse_zone": key_values.get("warehouse_zone", "north"),
                "loyalty_tier": key_values.get("loyalty_tier", "standard"),
            },
        }
    ]
    items = [
        {"type": "account", "name": account["name"], "data": account["data"]}
        for account in accounts
    ]
    items.extend({"type": "variable", **item} for item in variables)
    items.extend({"type": "precondition_data", **item} for item in precondition_data)
    items.extend({"type": "missing_dependency", **item} for item in missing_dependencies)

    return redact_payload(
        {
            "case_id": case.id,
            "items": items,
            "accounts": accounts,
            "variables": variables,
            "precondition_data": precondition_data,
            "missing_dependencies": missing_dependencies,
            "preparation_steps": preparation_steps,
            "provider_call_performed": False,
            "llm_provider_called": False,
        }
    )


def generate_api_parameters(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    count = _bounded_count(payload.get("count"), payload.get("max_count") or payload.get("maxCount"))
    modes = _requested_modes(payload.get("modes"))
    targets = _requested_targets(payload.get("targets"))
    schema = _payload_schema(payload.get("schema"))
    fields = _field_specs(payload.get("fields"), schema)

    api_case_id = payload.get("api_case_id") or payload.get("apiCaseId")
    api_case_payload: dict[str, Any] | None = None
    if api_case_id is not None:
        api_case_payload = _api_case_sources(session, api_case_id)
        schema = _merge_schema(schema, api_case_payload.get("schema") or {})
        fields = _dedupe_field_specs([*fields, *_field_specs([], api_case_payload.get("schema") or {})])

    if not fields:
        fields = [{"name": "sample_value", "location": "body", "type": "string"}]

    items: list[dict[str, Any]] = []
    for index in range(count):
        mode = modes[index % len(modes)]
        items.append(_build_sample(index=index, mode=mode, targets=targets, fields=fields))

    included_modes = {str(item.get("mode")) for item in items}
    for mode in modes:
        if mode not in included_modes and len(items) < count:
            items.append(_build_sample(index=len(items), mode=mode, targets=targets, fields=fields))

    result = {
        "items": items[:count],
        "summary": {
            "requested_count": _safe_int(payload.get("count"), default=count),
            "count": min(count, len(items)),
            "max_count": MAX_GENERATION_COUNT,
            "modes": modes,
            "targets": targets,
            "field_count": len(fields),
            "source": "synthetic-rules-v1",
            "api_case_id": int(api_case_id) if api_case_id is not None and str(api_case_id).isdigit() else None,
        },
        "provider_call_performed": False,
        "llm_provider_called": False,
    }
    return redact_payload(result)


def redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                clean[key] = "***"
            else:
                clean[key] = redact_payload(item)
        return clean
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, str):
        text = SENSITIVE_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}***", value)
        text = AUTH_VALUE_RE.sub("***", text)
        text = PHONE_RE.sub("15500000000", text)
        text = CARD_RE.sub(_redact_card_like, text)

        def email_replacer(match: re.Match[str]) -> str:
            domain = match.group(1).lower()
            if domain.endswith(RESERVED_EMAIL_DOMAINS):
                return match.group(0)
            return "user@example.com"

        return EMAIL_RE.sub(email_replacer, text)
    return value


def _api_case_sources(session: Session, api_case_id: Any) -> dict[str, Any]:
    if not str(api_case_id).isdigit():
        raise DataFactoryError("api_case_id must be an integer")
    case = session.get(ApiTestCase, int(api_case_id))
    if case is None or case.is_deleted:
        raise DataFactoryNotFoundError(f"ApiTestCase({api_case_id}) not found")
    endpoint = session.scalar(select(ApiEndpoint).where(ApiEndpoint.id == case.endpoint_id))
    if endpoint is None or endpoint.is_deleted:
        raise DataFactoryNotFoundError(f"ApiEndpoint({case.endpoint_id}) not found")
    return {
        "schema": {
            "body": endpoint.body_schema or _schema_from_value(case.request_body),
            "query": endpoint.query_schema or _schema_from_value(case.request_query),
            "variables": _schema_from_value(_variables_from_case(case)),
        }
    }


def _case_text(case: TestCase) -> str:
    parts = [
        case.title,
        case.precondition or "",
        json_dumps_safe(case.steps),
        case.expected_result,
        json_dumps_safe(case.tags or []),
    ]
    return "\n".join(part for part in parts if part)


def json_dumps_safe(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return str(redact_payload(value))
    except Exception:
        return str(type(value).__name__)


def _extract_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in re.finditer(r"\b([A-Za-z][A-Za-z0-9_]*)\s*=\s*([A-Za-z0-9_.+-]+)", text):
        key = match.group(1)
        if _is_sensitive_key(key):
            continue
        values[key] = _safe_identifier_value(key, match.group(2))
    return values


def _identifier_candidates(text: str, key_values: dict[str, str]) -> list[str]:
    preferred = ["warehouse_zone", "loyalty_tier", "cart_id", "retry_count", "coupon_code"]
    candidates = list(key_values)
    candidates.extend(re.findall(r"\b[A-Za-z][A-Za-z0-9_]*_[A-Za-z0-9_]+\b", text))
    candidates.extend(preferred)
    stop_words = {
        "authorization",
        "bearer",
        "cookie",
        "password",
        "token",
        "api_key",
        "round29",
        "submit",
        "call",
        "order",
        "response",
        "accepted",
        "special",
    }
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        name = str(candidate).strip().lower()
        if not name or name in seen or name in stop_words or _is_sensitive_key(name):
            continue
        seen.add(name)
        result.append(name)
    return result[:12] or preferred


def _variable_suggestion(name: str, value: str | None, index: int) -> dict[str, Any]:
    return {
        "name": name,
        "example_value": value or _default_variable_value(name, index),
        "required": True,
        "source": "case_text",
    }


def _default_variable_value(name: str, index: int) -> str | int:
    if "retry" in name or name.endswith("_count"):
        return 1
    if "cart" in name:
        return f"cart_{index + 1:04d}"
    if "coupon" in name:
        return "SAFE-COUPON"
    if "zone" in name:
        return "north"
    if "tier" in name:
        return "standard"
    return f"{name}_{index + 1}"


def _safe_identifier_value(key: str, value: str) -> str:
    if _is_sensitive_key(key):
        return "***"
    if "email" in key.lower():
        return "user@example.com"
    if "phone" in key.lower():
        return "15500000000"
    return str(redact_payload(value))


def _variables_from_case(case: ApiTestCase) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    for source in (case.request_query, case.request_body, case.request_headers):
        _collect_template_variables(source, variables)
    return variables


def _collect_template_variables(value: Any, output: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _collect_template_variables(item, output)
        return
    if isinstance(value, list):
        for item in value:
            _collect_template_variables(item, output)
        return
    if not isinstance(value, str):
        return
    for match in re.finditer(r"{{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*}}", value):
        output.setdefault(match.group(1), {"type": "string"})


def _schema_from_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {key: _schema_from_value(item) for key, item in value.items() if not _is_sensitive_key(key)}
    if isinstance(value, list):
        return {"type": "array"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    return {"type": "string"}


def _bounded_count(count_value: Any, max_count_value: Any) -> int:
    requested = _safe_int(count_value, default=5)
    local_max = _safe_int(max_count_value, default=MAX_GENERATION_COUNT)
    if requested < 1:
        requested = 1
    if local_max < 1:
        local_max = 1
    return max(1, min(requested, local_max, MAX_GENERATION_COUNT))


def _requested_modes(value: Any) -> list[str]:
    raw_items = value if isinstance(value, list) else []
    modes = [str(item).strip().lower() for item in raw_items if str(item).strip().lower() in SUPPORTED_MODES]
    return list(dict.fromkeys(modes)) or ["normal"]


def _requested_targets(value: Any) -> list[str]:
    raw_items = value if isinstance(value, list) else SUPPORTED_TARGETS
    targets = [str(item).strip().lower() for item in raw_items if str(item).strip().lower() in SUPPORTED_TARGETS]
    return list(dict.fromkeys(targets)) or list(SUPPORTED_TARGETS)


def _payload_schema(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {target: value.get(target) for target in SUPPORTED_TARGETS if isinstance(value.get(target), dict)}


def _merge_schema(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = {target: dict(base.get(target) or {}) for target in SUPPORTED_TARGETS}
    for target, value in overlay.items():
        if isinstance(value, dict):
            merged[target] = _deep_merge_schema(merged.get(target) or {}, value)
    return {target: value for target, value in merged.items() if value}


def _deep_merge_schema(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge_schema(result[key], value)
        elif key not in result:
            result[key] = value
    return result


def _field_specs(raw_fields: Any, schema: dict[str, Any]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    if isinstance(raw_fields, list):
        for raw in raw_fields:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or raw.get("field") or "").strip()
            if not name or _is_sensitive_key(name):
                continue
            location = str(raw.get("location") or raw.get("target") or "body").strip().lower()
            if location not in SUPPORTED_TARGETS:
                location = "body"
            fields.append(_normalize_field({**raw, "name": name, "location": location}))
    for target in SUPPORTED_TARGETS:
        target_schema = schema.get(target)
        if isinstance(target_schema, dict):
            fields.extend(_fields_from_schema(target_schema, target))
    return _dedupe_field_specs(fields)


def _fields_from_schema(schema: dict[str, Any], location: str, prefix: str = "") -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else schema
    required = schema.get("required") if isinstance(schema.get("required"), list) else []
    for name, definition in properties.items():
        if _is_sensitive_key(name) or not isinstance(definition, dict):
            continue
        path = f"{prefix}.{name}" if prefix else str(name)
        nested = definition.get("properties")
        if isinstance(nested, dict):
            fields.extend(_fields_from_schema(definition, location, path))
            continue
        fields.append(_normalize_field({"name": path, "location": location, **definition, "required": name in required}))
    return fields


def _normalize_field(field: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(field)
    name = str(normalized.get("name") or "value")
    normalized["name"] = name
    normalized["location"] = str(normalized.get("location") or "body").lower()
    normalized["type"] = _infer_type(normalized)
    return normalized


def _dedupe_field_specs(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for field in fields:
        key = (str(field.get("location") or "body"), str(field.get("name") or "value"))
        if key in seen:
            continue
        seen.add(key)
        result.append(field)
    return result


def _infer_type(field: dict[str, Any]) -> str:
    raw = str(field.get("type") or "").lower()
    if raw in {"integer", "number", "boolean", "array", "object", "string"}:
        return raw
    name = str(field.get("name") or "").lower()
    if any(fragment in name for fragment in ("count", "page", "amount", "total", "size", "age")):
        return "integer"
    return "string"


def _build_sample(index: int, mode: str, targets: list[str], fields: list[dict[str, Any]]) -> dict[str, Any]:
    mapped: dict[str, dict[str, Any]] = {target: {} for target in SUPPORTED_TARGETS}
    for field in fields:
        location = str(field.get("location") or "body").lower()
        if location not in mapped:
            location = "body"
        if location not in targets:
            continue
        _set_nested(mapped[location], str(field.get("name") or "value"), _value_for_field(field, mode, index))

    sample = {
        "id": f"sample-{index + 1}",
        "mode": mode,
        "case_type": mode,
        "request": {target: mapped[target] for target in targets},
        "body": mapped["body"],
        "query": mapped["query"],
        "variables": mapped["variables"],
        "notes": _mode_note(mode),
    }
    return sample


def _set_nested(container: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = [part for part in dotted_path.split(".") if part]
    if not parts:
        return
    current = container
    for part in parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[parts[-1]] = value


def _value_for_field(field: dict[str, Any], mode: str, index: int) -> Any:
    if mode == "empty":
        return None if field.get("required") else ""
    field_type = str(field.get("type") or "string").lower()
    name = str(field.get("name") or "value").lower()
    fmt = str(field.get("format") or "").lower()

    if mode == "invalid":
        if field_type in {"integer", "number"}:
            return "not-a-number"
        if field_type == "boolean":
            return "not-a-boolean"
        if fmt == "email" or "email" in name:
            return "invalid-email"
        return "invalid_value"

    if field_type in {"integer", "number"}:
        minimum = field.get("minimum")
        maximum = field.get("maximum")
        if mode == "boundary":
            return _safe_number(minimum, default=0)
        if mode == "special":
            return _safe_number(maximum, default=999)
        base = _safe_number(minimum, default=1)
        return base + index

    if field_type == "boolean":
        return mode != "boundary"

    if fmt == "email" or "email" in name:
        if mode == "boundary":
            return "a@example.com"
        if mode == "special":
            return f"qa+special{index + 1}@example.com"
        return f"user{index + 1}@example.com"
    if "phone" in name or fmt == "phone":
        return f"1550000{index + 1:04d}"[-11:]
    if "name" in name:
        return f"Test User {index + 1}"
    if "trace" in name:
        return f"trace_{mode}_{index + 1}"
    if "cart" in name:
        return f"cart_{index + 1:04d}"
    if "coupon" in name:
        return "SAFE-COUPON" if mode != "special" else "SAFE-COUPON-PLUS"
    if mode == "boundary":
        return "a"
    if mode == "special":
        return f"special_value_{index + 1}_at_hash"
    return f"{name.replace('.', '_')}_{index + 1}"


def _mode_note(mode: str) -> str:
    return {
        "normal": "valid representative synthetic data",
        "boundary": "boundary-oriented synthetic data",
        "invalid": "intentionally invalid synthetic data",
        "empty": "empty and missing-value synthetic data",
        "special": "special-character synthetic data",
    }.get(mode, "synthetic data")


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_number(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_sensitive_key(key: Any) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def _redact_card_like(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    if len(digits) < 13:
        return match.group(0)
    return "4000000000000002"
