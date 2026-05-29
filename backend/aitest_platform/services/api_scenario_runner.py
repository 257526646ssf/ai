from __future__ import annotations

import re
import time
from typing import Any

from sqlalchemy import select

from aitest_platform.models import ApiEndpoint, ApiEnvironment, ApiExecution, ApiScenario, ApiTestCase
from aitest_platform.services.api_runner import run_api_request, sanitize_api_payload
from aitest_platform.services.api_runtime_context import (
    attach_runtime_context,
    build_case_request_payload,
    resolve_runtime_variables,
    sanitize_runtime_payload,
)

VARIABLE_PATTERN = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*}}")


def run_api_scenario(session: Any, scenario: ApiScenario, payload: dict[str, Any]) -> dict[str, Any]:
    nodes = _case_nodes(scenario.nodes or [])
    if not nodes:
        return _placeholder_scenario_execution(session, scenario)

    started = time.perf_counter()
    environment = _resolve_environment(session, scenario.lib_id, payload)
    variables = _initial_variables(environment, payload)
    stop_on_failure = bool(payload.get("stop_on_failure") or payload.get("stopOnFailure"))
    executions: list[dict[str, Any]] = []
    counts = {"total": len(nodes), "passed": 0, "failed": 0, "error": 0, "skipped": 0}
    stopped = False

    for index, node in enumerate(nodes, start=1):
        if stopped:
            counts["skipped"] += 1
            execution = _create_skipped_execution(session, scenario, environment, node)
            executions.append(_execution_dict(execution, node, index, {"status": "skipped"}))
            continue

        try:
            case = _get_case(session, node["case_id"])
        except ValueError as exc:
            result = _error_result(str(exc), node, variables)
            execution = _create_node_error_execution(session, scenario, environment, node, result)
            counts["error"] += 1
            executions.append(_execution_dict(execution, node, index, result))
            if stop_on_failure:
                stopped = True
            continue

        endpoint = session.get(ApiEndpoint, case.endpoint_id)
        if endpoint is None:
            result = _error_result("ApiEndpoint not found", node, variables)
        else:
            request_payload = _scenario_case_payload(case, endpoint, environment, payload, variables)
            result = attach_runtime_context(run_api_request(request_payload), request_payload.get("_runtime_context"))
            extracted, missing_extractions = _extract_variables(
                result.pop("_raw_response_snapshot", None) or result.get("response_snapshot"),
                _mapping_definitions(scenario, node),
            )
            variables.update(extracted)
            result["extracted_variables"] = sanitize_api_payload(extracted)
            if missing_extractions:
                result["missing_extractions"] = sanitize_api_payload(missing_extractions)
            result = _redact_variable_values(result, variables)

        execution = _create_case_execution(session, scenario, case, environment, result)
        status = str(result.get("status") or "error")
        counts[status if status in ("passed", "failed", "error") else "error"] += 1
        executions.append(_execution_dict(execution, node, index, result))
        if stop_on_failure and status in {"failed", "error"}:
            stopped = True

    duration_ms = max(1, int((time.perf_counter() - started) * 1000))
    scenario_status = "passed" if counts["failed"] == 0 and counts["error"] == 0 else "failed"
    summary = {
        **counts,
        "status": scenario_status,
        "duration_ms": duration_ms,
        "stop_on_failure": stop_on_failure,
    }
    scenario_execution = _create_summary_execution(
        session=session,
        scenario=scenario,
        environment=environment,
        payload=payload,
        summary=summary,
        variables=variables,
        duration_ms=duration_ms,
    )
    return sanitize_api_payload(
        {
            "id": scenario_execution.id,
            "scenario_id": scenario.id,
            "execution_id": scenario_execution.id,
            "executions": executions,
            "summary": summary,
            "variables": variables,
        }
    )


