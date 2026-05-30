from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from aitest_platform.models import PerfPlan, PerfResult
from aitest_platform.services.perf_runner import sanitize_perf_payload


class PerfPayloadError(ValueError):
    pass


SENSITIVE_MARKERS = (
    "authorization",
    "api_key",
    "api-key",
    "apikey",
    "token",
    "cookie",
    "secret",
    "password",
)
RUNNING_STATUSES = {"pending", "running"}
TERMINAL_STATUSES = {"completed", "failed", "error", "timeout"}
SUCCESS_STATUSES = {"completed", "passed", "success", "succeeded", "ok"}
FAIL_STATUSES = {"failed", "error", "timeout", "cancelled", "canceled"}
LOWER_IS_BETTER = {"avg_ms", "p50_ms", "p90_ms", "p95_ms", "p99_ms", "max_ms", "error_rate", "failed", "errors"}
HIGHER_IS_BETTER = {"tps", "rps", "throughput", "success_rate", "passed"}
TEMPLATE_INT_FIELDS = {
    "threads": (1, 100_000),
    "ramp_up_seconds": (0, 86_400),
    "duration_seconds": (1, 604_800),
    "loops": (1, 10_000_000),
}
TEMPLATE_FLOAT_FIELDS = {
    "tps": (0.0, 1_000_000.0),
    "rps": (0.0, 1_000_000.0),
}
TEMPLATE_TEXT_FIELDS = {"base_url", "path", "method", "label"}
METRIC_ALIASES = {
    "avg_ms": ("avg_ms", "average_ms", "avg", "mean_ms"),
    "p50_ms": ("p50_ms", "p50"),
    "p90_ms": ("p90_ms", "p90"),
    "p95_ms": ("p95_ms", "p95"),
    "p99_ms": ("p99_ms", "p99"),
    "max_ms": ("max_ms", "max"),
    "error_rate": ("error_rate", "errorRate"),
    "success_rate": ("success_rate", "successRate"),
    "tps": ("tps", "rps", "throughput", "requests_per_second"),
    "rps": ("rps", "tps", "throughput", "requests_per_second"),
    "throughput": ("throughput", "tps", "rps", "requests_per_second"),
    "failed": ("failed", "errors", "error_count"),
    "errors": ("errors", "failed", "error_count"),
    "passed": ("passed", "success_count"),
}
THRESHOLD_KEY_ALIASES = {
    "p95": "p95_ms",
    "p95ms": "p95_ms",
    "p95_ms": "p95_ms",
    "avg": "avg_ms",
    "avgms": "avg_ms",
    "avg_ms": "avg_ms",
    "average_ms": "avg_ms",
    "errorrate": "error_rate",
    "error_rate": "error_rate",
    "tps": "tps",
    "rps": "tps",
    "throughput": "tps",
    "p50": "p50_ms",
    "p50_ms": "p50_ms",
    "p90": "p90_ms",
    "p90_ms": "p90_ms",
    "p99": "p99_ms",
    "p99_ms": "p99_ms",
    "max": "max_ms",
    "max_ms": "max_ms",
    "success_rate": "success_rate",
    "successrate": "success_rate",
}
AUTH_VALUE_RE = re.compile(r"(?i)\b(?:bearer|basic)\s+[^\s,;}\"']+")


def normalize_plan_schema_template_params(plan_schema: Any) -> dict[str, Any]:
    if plan_schema in (None, ""):
        return {}
    if not isinstance(plan_schema, dict):
        raise PerfPayloadError("plan_schema must be an object")
    schema = dict(plan_schema)
    if "template_params" in schema:
        schema["template_params"] = sanitize_jmeter_template_params(schema.get("template_params"))
    return sanitize_perf_payload(schema)


