from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from aitest_platform.models import ApiEndpoint, ApiEnvironment, ApiExecution, ApiScenario, ApiSchedule, ApiTestCase
from aitest_platform.services.api_runner import run_api_request, sanitize_api_payload
from aitest_platform.services.api_scenario_runner import run_api_scenario

CASE_TARGET_TYPES = {"case", "api_case", "cases"}
SCENARIO_TARGET_TYPES = {"scenario", "scenarios"}
VARIABLE_PATTERN = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*}}")


def run_api_schedule(session: Any, schedule: ApiSchedule, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = payload or {}
    if not schedule.is_enabled and not bool(data.get("force")):
        return sanitize_api_payload(
            {
                "status": "skipped",
                "reason": "schedule_disabled",
                "schedule_id": schedule.id,
                "target_type": schedule.target_type,
                "executed": False,
                "last_result_updated": False,
            }
        )

    started = time.perf_counter()
    target_type = str(schedule.target_type or "").strip().lower()
    try:
        if target_type in CASE_TARGET_TYPES:
            items = _run_case_targets(session, schedule, data)
        elif target_type in SCENARIO_TARGET_TYPES:
            items = _run_scenario_targets(session, schedule, data)
        else:
            items = [_create_schedule_error_execution(session, schedule, f"Unsupported target_type: {schedule.target_type}")]
    except Exception as exc:  # Keep schedule endpoints from turning runner failures into 500s.
        items = [_create_schedule_error_execution(session, schedule, str(exc))]

    duration_ms = max(1, int((time.perf_counter() - started) * 1000))
    result = _summary(schedule, target_type, items, duration_ms)
    now = datetime.now(timezone.utc)
    schedule.last_run_at = now
    schedule.last_result = sanitize_api_payload(result)
    session.flush()
    return sanitize_api_payload(
        {
            "schedule_id": schedule.id,
            "executed": True,
            "last_run_at": now.isoformat(),
            "last_result": result,
            **result,
        }
    )


def run_due_api_schedules(session: Any, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = payload or {}
    force = bool(data.get("force"))
    stmt = select(ApiSchedule).where(
        ApiSchedule.is_deleted.is_(False),
        ApiSchedule.is_enabled.is_(True),
    )
    lib_id = data.get("lib_id") or data.get("libId")
    if lib_id is not None:
        try:
            stmt = stmt.where(ApiSchedule.lib_id == int(lib_id))
        except (TypeError, ValueError):
            return sanitize_api_payload({"executed": [], "skipped": [], "total": 0, "error": "lib_id must be an integer"})
    schedules = list(session.scalars(stmt.order_by(ApiSchedule.id)))
    executed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for schedule in schedules:
        if not force and (schedule.last_run_at is not None or str(schedule.cron_expression or "").strip() == "@manual"):
            skipped.append(
                sanitize_api_payload(
                    {
                        "schedule_id": schedule.id,
                        "status": "skipped",
                        "reason": "not_due",
                        "cron_expression": schedule.cron_expression,
                        "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
                    }
                )
            )
            continue
        try:
            executed.append(_compact_due_result(run_api_schedule(session, schedule, {**data, "force": True})))
        except Exception as exc:
            skipped.append(
                sanitize_api_payload(
                    {
                        "schedule_id": schedule.id,
                        "status": "error",
                        "reason": str(exc),
                    }
                )
            )
    return sanitize_api_payload({"executed": executed, "skipped": skipped, "total": len(schedules)})


def _compact_due_result(result: dict[str, Any]) -> dict[str, Any]:
    return sanitize_api_payload(
        {
            "schedule_id": result.get("schedule_id"),
            "status": result.get("status"),
            "executed": result.get("executed"),
            "target_type": result.get("target_type"),
            "total": result.get("total"),
            "passed": result.get("passed"),
            "failed": result.get("failed"),
            "error": result.get("error"),
        }
    )


def _run_case_targets(session: Any, schedule: ApiSchedule, payload: dict[str, Any]) -> list[dict[str, Any]]:
    environment = _resolve_environment(session, schedule.lib_id, payload)
    variables = _variables(environment, payload)
    stop_on_failure = bool(payload.get("stop_on_failure") or payload.get("stopOnFailure"))
    items: list[dict[str, Any]] = []
    stopped = False
    for case_id in _target_ids(schedule):
        if stopped:
            execution = _create_skipped_case_execution(session, schedule, case_id, environment)
            items.append({"execution_id": execution.id, "status": "skipped", "error": "stop_on_failure"})
            continue
        case = session.get(ApiTestCase, case_id)
        if case is None or getattr(case, "is_deleted", False) or case.lib_id != schedule.lib_id:
            execution = _create_schedule_error_execution(session, schedule, f"ApiTestCase({case_id}) not found")
            items.append({"execution_id": execution.id, "status": "error", "error": execution.error_message})
            if stop_on_failure:
                stopped = True
            continue
        endpoint = session.get(ApiEndpoint, case.endpoint_id)
        if endpoint is None or getattr(endpoint, "is_deleted", False):
            result = _error_result(f"ApiEndpoint({case.endpoint_id}) not found", {"case_id": case.id})
        elif environment is not None or payload.get("base_url") or payload.get("baseUrl"):
            result = run_api_request(_inject_variables(_api_case_payload(case, endpoint, environment, payload), variables))
        else:
            result = _placeholder_case_result(case, endpoint)
        result = _redact_variable_values(result, variables)
        execution = _create_case_execution(session, schedule, case, environment, result)
        status = str(result.get("status") or "error")
        items.append({"execution_id": execution.id, "status": status, "error": execution.error_message})
        if stop_on_failure and status in {"failed", "error"}:
            stopped = True
    return items


def _run_scenario_targets(session: Any, schedule: ApiSchedule, payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    stop_on_failure = bool(payload.get("stop_on_failure") or payload.get("stopOnFailure"))
    stopped = False
    for scenario_id in _target_ids(schedule):
        if stopped:
            execution = _create_schedule_error_execution(session, schedule, "stop_on_failure")
            execution.status = "skipped"
            execution.scenario_id = scenario_id
            items.append({"execution_id": execution.id, "status": "skipped", "error": "stop_on_failure"})
            continue
        scenario = session.get(ApiScenario, scenario_id)
        if scenario is None or scenario.lib_id != schedule.lib_id:
            execution = _create_schedule_error_execution(session, schedule, f"ApiScenario({scenario_id}) not found")
            items.append({"execution_id": execution.id, "status": "error", "error": execution.error_message})
            if stop_on_failure:
                stopped = True
            continue
        result = run_api_scenario(session, scenario, payload)
        execution_ids = _scenario_execution_ids(result)
        _mark_scenario_executions(session, schedule, execution_ids)
        status = _scenario_status(result)
        items.append({"execution_id": execution_ids[0] if execution_ids else None, "execution_ids": execution_ids, "status": status, "error": None})
        if stop_on_failure and status in {"failed", "error"}:
            stopped = True
    return items


def _resolve_environment(session: Any, lib_id: int, payload: dict[str, Any]) -> ApiEnvironment | None:
    environment_id = payload.get("environment_id") or payload.get("environmentId")
    if environment_id:
        try:
            environment = session.get(ApiEnvironment, int(environment_id))
        except (TypeError, ValueError):
            return None
        if environment is not None and not getattr(environment, "is_deleted", False):
            return environment
        return None
    return session.scalar(
        select(ApiEnvironment).where(
            ApiEnvironment.lib_id == lib_id,
            ApiEnvironment.is_active.is_(True),
            ApiEnvironment.is_deleted.is_(False),
        )
    )


def _variables(environment: ApiEnvironment | None, payload: dict[str, Any]) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    if environment and isinstance(environment.variables, dict):
        variables.update(environment.variables)
    if isinstance(payload.get("variables"), dict):
        variables.update(payload["variables"])
    return variables


def _target_ids(schedule: ApiSchedule) -> list[int]:
    ids: list[int] = []
    for item in schedule.target_ids or []:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return ids


def _api_case_payload(case: ApiTestCase, endpoint: ApiEndpoint, environment: ApiEnvironment | None, overrides: dict[str, Any]) -> dict[str, Any]:
    env_headers = environment.headers if environment else {}
    return {
        "method": overrides.get("method") or endpoint.method,
        "url": overrides.get("url"),
        "base_url": overrides.get("base_url") or overrides.get("baseUrl") or (environment.base_url if environment else None),
        "path": overrides.get("path") or endpoint.path,
        "headers": {**(env_headers or {}), **(case.request_headers or {}), **(overrides.get("headers") or {})},
        "query": overrides.get("query") or overrides.get("params") or case.request_query or {},
        "body": overrides["body"] if "body" in overrides else case.request_body,
        "content_type": overrides.get("content_type") or overrides.get("contentType") or case.content_type,
        "timeout_ms": overrides.get("timeout_ms") or overrides.get("timeoutMs"),
        "assertions": overrides.get("assertions") or case.assertions or [{"type": "status_code", "expected": case.expected_status}],
    }


def _inject_variables(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _inject_variables(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_inject_variables(item, variables) for item in value]
    if isinstance(value, str):
        return VARIABLE_PATTERN.sub(lambda match: str(variables.get(match.group(1), match.group(0))), value)
    return value


def _redact_variable_values(value: Any, variables: dict[str, Any]) -> Any:
    secret_values = [str(item) for key, item in variables.items() if _is_sensitive_variable(key, item)]
    if isinstance(value, dict):
        return {key: _redact_variable_values(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_variable_values(item, variables) for item in value]
    if isinstance(value, str):
        redacted = value
        for secret in secret_values:
            redacted = redacted.replace(secret, "***")
        return redacted
    return value


def _is_sensitive_variable(key: Any, value: Any) -> bool:
    if not isinstance(value, str) or len(value) < 3:
        return False
    lowered = str(key).lower()
    return any(part in lowered for part in ("authorization", "api_key", "api-key", "apikey", "token", "cookie", "secret", "password"))


def _placeholder_case_result(case: ApiTestCase, endpoint: ApiEndpoint) -> dict[str, Any]:
    return {
        "status": "passed",
        "request_snapshot": sanitize_api_payload(
            {
                "method": endpoint.method,
                "path": endpoint.path,
                "headers": case.request_headers,
                "query": case.request_query,
                "body": case.request_body,
                "placeholder": True,
            }
        ),
        "response_snapshot": {"status_code": case.expected_status, "body": {"placeholder": True}},
        "assertion_results": [{"type": "status_code", "passed": True, "expected": case.expected_status, "actual": case.expected_status}],
        "duration_ms": 20,
        "error_message": None,
    }


def _error_result(message: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "error",
        "request_snapshot": sanitize_api_payload(snapshot),
        "response_snapshot": None,
        "assertion_results": [],
        "duration_ms": 1,
        "error_message": sanitize_api_payload({"error": message})["error"],
    }


def _create_case_execution(
    session: Any,
    schedule: ApiSchedule,
    case: ApiTestCase,
    environment: ApiEnvironment | None,
    result: dict[str, Any],
) -> ApiExecution:
    execution = ApiExecution(
        lib_id=case.lib_id,
        endpoint_id=case.endpoint_id,
        case_id=case.id,
        environment_id=environment.id if environment else None,
        schedule_id=schedule.id,
        run_type="schedule_case",
        status=result.get("status") or "error",
        request_snapshot=sanitize_api_payload(result.get("request_snapshot")),
        response_snapshot=sanitize_api_payload(result.get("response_snapshot")),
        assertion_results=sanitize_api_payload(result.get("assertion_results") or []),
        duration_ms=result.get("duration_ms"),
        error_message=sanitize_api_payload({"error": result.get("error_message")}).get("error"),
    )
    session.add(execution)
    session.flush()
    return execution


def _create_skipped_case_execution(
    session: Any,
    schedule: ApiSchedule,
    case_id: int,
    environment: ApiEnvironment | None,
) -> ApiExecution:
    case = session.get(ApiTestCase, case_id)
    execution = ApiExecution(
        lib_id=schedule.lib_id,
        endpoint_id=case.endpoint_id if case else None,
        case_id=case.id if case else None,
        environment_id=environment.id if environment else None,
        schedule_id=schedule.id,
        run_type="schedule_case",
        status="skipped",
        request_snapshot={"reason": "stop_on_failure"},
        response_snapshot=None,
        assertion_results=[],
        duration_ms=0,
        error_message="stop_on_failure",
    )
    session.add(execution)
    session.flush()
    return execution


def _create_schedule_error_execution(session: Any, schedule: ApiSchedule, message: str) -> ApiExecution:
    execution = ApiExecution(
        lib_id=schedule.lib_id,
        schedule_id=schedule.id,
        run_type="schedule",
        status="error",
        request_snapshot=sanitize_api_payload({"target_type": schedule.target_type, "target_ids": schedule.target_ids}),
        response_snapshot=None,
        assertion_results=[],
        duration_ms=1,
        error_message=sanitize_api_payload({"error": message})["error"],
    )
    session.add(execution)
    session.flush()
    return execution


def _scenario_execution_ids(result: dict[str, Any]) -> list[int]:
    ids: list[int] = []
    for key in ("execution_id", "id"):
        if result.get(key):
            ids.append(int(result[key]))
            break
    for item in result.get("executions") or []:
        if isinstance(item, dict) and item.get("id"):
            ids.append(int(item["id"]))
    return list(dict.fromkeys(ids))


def _mark_scenario_executions(session: Any, schedule: ApiSchedule, execution_ids: list[int]) -> None:
    for execution_id in execution_ids:
        execution = session.get(ApiExecution, execution_id)
        if execution is None:
            continue
        execution.schedule_id = schedule.id
        execution.run_type = "schedule_scenario" if execution.scenario_id and not execution.case_id else "schedule_scenario_case"
        execution.request_snapshot = sanitize_api_payload(execution.request_snapshot)
        execution.response_snapshot = sanitize_api_payload(execution.response_snapshot)
        execution.assertion_results = sanitize_api_payload(execution.assertion_results or [])
        if execution.error_message:
            execution.error_message = sanitize_api_payload({"error": execution.error_message})["error"]
    session.flush()


def _scenario_status(result: dict[str, Any]) -> str:
    summary = result.get("summary") if isinstance(result, dict) else None
    if isinstance(summary, dict):
        return str(summary.get("status") or "error")
    return str(result.get("status") or "passed")


def _summary(schedule: ApiSchedule, target_type: str, items: list[dict[str, Any]], duration_ms: int) -> dict[str, Any]:
    total = len(items)
    passed = sum(1 for item in items if item.get("status") == "passed")
    failed = sum(1 for item in items if item.get("status") == "failed")
    error = sum(1 for item in items if item.get("status") == "error")
    status = "passed" if failed == 0 and error == 0 else "failed"
    if total == 0:
        status = "skipped"
    errors = [item.get("error") for item in items if item.get("error")]
    return sanitize_api_payload(
        {
            "status": status,
            "total": total,
            "passed": passed,
            "failed": failed,
            "error": error,
            "execution_ids": _summary_execution_ids(items),
            "target_type": target_type or schedule.target_type,
            "duration_ms": duration_ms,
            "errors": errors[:10],
        }
    )


def _summary_execution_ids(items: list[dict[str, Any]]) -> list[int]:
    execution_ids: list[int] = []
    for item in items:
        if item.get("execution_id"):
            execution_ids.append(int(item["execution_id"]))
        for execution_id in item.get("execution_ids") or []:
            execution_ids.append(int(execution_id))
    return list(dict.fromkeys(execution_ids))