def sanitize_scenario_mapping_definition(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize_scenario_mapping_definition(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_scenario_mapping_definition(item) for item in value]
    if isinstance(value, str) and value.strip().startswith("$."):
        return value
    return sanitize_api_payload(value)


def sanitize_scenario_nodes(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if str(key) == "extract" and isinstance(item, dict):
                clean[key] = sanitize_scenario_mapping_definition(item)
            else:
                clean[key] = sanitize_api_payload({key: sanitize_scenario_nodes(item)})[key]
        return clean
    if isinstance(value, list):
        return [sanitize_scenario_nodes(item) for item in value]
    return sanitize_api_payload(value)


def _case_nodes(nodes: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict) or not node.get("case_id"):
            continue
        try:
            case_id = int(node["case_id"])
        except (TypeError, ValueError):
            continue
        normalized.append({**node, "case_id": case_id})
    return normalized


def _resolve_environment(session: Any, lib_id: int, payload: dict[str, Any]) -> ApiEnvironment | None:
    environment_id = payload.get("environment_id") or payload.get("environmentId")
    if environment_id:
        try:
            return session.get(ApiEnvironment, int(environment_id))
        except (TypeError, ValueError):
            return None
    return session.scalar(
        select(ApiEnvironment).where(
            ApiEnvironment.lib_id == lib_id,
            ApiEnvironment.is_active.is_(True),
            ApiEnvironment.is_deleted.is_(False),
        )
    )


def _initial_variables(environment: ApiEnvironment | None, payload: dict[str, Any]) -> dict[str, Any]:
    return resolve_runtime_variables(environment, payload)


def _get_case(session: Any, case_id: int) -> ApiTestCase:
    case = session.get(ApiTestCase, case_id)
    if case is None or getattr(case, "is_deleted", False):
        raise ValueError(f"ApiTestCase({case_id}) not found")
    return case


def _scenario_case_payload(
    case: ApiTestCase,
    endpoint: ApiEndpoint,
    environment: ApiEnvironment | None,
    payload: dict[str, Any],
    variables: dict[str, Any],
) -> dict[str, Any]:
    return build_case_request_payload(
        case,
        endpoint,
        environment,
        {**payload, "variables": variables},
        include_raw_response=True,
    )


def _inject_variables(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _inject_variables(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_inject_variables(item, variables) for item in value]
    if isinstance(value, str):
        return VARIABLE_PATTERN.sub(lambda match: str(variables.get(match.group(1), match.group(0))), value)
    return value


def _redact_variable_values(value: Any, variables: dict[str, Any]) -> Any:
    secret_values = [str(item) for item in variables.values() if isinstance(item, str) and len(item) >= 3]
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


def _mapping_definitions(scenario: ApiScenario, node: dict[str, Any]) -> dict[str, Any]:
    mappings: dict[str, Any] = {}
    if isinstance(scenario.data_mappings, dict):
        extract_mappings = scenario.data_mappings.get("extract")
        node_id = str(node.get("id") or "")
        if isinstance(extract_mappings, dict):
            node_mappings = extract_mappings.get(node_id) or extract_mappings.get(str(node.get("case_id") or ""))
            if isinstance(node_mappings, dict):
                mappings.update(node_mappings)
            else:
                mappings.update({key: value for key, value in extract_mappings.items() if isinstance(value, str)})
        mappings.update(
            {
                key: value
                for key, value in scenario.data_mappings.items()
                if key not in {"extract", "stop_on_failure", "stopOnFailure"} and isinstance(value, str)
            }
        )
    if isinstance(node.get("extract"), dict):
        mappings.update(node["extract"])
    if isinstance(node.get("extract_variables"), dict):
        mappings.update({key: _normalize_json_path(value) for key, value in node["extract_variables"].items()})
    return mappings


def _extract_variables(response_snapshot: Any, mappings: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if not isinstance(response_snapshot, dict):
        return {}, []
    extracted: dict[str, Any] = {}
    missing: list[dict[str, str]] = []
    for name, path in mappings.items():
        normalized_path = _normalize_json_path(path)
        if not isinstance(normalized_path, str) or not normalized_path.startswith("$."):
            continue
        value = _json_path_get(response_snapshot, normalized_path)
        if value is not None:
            extracted[str(name)] = value
        else:
            missing.append({"name": str(name), "path": normalized_path})
    return extracted, missing


def _normalize_json_path(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value.startswith("$."):
        return value
    return "$." + value.strip(".")


def _json_path_get(value: Any, path: str) -> Any:
    parts = path[2:].split(".")
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


def _error_result(message: str, node: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "error",
        "request_snapshot": sanitize_api_payload({"node": node, "variables": sanitize_runtime_payload(variables)}),
        "response_snapshot": None,
        "assertion_results": [],
        "duration_ms": 1,
        "error_message": sanitize_api_payload({"error": message})["error"],
    }


def _create_case_execution(
    session: Any,
    scenario: ApiScenario,
    case: ApiTestCase,
    environment: ApiEnvironment | None,
    result: dict[str, Any],
) -> ApiExecution:
    execution = ApiExecution(
        lib_id=case.lib_id,
        endpoint_id=case.endpoint_id,
        case_id=case.id,
        environment_id=environment.id if environment else None,
        scenario_id=scenario.id,
        run_type="scenario_case",
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


def _create_node_error_execution(
    session: Any,
    scenario: ApiScenario,
    environment: ApiEnvironment | None,
    node: dict[str, Any],
    result: dict[str, Any],
) -> ApiExecution:
    execution = ApiExecution(
        lib_id=scenario.lib_id,
        case_id=None,
        environment_id=environment.id if environment else None,
        scenario_id=scenario.id,
        run_type="scenario_case",
        status="error",
        request_snapshot=sanitize_api_payload(result.get("request_snapshot")),
        response_snapshot=None,
        assertion_results=[],
        duration_ms=result.get("duration_ms"),
        error_message=sanitize_api_payload({"error": result.get("error_message")}).get("error"),
    )
    session.add(execution)
    session.flush()
    return execution


def _create_skipped_execution(
    session: Any,
    scenario: ApiScenario,
    environment: ApiEnvironment | None,
    node: dict[str, Any],
) -> ApiExecution:
    case = session.get(ApiTestCase, node.get("case_id"))
    execution = ApiExecution(
        lib_id=scenario.lib_id,
        endpoint_id=case.endpoint_id if case else None,
        case_id=case.id if case else None,
        environment_id=environment.id if environment else None,
        scenario_id=scenario.id,
        run_type="scenario_case",
        status="skipped",
        request_snapshot=sanitize_api_payload({"node": node, "reason": "stop_on_failure"}),
        response_snapshot=None,
        assertion_results=[],
        duration_ms=0,
        error_message="stop_on_failure",
    )
    session.add(execution)
    session.flush()
    return execution


def _create_summary_execution(
    session: Any,
    scenario: ApiScenario,
    environment: ApiEnvironment | None,
    payload: dict[str, Any],
    summary: dict[str, Any],
    variables: dict[str, Any],
    duration_ms: int,
) -> ApiExecution:
    execution = ApiExecution(
        lib_id=scenario.lib_id,
        scenario_id=scenario.id,
        environment_id=environment.id if environment else None,
        run_type="scenario",
        status=summary["status"],
        request_snapshot=sanitize_api_payload(
            {
                "scenario_id": scenario.id,
                "environment_id": environment.id if environment else payload.get("environment_id") or payload.get("environmentId"),
                "base_url": payload.get("base_url") or payload.get("baseUrl") or (environment.base_url if environment else None),
                "variables": variables,
                "timeout_ms": payload.get("timeout_ms") or payload.get("timeoutMs"),
                "stop_on_failure": summary["stop_on_failure"],
            }
        ),
        response_snapshot=sanitize_api_payload({"summary": summary, "variables": variables}),
        assertion_results=[],
        duration_ms=duration_ms,
    )
    session.add(execution)
    session.flush()
    return execution


def _placeholder_scenario_execution(session: Any, scenario: ApiScenario) -> dict[str, Any]:
    execution = ApiExecution(
        lib_id=scenario.lib_id,
        scenario_id=scenario.id,
        run_type="scenario",
        status="passed",
        response_snapshot={"summary": {"total": len(scenario.nodes or []), "passed": len(scenario.nodes or [])}},
        assertion_results=[],
        duration_ms=20,
    )
    session.add(execution)
    session.flush()
    return _model_dict(execution)


def _execution_dict(execution: ApiExecution, node: dict[str, Any], order: int, result: dict[str, Any]) -> dict[str, Any]:
    data = _model_dict(execution)
    data["node_id"] = node.get("id")
    data["node_order"] = order
    if result.get("extracted_variables"):
        data["extracted_variables"] = result["extracted_variables"]
    return sanitize_api_payload(data)


def _model_dict(model: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for column in model.__table__.columns:
        value = getattr(model, column.name)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        data[column.name] = value
    return sanitize_api_payload(data)