def merge_jmeter_template_params(plan_schema: Any, payload: dict[str, Any]) -> dict[str, Any]:
    schema = normalize_plan_schema_template_params(plan_schema)
    current = sanitize_jmeter_template_params(schema.get("template_params") or {})
    updates_source = payload.get("template_params") if isinstance(payload.get("template_params"), dict) else payload
    updates = sanitize_jmeter_template_params(updates_source)
    merged = {**current, **updates}
    if "headers" in updates:
        merged["headers"] = updates["headers"]
    if "thresholds" in updates:
        merged["thresholds"] = updates["thresholds"]
    schema["template_params"] = sanitize_jmeter_template_params(merged)
    return sanitize_perf_payload(schema)


def template_params_from_schema(plan_schema: Any) -> dict[str, Any]:
    if not isinstance(plan_schema, dict):
        return {}
    return sanitize_jmeter_template_params(plan_schema.get("template_params") or {})


def sanitize_jmeter_template_params(raw: Any) -> dict[str, Any]:
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise PerfPayloadError("template_params must be an object")
    params: dict[str, Any] = {}
    for key, (minimum, maximum) in TEMPLATE_INT_FIELDS.items():
        if key in raw:
            params[key] = _coerce_int(raw[key], key, minimum, maximum)
    for key, (minimum, maximum) in TEMPLATE_FLOAT_FIELDS.items():
        if key in raw:
            params[key] = _coerce_float(raw[key], key, minimum, maximum)
    for key in TEMPLATE_TEXT_FIELDS:
        if key not in raw:
            continue
        value = _safe_text(raw[key], max_length=2048 if key == "base_url" else 256)
        if key == "base_url":
            value = _sanitize_url(value)
        if value:
            params[key] = value
    if "headers" in raw:
        params["headers"] = _sanitize_headers(raw.get("headers"))
    if "thresholds" in raw:
        params["thresholds"] = normalize_thresholds(raw.get("thresholds"))
    return sanitize_perf_payload(params)


