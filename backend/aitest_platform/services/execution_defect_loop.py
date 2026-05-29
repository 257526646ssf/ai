from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any


SENSITIVE_KEY_PARTS = ("authorization", "api_key", "api-key", "apikey", "token", "cookie", "secret", "password")
SECRET_TEXT_RE = re.compile(
    r"(?i)(authorization|api[_-]?key|api-key|apikey|token|cookie|secret|password)(\s*[:=]\s*)(Bearer\s+)?[^\s,;}\"']+"
)
AUTH_VALUE_RE = re.compile(r"(?i)\b(?:bearer|basic)\s+[^\s,;}\"']+")
SECRET_VALUE_RE = re.compile(r"(?i)\bsk-[a-z0-9][a-z0-9_-]{6,}")
DEFECT_REMARK_PREFIX = "R24_DEFECT_LOOP:"


def sanitize_loop_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("***" if _is_sensitive_key(key) else sanitize_loop_payload(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_loop_payload(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def redact_sensitive_text(value: str) -> str:
    text = SECRET_TEXT_RE.sub("***", value)
    text = AUTH_VALUE_RE.sub("***", text)
    return SECRET_VALUE_RE.sub("***", text)


def execution_templates() -> dict[str, Any]:
    return sanitize_loop_payload(
        {
            "failed": {
                "status": "failed",
                "required_fields": ["case_id", "actual_result"],
                "default_payload": {"status": "failed", "executor_type": "manual", "create_defect": True},
                "suggested_defect_fields": [
                    "title",
                    "severity",
                    "steps",
                    "expected_result",
                    "actual_result",
                    "impact",
                    "retest_suggestion",
                    "fix_hints",
                ],
            },
            "blocked": {
                "status": "blocked",
                "required_fields": ["case_id", "block_reason"],
                "default_payload": {"status": "blocked", "executor_type": "manual", "create_defect": True},
                "suggested_defect_fields": ["title", "severity", "steps", "impact", "retest_suggestion", "fix_hints"],
            },
            "skipped": {
                "status": "skipped",
                "required_fields": ["case_id", "skip_reason"],
                "default_payload": {"status": "skipped", "executor_type": "manual", "create_defect": False},
                "suggested_defect_fields": ["title", "steps", "impact", "retest_suggestion"],
            },
        }
    )


def normalize_execution_status(status: Any) -> str:
    raw = str(status or "").strip().lower()
    return {
        "passed": "pass",
        "success": "pass",
        "ok": "pass",
        "failed": "fail",
        "failure": "fail",
        "error": "fail",
        "blocked": "blocked",
        "block": "blocked",
        "skipped": "skipped",
        "skip": "skipped",
    }.get(raw, raw or "pass")


def status_bucket(status: Any) -> str:
    normalized = normalize_execution_status(status)
    if normalized in {"pass", "passed"}:
        return "passed"
    if normalized in {"fail", "failed", "error"}:
        return "failed"
    if normalized == "blocked":
        return "blocked"
    if normalized == "skipped":
        return "skipped"
    return normalized or "unknown"


def build_defect_suggestion(execution: Any, case: Any | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = sanitize_loop_payload(payload or {})
    bucket = status_bucket(getattr(execution, "status", None) or payload.get("status"))
    title = _first_text(payload.get("defect_title"), payload.get("title"))
    case_title = _safe_attr(case, "title", "Test case")
    if not title:
        suffix = {"failed": "failed during execution", "blocked": "is blocked", "skipped": "was skipped"}.get(bucket, "needs review")
        title = f"{case_title} {suffix}"

    actual = _first_text(
        payload.get("actual_result"),
        _safe_attr(execution, "actual_result"),
        _safe_attr(execution, "block_reason") if bucket == "blocked" else None,
        _safe_attr(execution, "skip_reason") if bucket == "skipped" else None,
        "No actual result was recorded.",
    )
    expected = _first_text(payload.get("expected_result"), _safe_attr(case, "expected_result"), "Actual behavior should match the expected result.")
    steps = _normalize_steps(payload.get("steps") if payload.get("steps") is not None else _safe_attr(case, "steps"))
    severity = _first_text(payload.get("severity"), _suggest_severity(bucket, case, actual))
    impact = _first_text(payload.get("impact"), _suggest_impact(bucket, case, actual))
    retest = _first_text(payload.get("retest_suggestion"), _suggest_retest(bucket, case))
    fix_hints = _normalize_list(payload.get("fix_hints")) or _suggest_fix_hints(bucket, actual)
    description = _first_text(payload.get("description"), f"Execution {getattr(execution, 'id', None)} produced status {bucket} for case {case_title}.")

    suggestion = {
        "provider": "deterministic",
        "provider_call_performed": False,
        "llm_provider_called": False,
        "execution_id": getattr(execution, "id", None),
        "project_id": getattr(execution, "project_id", None) or _safe_attr(case, "project_id"),
        "case_id": getattr(execution, "case_id", None) or _safe_attr(case, "id"),
        "requirement_item_id": getattr(execution, "requirement_item_id", None) or _safe_attr(case, "requirement_item_id"),
        "execution_status": bucket,
        "title": title,
        "severity": severity,
        "description": description,
        "steps": steps,
        "steps_to_reproduce": steps,
        "expected_result": expected,
        "actual_result": actual,
        "impact": impact,
        "retest_suggestion": retest,
        "fix_hints": fix_hints,
        "suggested_defect_fields": {
            "title": title,
            "severity": severity,
            "description": description,
            "steps": steps,
            "steps_to_reproduce": steps,
            "expected_result": expected,
            "actual_result": actual,
            "impact": impact,
            "retest_suggestion": retest,
            "fix_hints": fix_hints,
        },
    }
    return sanitize_loop_payload(suggestion)


def encode_defect_remark(fields: dict[str, Any], existing_remark: Any = None) -> str:
    current = decode_defect_remark(existing_remark)
    note = current.get("note") or ""
    if existing_remark and not str(existing_remark).startswith(DEFECT_REMARK_PREFIX) and not current:
        note = str(existing_remark)
    merged = {**current, **sanitize_loop_payload(fields)}
    if note and "note" not in merged:
        merged["note"] = redact_sensitive_text(note)
    return DEFECT_REMARK_PREFIX + json.dumps(merged, ensure_ascii=False, sort_keys=True)


def decode_defect_remark(remark: Any) -> dict[str, Any]:
    if not remark:
        return {}
    text = str(remark)
    if text.startswith(DEFECT_REMARK_PREFIX):
        text = text[len(DEFECT_REMARK_PREFIX) :]
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return sanitize_loop_payload(data) if isinstance(data, dict) else {}


def enrich_defect_dict(defect: Any) -> dict[str, Any]:
    data = _model_dict(defect)
    extra = decode_defect_remark(data.get("remark"))
    for key in ("description", "steps", "expected_result", "impact", "retest_suggestion", "fix_hints", "note", "due_at", "assignee"):
        if key in extra:
            data[key] = extra[key]
    return sanitize_loop_payload(data)


def build_copy_text(defect: Any, case: Any | None = None) -> str:
    data = enrich_defect_dict(defect)
    steps = data.get("steps") or _normalize_steps(_safe_attr(case, "steps"))
    expected = _first_text(data.get("expected_result"), _safe_attr(case, "expected_result"), "Not recorded.")
    actual = _first_text(data.get("actual_result"), "Not recorded.")
    impact = _first_text(data.get("impact"), "Needs triage.")
    retest = _first_text(data.get("retest_suggestion"), "Retest the linked case after the fix is available.")
    lines = [
        f"标题 / Title: {data.get('title') or ''}",
        f"严重级别 / Severity: {data.get('severity') or ''}",
        f"状态 / Status: {data.get('status') or ''}",
        "复现步骤 / Reproduction Steps:",
    ]
    lines.extend([f"{index}. {step}" for index, step in enumerate(steps or ["No steps recorded."], start=1)])
    lines.extend(
        [
            f"预期结果 / Expected Result: {expected}",
            f"实际结果 / Actual Result: {actual}",
            f"影响 / Impact: {impact}",
            f"复测建议 / Retest Suggestion: {retest}",
        ]
    )
    return redact_sensitive_text("\n".join(str(line) for line in lines))


def build_retest_reminder(defect: Any, due_at: Any = None, assignee: Any = None) -> dict[str, Any]:
    due_text = _normalize_due_at(due_at)
    data = enrich_defect_dict(defect)
    reminder = {
        "defect_id": getattr(defect, "id", None),
        "title": data.get("title"),
        "status": data.get("status"),
        "severity": data.get("severity"),
        "case_id": data.get("case_id"),
        "due_at": due_text,
        "assignee": redact_sensitive_text(str(assignee)) if assignee not in (None, "") else None,
        "message": f"Retest defect {getattr(defect, 'defect_number', getattr(defect, 'id', ''))} by {due_text}.",
    }
    return sanitize_loop_payload(reminder)


def execution_statistics(records: list[Any], defects: list[Any], reminders: list[Any] | None = None, recent_days: int = 7) -> dict[str, Any]:
    counts = Counter(status_bucket(getattr(item, "status", None)) for item in records)
    total = len(records)
    open_defects = [item for item in defects if not _is_closed_status(getattr(item, "status", None))]
    return {
        "total": total,
        "passed": counts.get("passed", 0),
        "failed": counts.get("failed", 0),
        "blocked": counts.get("blocked", 0),
        "skipped": counts.get("skipped", 0),
        "open_defects": len(open_defects),
        "retest_due": count_due_reminders(reminders or [], defects),
        "pass_rate": _pass_rate(counts.get("passed", 0), total),
        "recent_trend": aggregate_execution_trend(records, defects, recent_days=recent_days)["trend"],
    }


def aggregate_execution_trend(records: list[Any], defects: list[Any], recent_days: int | None = None) -> dict[str, Any]:
    rows: dict[str, dict[str, Any]] = defaultdict(_empty_trend_row)
    for execution in records:
        day = _date_key(getattr(execution, "executed_at", None))
        bucket = status_bucket(getattr(execution, "status", None))
        row = rows[day]
        row[bucket] = row.get(bucket, 0) + 1
        row["total"] += 1
    for defect in defects:
        day = _date_key(getattr(defect, "created_at", None))
        row = rows[day]
        row["defects"] += 1
        if not _is_closed_status(getattr(defect, "status", None)):
            row["open_defects"] += 1
    trend = []
    keys = sorted(rows)
    if recent_days and recent_days > 0:
        keys = keys[-recent_days:]
    for day in keys:
        row = rows[day]
        row["date"] = day
        row["pass_rate"] = _pass_rate(row.get("passed", 0), row.get("total", 0))
        trend.append(row)
    return {"trend": trend, "total_days": len(trend)}


def defect_loop_summary(records: list[Any], defects: list[Any], reminders: list[Any] | None = None) -> dict[str, Any]:
    open_items = [item for item in defects if not _is_closed_status(getattr(item, "status", None))]
    closed_items = [item for item in defects if _is_closed_status(getattr(item, "status", None))]
    by_severity = Counter(str(getattr(item, "severity", "normal") or "normal") for item in defects)
    linked = [item for item in defects if getattr(item, "case_id", None) is not None]
    failed_by_case: Counter[int] = Counter(
        int(getattr(item, "case_id"))
        for item in records
        if getattr(item, "case_id", None) is not None and status_bucket(getattr(item, "status", None)) in {"failed", "blocked"}
    )
    return sanitize_loop_payload(
        {
            "open": len(open_items),
            "closed": len(closed_items),
            "total": len(defects),
            "by_severity": dict(sorted(by_severity.items())),
            "retest_due": count_due_reminders(reminders or [], defects),
            "linked": len(linked),
            "unlinked": len(defects) - len(linked),
            "top_failed_cases": [
                {"case_id": case_id, "failed_or_blocked": count} for case_id, count in failed_by_case.most_common(10)
            ],
        }
    )


def count_due_reminders(reminders: list[Any], defects: list[Any]) -> int:
    defect_by_id = {getattr(item, "id", None): item for item in defects}
    now = datetime.now(timezone.utc)
    count = 0
    for reminder in reminders:
        detail = getattr(reminder, "detail", None) or {}
        if not isinstance(detail, dict):
            continue
        defect = defect_by_id.get(detail.get("defect_id"))
        if defect is not None and _is_closed_status(getattr(defect, "status", None)):
            continue
        due_at = _parse_datetime(detail.get("due_at"))
        if due_at and due_at <= now:
            count += 1
    return count


def remark_update_fields(data: dict[str, Any]) -> dict[str, Any]:
    keys = ("description", "steps", "expected_result", "impact", "retest_suggestion", "fix_hints", "note", "due_at", "assignee")
    return {key: data[key] for key in keys if key in data}


def _model_dict(model: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for column in model.__table__.columns:
        value = getattr(model, column.name)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        data[column.name] = value
    return data


def _is_sensitive_key(key: Any) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS) or lowered.endswith("_token") or lowered.endswith("-token")


def _safe_attr(item: Any | None, attr: str, default: Any = None) -> Any:
    return getattr(item, attr, default) if item is not None else default


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = redact_sensitive_text(str(value).strip())
        if text:
            return text
    return ""


def _normalize_steps(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (list, dict)):
                return _normalize_steps(parsed)
        except ValueError:
            return [redact_sensitive_text(line.strip()) for line in value.splitlines() if line.strip()]
    if isinstance(value, dict):
        return [_first_text(value.get("action"), value.get("step"), value.get("description"), value.get("text"), value)]
    if isinstance(value, list):
        steps: list[str] = []
        for item in value:
            if isinstance(item, dict):
                steps.append(_first_text(item.get("action"), item.get("step"), item.get("description"), item.get("text"), item))
            else:
                steps.append(_first_text(item))
        return [step for step in steps if step]
    return [_first_text(value)]


def _normalize_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [_first_text(item) for item in value if _first_text(item)]
    return [_first_text(value)]


def _suggest_severity(bucket: str, case: Any | None, actual: str) -> str:
    text = f"{_safe_attr(case, 'priority', '')} {actual}".lower()
    if any(marker in text for marker in ("p0", "critical", "security", "data loss", "payment", "crash")):
        return "critical"
    if bucket == "failed":
        return "major"
    if bucket == "blocked":
        return "normal"
    return "minor"


def _suggest_impact(bucket: str, case: Any | None, actual: str) -> str:
    if bucket == "blocked":
        return "Case execution is blocked, so release confidence for this path is unknown."
    if bucket == "skipped":
        return "Case was skipped and should not be counted as validated coverage."
    if any(marker in actual.lower() for marker in ("payment", "order", "cart")):
        return "Core checkout behavior may be affected."
    return "The linked requirement path may not meet acceptance expectations."


def _suggest_retest(bucket: str, case: Any | None) -> str:
    title = _safe_attr(case, "title", "the linked case")
    if bucket == "blocked":
        return f"Remove the blocking condition and rerun {title} with the same preconditions."
    if bucket == "skipped":
        return f"Confirm the skip reason, then rerun {title} before closing the loop."
    return f"After the fix is available, rerun {title} and attach fresh execution evidence."


def _suggest_fix_hints(bucket: str, actual: str) -> list[str]:
    if bucket == "blocked":
        return ["Check environment readiness and required test data.", "Confirm upstream dependency availability."]
    if bucket == "skipped":
        return ["Review whether the skip reason is still valid.", "Schedule execution before release sign-off."]
    hints = ["Compare actual behavior with the case expected result.", "Inspect recent changes around the affected requirement path."]
    if any(marker in actual.lower() for marker in ("timeout", "network", "http", "api")):
        hints.append("Check API response, timeout and retry handling.")
    return hints


def _normalize_due_at(value: Any) -> str:
    if value not in (None, ""):
        parsed = _parse_datetime(value)
        if parsed:
            return parsed.isoformat()
        return redact_sensitive_text(str(value))
    return (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _date_key(value: Any) -> str:
    parsed = _parse_datetime(value) if not isinstance(value, datetime) else value
    if parsed is None:
        return datetime.now(timezone.utc).date().isoformat()
    return parsed.date().isoformat()


def _empty_trend_row() -> dict[str, Any]:
    return {"passed": 0, "failed": 0, "blocked": 0, "skipped": 0, "total": 0, "defects": 0, "open_defects": 0, "pass_rate": 0.0}


def _pass_rate(passed: int, total: int) -> float:
    return round((passed / total) * 100, 2) if total else 0.0


def _is_closed_status(status: Any) -> bool:
    return str(status or "").strip().lower() in {"closed", "resolved", "done", "fixed", "verified"}