def resolve_thresholds(plan_schema: Any, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    schema = plan_schema if isinstance(plan_schema, dict) else {}
    for candidate in (
        schema.get("targets"),
        schema.get("thresholds"),
        (schema.get("template_params") or {}).get("thresholds") if isinstance(schema.get("template_params"), dict) else None,
    ):
        merged.update(normalize_thresholds(candidate))
    data = payload or {}
    if isinstance(data.get("template_params"), dict):
        merged.update(normalize_thresholds(data["template_params"].get("thresholds")))
    if "thresholds" in data:
        merged.update(normalize_thresholds(data.get("thresholds")))
    return sanitize_perf_payload(merged)


def normalize_thresholds(raw: Any) -> dict[str, Any]:
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise PerfPayloadError("thresholds must be an object")
    thresholds: dict[str, Any] = {}
    for raw_key, raw_value in raw.items():
        metric = _normalize_threshold_metric(raw_key)
        if metric is None:
            continue
        direction = _threshold_direction(metric, raw_value)
        value = _threshold_value(metric, raw_value, direction)
        thresholds[metric] = {
            "metric": metric,
            "threshold": value,
            "direction": direction,
        }
    return thresholds


def apply_thresholds(summary_data: dict[str, Any], thresholds: dict[str, Any]) -> tuple[dict[str, Any], str]:
    summary = dict(summary_data or {})
    evaluation = evaluate_thresholds(summary, thresholds)
    summary["threshold_status"] = evaluation["status"]
    summary["threshold_results"] = evaluation["results"]
    summary["threshold_violation_count"] = evaluation["violation_count"]
    return sanitize_perf_payload(summary), evaluation["status"]


def evaluate_thresholds(summary_data: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    if not thresholds:
        return {"status": "not_configured", "results": [], "violation_count": 0}
    results: list[dict[str, Any]] = []
    for metric, config in thresholds.items():
        threshold = config.get("threshold") if isinstance(config, dict) else config
        direction = config.get("direction") if isinstance(config, dict) else _default_direction(metric)
        actual = _metric_value(summary_data, metric)
        passed = False
        reason = None
        if actual is None:
            reason = "metric_missing"
        elif direction == "min":
            passed = actual >= threshold
        else:
            passed = actual <= threshold
        delta = None if actual is None else round(actual - threshold, 6)
        results.append(
            {
                "metric": metric,
                "actual": actual,
                "threshold": threshold,
                "direction": direction,
                "passed": passed,
                "delta": delta,
                "reason": reason,
            }
        )
    violation_count = sum(1 for item in results if not item["passed"])
    return {"status": "failed" if violation_count else "passed", "results": results, "violation_count": violation_count}


def status_after_thresholds(current_status: str, threshold_status: str) -> str:
    normalized = _norm(current_status)
    if threshold_status == "failed" and normalized in SUCCESS_STATUSES:
        return "failed"
    return current_status


def render_jmeter_script(plan_schema: Any, fallback_jmx: str | None = None) -> str:
    params = template_params_from_schema(plan_schema)
    if not params:
        fallback = str(fallback_jmx or "").strip()
        return fallback or "<jmeterTestPlan version=\"1.2\"><hashTree /></jmeterTestPlan>"

    root = ET.Element("jmeterTestPlan", version="1.2", properties="5.0", jmeter="aitest-platform")
    root_tree = ET.SubElement(root, "hashTree")
    test_plan = ET.SubElement(root_tree, "TestPlan", guiclass="TestPlanGui", testclass="TestPlan", testname="AI Test Platform Performance Plan", enabled="true")
    ET.SubElement(test_plan, "stringProp", name="TestPlan.comments").text = "Generated from non-sensitive JMeter template parameters."
    ET.SubElement(test_plan, "boolProp", name="TestPlan.functional_mode").text = "false"
    ET.SubElement(test_plan, "boolProp", name="TestPlan.serialize_threadgroups").text = "false"
    variables = ET.SubElement(test_plan, "elementProp", name="TestPlan.user_defined_variables", elementType="Arguments")
    ET.SubElement(variables, "collectionProp", name="Arguments.arguments")
    test_plan_tree = ET.SubElement(root_tree, "hashTree")

    thread_group = ET.SubElement(
        test_plan_tree,
        "ThreadGroup",
        guiclass="ThreadGroupGui",
        testclass="ThreadGroup",
        testname=str(params.get("label") or "load-test"),
        enabled="true",
    )
    ET.SubElement(thread_group, "stringProp", name="ThreadGroup.num_threads").text = str(params.get("threads", 1))
    ET.SubElement(thread_group, "stringProp", name="ThreadGroup.ramp_time").text = str(params.get("ramp_up_seconds", 1))
    ET.SubElement(thread_group, "boolProp", name="ThreadGroup.scheduler").text = "true"
    ET.SubElement(thread_group, "stringProp", name="ThreadGroup.duration").text = str(params.get("duration_seconds", 60))
    loop_controller = ET.SubElement(thread_group, "elementProp", name="ThreadGroup.main_controller", elementType="LoopController")
    ET.SubElement(loop_controller, "boolProp", name="LoopController.continue_forever").text = "false"
    ET.SubElement(loop_controller, "stringProp", name="LoopController.loops").text = str(params.get("loops", 1))
    thread_tree = ET.SubElement(test_plan_tree, "hashTree")

    base_url = str(params.get("base_url") or "")
    parsed = urlparse(base_url)
    sampler = ET.SubElement(thread_tree, "HTTPSamplerProxy", guiclass="HttpTestSampleGui", testclass="HTTPSamplerProxy", testname="HTTP Request", enabled="true")
    ET.SubElement(sampler, "stringProp", name="HTTPSampler.protocol").text = parsed.scheme or "https"
    ET.SubElement(sampler, "stringProp", name="HTTPSampler.domain").text = parsed.netloc or parsed.path.strip("/")
    ET.SubElement(sampler, "stringProp", name="HTTPSampler.path").text = str(params.get("path") or (parsed.path if parsed.netloc else "/") or "/")
    ET.SubElement(sampler, "stringProp", name="HTTPSampler.method").text = str(params.get("method") or "GET").upper()
    ET.SubElement(sampler, "boolProp", name="HTTPSampler.follow_redirects").text = "true"
    sampler_tree = ET.SubElement(thread_tree, "hashTree")

    headers = params.get("headers") if isinstance(params.get("headers"), dict) else {}
    if headers:
        header_manager = ET.SubElement(sampler_tree, "HeaderManager", guiclass="HeaderPanel", testclass="HeaderManager", testname="HTTP Headers", enabled="true")
        header_collection = ET.SubElement(header_manager, "collectionProp", name="HeaderManager.headers")
        for name, value in sorted(headers.items()):
            header = ET.SubElement(header_collection, "elementProp", name=str(name), elementType="Header")
            ET.SubElement(header, "stringProp", name="Header.name").text = str(name)
            ET.SubElement(header, "stringProp", name="Header.value").text = str(value)
        ET.SubElement(sampler_tree, "hashTree")

    thresholds = params.get("thresholds") if isinstance(params.get("thresholds"), dict) else {}
    if thresholds:
        comments = ET.SubElement(test_plan, "stringProp", name="TestPlan.thresholds")
        comments.text = ",".join(f"{key}:{item.get('direction')}:{item.get('threshold')}" for key, item in sorted(thresholds.items()))

    xml_body = ET.tostring(root, encoding="unicode", short_empty_elements=True)
    return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" + sanitize_perf_payload(xml_body)


def abort_perf_result(result: PerfResult, reason: Any = None) -> dict[str, Any]:
    status = _norm(result.status)
    if status in {"cancelled", "canceled"}:
        return {"aborted": True, "idempotent": True, "status": result.status}
    if status not in RUNNING_STATUSES:
        raise PerfPayloadError(f"PerfResult({result.id}) status {result.status} cannot be aborted")

    safe_reason = _safe_text(reason or "manual_abort", max_length=1000) or "manual_abort"
    cancelled_at = datetime.now(timezone.utc).isoformat()
    result.status = "cancelled"
    result.summary_data = sanitize_perf_payload(
        {
            **(result.summary_data or {}),
            "status_reason": "cancelled",
            "abort": {"reason": safe_reason, "cancelled_at": cancelled_at},
        }
    )
    errors = list(result.error_details or [])
    errors.append({"type": "abort", "reason": safe_reason, "cancelled_at": cancelled_at})
    result.error_details = sanitize_perf_payload(errors)
    return {"aborted": True, "idempotent": False, "status": result.status, "reason": safe_reason}


def compare_perf_results(plan: PerfPlan, current: PerfResult, baseline: PerfResult) -> dict[str, Any]:
    if current.plan_id != plan.id or baseline.plan_id != plan.id:
        raise PerfPayloadError("baseline and current result must belong to the requested plan")
    if current.project_id != plan.project_id or baseline.project_id != plan.project_id:
        raise PerfPayloadError("baseline and current result must belong to the requested project")
    comparison = _compare_summaries(current.summary_data or {}, baseline.summary_data or {})
    return sanitize_perf_payload(
        {
            "plan_id": plan.id,
            "project_id": plan.project_id,
            "baseline": _result_snapshot(baseline),
            "current": _result_snapshot(current),
            "delta": comparison["delta"],
            "regressions": comparison["regressions"],
        }
    )


def project_performance_trend(session: Session, project_id: int, days: int = 7) -> dict[str, Any]:
    day_count = max(1, min(90, int(days or 7)))
    end_day = datetime.now(timezone.utc).date()
    start_day = end_day - timedelta(days=day_count - 1)
    rows = list(
        session.scalars(
            select(PerfResult)
            .where(PerfResult.project_id == project_id)
            .order_by(PerfResult.executed_at.desc(), PerfResult.id.desc())
        )
    )
    buckets: dict[date, list[PerfResult]] = {start_day + timedelta(days=offset): [] for offset in range(day_count)}
    for result in rows:
        result_day = _result_day(result)
        if start_day <= result_day <= end_day:
            buckets[result_day].append(result)

    items = [_trend_bucket(day, buckets[day]) for day in sorted(buckets)]
    all_results = [result for day in sorted(buckets) for result in buckets[day]]
    p95_values = [_metric_value(result.summary_data or {}, "p95_ms") for result in all_results]
    error_values = [_metric_value(result.summary_data or {}, "error_rate") for result in all_results]
    latest = max(all_results, key=lambda item: (_coerce_datetime(item.executed_at), item.id), default=None)
    summary = {
        "days": day_count,
        "total": len(all_results),
        "result_count": len(all_results),
        "passed": sum(_is_passed_result(result) for result in all_results),
        "failed": sum(_is_failed_result(result) for result in all_results),
        "threshold_failed_count": sum(_has_threshold_failure(result) for result in all_results),
        "regression_count": sum(_regression_count(result) for result in all_results),
        "avg_p95_ms": _average([value for value in p95_values if value is not None]),
        "max_p95_ms": _max_or_none([value for value in p95_values if value is not None]),
        "avg_error_rate": _average([value for value in error_values if value is not None], digits=6),
        "latest_result_id": latest.id if latest else None,
    }
    return sanitize_perf_payload(
        {
            "project_id": project_id,
            "days": day_count,
            "start_date": start_day.isoformat(),
            "end_date": end_day.isoformat(),
            "items": items,
            "summary": summary,
        }
    )


def build_performance_summary(results: list[PerfResult]) -> dict[str, Any]:
    if not results:
        return {
            "latest_result_id": None,
            "latest_status": None,
            "latest_p95_ms": None,
            "latest_error_rate": None,
            "result_count": 0,
            "threshold_status": "not_configured",
            "threshold_violations": [],
            "history_regressions": [],
            "trend_status": "insufficient_data",
        }
    latest = results[0]
    latest_summary = latest.summary_data or {}
    previous_same_plan = next((item for item in results[1:] if item.plan_id == latest.plan_id), None)
    history = _compare_summaries(latest_summary, previous_same_plan.summary_data or {}) if previous_same_plan else {"delta": {}, "regressions": []}
    trend = _trend_signal(results)
    threshold_results = latest_summary.get("threshold_results") if isinstance(latest_summary.get("threshold_results"), list) else []
    threshold_violations = [item for item in threshold_results if isinstance(item, dict) and not item.get("passed")]
    status_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
    return sanitize_perf_payload(
        {
            "latest_result_id": latest.id,
            "latest_status": latest.status,
            "latest_avg_ms": _metric_value(latest_summary, "avg_ms"),
            "latest_p95_ms": _metric_value(latest_summary, "p95_ms"),
            "latest_error_rate": _metric_value(latest_summary, "error_rate"),
            "latest_tps": _metric_value(latest_summary, "tps"),
            "latest_success_rate": _metric_value(latest_summary, "success_rate"),
            "result_count": len(results),
            "status_counts": status_counts,
            "threshold_status": latest_summary.get("threshold_status") or "not_configured",
            "threshold_violations": threshold_violations,
            "history_baseline_result_id": previous_same_plan.id if previous_same_plan else None,
            "history_delta": history["delta"],
            "history_regressions": history["regressions"],
            "trend_status": trend["status"],
            "trend_detail": trend,
        }
    )


def performance_risk_items(performance_summary: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    violations = performance_summary.get("threshold_violations") or []
    if violations:
        metrics = ", ".join(str(item.get("metric")) for item in violations[:5])
        risks.append(
            {
                "level": "high",
                "title": "Performance thresholds failed",
                "detail": f"Latest performance result violated thresholds: {metrics}.",
                "source": "performance_threshold",
            }
        )
    regressions = performance_summary.get("history_regressions") or []
    if regressions:
        metrics = ", ".join(str(item.get("metric")) for item in regressions[:5])
        risks.append(
            {
                "level": "medium",
                "title": "Performance regressed from baseline",
                "detail": f"Latest result regressed against previous result on: {metrics}.",
                "source": "performance_compare",
            }
        )
    if performance_summary.get("trend_status") == "worsening":
        risks.append(
            {
                "level": "medium",
                "title": "Performance trend is worsening",
                "detail": "Recent P95 latency or error rate is higher than the earlier comparison window.",
                "source": "performance_trend",
            }
        )
    return sanitize_perf_payload(risks)


def performance_recommendations(performance_summary: dict[str, Any]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    if performance_summary.get("threshold_violations"):
        recommendations.append(
            {
                "priority": "high",
                "title": "Stabilize threshold violations before release",
                "action": "Inspect slow/error samples, confirm load model parameters, then rerun the same JMeter script after fixes.",
            }
        )
    if performance_summary.get("history_regressions"):
        recommendations.append(
            {
                "priority": "medium",
                "title": "Compare against the baseline run",
                "action": "Review changes between baseline and current result, especially dependency, cache, database, and external API changes.",
            }
        )
    if performance_summary.get("trend_status") == "worsening":
        recommendations.append(
            {
                "priority": "medium",
                "title": "Add recurring trend monitoring",
                "action": "Run a daily short load test and alert on P95 latency or error-rate growth before it becomes a release blocker.",
            }
        )
    if not recommendations and performance_summary.get("latest_result_id"):
        recommendations.append(
            {
                "priority": "low",
                "title": "Keep the current baseline fresh",
                "action": "Mark a stable result as baseline and compare future runs before major releases.",
            }
        )
    return sanitize_perf_payload(recommendations)


def _sanitize_headers(raw: Any) -> dict[str, str]:
    if raw in (None, ""):
        return {}
    pairs: list[tuple[Any, Any]]
    if isinstance(raw, dict):
        pairs = list(raw.items())
    elif isinstance(raw, list):
        pairs = []
        for item in raw:
            if isinstance(item, dict):
                pairs.append((item.get("name") or item.get("key"), item.get("value")))
    else:
        raise PerfPayloadError("headers must be an object or a list of name/value objects")
    headers: dict[str, str] = {}
    for name, value in pairs:
        key = _safe_text(name, max_length=128)
        if not key or _is_sensitive_key(key):
            continue
        safe_value = _safe_text(value, max_length=2048)
        if not safe_value or _looks_sensitive_text(safe_value):
            continue
        headers[key] = safe_value
    return headers


def _normalize_threshold_metric(key: Any) -> str | None:
    normalized = re.sub(r"[^a-z0-9_]+", "", str(key or "").strip().lower())
    return THRESHOLD_KEY_ALIASES.get(normalized)


def _threshold_value(metric: str, raw_value: Any, direction: str) -> float:
    source = raw_value
    if isinstance(raw_value, dict):
        if "value" in raw_value:
            source = raw_value["value"]
        elif direction == "min" and "min" in raw_value:
            source = raw_value["min"]
        elif direction == "max" and "max" in raw_value:
            source = raw_value["max"]
        elif "threshold" in raw_value:
            source = raw_value["threshold"]
    value = _coerce_float(source, f"thresholds.{metric}", 0.0, 1_000_000_000.0)
    if metric == "error_rate" and value > 1:
        raise PerfPayloadError("thresholds.error_rate must be between 0 and 1")
    return value


def _threshold_direction(metric: str, raw_value: Any) -> str:
    if isinstance(raw_value, dict):
        operator = str(raw_value.get("operator") or raw_value.get("direction") or "").strip().lower()
        if operator in {"min", ">=", "greater_equal", "at_least"}:
            return "min"
        if operator in {"max", "<=", "less_equal", "at_most"}:
            return "max"
    return _default_direction(metric)


def _default_direction(metric: str) -> str:
    if metric in HIGHER_IS_BETTER:
        return "min"
    return "max"


def _metric_value(summary: dict[str, Any], metric: str) -> float | None:
    aliases = METRIC_ALIASES.get(metric, (metric,))
    for key in aliases:
        value = summary.get(key)
        if value is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric):
            return numeric
    return None


def _compare_summaries(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    metrics = sorted(set(METRIC_ALIASES) | set(current) | set(baseline))
    delta: dict[str, Any] = {}
    regressions: list[dict[str, Any]] = []
    for metric in metrics:
        current_value = _metric_value(current, metric)
        baseline_value = _metric_value(baseline, metric)
        if current_value is None or baseline_value is None:
            continue
        raw_delta = round(current_value - baseline_value, 6)
        percent = None if baseline_value == 0 else round(raw_delta * 100 / abs(baseline_value), 2)
        direction = _default_direction(metric)
        regressed = raw_delta < 0 if direction == "min" else raw_delta > 0
        delta[metric] = {
            "baseline": baseline_value,
            "current": current_value,
            "absolute": raw_delta,
            "percent": percent,
            "direction": direction,
        }
        if regressed:
            regressions.append(
                {
                    "metric": metric,
                    "baseline": baseline_value,
                    "current": current_value,
                    "delta": raw_delta,
                    "percent": percent,
                    "direction": direction,
                }
            )
    return {"delta": delta, "regressions": regressions}


def _trend_signal(results: list[PerfResult]) -> dict[str, Any]:
    finished = [result for result in results if _metric_value(result.summary_data or {}, "p95_ms") is not None or _metric_value(result.summary_data or {}, "error_rate") is not None]
    if len(finished) < 4:
        return {"status": "insufficient_data", "sample_count": len(finished)}
    ordered = list(reversed(finished[:14]))
    midpoint = len(ordered) // 2
    earlier = ordered[:midpoint]
    recent = ordered[midpoint:]
    early_p95 = _average([_metric_value(item.summary_data or {}, "p95_ms") for item in earlier if _metric_value(item.summary_data or {}, "p95_ms") is not None])
    recent_p95 = _average([_metric_value(item.summary_data or {}, "p95_ms") for item in recent if _metric_value(item.summary_data or {}, "p95_ms") is not None])
    early_error = _average([_metric_value(item.summary_data or {}, "error_rate") for item in earlier if _metric_value(item.summary_data or {}, "error_rate") is not None], digits=6)
    recent_error = _average([_metric_value(item.summary_data or {}, "error_rate") for item in recent if _metric_value(item.summary_data or {}, "error_rate") is not None], digits=6)
    worsening = _is_growth_bad(early_p95, recent_p95, 0.1) or _is_growth_bad(early_error, recent_error, 0.1)
    return {
        "status": "worsening" if worsening else "stable",
        "sample_count": len(finished),
        "earlier_avg_p95_ms": early_p95,
        "recent_avg_p95_ms": recent_p95,
        "earlier_avg_error_rate": early_error,
        "recent_avg_error_rate": recent_error,
    }


def _trend_bucket(day: date, results: list[PerfResult]) -> dict[str, Any]:
    p95_values = [_metric_value(result.summary_data or {}, "p95_ms") for result in results]
    error_values = [_metric_value(result.summary_data or {}, "error_rate") for result in results]
    latest = max(results, key=lambda item: (_coerce_datetime(item.executed_at), item.id), default=None)
    return {
        "date": day.isoformat(),
        "total": len(results),
        "passed": sum(_is_passed_result(result) for result in results),
        "failed": sum(_is_failed_result(result) for result in results),
        "threshold_failed_count": sum(_has_threshold_failure(result) for result in results),
        "regression_count": sum(_regression_count(result) for result in results),
        "avg_p95_ms": _average([value for value in p95_values if value is not None]),
        "max_p95_ms": _max_or_none([value for value in p95_values if value is not None]),
        "avg_error_rate": _average([value for value in error_values if value is not None], digits=6),
        "latest_result_id": latest.id if latest else None,
    }


def _result_snapshot(result: PerfResult) -> dict[str, Any]:
    return {
        "id": result.id,
        "plan_id": result.plan_id,
        "project_id": result.project_id,
        "status": result.status,
        "summary_data": result.summary_data or {},
        "executed_at": result.executed_at.isoformat() if hasattr(result.executed_at, "isoformat") else result.executed_at,
    }


def _is_passed_result(result: PerfResult) -> int:
    summary = result.summary_data or {}
    return int(_norm(result.status) in SUCCESS_STATUSES and summary.get("threshold_status") != "failed")


def _is_failed_result(result: PerfResult) -> int:
    summary = result.summary_data or {}
    return int(_norm(result.status) in FAIL_STATUSES or summary.get("threshold_status") == "failed")


def _has_threshold_failure(result: PerfResult) -> int:
    summary = result.summary_data or {}
    if summary.get("threshold_status") == "failed":
        return 1
    threshold_results = summary.get("threshold_results")
    if isinstance(threshold_results, list):
        return int(any(isinstance(item, dict) and item.get("passed") is False for item in threshold_results))
    if isinstance(threshold_results, dict):
        return int(any(isinstance(item, dict) and item.get("passed") is False for item in threshold_results.values()))
    return 0


def _regression_count(result: PerfResult) -> int:
    summary = result.summary_data or {}
    comparison = summary.get("comparison")
    if not isinstance(comparison, dict):
        return 0
    regressions = comparison.get("regressions")
    return len(regressions) if isinstance(regressions, list) else 0


def _result_day(result: PerfResult) -> date:
    return _coerce_datetime(result.executed_at).date()


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _average(values: list[float | None], digits: int = 2) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return round(mean(clean), digits) if clean else None


def _max_or_none(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return round(max(clean), 2) if clean else None


def _is_growth_bad(old: float | None, new: float | None, ratio: float) -> bool:
    if old is None or new is None:
        return False
    if old == 0:
        return new > 0
    return new > old * (1 + ratio)


def _safe_text(value: Any, max_length: int) -> str:
    if value is None:
        return ""
    text = str(sanitize_perf_payload(value)).strip()
    if _looks_sensitive_text(text):
        return ""
    return text[:max_length]


def _sanitize_url(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    query = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True) if not _is_sensitive_key(key)]
    clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path or "", parsed.params, urlencode(query), ""))
    if _looks_sensitive_text(clean):
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "", "", "", "")) if parsed.netloc else ""
    return clean


def _coerce_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise PerfPayloadError(f"{name} must be an integer") from exc
    if number < minimum or number > maximum:
        raise PerfPayloadError(f"{name} must be between {minimum} and {maximum}")
    return number


def _coerce_float(value: Any, name: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PerfPayloadError(f"{name} must be a number") from exc
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise PerfPayloadError(f"{name} must be between {minimum} and {maximum}")
    return number


def _is_sensitive_key(key: str) -> bool:
    lowered = str(key or "").lower()
    return any(marker in lowered for marker in SENSITIVE_MARKERS) or lowered.endswith("_token") or lowered.endswith("-token")


def _looks_sensitive_text(value: str) -> bool:
    lowered = str(value or "").lower()
    return AUTH_VALUE_RE.search(value or "") is not None or any(marker in lowered for marker in ("token=", "api_key=", "apikey=", "password=", "secret=", "cookie="))


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()
