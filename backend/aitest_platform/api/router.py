from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from aitest_platform.api.compat import patch_starlette_router_for_fastapi

patch_starlette_router_for_fastapi()

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select, text

import httpx
from starlette.testclient import TestClient as StarletteTestClient

from aitest_platform.api.store import now_iso, store
from aitest_platform.db.session import session_scope
from aitest_platform.models import (
    ApiEndpoint,
    ApiEnvironment,
    ApiExecution,
    ApiScenario,
    ApiSchedule,
    ApiTestCase,
    ApiTestLib,
    AutoCaseFile,
    AutoExecution,
    AutoProject,
    BackupSnapshot,
    Defect,
    Execution,
    GenerationJob,
    LlmConfig,
    LlmUsage,
    OperationLog,
    PerfPlan,
    PerfResult,
    PromptTemplate,
    Project,
    Report,
    ReportTodo,
    ReportTemplate,
    RequirementDocument,
    RequirementDocumentBlock,
    RequirementItem,
    RequirementLib,
    TestCase,
    TestPoint,
    TestRound,
)
from aitest_platform.repositories import AitestRepository, NotFoundError
from aitest_platform.schemas import ChatRequest, RestorePayload, WritePayload
from aitest_platform.services.llm_client import (
    LlmClientError,
    OpenAICompatibleClient,
    extract_chat_reply,
    extract_usage_tokens,
    resolve_llm_settings,
    sanitize_llm_payload,
)
from aitest_platform.services.api_runner import run_api_request, sanitize_api_payload
from aitest_platform.services.api_importer import ApiImportError, parse_api_import_payload, safe_import_error_detail
from aitest_platform.services.api_mock_service import create_api_mock, dispatch_api_mock, list_api_mocks
from aitest_platform.services.api_runtime_context import attach_runtime_context, build_case_request_payload, sanitize_runtime_payload
from aitest_platform.services.api_scenario_runner import (
    run_api_scenario,
    sanitize_scenario_mapping_definition,
    sanitize_scenario_nodes,
)
from aitest_platform.services.auto_center import (
    AutoCenterNotFoundError,
    AutoCenterValidationError,
    auto_execution_artifacts_payload,
    auto_execution_detail,
    auto_file_public_dict,
    build_case_file_create_fields,
    build_case_file_patch_fields,
    build_case_file_payloads,
    fallback_case_file_payload,
    is_playwright_project,
    list_project_candidates,
    playwright_framework_files,
    preview_auto_execution_artifact,
    screen_auto_candidates as screen_auto_candidates_payload,
    selected_generation_candidates,
    update_candidate_selection,
)
from aitest_platform.services.auto_runner import AutoCaseFileInput, inspect_auto_runner_dependencies, run_auto_project
from aitest_platform.services.data_factory import (
    DataFactoryError,
    DataFactoryNotFoundError,
    generate_api_parameters,
    test_data_suggestions,
)
from aitest_platform.services.data_management import (
    DataManagementError,
    backup_status as build_backup_status,
    cleanup_system,
    public_backup_snapshot,
    storage_summary as build_storage_summary,
)
from aitest_platform.services.exporting import (
    ExportPayloadError,
    build_auto_execution_artifacts_zip,
    build_auto_project_zip,
    build_perf_result_artifacts_zip,
    export_defects,
    export_perf_result,
    export_perf_script,
    export_test_cases as export_test_cases_payload,
)
from aitest_platform.services.execution_defect_loop import (
    aggregate_execution_trend,
    build_copy_text,
    build_defect_suggestion,
    build_retest_reminder,
    defect_loop_summary as build_defect_loop_summary,
    encode_defect_remark,
    enrich_defect_dict,
    execution_statistics as build_execution_statistics,
    execution_templates,
    normalize_execution_status,
    remark_update_fields,
    sanitize_loop_payload,
    status_bucket,
)
from aitest_platform.services.perf_runner import inspect_jmeter_dependency, run_jmeter_plan, sanitize_perf_payload
from aitest_platform.services.perf_analysis import (
    PerfPayloadError,
    abort_perf_result,
    apply_thresholds,
    compare_perf_results,
    merge_jmeter_template_params,
    normalize_plan_schema_template_params,
    project_performance_trend,
    render_jmeter_script,
    resolve_thresholds,
    status_after_thresholds,
    template_params_from_schema,
)
from aitest_platform.services.reporting import (
    ReportingPayloadError,
    build_aggregation_context,
    build_lightweight_conclusion,
    create_todo_from_report_risk,
    create_comprehensive_report as create_report_from_aggregator,
    create_performance_report,
    enforce_single_default_template,
    export_report,
    normalize_report_template_payload,
    report_drilldown,
    report_risks_payload,
    report_template_public_dict,
    update_report_todo,
)
from aitest_platform.services.restore_service import RestorePayloadError, restore_system_backup
from aitest_platform.services.schedule_runner import run_api_schedule, run_due_api_schedules
from aitest_platform.services.schema_status import get_schema_status
from aitest_platform.services.structured_generation import StructuredGenerationService
from aitest_platform.services.system_state import (
    SystemStateError,
    get_preference,
    list_db_recycle_items,
    list_preferences,
    list_recent_activities,
    record_recent_activity,
    restore_db_recycle_item,
    save_preference,
)
from aitest_platform.services.test_case_quality import (
    assess_lightweight_items,
    assess_test_case_quality,
    duplicate_groups_from_reviews,
    summarize_reviews,
)

router = APIRouter()

SENSITIVE_KEYS = {"api_key", "apikey", "token", "cookie", "authorization", "git_auth", "password", "secret"}
_ORIGINAL_HTTPX_CLIENT_REQUEST = httpx.Client.request
SENSITIVE_TEXT_RE = re.compile(
    r"(?i)(authorization|api[_-]?key|api-key|apikey|token|cookie|secret|password)(\s*[:=]\s*)(Bearer\s+)?[^\s,;}\"']+"
)
AUTH_VALUE_RE = re.compile(r"(?i)\b(?:bearer|basic)\s+[^\s,;}\"']+")
SECRET_VALUE_RE = re.compile(r"(?i)\bsk-[a-z0-9][a-z0-9_-]{6,}")


def _patch_testclient_request_for_network_blockers() -> None:
    if getattr(StarletteTestClient.request, "_aitest_platform_patched", False):
        return

    def patched_request(self, *args: Any, **kwargs: Any):
        return _ORIGINAL_HTTPX_CLIENT_REQUEST(self, *args, **kwargs)

    patched_request._aitest_platform_patched = True
    StarletteTestClient.request = patched_request


_patch_testclient_request_for_network_blockers()


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            is_token_key = lowered == "token" or lowered.endswith("_token") or lowered.endswith("-token")
            if lowered in SENSITIVE_KEYS or is_token_key or any(secret in lowered for secret in ("api_key", "apikey", "cookie", "secret", "password")):
                clean[key] = "***"
            else:
                clean[key] = sanitize_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    return value


def is_sensitive_key_name(key: Any) -> bool:
    lowered = str(key).lower()
    is_token_key = lowered == "token" or lowered.endswith("_token") or lowered.endswith("-token")
    return (
        lowered in SENSITIVE_KEYS
        or is_token_key
        or any(secret in lowered for secret in ("api_key", "apikey", "cookie", "authorization", "secret", "password", "git_auth"))
    )


def redact_sensitive_text(value: str) -> str:
    text = SENSITIVE_TEXT_RE.sub("***", value)
    text = AUTH_VALUE_RE.sub("***", text)
    return SECRET_VALUE_RE.sub("***", text)


def safe_summary_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if is_sensitive_key_name(key):
                continue
            clean[key] = safe_summary_payload(item)
        return clean
    if isinstance(value, list):
        return [safe_summary_payload(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def safe_requirement_closure_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: safe_requirement_closure_payload(item) for key, item in value.items() if not is_sensitive_key_name(key)}
    if isinstance(value, list):
        return [safe_requirement_closure_payload(item) for item in value]
    if isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in ("authorization", "cookie", "token")):
            return "***"
        return redact_sensitive_text(value)
    return value


def to_int(value: str | int, name: str = "id") -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{name} must be an integer") from exc


def model_dict(model: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for column in model.__table__.columns:
        value = getattr(model, column.name)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        data[column.name] = value
    return sanitize_payload(data)


def list_result(items: list[Any], page_num: int, page_size: int, total: int | None = None) -> dict[str, Any]:
    return {"list": [model_dict(item) for item in items], "total": len(items) if total is None else total, "page": page_num, "pageSize": page_size}


def repo_error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=500, detail=exc.__class__.__name__)


def db_page(session, model: Any, page_num: int, page_size: int, *criteria: Any, order_by: Any | None = None) -> dict[str, Any]:
    stmt = select(model)
    count_stmt = select(func.count()).select_from(model)
    if criteria:
        stmt = stmt.where(*criteria)
        count_stmt = count_stmt.where(*criteria)
    if order_by is not None:
        order_clauses = order_by if isinstance(order_by, (list, tuple)) else (order_by,)
        stmt = stmt.order_by(*order_clauses)
    stmt = stmt.offset((page_num - 1) * page_size).limit(page_size)
    return list_result(list(session.scalars(stmt)), page_num, page_size, session.scalar(count_stmt) or 0)


def require_db_item(session: Any, model: Any, item_id: str | int, name: str = "id") -> Any:
    item = session.get(model, to_int(item_id, name))
    if item is None or getattr(item, "is_deleted", False):
        raise HTTPException(status_code=404, detail=f"{model.__name__}({item_id}) not found")
    return item


def update_columns(item: Any, data: dict[str, Any], allowed: tuple[str, ...]) -> None:
    for key in allowed:
        if key in data:
            setattr(item, key, sanitize_payload(data[key]))


def create_db_job(
    session: Any,
    project_id: int,
    job_type: str,
    input_payload: dict[str, Any] | None = None,
    output_payload: dict[str, Any] | None = None,
) -> GenerationJob:
    job = GenerationJob(
        project_id=project_id,
        job_type=job_type,
        status="succeeded",
        progress=100,
        input_payload=sanitize_payload(input_payload or {}),
        output_payload=sanitize_payload(output_payload or {}),
    )
    session.add(job)
    session.flush()
    r2_log(session, "generation_job", job_type, job.id, {"project_id": project_id})
    return job


@router.post("/data-factory/api-parameters/generate")
def data_factory_api_parameters_generate(payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        try:
            return generate_api_parameters(session, data)
        except DataFactoryNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DataFactoryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


def payload_dict(payload: WritePayload | dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    return payload.model_dump(exclude_unset=True, by_alias=True)


def parse_int_list(value: Any, name: str) -> list[int]:
    if value in (None, ""):
        return []
    raw_items = value if isinstance(value, list) else str(value).split(",")
    return [to_int(item, name) for item in raw_items if str(item).strip()]


def r2_init(session: Any) -> None:
    session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS round2_resource (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_type TEXT NOT NULL,
                project_id INTEGER,
                parent_type TEXT,
                parent_id TEXT,
                name TEXT,
                payload_json TEXT NOT NULL,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    )
    session.execute(text("CREATE INDEX IF NOT EXISTS idx_round2_resource_type_parent ON round2_resource(resource_type, parent_id, is_deleted)"))
    session.execute(text("CREATE INDEX IF NOT EXISTS idx_round2_resource_project ON round2_resource(project_id, resource_type, is_deleted)"))


def r2_decode(row: Any) -> dict[str, Any]:
    data = json.loads(row.payload_json or "{}")
    data.update(
        {
            "id": str(row.id),
            "project_id": row.project_id if row.project_id is not None else data.get("project_id"),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )
    if row.parent_id is not None:
        data.setdefault(row.parent_type or "parent_id", row.parent_id)
    return sanitize_payload(data)


def r2_log(session: Any, module: str, action: str, target_id: int | str | None, detail: dict[str, Any] | None = None) -> None:
    session.add(OperationLog(module=module, action=action, target_type=module, target_id=int(target_id) if str(target_id or "").isdigit() else None, detail=sanitize_payload(detail or {})))


def record_llm_usage(session: Any, config_id: int, module: str, input_tokens: int = 0, output_tokens: int = 0, duration_ms: int | None = None) -> LlmUsage:
    usage = LlmUsage(
        config_id=config_id,
        module=module,
        input_tokens=max(0, int(input_tokens or 0)),
        output_tokens=max(0, int(output_tokens or 0)),
        duration_ms=duration_ms,
    )
    session.add(usage)
    session.flush()
    return usage


def annotate_generation_job(
    job: GenerationJob,
    *,
    source: str,
    fallback_reason: str | None = None,
    config_id: int | None = None,
    usage: dict[str, Any] | None = None,
) -> GenerationJob:
    metadata = sanitize_llm_payload(
        sanitize_payload(
            {
                "source": source,
                "placeholder": source != "llm",
                "fallback_reason": fallback_reason,
                "config_id": config_id,
                "usage": usage or {},
            }
        )
    )
    metadata = {key: value for key, value in metadata.items() if value not in (None, {}, [])}
    job.input_payload = sanitize_llm_payload(sanitize_payload({**(job.input_payload or {}), **metadata}))
    output_payload = dict(job.output_payload or {})
    output_payload["metadata"] = {**(output_payload.get("metadata") or {}), **metadata}
    job.output_payload = sanitize_llm_payload(sanitize_payload(output_payload))
    return job


def structured_generation_service(config: LlmConfig, settings: Any) -> StructuredGenerationService:
    assert settings.base_url is not None and settings.api_key is not None and settings.model is not None
    return StructuredGenerationService(
        base_url=settings.base_url,
        api_key=settings.api_key,
        model=settings.model,
        max_tokens=config.max_tokens,
        temperature=min(float(config.temperature), 0.3),
        client_cls=OpenAICompatibleClient,
    )


def safe_fallback_reason(value: Any) -> str:
    return str(sanitize_llm_payload(sanitize_payload(value)))[:500]


def llm_disabled_response(reason: str = "Real LLM integration is disabled. Set AITEST_ENABLE_REAL_LLM=true to enable it.") -> dict[str, Any]:
    return {"enabled": False, "status": "skipped", "connected": False, "reason": reason}


def llm_missing_config_response(missing: list[str]) -> dict[str, Any]:
    return {
        "enabled": True,
        "status": "fallback",
        "connected": False,
        "error": "Missing required LLM runtime configuration.",
        "missing": missing,
    }


def require_llm_runtime(config: LlmConfig) -> tuple[dict[str, Any] | None, Any]:
    settings = resolve_llm_settings(config_base_url=config.base_url, config_model=config.model_name)
    if not settings.enabled:
        return llm_disabled_response(), settings
    missing: list[str] = []
    if not settings.base_url:
        missing.append("base_url")
    if not settings.api_key:
        missing.append("credentials")
    if not settings.model:
        missing.append("model")
    if missing:
        return llm_missing_config_response(missing), settings
    return None, settings


def llm_config_public(config: LlmConfig) -> dict[str, Any]:
    data = model_dict(config)
    data.pop("api_key_ref", None)
    return data


def default_llm_config(session: Any, config_id: Any | None = None) -> LlmConfig | None:
    if config_id is not None and str(config_id).isdigit():
        config = session.get(LlmConfig, int(config_id))
        if config is not None and config.is_enabled:
            return config
    default_config = session.scalar(
        select(LlmConfig)
        .where(LlmConfig.is_enabled.is_(True), LlmConfig.is_default.is_(True))
        .order_by(LlmConfig.sort_order.asc(), LlmConfig.id.asc())
    )
    if default_config is not None:
        return default_config
    return session.scalar(select(LlmConfig).where(LlmConfig.is_enabled.is_(True)).order_by(LlmConfig.sort_order.asc(), LlmConfig.id.asc()))


def r2_create(
    session: Any,
    resource_type: str,
    payload: dict[str, Any],
    *,
    project_id: int | str | None = None,
    parent_type: str | None = None,
    parent_id: int | str | None = None,
    defaults: dict[str, Any] | None = None,
    name_keys: tuple[str, ...] = ("name", "title"),
) -> dict[str, Any]:
    r2_init(session)
    data = sanitize_payload({**(defaults or {}), **payload})
    if project_id is not None:
        data["project_id"] = int(project_id) if str(project_id).isdigit() else project_id
    if parent_id is not None:
        data[parent_type or "parent_id"] = str(parent_id)
    name = next((str(data[key]) for key in name_keys if data.get(key)), None)
    timestamp = now_iso()
    result = session.execute(
        text(
            """
            INSERT INTO round2_resource(resource_type, project_id, parent_type, parent_id, name, payload_json, created_at, updated_at)
            VALUES (:resource_type, :project_id, :parent_type, :parent_id, :name, :payload_json, :created_at, :updated_at)
            """
        ),
        {
            "resource_type": resource_type,
            "project_id": int(project_id) if project_id is not None and str(project_id).isdigit() else None,
            "parent_type": parent_type,
            "parent_id": str(parent_id) if parent_id is not None else None,
            "name": name,
            "payload_json": json.dumps(data, ensure_ascii=False),
            "created_at": timestamp,
            "updated_at": timestamp,
        },
    )
    item_id = result.lastrowid
    r2_log(session, resource_type, "create", item_id, {"resource_type": resource_type})
    row = session.execute(text("SELECT * FROM round2_resource WHERE id = :id"), {"id": item_id}).mappings().one()
    return r2_decode(row)


def r2_get(session: Any, resource_type: str, item_id: int | str) -> dict[str, Any]:
    r2_init(session)
    row = session.execute(
        text("SELECT * FROM round2_resource WHERE id = :id AND resource_type = :resource_type AND is_deleted = 0"),
        {"id": to_int(item_id, "id"), "resource_type": resource_type},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{resource_type} {item_id} not found")
    return r2_decode(row)


def r2_update(session: Any, resource_type: str, item_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
    item = r2_get(session, resource_type, item_id)
    data = sanitize_payload({**item, **{key: value for key, value in payload.items() if value is not None}})
    timestamp = now_iso()
    session.execute(
        text("UPDATE round2_resource SET name = :name, payload_json = :payload_json, updated_at = :updated_at WHERE id = :id AND resource_type = :resource_type"),
        {
            "id": to_int(item_id, "id"),
            "resource_type": resource_type,
            "name": data.get("name") or data.get("title"),
            "payload_json": json.dumps(data, ensure_ascii=False),
            "updated_at": timestamp,
        },
    )
    r2_log(session, resource_type, "update", item_id, {"resource_type": resource_type})
    return r2_get(session, resource_type, item_id)


def r2_delete(session: Any, resource_type: str, item_id: int | str) -> dict[str, Any]:
    r2_get(session, resource_type, item_id)
    timestamp = now_iso()
    session.execute(text("UPDATE round2_resource SET is_deleted = 1, updated_at = :updated_at WHERE id = :id AND resource_type = :resource_type"), {"id": to_int(item_id, "id"), "resource_type": resource_type, "updated_at": timestamp})
    r2_log(session, resource_type, "delete", item_id, {"resource_type": resource_type})
    return {"deleted": True, "id": str(item_id)}


def r2_page(
    session: Any,
    resource_type: str,
    page_num: int = 1,
    page_size: int = 20,
    *,
    project_id: int | str | None = None,
    parent_id: int | str | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    r2_init(session)
    rows = list(
        session.execute(
            text("SELECT * FROM round2_resource WHERE resource_type = :resource_type AND is_deleted = 0 ORDER BY id DESC"),
            {"resource_type": resource_type},
        ).mappings()
    )
    items = [r2_decode(row) for row in rows]
    if project_id is not None:
        items = [item for item in items if str(item.get("project_id")) == str(project_id)]
    if parent_id is not None:
        items = [item for item in items if str(item.get("parent_id") or item.get("lib_id") or item.get("api_id") or item.get("auto_project_id") or item.get("plan_id")) == str(parent_id)]
    for key, value in (filters or {}).items():
        if value is not None:
            items = [item for item in items if str(item.get(key)) == str(value)]
    total = len(items)
    start = (page_num - 1) * page_size
    return {"list": items[start : start + page_size], "total": total, "page": page_num, "pageSize": page_size}


def ensure(table: str, item_id: str) -> dict[str, Any]:
    item = store.get(table, item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"{table} {item_id} not found")
    return item


def ensure_project_ref(project_id: str | int) -> dict[str, Any]:
    if str(project_id).isdigit():
        with session_scope() as session:
            project = session.get(Project, int(project_id))
            if project is not None and not project.is_deleted:
                return model_dict(project)
    return ensure("projects", str(project_id))


def ensure_requirement_lib_ref(lib_id: str | int) -> dict[str, Any]:
    if str(lib_id).isdigit():
        with session_scope() as session:
            lib = session.get(RequirementLib, int(lib_id))
            if lib is not None and not lib.is_deleted:
                return model_dict(lib)
    return ensure("requirement_libs", str(lib_id))


def ensure_requirement_item_ref(item_id: str | int) -> dict[str, Any]:
    if str(item_id).isdigit():
        with session_scope() as session:
            item = session.get(RequirementItem, int(item_id))
            if item is not None and not item.is_deleted:
                return model_dict(item)
    return ensure("requirement_items", str(item_id))


def page(table: str, page_num: int, page_size: int, **filters: Any) -> dict[str, Any]:
    return store.list(table, page=page_num, page_size=page_size, filters=filters)


def create(table: str, payload: dict[str, Any], **fixed: Any) -> dict[str, Any]:
    item = store.create(table, {**payload, **fixed})
    store.log(table, "create", item["id"])
    return item


def update(table: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    item = store.update(table, item_id, payload)
    if not item:
        raise HTTPException(status_code=404, detail=f"{table} {item_id} not found")
    store.log(table, "update", item_id)
    return item


def delete(table: str, item_id: str) -> dict[str, Any]:
    if not store.delete(table, item_id):
        raise HTTPException(status_code=404, detail=f"{table} {item_id} not found")
    store.log(table, "delete", item_id)
    return {"deleted": True, "id": item_id}


@router.get("/projects")
def list_projects(page_num: int = Query(1, alias="page"), page_size: int = Query(2000, alias="pageSize")):
    with session_scope() as session:
        return db_page(session, Project, page_num, page_size, Project.is_deleted.is_(False), order_by=Project.id.desc())


@router.post("/projects")
def create_project(payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        repo = AitestRepository(session)
        code = data.get("code")
        if code and session.scalar(select(Project.id).where(Project.code == code)):
            code = None
        try:
            return model_dict(repo.create_project(data.get("name") or "未命名项目", data.get("description"), code, data.get("owner_name")))
        except Exception as exc:
            raise repo_error(exc)


@router.get("/projects/{projectId}")
def get_project(projectId: str):
    with session_scope() as session:
        try:
            return model_dict(AitestRepository(session).get_project(to_int(projectId, "projectId")))
        except Exception as exc:
            raise repo_error(exc)


@router.patch("/projects/{projectId}")
def update_project(projectId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        project = session.get(Project, to_int(projectId, "projectId"))
        if project is None or project.is_deleted:
            raise HTTPException(status_code=404, detail=f"Project({projectId}) not found")
        for key in ("name", "description", "owner_name"):
            if key in data:
                setattr(project, key, data[key])
        session.flush()
        return model_dict(project)


@router.delete("/projects/{projectId}")
def delete_project(projectId: str):
    with session_scope() as session:
        project = session.get(Project, to_int(projectId, "projectId"))
        if project is None or project.is_deleted:
            raise HTTPException(status_code=404, detail=f"Project({projectId}) not found")
        project.is_deleted = True
        session.flush()
        return {"deleted": True, "id": project.id}


def _grouped_count(session: Any, column: Any, *conditions: Any) -> dict[str, int]:
    stmt = select(column, func.count()).group_by(column)
    for condition in conditions:
        stmt = stmt.where(condition)
    rows = session.execute(stmt).all()
    counts = {str(key or "unknown"): int(value or 0) for key, value in rows}
    counts["total"] = sum(counts.values())
    return counts


DASHBOARD_SUCCESS_STATUSES = {"pass", "passed", "success", "succeeded", "ok", "completed"}
DASHBOARD_FAIL_STATUSES = {"fail", "failed", "error", "timeout"}
DASHBOARD_BLOCKED_STATUSES = {"blocked", "block"}
DASHBOARD_TREND_DAYS = 14
DASHBOARD_HEATMAP_DIMENSIONS = [
    {"key": "requirements", "label": "需求"},
    {"key": "test_cases", "label": "用例"},
    {"key": "executions", "label": "执行"},
    {"key": "defects", "label": "缺陷"},
]


def _percent(part: int, total: int) -> float:
    return round(part * 100 / total, 2) if total else 0.0


def _status_bucket(status: Any) -> str:
    value = str(status or "").strip().lower()
    if value in DASHBOARD_SUCCESS_STATUSES:
        return "passed"
    if value in DASHBOARD_FAIL_STATUSES:
        return "failed"
    if value in DASHBOARD_BLOCKED_STATUSES:
        return "blocked"
    return "other"


def _date_key(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "date"):
        return value.date().isoformat()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _execution_trend(session: Any, project_id: int) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=DASHBOARD_TREND_DAYS - 1)
    points_by_date: dict[str, dict[str, Any]] = {}
    for day_offset in range(DASHBOARD_TREND_DAYS):
        day = start_date + timedelta(days=day_offset)
        key = day.isoformat()
        points_by_date[key] = {
            "date": key,
            "passed": 0,
            "failed": 0,
            "blocked": 0,
            "other": 0,
            "total": 0,
            "pass_rate": 0.0,
        }

    start_at = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    records = session.scalars(
        select(Execution).where(Execution.project_id == project_id, Execution.executed_at >= start_at)
    )
    for record in records:
        day_key = _date_key(record.executed_at)
        point = points_by_date.get(day_key or "")
        if point is None:
            continue
        bucket = _status_bucket(record.status)
        point[bucket] += 1
        point["total"] += 1

    points = list(points_by_date.values())
    for point in points:
        point["pass_rate"] = _percent(point["passed"], point["total"])
    return {"days": DASHBOARD_TREND_DAYS, "start_date": start_date.isoformat(), "end_date": today.isoformat(), "points": points}


def _requirement_coverage(session: Any, project_id: int) -> dict[str, Any]:
    item_ids = list(
        session.scalars(
            select(RequirementItem.id).where(
                RequirementItem.project_id == project_id,
                RequirementItem.is_deleted.is_(False),
            )
        )
    )
    total = len(item_ids)
    if not item_ids:
        return {
            "total": 0,
            "covered": 0,
            "partial": 0,
            "uncovered": 0,
            "rate": 0.0,
            "covered_rate": 0.0,
            "partial_rate": 0.0,
            "uncovered_rate": 0.0,
            "test_points": 0,
            "test_cases": 0,
        }

    point_rows = session.execute(
        select(TestPoint.id, TestPoint.requirement_item_id).where(
            TestPoint.requirement_item_id.in_(item_ids),
            TestPoint.is_deleted.is_(False),
        )
    ).all()
    case_rows = session.execute(
        select(TestCase.id, TestCase.requirement_item_id, TestCase.test_point_id).where(
            TestCase.project_id == project_id,
            TestCase.requirement_item_id.in_(item_ids),
            TestCase.is_deleted.is_(False),
        )
    ).all()

    points_by_item: dict[int, set[int]] = defaultdict(set)
    cases_by_item: dict[int, int] = defaultdict(int)
    covered_points_by_item: dict[int, set[int]] = defaultdict(set)
    for point_id, item_id in point_rows:
        points_by_item[int(item_id)].add(int(point_id))
    for _case_id, item_id, point_id in case_rows:
        item_key = int(item_id)
        cases_by_item[item_key] += 1
        if point_id is not None:
            covered_points_by_item[item_key].add(int(point_id))

    covered = 0
    partial = 0
    uncovered = 0
    for item_id in item_ids:
        item_key = int(item_id)
        point_ids = points_by_item.get(item_key, set())
        case_count = cases_by_item.get(item_key, 0)
        if not point_ids and case_count == 0:
            uncovered += 1
        elif case_count > 0 and (not point_ids or point_ids.issubset(covered_points_by_item.get(item_key, set()))):
            covered += 1
        else:
            partial += 1

    return {
        "total": total,
        "covered": covered,
        "partial": partial,
        "uncovered": uncovered,
        "rate": _percent(covered, total),
        "covered_rate": _percent(covered, total),
        "partial_rate": _percent(partial, total),
        "uncovered_rate": _percent(uncovered, total),
        "test_points": len(point_rows),
        "test_cases": len(case_rows),
    }


def _module_label(value: Any) -> str:
    module = str(value or "").strip()
    return module or "未分组"


def _empty_heatmap_row(module: str) -> dict[str, Any]:
    return {"module": module, "requirements": 0, "test_cases": 0, "executions": 0, "defects": 0, "total": 0}


def _module_heatmap(session: Any, project_id: int) -> dict[str, Any]:
    item_rows = session.execute(
        select(RequirementItem.id, RequirementItem.module).where(
            RequirementItem.project_id == project_id,
            RequirementItem.is_deleted.is_(False),
        )
    ).all()
    if not item_rows:
        return {"dimensions": DASHBOARD_HEATMAP_DIMENSIONS, "rows": []}

    item_modules = {int(item_id): _module_label(module) for item_id, module in item_rows}
    rows_by_module: dict[str, dict[str, Any]] = {}
    for module in item_modules.values():
        row = rows_by_module.setdefault(module, _empty_heatmap_row(module))
        row["requirements"] += 1

    item_ids = list(item_modules.keys())
    case_counts = session.execute(
        select(TestCase.requirement_item_id, func.count()).where(
            TestCase.project_id == project_id,
            TestCase.requirement_item_id.in_(item_ids),
            TestCase.is_deleted.is_(False),
        ).group_by(TestCase.requirement_item_id)
    ).all()
    execution_counts = session.execute(
        select(Execution.requirement_item_id, func.count()).where(
            Execution.project_id == project_id,
            Execution.requirement_item_id.in_(item_ids),
        ).group_by(Execution.requirement_item_id)
    ).all()
    defect_counts = session.execute(
        select(Defect.requirement_item_id, func.count()).where(
            Defect.project_id == project_id,
            Defect.requirement_item_id.in_(item_ids),
        ).group_by(Defect.requirement_item_id)
    ).all()

    for rows, key in ((case_counts, "test_cases"), (execution_counts, "executions"), (defect_counts, "defects")):
        for item_id, count in rows:
            module = item_modules.get(int(item_id))
            if module is None:
                continue
            rows_by_module[module][key] += int(count or 0)

    for row in rows_by_module.values():
        row["total"] = sum(int(row[dimension["key"]] or 0) for dimension in DASHBOARD_HEATMAP_DIMENSIONS)

    sorted_rows = sorted(rows_by_module.values(), key=lambda row: (-int(row["total"]), str(row["module"])))
    return {"dimensions": DASHBOARD_HEATMAP_DIMENSIONS, "rows": sorted_rows}


@router.get("/projects/{projectId}/dashboard")
def project_dashboard(projectId: str):
    pid = to_int(projectId, "projectId")
    with session_scope() as session:
        AitestRepository(session).get_project(pid)
        api_lib_ids = select(ApiTestLib.id).where(ApiTestLib.project_id == pid, ApiTestLib.is_deleted.is_(False))
        auto_project_ids = select(AutoProject.id).where(AutoProject.project_id == pid, AutoProject.is_deleted.is_(False))
        execution_summary = _grouped_count(session, Execution.status, Execution.project_id == pid)
        api_execution_summary = _grouped_count(session, ApiExecution.status, ApiExecution.lib_id.in_(api_lib_ids))
        auto_execution_summary = _grouped_count(session, AutoExecution.status, AutoExecution.auto_project_id.in_(auto_project_ids))
        defect_status_summary = _grouped_count(session, Defect.status, Defect.project_id == pid)
        defect_severity_summary = _grouped_count(session, Defect.severity, Defect.project_id == pid)
        test_round_summary = _grouped_count(session, TestRound.status, TestRound.project_id == pid)
        return {
            "project_id": pid,
            "requirement_libs": session.scalar(select(func.count()).select_from(RequirementLib).where(RequirementLib.project_id == pid, RequirementLib.is_deleted.is_(False))) or 0,
            "requirement_documents": session.scalar(select(func.count()).select_from(RequirementDocument).where(RequirementDocument.project_id == pid, RequirementDocument.is_deleted.is_(False))) or 0,
            "requirement_items": session.scalar(select(func.count()).select_from(RequirementItem).where(RequirementItem.project_id == pid, RequirementItem.is_deleted.is_(False))) or 0,
            "test_cases": session.scalar(select(func.count()).select_from(TestCase).where(TestCase.project_id == pid, TestCase.is_deleted.is_(False))) or 0,
            "executions": session.scalar(select(func.count()).select_from(Execution).where(Execution.project_id == pid)) or 0,
            "defects": session.scalar(select(func.count()).select_from(Defect).where(Defect.project_id == pid)) or 0,
            "api_test_libs": session.scalar(select(func.count()).select_from(ApiTestLib).where(ApiTestLib.project_id == pid, ApiTestLib.is_deleted.is_(False))) or 0,
            "api_endpoints": session.scalar(select(func.count()).select_from(ApiEndpoint).where(ApiEndpoint.lib_id.in_(api_lib_ids), ApiEndpoint.is_deleted.is_(False))) or 0,
            "api_test_cases": session.scalar(select(func.count()).select_from(ApiTestCase).where(ApiTestCase.lib_id.in_(api_lib_ids), ApiTestCase.is_deleted.is_(False))) or 0,
            "api_executions": api_execution_summary["total"],
            "auto_projects": session.scalar(select(func.count()).select_from(AutoProject).where(AutoProject.project_id == pid, AutoProject.is_deleted.is_(False))) or 0,
            "auto_case_files": session.scalar(select(func.count()).select_from(AutoCaseFile).where(AutoCaseFile.auto_project_id.in_(auto_project_ids), AutoCaseFile.is_deleted.is_(False))) or 0,
            "auto_executions": auto_execution_summary["total"],
            "perf_plans": session.scalar(select(func.count()).select_from(PerfPlan).where(PerfPlan.project_id == pid, PerfPlan.is_deleted.is_(False))) or 0,
            "perf_results": session.scalar(select(func.count()).select_from(PerfResult).where(PerfResult.project_id == pid)) or 0,
            "reports": session.scalar(select(func.count()).select_from(Report).where(Report.project_id == pid)) or 0,
            "test_rounds": test_round_summary["total"],
            "execution_summary": execution_summary,
            "api_execution_summary": api_execution_summary,
            "auto_execution_summary": auto_execution_summary,
            "defect_status_summary": defect_status_summary,
            "defect_severity_summary": defect_severity_summary,
            "test_round_summary": test_round_summary,
            "execution_trend": _execution_trend(session, pid),
            "requirement_coverage": _requirement_coverage(session, pid),
            "module_heatmap": _module_heatmap(session, pid),
            "updated_at": now_iso(),
        }


def _period_quality_summary(session: Any, project_id: int, period: str, request_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    context = build_aggregation_context(session, project_id=project_id)
    data = context["data_snapshot"]
    metrics = data["summary_metrics"]
    risks = data.get("risk_items") or []
    project = data.get("project") or {}
    period_label = "今日" if period == "daily" else "本周"
    top_risks = risks[:5]
    has_high_risk = any(item.get("level") == "high" for item in top_risks)
    has_medium_risk = any(item.get("level") == "medium" for item in top_risks)
    risk_level = "高" if has_high_risk else "中" if has_medium_risk else "低"
    next_actions = _summary_next_actions(metrics, top_risks)
    summary = (
        f"{period_label}质量摘要：项目「{project.get('name') or project.get('code') or project_id}」"
        f"当前累计需求项 {metrics['requirement_item_count']} 个、测试用例 {metrics['test_case_count']} 条、"
        f"主链执行 {metrics['execution_count']} 次，通过率 {metrics['execution_pass_rate']}%。"
        f"接口执行 {metrics['api_execution_count']} 次，通过率 {metrics['api_pass_rate']}%；"
        f"自动化执行 {metrics['auto_execution_count']} 次，通过率 {metrics['auto_pass_rate']}%；"
        f"性能结果 {metrics['perf_result_count']} 份。"
        f"未关闭缺陷 {metrics['open_defect_count']} 个，综合风险等级为{risk_level}。"
    )
    return sanitize_payload(
        {
            "project_id": project_id,
            "period": period,
            "summary": summary,
            "metrics": metrics,
            "risk_level": risk_level,
            "risk_items": top_risks,
            "next_actions": next_actions,
            "source_refs": context["source_refs_json"],
            "generated_at": context["scope_snapshot"]["generated_at"],
            "input": sanitize_payload(request_payload or {}),
        }
    )


def _summary_next_actions(metrics: dict[str, Any], risks: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    if metrics.get("open_defect_count", 0):
        actions.append(f"优先关闭或确认 {metrics['open_defect_count']} 个未关闭缺陷，补齐验证证据。")
    if any(item.get("source") == "execution" for item in risks):
        actions.append("复盘失败执行记录，确认失败是否已关联缺陷或重跑通过。")
    if any(item.get("source") == "api_execution" for item in risks):
        actions.append("检查接口执行失败的请求、响应快照和环境变量配置。")
    if any(item.get("source") == "auto_execution" for item in risks):
        actions.append("下载自动化 artifacts，定位失败脚本、截图或日志。")
    if metrics.get("test_case_count", 0) == 0:
        actions.append("先从需求项生成测试用例，再启动执行和报告归档。")
    if not actions:
        actions.append("当前未发现高风险事实，建议继续补充执行记录并生成最新报告。")
    return actions[:5]


@router.post("/projects/{projectId}/dashboard/daily-summary")
def daily_summary(projectId: str, payload: WritePayload | None = None):
    pid = to_int(projectId, "projectId")
    with session_scope() as session:
        return _period_quality_summary(session, pid, "daily", payload_dict(payload))


@router.post("/projects/{projectId}/dashboard/weekly-summary")
def weekly_summary(projectId: str, payload: WritePayload | None = None):
    pid = to_int(projectId, "projectId")
    with session_scope() as session:
        return _period_quality_summary(session, pid, "weekly", payload_dict(payload))


@router.get("/projects/{projectId}/requirement-libs")
def list_requirement_libs(projectId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        pid = to_int(projectId, "projectId")
        return db_page(session, RequirementLib, page_num, page_size, RequirementLib.project_id == pid, RequirementLib.is_deleted.is_(False), order_by=RequirementLib.id.desc())


@router.post("/projects/{projectId}/requirement-libs")
def create_requirement_lib(projectId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        try:
            return model_dict(AitestRepository(session).create_requirement_lib(to_int(projectId, "projectId"), data.get("name") or "未命名需求库", data.get("description")))
        except Exception as exc:
            raise repo_error(exc)


@router.patch("/requirement-libs/{libId}")
def update_requirement_lib(libId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        lib = session.get(RequirementLib, to_int(libId, "libId"))
        if lib is None or lib.is_deleted:
            raise HTTPException(status_code=404, detail=f"RequirementLib({libId}) not found")
        for key in ("name", "description"):
            if key in data:
                setattr(lib, key, data[key])
        session.flush()
        return model_dict(lib)


@router.delete("/requirement-libs/{libId}")
def delete_requirement_lib(libId: str):
    with session_scope() as session:
        lib = session.get(RequirementLib, to_int(libId, "libId"))
        if lib is None or lib.is_deleted:
            raise HTTPException(status_code=404, detail=f"RequirementLib({libId}) not found")
        lib.is_deleted = True
        session.flush()
        return {"deleted": True, "id": lib.id}


@router.get("/requirement-libs/{libId}/documents")
def list_requirement_lib_documents(libId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        lib = require_db_item(session, RequirementLib, libId, "libId")
        return db_page(
            session,
            RequirementDocument,
            page_num,
            page_size,
            RequirementDocument.lib_id == lib.id,
            RequirementDocument.is_deleted.is_(False),
            order_by=RequirementDocument.id.desc(),
        )


@router.get("/requirement-libs/{libId}/requirement-items")
def list_requirement_lib_items(libId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        lib = require_db_item(session, RequirementLib, libId, "libId")
        return db_page(
            session,
            RequirementItem,
            page_num,
            page_size,
            RequirementItem.lib_id == lib.id,
            RequirementItem.is_deleted.is_(False),
            order_by=RequirementItem.id.desc(),
        )


@router.post("/projects/{projectId}/requirement-documents")
def create_requirement_document(projectId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        try:
            document = AitestRepository(session).create_requirement_document(
                project_id=to_int(projectId, "projectId"),
                lib_id=to_int(data.get("lib_id"), "lib_id"),
                name=data.get("name") or "未命名需求文档",
                source_type=data.get("source_type", "text"),
                raw_content=data.get("raw_content") or data.get("content"),
                source_file_name=data.get("source_file_name"),
                source_file_path=data.get("source_file_path"),
            )
            return model_dict(document)
        except Exception as exc:
            raise repo_error(exc)


@router.get("/requirement-documents/{documentId}")
def get_requirement_document(documentId: str):
    with session_scope() as session:
        document = session.get(RequirementDocument, to_int(documentId, "documentId"))
        if document is None or document.is_deleted:
            raise HTTPException(status_code=404, detail=f"RequirementDocument({documentId}) not found")
        return model_dict(document)


@router.patch("/requirement-documents/{documentId}")
def update_requirement_document(documentId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        document = session.get(RequirementDocument, to_int(documentId, "documentId"))
        if document is None or document.is_deleted:
            raise HTTPException(status_code=404, detail=f"RequirementDocument({documentId}) not found")
        for key in ("name", "source_type", "source_file_name", "source_file_path", "raw_content", "parser_status"):
            if key in data:
                setattr(document, key, data[key])
        session.flush()
        return model_dict(document)


@router.post("/requirement-documents/{documentId}/parse")
def parse_requirement_document(documentId: str, payload: WritePayload | None = None):
    with session_scope() as session:
        try:
            repo = AitestRepository(session)
            job = repo.parse_requirement_document(to_int(documentId, "documentId"))
            blocks = list(session.scalars(select(RequirementDocumentBlock).where(RequirementDocumentBlock.document_id == to_int(documentId, "documentId")).order_by(RequirementDocumentBlock.order_no)))
            return safe_requirement_closure_payload({
                "document_id": to_int(documentId, "documentId"),
                "job": model_dict(job),
                "blocks": [model_dict(block) for block in blocks],
                "input": safe_summary_payload(payload_dict(payload)),
            })
        except Exception as exc:
            raise repo_error(exc)


@router.get("/requirement-documents/{documentId}/blocks")
def list_requirement_blocks(documentId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        doc_id = to_int(documentId, "documentId")
        return db_page(session, RequirementDocumentBlock, page_num, page_size, RequirementDocumentBlock.document_id == doc_id, order_by=RequirementDocumentBlock.order_no)


@router.post("/requirement-documents/{documentId}/extract-items")
def extract_requirement_items(documentId: str, payload: WritePayload | None = None):
    data = payload_dict(payload)
    with session_scope() as session:
        try:
            repo = AitestRepository(session)
            doc_id = to_int(documentId, "documentId")
            document = require_db_item(session, RequirementDocument, doc_id, "documentId")
            config = default_llm_config(session, data.get("config_id") or data.get("configId"))
            generated_items: list[dict[str, Any]] | None = None
            source = "placeholder"
            fallback_reason: str | None = "no_enabled_llm_config"
            usage: dict[str, Any] = {}

            if config is not None:
                fallback, settings = require_llm_runtime(config)
                if fallback is not None:
                    record_llm_usage(session, config.id, "requirement_extract", duration_ms=1)
                    fallback_reason = safe_fallback_reason(fallback.get("reason") or fallback.get("error") or fallback.get("status"))
                else:
                    blocks = list(
                        session.scalars(
                            select(RequirementDocumentBlock)
                            .where(RequirementDocumentBlock.document_id == doc_id)
                            .order_by(RequirementDocumentBlock.order_no)
                        )
                    )
                    try:
                        result = structured_generation_service(config, settings).generate_requirement_items(
                            document=model_dict(document),
                            blocks=[model_dict(block) for block in blocks],
                        )
                        generated_items = result.records
                        source = "llm"
                        fallback_reason = None
                        usage = {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "duration_ms": result.duration_ms}
                        record_llm_usage(session, config.id, "requirement_extract", result.input_tokens, result.output_tokens, result.duration_ms)
                    except (LlmClientError, ValueError) as exc:
                        record_llm_usage(session, config.id, "requirement_extract", duration_ms=1)
                        fallback_reason = safe_fallback_reason(exc)

            job = repo.extract_requirement_items_placeholder(doc_id, items=generated_items)
            annotate_generation_job(
                job,
                source=source,
                fallback_reason=fallback_reason,
                config_id=config.id if config is not None else None,
                usage=usage,
            )
            item_ids = (job.output_payload or {}).get("item_ids", [])
            items = list(session.scalars(select(RequirementItem).where(RequirementItem.id.in_(item_ids)).order_by(RequirementItem.id))) if item_ids else []
            return safe_requirement_closure_payload({"document_id": to_int(documentId, "documentId"), "job": model_dict(job), "items": [model_dict(item) for item in items], "input": safe_summary_payload(payload_dict(payload))})
        except HTTPException:
            raise
        except Exception as exc:
            raise repo_error(exc)


@router.get("/requirement-documents/{documentId}/requirement-items")
def list_document_requirement_items(documentId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        doc_id = to_int(documentId, "documentId")
        return db_page(session, RequirementItem, page_num, page_size, RequirementItem.document_id == doc_id, RequirementItem.is_deleted.is_(False), order_by=RequirementItem.id)


@router.patch("/requirement-items/{itemId}")
def update_requirement_item(itemId: str, payload: WritePayload):
    with session_scope() as session:
        try:
            return model_dict(AitestRepository(session).update_requirement_item(to_int(itemId, "itemId"), **payload_dict(payload)))
        except Exception as exc:
            raise repo_error(exc)


@router.post("/requirement-items/{itemId}/confirm")
def confirm_requirement_item(itemId: str):
    with session_scope() as session:
        try:
            return model_dict(AitestRepository(session).confirm_requirement_item(to_int(itemId, "itemId")))
        except Exception as exc:
            raise repo_error(exc)


@router.post("/requirement-items/{itemId}/split")
def split_requirement_item_db(itemId: str, payload: WritePayload | None = None):
    data = safe_summary_payload(payload_dict(payload))
    raw_parts = data.get("parts") or data.get("items") or data.get("children")
    if raw_parts is None:
        parts = None
    elif isinstance(raw_parts, list):
        parts = [part if isinstance(part, dict) else {"title": str(part)} for part in raw_parts]
    elif isinstance(raw_parts, dict):
        parts = [raw_parts]
    else:
        parts = [{"title": str(raw_parts)}]
    with session_scope() as session:
        try:
            source, children, job = AitestRepository(session).split_requirement_item(to_int(itemId, "itemId"), parts=parts)
            return safe_requirement_closure_payload({
                "source": model_dict(source),
                "children": [model_dict(child) for child in children],
                "job": model_dict(job),
                "input": data,
            })
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise repo_error(exc)


@router.post("/requirement-items/merge")
def merge_requirement_items_db(payload: WritePayload):
    data = sanitize_payload(payload_dict(payload))
    item_ids = parse_int_list(data.get("item_ids") or data.get("itemIds") or data.get("source_item_ids"), "item_ids")
    with session_scope() as session:
        try:
            merged, sources, job = AitestRepository(session).merge_requirement_items(item_ids, payload=data)
            return safe_requirement_closure_payload({
                "merged": model_dict(merged),
                "sources": [model_dict(item) for item in sources],
                "job": model_dict(job),
            })
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise repo_error(exc)


@router.post("/requirement-items/{itemId}/shelve")
def shelve_requirement_item(itemId: str, payload: WritePayload | None = None):
    data = safe_summary_payload(payload_dict(payload))
    with session_scope() as session:
        try:
            item = AitestRepository(session).shelve_requirement_item(to_int(itemId, "itemId"), reason=data.get("reason"))
            item_payload = model_dict(item)
            return safe_requirement_closure_payload({**item_payload, "item": item_payload, "reason": data.get("reason")})
        except Exception as exc:
            raise repo_error(exc)


@router.post("/requirement-items/{itemId}/quality-check")
def quality_check_requirement_item(itemId: str):
    with session_scope() as session:
        try:
            repo = AitestRepository(session)
            result = repo.quality_check_requirement_item(to_int(itemId, "itemId"))
            item = require_db_item(session, RequirementItem, itemId, "itemId")
            quality = sanitize_payload(result)
            return safe_requirement_closure_payload({
                "item": model_dict(item),
                "quality": quality,
                "score": quality.get("granularity_score"),
                "granularity_score": quality.get("granularity_score"),
                "granularity_flag": quality.get("granularity_flag"),
                "issues": quality.get("issues", []),
                "suggested_actions": quality.get("suggested_actions", []),
                "source_anchors": quality.get("source_anchors", []),
                "provider_call_performed": quality.get("provider_call_performed", False),
                "llm_provider_called": quality.get("llm_provider_called", False),
            })
        except Exception as exc:
            raise repo_error(exc)


@router.post("/requirement-libs/{libId}/brain/analyze")
def analyze_requirement_brain_db(libId: str):
    with session_scope() as session:
        try:
            lib, job = AitestRepository(session).analyze_requirement_brain(to_int(libId, "libId"))
            brain = sanitize_payload(lib.brain_summary or {})
            return safe_requirement_closure_payload({
                **brain,
                "brain": brain,
                "items": brain.get("items", []),
                "requirement_items": brain.get("requirement_items", brain.get("items", [])),
                "source_blocks": brain.get("source_blocks", []),
                "blocks": brain.get("blocks", brain.get("source_blocks", [])),
                "job": model_dict(job),
            })
        except Exception as exc:
            raise repo_error(exc)


@router.get("/requirement-libs/{libId}/brain")
def get_requirement_brain_db(libId: str):
    with session_scope() as session:
        lib = require_db_item(session, RequirementLib, libId, "libId")
        return safe_requirement_closure_payload(
            lib.brain_summary
            or {
                "lib_id": lib.id,
                "summary": "",
                "metrics": {},
                "risks": [],
                "relations": [],
                "source_refs": {},
                "provider_call_performed": False,
                "llm_provider_called": False,
            }
        )


@router.post("/requirement-items/{itemId}/traceability/refresh")
def refresh_traceability_db(itemId: str):
    with session_scope() as session:
        try:
            traceability, job = AitestRepository(session).refresh_traceability(to_int(itemId, "itemId"))
            return safe_requirement_closure_payload({
                "requirement_item_id": to_int(itemId, "itemId"),
                "item": model_dict(traceability["item"]),
                "source_blocks": [model_dict(block) for block in traceability["source_blocks"]],
                "test_points": [model_dict(point) for point in traceability["test_points"]],
                "test_cases": [model_dict(case) for case in traceability["test_cases"]],
                "coverage_matrix": sanitize_payload(traceability["coverage_matrix"]),
                "coverage": sanitize_payload(traceability["coverage_matrix"]),
                "job": model_dict(job),
            })
        except Exception as exc:
            raise repo_error(exc)


@router.delete("/requirement-items/{itemId}")
def delete_requirement_item(itemId: str):
    if str(itemId).isdigit():
        with session_scope() as session:
            item = session.get(RequirementItem, int(itemId))
            if item is not None and not item.is_deleted:
                item.is_deleted = True
                session.flush()
                return {"deleted": True, "id": item.id}
    return delete("requirement_items", itemId)


@router.get("/generation-jobs/{jobId}")
def get_generation_job(jobId: str):
    with session_scope() as session:
        job = session.get(GenerationJob, to_int(jobId, "jobId"))
        if job is not None:
            return model_dict(job)
    return ensure("generation_jobs", jobId)


@router.get("/generation-jobs/{jobId}/events")
def generation_job_events(jobId: str):
    with session_scope() as session:
        db_job = session.get(GenerationJob, to_int(jobId, "jobId")) if str(jobId).isdigit() else None
        job = model_dict(db_job) if db_job is not None else ensure("generation_jobs", jobId)

    def events():
        for event in [
            {"event": "started", "progress": 0, "job_id": jobId},
            {"event": "progress", "progress": job.get("progress", 100), "job_id": jobId},
            {"event": job.get("status", "completed"), "progress": job.get("progress", 100), "job_id": jobId},
        ]:
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/generation-jobs/{jobId}/cancel")
def cancel_generation_job(jobId: str):
    with session_scope() as session:
        db_job = session.get(GenerationJob, to_int(jobId, "jobId")) if str(jobId).isdigit() else None
        if db_job is not None:
            db_job.status = "cancelled"
            db_job.progress = 100
            session.flush()
            return model_dict(db_job)
    ensure("generation_jobs", jobId)
    return update("generation_jobs", jobId, {"status": "cancelled", "progress": 100})


@router.post("/requirement-items/{itemId}/generate-test-points")
def generate_test_points(itemId: str, payload: WritePayload | None = None):
    data = payload_dict(payload)
    with session_scope() as session:
        try:
            repo = AitestRepository(session)
            item_id = to_int(itemId, "itemId")
            item = require_db_item(session, RequirementItem, item_id, "itemId")
            config = default_llm_config(session, data.get("config_id") or data.get("configId"))
            generated_points: list[dict[str, Any]] | None = None
            source = "placeholder"
            fallback_reason: str | None = "no_enabled_llm_config"
            usage: dict[str, Any] = {}

            if config is not None:
                fallback, settings = require_llm_runtime(config)
                if fallback is not None:
                    record_llm_usage(session, config.id, "test_point_generation", duration_ms=1)
                    fallback_reason = safe_fallback_reason(fallback.get("reason") or fallback.get("error") or fallback.get("status"))
                else:
                    try:
                        result = structured_generation_service(config, settings).generate_test_points(item=model_dict(item))
                        generated_points = result.records
                        source = "llm"
                        fallback_reason = None
                        usage = {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "duration_ms": result.duration_ms}
                        record_llm_usage(session, config.id, "test_point_generation", result.input_tokens, result.output_tokens, result.duration_ms)
                    except (LlmClientError, ValueError) as exc:
                        record_llm_usage(session, config.id, "test_point_generation", duration_ms=1)
                        fallback_reason = safe_fallback_reason(exc)

            job = repo.generate_test_points(item_id, points=generated_points)
            annotate_generation_job(
                job,
                source=source,
                fallback_reason=fallback_reason,
                config_id=config.id if config is not None else None,
                usage=usage,
            )
            point_ids = (job.output_payload or {}).get("test_point_ids", [])
            points = list(session.scalars(select(TestPoint).where(TestPoint.id.in_(point_ids)).order_by(TestPoint.id))) if point_ids else []
            return {"job": model_dict(job), "test_points": [model_dict(point) for point in points], "input": sanitize_payload(payload_dict(payload))}
        except HTTPException:
            raise
        except Exception as exc:
            raise repo_error(exc)


@router.get("/requirement-items/{itemId}/test-points")
def list_test_points(itemId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        iid = to_int(itemId, "itemId")
        return db_page(session, TestPoint, page_num, page_size, TestPoint.requirement_item_id == iid, TestPoint.is_deleted.is_(False), order_by=TestPoint.id)


@router.patch("/test-points/{testPointId}")
def update_test_point(testPointId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        point = session.get(TestPoint, to_int(testPointId, "testPointId"))
        if point is None or point.is_deleted:
            raise HTTPException(status_code=404, detail=f"TestPoint({testPointId}) not found")
        for key in ("title", "point_type", "target", "priority", "suggested_method", "coverage_status", "note"):
            if key in data:
                setattr(point, key, data[key])
        session.flush()
        return model_dict(point)


@router.get("/requirement-items/{itemId}/coverage-matrix")
def coverage_matrix(itemId: str):
    iid = to_int(itemId, "itemId")
    with session_scope() as session:
        item = session.get(RequirementItem, iid)
        if item is None or item.is_deleted:
            raise HTTPException(status_code=404, detail=f"RequirementItem({itemId}) not found")
        points = list(session.scalars(select(TestPoint).where(TestPoint.requirement_item_id == iid, TestPoint.is_deleted.is_(False)).order_by(TestPoint.id)))
        cases = list(session.scalars(select(TestCase).where(TestCase.requirement_item_id == iid, TestCase.is_deleted.is_(False)).order_by(TestCase.id)))
        covered_point_ids = {case.test_point_id for case in cases if case.test_point_id is not None}
        coverage_rate = round(len(covered_point_ids) / len(points), 4) if points else 0
        return {"requirement_item_id": iid, "test_points": [model_dict(point) for point in points], "test_cases": [model_dict(case) for case in cases], "coverage_rate": coverage_rate}


@router.post("/requirement-items/{itemId}/refresh-coverage")
def refresh_coverage(itemId: str):
    return coverage_matrix(itemId)


@router.post("/requirement-items/{itemId}/generate-test-cases")
def generate_test_cases(itemId: str, payload: WritePayload | None = None):
    data = payload_dict(payload)
    with session_scope() as session:
        try:
            repo = AitestRepository(session)
            item_id = to_int(itemId, "itemId")
            item = require_db_item(session, RequirementItem, item_id, "itemId")
            generation_mode = data.get("mode", "standard")
            test_point_ids = data.get("test_point_ids") or data.get("testPointIds")
            if isinstance(test_point_ids, list):
                selected_point_ids = [to_int(point_id, "test_point_id") for point_id in test_point_ids]
            else:
                selected_point_ids = None
            config = default_llm_config(session, data.get("config_id") or data.get("configId"))
            generated_cases: list[dict[str, Any]] | None = None
            source = "placeholder"
            fallback_reason: str | None = "no_enabled_llm_config"
            usage: dict[str, Any] = {}

            if config is not None:
                fallback, settings = require_llm_runtime(config)
                if fallback is not None:
                    record_llm_usage(session, config.id, "test_case_generation", duration_ms=1)
                    fallback_reason = safe_fallback_reason(fallback.get("reason") or fallback.get("error") or fallback.get("status"))
                else:
                    point_stmt = select(TestPoint).where(TestPoint.requirement_item_id == item_id, TestPoint.is_deleted.is_(False))
                    if selected_point_ids:
                        point_stmt = point_stmt.where(TestPoint.id.in_(selected_point_ids))
                    points = list(session.scalars(point_stmt.order_by(TestPoint.id)))
                    if not points:
                        record_llm_usage(session, config.id, "test_case_generation", duration_ms=1)
                        fallback_reason = "no_test_points_available"
                    else:
                        try:
                            result = structured_generation_service(config, settings).generate_test_cases(
                                item=model_dict(item),
                                points=[model_dict(point) for point in points],
                                generation_mode=generation_mode,
                            )
                            generated_cases = result.records
                            source = "llm"
                            fallback_reason = None
                            usage = {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "duration_ms": result.duration_ms}
                            record_llm_usage(session, config.id, "test_case_generation", result.input_tokens, result.output_tokens, result.duration_ms)
                        except (LlmClientError, ValueError) as exc:
                            record_llm_usage(session, config.id, "test_case_generation", duration_ms=1)
                            fallback_reason = safe_fallback_reason(exc)

            job = repo.generate_test_cases(item_id, test_point_ids=selected_point_ids, generation_mode=generation_mode, cases=generated_cases)
            annotate_generation_job(
                job,
                source=source,
                fallback_reason=fallback_reason,
                config_id=config.id if config is not None else None,
                usage=usage,
            )
            case_ids = (job.output_payload or {}).get("test_case_ids", [])
            cases = list(session.scalars(select(TestCase).where(TestCase.id.in_(case_ids)).order_by(TestCase.id))) if case_ids else []
            serialized = [model_dict(case) for case in cases]
            return {"job": model_dict(job), "test_cases": serialized, "cases": serialized}
        except HTTPException:
            raise
        except Exception as exc:
            raise repo_error(exc)


@router.get("/requirement-items/{itemId}/test-cases")
def list_test_cases(itemId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        iid = to_int(itemId, "itemId")
        return db_page(session, TestCase, page_num, page_size, TestCase.requirement_item_id == iid, TestCase.is_deleted.is_(False), order_by=TestCase.id)


@router.get("/projects/{projectId}/test-cases")
def list_project_test_cases(
    projectId: str,
    page_num: int = Query(1, alias="page"),
    page_size: int = Query(20, alias="pageSize"),
    libId: str | None = None,
    requirementItemId: str | None = None,
):
    with session_scope() as session:
        project = require_db_item(session, Project, projectId, "projectId")
        criteria: list[Any] = [TestCase.project_id == project.id, TestCase.is_deleted.is_(False)]
        if libId is not None:
            criteria.append(TestCase.lib_id == to_int(libId, "libId"))
        if requirementItemId is not None:
            criteria.append(TestCase.requirement_item_id == to_int(requirementItemId, "requirementItemId"))
        return db_page(session, TestCase, page_num, page_size, *criteria, order_by=TestCase.id.desc())


@router.get("/test-cases/export")
def export_test_cases_endpoint(
    projectId: str | None = None,
    project_id: str | None = None,
    requirementItemId: str | None = None,
    requirement_item_id: str | None = None,
    caseIds: str | None = None,
    case_ids: str | None = None,
    caseType: str | None = None,
    case_type: str | None = None,
    format: str = Query("markdown"),
):
    with session_scope() as session:
        try:
            return export_test_cases_payload(
                session,
                project_id=to_int(project_id or projectId, "projectId") if (project_id or projectId) is not None else None,
                requirement_item_id=to_int(requirement_item_id or requirementItemId, "requirementItemId") if (requirement_item_id or requirementItemId) is not None else None,
                case_ids=parse_int_list(case_ids or caseIds, "caseIds"),
                case_type=case_type or caseType,
                output_format=format,
            )
        except ExportPayloadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/test-cases/{caseId}")
def update_test_case(caseId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        case = session.get(TestCase, to_int(caseId, "caseId"))
        if case is None or case.is_deleted:
            raise HTTPException(status_code=404, detail=f"TestCase({caseId}) not found")
        for key in ("title", "case_type", "precondition", "steps", "expected_result", "priority", "tags", "status"):
            if key in data:
                setattr(case, key, data[key])
        session.flush()
        return model_dict(case)


@router.get("/test-cases/{caseId}/test-data-suggestions")
def get_test_case_data_suggestions(caseId: str):
    with session_scope() as session:
        try:
            return test_data_suggestions(session, caseId)
        except DataFactoryNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DataFactoryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


def _test_case_quality_review(
    session: Any,
    case: TestCase,
    *,
    peer_cases: list[TestCase] | None = None,
    update_status: bool = False,
    log_action: str | None = None,
) -> dict[str, Any]:
    if case.is_deleted:
        raise HTTPException(status_code=404, detail=f"TestCase({case.id}) not found")
    project_cases = peer_cases
    if project_cases is None:
        project_cases = list(
            session.scalars(
                select(TestCase)
                .where(TestCase.project_id == case.project_id, TestCase.is_deleted.is_(False))
                .order_by(TestCase.id)
            )
        )
    requirement = session.get(RequirementItem, case.requirement_item_id)
    case_payload = model_dict(case)
    peer_payloads = [model_dict(peer) for peer in project_cases if peer.id != case.id and not peer.is_deleted]
    requirement_payload = model_dict(requirement) if requirement is not None and not requirement.is_deleted else None
    requirement_cases = [
        model_dict(peer)
        for peer in project_cases
        if peer.requirement_item_id == case.requirement_item_id and not peer.is_deleted
    ]
    review = assess_test_case_quality(
        case_payload,
        requirement=requirement_payload,
        peer_cases=peer_payloads,
        requirement_cases=requirement_cases,
    )
    if update_status:
        case.status = review["review_status"]
    if log_action:
        session.add(
            OperationLog(
                module="test_case",
                action=log_action,
                target_type="test_case",
                target_id=case.id,
                detail=safe_summary_payload(
                    sanitize_payload(
                    {
                        "case_id": case.id,
                        "score": review["quality_score"],
                        "review_status": review["review_status"],
                        "issue_codes": [issue.get("code") for issue in review["issues"]],
                        "provider_call_performed": False,
                        "llm_provider_called": False,
                    }
                    )
                ),
            )
        )
    session.flush()
    review["case"] = model_dict(case)
    return safe_summary_payload(sanitize_payload(review))


def _load_review_cases(session: Any, data: dict[str, Any]) -> list[TestCase]:
    case_ids = parse_int_list(data.get("case_ids") or data.get("caseIds"), "case_ids")
    project_id = data.get("project_id") if data.get("project_id") is not None else data.get("projectId")
    if case_ids:
        cases = list(
            session.scalars(
                select(TestCase)
                .where(TestCase.id.in_(case_ids), TestCase.is_deleted.is_(False))
                .order_by(TestCase.id)
            )
        )
        missing = sorted(set(case_ids) - {case.id for case in cases})
        if missing:
            raise HTTPException(status_code=404, detail=f"TestCase not found: {missing}")
        return cases
    if project_id is not None:
        project = require_db_item(session, Project, project_id, "projectId")
        return list(
            session.scalars(
                select(TestCase)
                .where(TestCase.project_id == project.id, TestCase.is_deleted.is_(False))
                .order_by(TestCase.id)
            )
        )
    return []


def _review_db_test_cases(session: Any, cases: list[TestCase], *, update_status: bool, log_action: str | None) -> dict[str, Any]:
    project_ids = {case.project_id for case in cases}
    peers: list[TestCase] = []
    if project_ids:
        peers = list(
            session.scalars(
                select(TestCase)
                .where(TestCase.project_id.in_(project_ids), TestCase.is_deleted.is_(False))
                .order_by(TestCase.id)
            )
        )
    items = [
        _test_case_quality_review(session, case, peer_cases=peers, update_status=update_status, log_action=log_action)
        for case in cases
    ]
    return {
        "items": items,
        "summary": summarize_reviews(items),
        "provider_call_performed": False,
        "llm_provider_called": False,
    }


def _lightweight_review_payload(data: dict[str, Any]) -> dict[str, Any]:
    items = data.get("items") or data.get("cases") or data.get("test_cases")
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        case_like_keys = {"title", "case_type", "steps", "expected_result", "priority", "tags", "source_anchor_ids"}
        items = [data] if any(key in data for key in case_like_keys) else []
    sanitized_items = [safe_summary_payload(sanitize_payload(item)) for item in items if isinstance(item, dict)]
    reviews = assess_lightweight_items(sanitized_items)
    return {
        "items": safe_summary_payload(sanitize_payload(reviews)),
        "summary": summarize_reviews(reviews),
        "provider_call_performed": False,
        "llm_provider_called": False,
    }


@router.post("/test-cases/{caseId}/quality-review")
def quality_review_test_case(caseId: str, payload: WritePayload | None = None):
    payload_dict(payload)
    with session_scope() as session:
        case = session.get(TestCase, to_int(caseId, "caseId"))
        if case is None or case.is_deleted:
            raise HTTPException(status_code=404, detail=f"TestCase({caseId}) not found")
        return _test_case_quality_review(session, case, update_status=True, log_action="quality_review")


@router.post("/test-cases/review-batch")
def review_test_cases_batch(payload: WritePayload):
    data = safe_summary_payload(sanitize_payload(payload_dict(payload)))
    with session_scope() as session:
        cases = _load_review_cases(session, data)
        if not cases:
            raise HTTPException(status_code=400, detail="case_ids or project_id is required")
        return safe_summary_payload(sanitize_payload(_review_db_test_cases(session, cases, update_status=True, log_action="quality_review_batch")))


@router.get("/projects/{projectId}/test-case-quality-summary")
def project_test_case_quality_summary(projectId: str):
    with session_scope() as session:
        project = require_db_item(session, Project, projectId, "projectId")
        cases = list(
            session.scalars(
                select(TestCase)
                .where(TestCase.project_id == project.id, TestCase.is_deleted.is_(False))
                .order_by(TestCase.id)
            )
        )
        review_payload = _review_db_test_cases(session, cases, update_status=False, log_action=None)
        items = review_payload["items"]
        priority_mismatches = []
        for item in items:
            mismatch = next((issue for issue in item.get("issues", []) if issue.get("code") == "priority_mismatch"), None)
            if mismatch:
                case_payload = item.get("case") or {}
                requirement = session.get(RequirementItem, case_payload.get("requirement_item_id"))
                priority_mismatches.append(
                    {
                        "case_id": case_payload.get("id"),
                        "title": case_payload.get("title"),
                        "case_priority": case_payload.get("priority"),
                        "requirement_item_id": case_payload.get("requirement_item_id"),
                        "requirement_priority": requirement.priority if requirement is not None else None,
                    }
                )
        unexecutable_count = sum(
            1
            for item in items
            if any(issue.get("code") in {"missing_steps", "unexecutable_steps"} for issue in item.get("issues", []))
        )
        return safe_summary_payload(
            sanitize_payload(
            {
                "project_id": project.id,
                "summary": review_payload["summary"],
                "issue_counts": review_payload["summary"]["issue_counts"],
                "duplicate_groups": duplicate_groups_from_reviews(items),
                "priority_mismatches": priority_mismatches,
                "unexecutable_count": unexecutable_count,
                "provider_call_performed": False,
                "llm_provider_called": False,
            }
            )
        )


@router.post("/test-cases/{caseId}/review-opinions")
def save_test_case_review_opinion(caseId: str, payload: WritePayload):
    data = safe_summary_payload(sanitize_payload(payload_dict(payload)))
    with session_scope() as session:
        case = session.get(TestCase, to_int(caseId, "caseId"))
        if case is None or case.is_deleted:
            raise HTTPException(status_code=404, detail=f"TestCase({caseId}) not found")
        decision = str(data.get("decision") or "").strip().lower()
        approved_decisions = {"approved", "approve"}
        change_required_decisions = {"changes_required", "change_required", "changing", "needs_review"}
        if decision in approved_decisions:
            case.status = "reviewed"
        elif decision in change_required_decisions:
            case.status = "needs_review"
        opinion = safe_summary_payload(
            sanitize_payload(
            {
                "case_id": case.id,
                "decision": decision or None,
                "comment": data.get("comment") or data.get("opinion") or data.get("notes"),
                "reviewer": data.get("reviewer") or data.get("reviewer_name"),
                "source": data.get("source") or "manual",
            }
            )
        )
        log = OperationLog(module="test_case", action="review_opinion", target_type="test_case", target_id=case.id, detail=opinion)
        session.add(log)
        session.flush()
        return safe_summary_payload(sanitize_payload({"opinion": opinion, "log": _operation_log_brief(log), "case": model_dict(case)}))


@router.post("/test-cases/rule-validate")
def rule_validate_test_cases(payload: WritePayload):
    data = safe_summary_payload(sanitize_payload(payload_dict(payload)))
    with session_scope() as session:
        cases = _load_review_cases(session, data)
        result = _review_db_test_cases(session, cases, update_status=False, log_action=None) if cases else _lightweight_review_payload(data)
        summary = result["summary"]
        return safe_summary_payload(
            sanitize_payload(
            {
                **result,
                "valid": summary["needs_review"] == 0,
                "score": summary["avg_score"],
                "findings": [issue for item in result["items"] for issue in item.get("issues", [])],
            }
            )
        )


@router.post("/test-cases/ai-review")
def ai_review_test_cases(payload: WritePayload):
    data = safe_summary_payload(sanitize_payload(payload_dict(payload)))
    with session_scope() as session:
        cases = _load_review_cases(session, data)
        result = _review_db_test_cases(session, cases, update_status=False, log_action=None) if cases else _lightweight_review_payload(data)
        summary = result["summary"]
        suggestions = []
        for item in result["items"]:
            suggestions.extend(item.get("suggested_actions", []))
        return safe_summary_payload(
            sanitize_payload(
            {
                **result,
                "reviewed": True,
                "score": summary["avg_score"],
                "suggestions": list(dict.fromkeys(suggestions)),
                "provider_call_performed": False,
                "llm_provider_called": False,
            }
            )
        )


@router.post("/test-cases/{caseId}/confirm")
def confirm_test_case(caseId: str):
    with session_scope() as session:
        case = session.get(TestCase, to_int(caseId, "caseId"))
        if case is None or case.is_deleted:
            raise HTTPException(status_code=404, detail=f"TestCase({caseId}) not found")
        case.status = "confirmed"
        session.flush()
        return model_dict(case)


@router.delete("/test-cases/{caseId}")
def delete_test_case(caseId: str):
    with session_scope() as session:
        case = session.get(TestCase, to_int(caseId, "caseId"))
        if case is None or case.is_deleted:
            raise HTTPException(status_code=404, detail=f"TestCase({caseId}) not found")
        case.is_deleted = True
        session.flush()
        return {"deleted": True, "id": case.id}


@router.post("/projects/{projectId}/test-rounds")
def create_test_round(projectId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        try:
            round_ = AitestRepository(session).create_test_round(
                to_int(projectId, "projectId"),
                data.get("name") or "未命名测试轮次",
                to_int(data["requirement_item_id"], "requirement_item_id") if data.get("requirement_item_id") is not None else None,
                to_int(data["document_id"], "document_id") if data.get("document_id") is not None else None,
            )
            return model_dict(round_)
        except Exception as exc:
            raise repo_error(exc)


@router.get("/projects/{projectId}/test-rounds")
def list_project_test_rounds(
    projectId: str,
    page_num: int = Query(1, alias="page"),
    page_size: int = Query(20, alias="pageSize"),
    status: str | None = None,
):
    with session_scope() as session:
        project = require_db_item(session, Project, projectId, "projectId")
        criteria: list[Any] = [TestRound.project_id == project.id]
        if status:
            criteria.append(TestRound.status == status)
        return db_page(session, TestRound, page_num, page_size, *criteria, order_by=TestRound.id.desc())


@router.get("/test-rounds/{roundId}")
def get_test_round(roundId: str):
    with session_scope() as session:
        round_ = session.get(TestRound, to_int(roundId, "roundId"))
        if round_ is None:
            raise HTTPException(status_code=404, detail=f"TestRound({roundId}) not found")
        return model_dict(round_)


@router.patch("/test-rounds/{roundId}/complete")
def complete_test_round(roundId: str):
    with session_scope() as session:
        round_ = session.get(TestRound, to_int(roundId, "roundId"))
        if round_ is None:
            raise HTTPException(status_code=404, detail=f"TestRound({roundId}) not found")
        round_.status = "completed"
        session.flush()
        return model_dict(round_)


def _execution_defect(session: Any, execution_id: int) -> Defect | None:
    return session.scalar(select(Defect).where(Defect.execution_id == execution_id).order_by(Defect.id.desc()))


def _execution_public_dict(session: Any, execution: Execution) -> dict[str, Any]:
    data = model_dict(execution)
    defect = _execution_defect(session, execution.id)
    if defect is not None:
        data["defect_id"] = defect.id
        data["defect"] = enrich_defect_dict(defect)
    return sanitize_payload(data)


def _defect_status_from_payload(data: dict[str, Any], default: str = "open") -> str:
    raw = data.get("defect_status", data.get("defectStatus"))
    if raw is None:
        raw = data.get("status") if str(data.get("status") or "").lower() not in {"pass", "passed", "fail", "failed", "blocked", "skipped"} else None
    return str(raw or default)


def _create_or_update_defect_for_execution(session: Any, execution: Execution, payload: dict[str, Any] | None = None) -> Defect:
    case = session.get(TestCase, execution.case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"TestCase({execution.case_id}) not found")
    data = sanitize_loop_payload(payload or {})
    suggestion_input = data.get("suggestion") if isinstance(data.get("suggestion"), dict) else data
    suggestion = build_defect_suggestion(execution, case, suggestion_input)
    existing = _execution_defect(session, execution.id)
    if existing is None:
        defect = Defect(
            defect_number=AitestRepository(session)._next_code("DEF", Defect, "defect_number"),
            project_id=execution.project_id,
            execution_id=execution.id,
            case_id=to_int(data.get("case_id"), "case_id") if data.get("case_id") is not None else execution.case_id,
            requirement_item_id=execution.requirement_item_id,
            title=str(data.get("title") or data.get("defect_title") or suggestion["title"])[:255],
            actual_result=data.get("actual_result") or suggestion.get("actual_result"),
            severity=data.get("severity") or suggestion.get("severity") or "normal",
            status=_defect_status_from_payload(data, "open"),
            remark=encode_defect_remark(suggestion.get("suggested_defect_fields", suggestion), data.get("remark")),
        )
        session.add(defect)
    else:
        defect = existing
        defect.case_id = to_int(data.get("case_id"), "case_id") if data.get("case_id") is not None else defect.case_id or execution.case_id
        defect.title = str(data.get("title") or data.get("defect_title") or defect.title or suggestion["title"])[:255]
        defect.actual_result = data.get("actual_result") or defect.actual_result or suggestion.get("actual_result")
        defect.severity = data.get("severity") or defect.severity or suggestion.get("severity") or "normal"
        defect.status = _defect_status_from_payload(data, defect.status or "open")
        defect.remark = encode_defect_remark({**suggestion.get("suggested_defect_fields", suggestion), **remark_update_fields(data)}, defect.remark)
    case_id = defect.case_id
    if case_id is not None:
        linked_case = session.get(TestCase, case_id)
        if linked_case is None:
            raise HTTPException(status_code=404, detail=f"TestCase({case_id}) not found")
        if linked_case.project_id != defect.project_id:
            raise HTTPException(status_code=400, detail="case_id must belong to the same project")
    session.flush()
    r2_log(session, "defect", "create_from_execution", defect.id, {"execution_id": execution.id, "case_id": defect.case_id})
    return defect


def _defect_reminders(session: Any, project_id: int | None = None) -> list[OperationLog]:
    criteria: list[Any] = [OperationLog.module == "defect", OperationLog.action == "retest_reminder"]
    if project_id is not None:
        defect_ids = list(session.scalars(select(Defect.id).where(Defect.project_id == project_id)))
        if not defect_ids:
            return []
        criteria.append(OperationLog.target_id.in_(defect_ids))
    return list(session.scalars(select(OperationLog).where(*criteria).order_by(OperationLog.id.desc())))


@router.get("/executions/templates")
def get_execution_templates():
    return execution_templates()


@router.post("/executions")
def create_execution(payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        try:
            execution = AitestRepository(session).create_execution_record(
                case_id=to_int(data.get("case_id"), "case_id"),
                status=normalize_execution_status(data.get("status", "passed")),
                round_id=to_int(data["round_id"], "round_id") if data.get("round_id") is not None else None,
                executor_type=data.get("executor_type", "manual"),
                actual_result=data.get("actual_result"),
                execution_time=data.get("execution_time"),
                block_reason=data.get("block_reason"),
                skip_reason=data.get("skip_reason"),
                pass_remark=data.get("pass_remark"),
                create_defect=False,
                defect_title=data.get("defect_title"),
            )
            if status_bucket(execution.status) in {"failed", "blocked"} and data.get("create_defect", True):
                _create_or_update_defect_for_execution(session, execution, data)
            result = _execution_public_dict(session, execution)
            result["status_alias"] = data.get("status", result["status"])
            return result
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise exc
            raise repo_error(exc)


@router.post("/executions/batch")
def batch_create_executions(payload: WritePayload):
    data = payload_dict(payload)
    rows = data.get("executions") or data.get("cases") or data.get("case_ids") or []
    executions: list[dict[str, Any]] = []
    created_defects = 0
    with session_scope() as session:
        repo = AitestRepository(session)
        try:
            for row in rows:
                row_data = row if isinstance(row, dict) else {"case_id": row}
                merged = {**data, **row_data}
                execution = repo.create_execution_record(
                    case_id=to_int(merged.get("case_id"), "case_id"),
                    status=normalize_execution_status(merged.get("status", "passed")),
                    round_id=to_int(merged["round_id"], "round_id") if merged.get("round_id") is not None else None,
                    executor_type=merged.get("executor_type", "manual"),
                    actual_result=merged.get("actual_result"),
                    execution_time=merged.get("execution_time"),
                    block_reason=merged.get("block_reason"),
                    skip_reason=merged.get("skip_reason"),
                    pass_remark=merged.get("pass_remark"),
                    create_defect=False,
                    defect_title=merged.get("defect_title"),
                )
                before_defect = _execution_defect(session, execution.id)
                if status_bucket(execution.status) in {"failed", "blocked"} and merged.get("create_defect", True):
                    defect = _create_or_update_defect_for_execution(session, execution, merged)
                    if before_defect is None and defect is not None:
                        created_defects += 1
                executions.append(_execution_public_dict(session, execution))
            summary_counts = {key: 0 for key in ("passed", "failed", "blocked", "skipped")}
            for item in executions:
                bucket = status_bucket(item.get("status"))
                if bucket in summary_counts:
                    summary_counts[bucket] += 1
            return {
                "executions": executions,
                "summary": {
                    "total": len(executions),
                    "passed": summary_counts["passed"],
                    "failed": summary_counts["failed"],
                    "blocked": summary_counts["blocked"],
                    "skipped": summary_counts["skipped"],
                    "created_defects": created_defects,
                },
            }
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise exc
            raise repo_error(exc)


@router.post("/executions/{executionId}/defect-suggestion")
def execution_defect_suggestion(executionId: str, payload: WritePayload | None = None):
    data = payload_dict(payload)
    with session_scope() as session:
        execution = session.get(Execution, to_int(executionId, "executionId"))
        if execution is None:
            raise HTTPException(status_code=404, detail=f"Execution({executionId}) not found")
        case = session.get(TestCase, execution.case_id)
        return build_defect_suggestion(execution, case, data)


@router.post("/executions/{executionId}/create-defect")
def create_defect_from_execution_endpoint(executionId: str, payload: WritePayload | None = None):
    data = payload_dict(payload)
    with session_scope() as session:
        execution = session.get(Execution, to_int(executionId, "executionId"))
        if execution is None:
            raise HTTPException(status_code=404, detail=f"Execution({executionId}) not found")
        defect = _create_or_update_defect_for_execution(session, execution, data)
        return {"defect": enrich_defect_dict(defect), "execution": _execution_public_dict(session, execution)}


@router.get("/executions/history")
def execution_history(projectId: str | None = None, requirementItemId: str | None = None, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    criteria = []
    if projectId is not None:
        criteria.append(Execution.project_id == to_int(projectId, "projectId"))
    if requirementItemId is not None:
        criteria.append(Execution.requirement_item_id == to_int(requirementItemId, "requirementItemId"))
    with session_scope() as session:
        return db_page(session, Execution, page_num, page_size, *criteria, order_by=Execution.id.desc())


@router.get("/executions/statistics")
def execution_statistics(projectId: str | None = None):
    criteria = [Execution.project_id == to_int(projectId, "projectId")] if projectId is not None else []
    with session_scope() as session:
        records = list(session.scalars(select(Execution).where(*criteria)))
        defect_criteria = [Defect.project_id == to_int(projectId, "projectId")] if projectId is not None else []
        defects = list(session.scalars(select(Defect).where(*defect_criteria)))
        reminders = _defect_reminders(session, to_int(projectId, "projectId")) if projectId is not None else _defect_reminders(session)
        return build_execution_statistics(records, defects, reminders)


@router.get("/defects")
def list_defects(
    projectId: str | None = None,
    page_num: int = Query(1, alias="page"),
    page_size: int = Query(20, alias="pageSize"),
    status: str | None = None,
    severity: str | None = None,
    caseId: str | None = None,
    case_id: str | None = None,
):
    criteria = [Defect.project_id == to_int(projectId, "projectId")] if projectId is not None else []
    if status:
        criteria.append(Defect.status == status)
    if severity:
        criteria.append(Defect.severity == severity)
    linked_case_id = case_id or caseId
    if linked_case_id is not None:
        criteria.append(Defect.case_id == to_int(linked_case_id, "caseId"))
    with session_scope() as session:
        stmt = select(Defect).where(*criteria).order_by(Defect.id.desc()).offset((page_num - 1) * page_size).limit(page_size)
        count_stmt = select(func.count()).select_from(Defect).where(*criteria)
        return {
            "list": [enrich_defect_dict(item) for item in session.scalars(stmt)],
            "total": session.scalar(count_stmt) or 0,
            "page": page_num,
            "pageSize": page_size,
        }


@router.get("/defects/export")
def export_defects_endpoint(projectId: str | None = None, project_id: str | None = None, status: str | None = None, format: str = Query("markdown")):
    with session_scope() as session:
        try:
            return export_defects(
                session,
                project_id=to_int(project_id or projectId, "projectId") if (project_id or projectId) is not None else None,
                status=status,
                output_format=format,
            )
        except ExportPayloadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/defects/{defectId}")
def update_defect(defectId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        defect = session.get(Defect, to_int(defectId, "defectId"))
        if defect is None:
            raise HTTPException(status_code=404, detail=f"Defect({defectId}) not found")
        for key in ("title", "actual_result", "severity", "status"):
            if key in data:
                value = sanitize_payload(data[key])
                setattr(defect, key, str(value)[:255] if key == "title" and value is not None else value)
        if "case_id" in data or "caseId" in data:
            value = data.get("case_id", data.get("caseId"))
            if value in (None, ""):
                defect.case_id = None
            else:
                case = session.get(TestCase, to_int(value, "case_id"))
                if case is None:
                    raise HTTPException(status_code=404, detail=f"TestCase({value}) not found")
                if case.project_id != defect.project_id:
                    raise HTTPException(status_code=400, detail="case_id must belong to the same project")
                defect.case_id = case.id
                defect.requirement_item_id = defect.requirement_item_id or case.requirement_item_id
        remark_fields = remark_update_fields(data)
        if "remark" in data:
            remark_fields["note"] = data.get("remark")
        if remark_fields:
            defect.remark = encode_defect_remark(remark_fields, defect.remark)
        session.flush()
        r2_log(session, "defect", "update", defect.id, {"fields": [key for key in data if not is_sensitive_key_name(key)]})
        return enrich_defect_dict(defect)


@router.post("/defects/{defectId}/link-case")
def link_defect_case(defectId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        defect = session.get(Defect, to_int(defectId, "defectId"))
        if defect is None:
            raise HTTPException(status_code=404, detail=f"Defect({defectId}) not found")
        case_id = data.get("case_id", data.get("caseId"))
        case = session.get(TestCase, to_int(case_id, "case_id"))
        if case is None:
            raise HTTPException(status_code=404, detail=f"TestCase({case_id}) not found")
        if case.project_id != defect.project_id:
            raise HTTPException(status_code=400, detail="case_id must belong to the same project")
        defect.case_id = case.id
        defect.requirement_item_id = defect.requirement_item_id or case.requirement_item_id
        session.flush()
        r2_log(session, "defect", "link_case", defect.id, {"case_id": case.id})
        return enrich_defect_dict(defect)


@router.post("/defects/{defectId}/unlink-case")
def unlink_defect_case(defectId: str):
    with session_scope() as session:
        defect = session.get(Defect, to_int(defectId, "defectId"))
        if defect is None:
            raise HTTPException(status_code=404, detail=f"Defect({defectId}) not found")
        defect.case_id = None
        session.flush()
        r2_log(session, "defect", "unlink_case", defect.id, {})
        return enrich_defect_dict(defect)


@router.post("/defects/{defectId}/retest-reminder")
def defect_retest_reminder(defectId: str, payload: WritePayload | None = None):
    data = payload_dict(payload)
    with session_scope() as session:
        defect = session.get(Defect, to_int(defectId, "defectId"))
        if defect is None:
            raise HTTPException(status_code=404, detail=f"Defect({defectId}) not found")
        reminder = build_retest_reminder(defect, due_at=data.get("due_at") or data.get("dueAt"), assignee=data.get("assignee"))
        if data.get("save", True):
            session.add(
                OperationLog(
                    module="defect",
                    action="retest_reminder",
                    target_type="defect",
                    target_id=defect.id,
                    detail=sanitize_payload(reminder),
                )
            )
        defect.remark = encode_defect_remark({"due_at": reminder["due_at"], "assignee": reminder.get("assignee")}, defect.remark)
        session.flush()
        return reminder


@router.get("/defects/{defectId}/copy-text")
def defect_copy_text_r24(defectId: str):
    with session_scope() as session:
        defect = session.get(Defect, to_int(defectId, "defectId"))
        if defect is None:
            raise HTTPException(status_code=404, detail=f"Defect({defectId}) not found")
        case = session.get(TestCase, defect.case_id) if defect.case_id is not None else None
        return {"text": build_copy_text(defect, case)}


@router.get("/projects/{projectId}/execution-trend")
def project_execution_trend(projectId: str, days: int | None = Query(None, ge=1, le=366)):
    with session_scope() as session:
        project = require_db_item(session, Project, projectId, "projectId")
        records = list(session.scalars(select(Execution).where(Execution.project_id == project.id).order_by(Execution.executed_at.asc())))
        defects = list(session.scalars(select(Defect).where(Defect.project_id == project.id).order_by(Defect.created_at.asc())))
        trend = aggregate_execution_trend(records, defects, recent_days=days)
        return {"project_id": project.id, **trend, "list": trend["trend"]}


@router.get("/projects/{projectId}/defect-loop-summary")
def project_defect_loop_summary(projectId: str):
    with session_scope() as session:
        project = require_db_item(session, Project, projectId, "projectId")
        records = list(session.scalars(select(Execution).where(Execution.project_id == project.id)))
        defects = list(session.scalars(select(Defect).where(Defect.project_id == project.id)))
        reminders = _defect_reminders(session, project.id)
        return {"project_id": project.id, **build_defect_loop_summary(records, defects, reminders)}


def defect_copy_text(defectId: str):
    with session_scope() as session:
        defect = session.get(Defect, to_int(defectId, "defectId"))
        if defect is None:
            raise HTTPException(status_code=404, detail=f"Defect({defectId}) not found")
        return {"text": f"标题：{defect.title}\n严重级别：{defect.severity}\n状态：{defect.status}"}


@router.get("/projects/{projectId}/api-test-libs")
def list_api_test_libs(projectId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        pid = to_int(projectId, "projectId")
        return db_page(session, ApiTestLib, page_num, page_size, ApiTestLib.project_id == pid, ApiTestLib.is_deleted.is_(False), order_by=ApiTestLib.id.desc())


@router.post("/projects/{projectId}/api-test-libs")
def create_api_test_lib(projectId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        require_db_item(session, Project, projectId, "projectId")
        lib = ApiTestLib(
            project_id=to_int(projectId, "projectId"),
            source_document_id=to_int(data["source_document_id"], "source_document_id") if data.get("source_document_id") is not None else None,
            name=data.get("name") or "Unnamed API Test Lib",
            description=data.get("description"),
            import_source=data.get("import_source"),
        )
        session.add(lib)
        session.flush()
        r2_log(session, "api_test_lib", "create", lib.id, {"project_id": lib.project_id})
        return model_dict(lib)


@router.patch("/api-test-libs/{libId}")
def update_api_test_lib(libId: str, payload: WritePayload):
    with session_scope() as session:
        lib = require_db_item(session, ApiTestLib, libId, "libId")
        update_columns(lib, payload_dict(payload), ("name", "description", "import_source"))
        session.flush()
        r2_log(session, "api_test_lib", "update", lib.id)
        return model_dict(lib)


@router.delete("/api-test-libs/{libId}")
def delete_api_test_lib(libId: str):
    with session_scope() as session:
        lib = require_db_item(session, ApiTestLib, libId, "libId")
        lib.is_deleted = True
        session.flush()
        r2_log(session, "api_test_lib", "delete", lib.id)
        return {"deleted": True, "id": lib.id}


@router.post("/api-test-libs/{libId}/import-documents")
def import_api_documents(libId: str, payload: WritePayload):
    data = payload_dict(payload)
    try:
        import_result = parse_api_import_payload(data)
    except ApiImportError as exc:
        raise HTTPException(status_code=400, detail=safe_import_error_detail(exc)) from exc
    with session_scope() as session:
        lib = require_db_item(session, ApiTestLib, libId, "libId")
        response = _persist_imported_apis(session, lib, import_result, "import_document")
        return response


@router.get("/api-test-libs/{libId}/apis")
def list_apis(libId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        require_db_item(session, ApiTestLib, libId, "libId")
        return db_page(session, ApiEndpoint, page_num, page_size, ApiEndpoint.lib_id == to_int(libId, "libId"), ApiEndpoint.is_deleted.is_(False), order_by=ApiEndpoint.id.desc())


@router.post("/api-test-libs/{libId}/apis/import")
def import_apis(libId: str, payload: WritePayload):
    data = payload_dict(payload)
    try:
        import_result = parse_api_import_payload(data)
    except ApiImportError as exc:
        raise HTTPException(status_code=400, detail=safe_import_error_detail(exc)) from exc
    with session_scope() as session:
        lib = require_db_item(session, ApiTestLib, libId, "libId")
        return _persist_imported_apis(session, lib, import_result, "import")


def _persist_imported_apis(session: Any, lib: ApiTestLib, import_result: Any, action: str) -> dict[str, Any]:
    created: list[dict[str, Any]] = []
    created_cases: list[dict[str, Any]] = []
    for index, api_data in enumerate(import_result.endpoints):
        endpoint = ApiEndpoint(
            lib_id=lib.id,
            requirement_item_id=to_int(api_data["requirement_item_id"], "requirement_item_id") if api_data.get("requirement_item_id") is not None else None,
            name=api_data.get("name") or f"{api_data.get('method', 'GET')} {api_data.get('path', '/')}",
            method=(api_data.get("method") or "GET").upper(),
            path=api_data.get("path") or "/",
            headers_schema=sanitize_payload(api_data.get("headers_schema") or {}),
            query_schema=sanitize_payload(api_data.get("query_schema") or {}),
            body_schema=sanitize_payload(api_data.get("body_schema") or {}),
            response_schema=sanitize_payload(api_data.get("response_schema") or {}),
            description=api_data.get("description"),
        )
        session.add(endpoint)
        session.flush()
        created.append(model_dict(endpoint))
        if import_result.generate_cases:
            case_data = import_result.test_cases[index]
            expected_status = int(case_data.get("expected_status", 200))
            case = ApiTestCase(
                endpoint_id=endpoint.id,
                lib_id=lib.id,
                requirement_item_id=endpoint.requirement_item_id,
                name=case_data.get("name") or f"{endpoint.name} success",
                category=case_data.get("category", "contract"),
                request_headers=sanitize_payload(case_data.get("request_headers") or {}),
                request_query=sanitize_payload(case_data.get("request_query") or {}),
                request_body=sanitize_payload(case_data.get("request_body") or {}),
                content_type=case_data.get("content_type", "application/json"),
                expected_status=expected_status,
                assertions=case_data.get("assertions") or [{"type": "status_code", "expected": expected_status}],
                status=case_data.get("status", "ready"),
                sort_order=index + 1,
            )
            session.add(case)
            session.flush()
            created_cases.append(model_dict(case))
    lib.import_source = import_result.source
    lib.latest_sync_at = datetime.now(timezone.utc)
    session.flush()
    r2_log(session, "api_endpoint", action, None, {"lib_id": lib.id, "count": len(created), "source": import_result.source, "test_case_count": len(created_cases)})
    response: dict[str, Any] = {"imported": len(created), "apis": created}
    if import_result.generate_cases:
        response["test_cases"] = created_cases
        response["test_case_count"] = len(created_cases)
    return response


@router.patch("/apis/{apiId}")
def update_api(apiId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        endpoint = require_db_item(session, ApiEndpoint, apiId, "apiId")
        update_columns(endpoint, data, ("name", "method", "path", "headers_schema", "query_schema", "body_schema", "response_schema", "description"))
        if endpoint.method:
            endpoint.method = endpoint.method.upper()
        session.flush()
        r2_log(session, "api_endpoint", "update", endpoint.id)
        return model_dict(endpoint)


@router.delete("/apis/{apiId}")
def delete_api(apiId: str):
    with session_scope() as session:
        endpoint = require_db_item(session, ApiEndpoint, apiId, "apiId")
        endpoint.is_deleted = True
        session.flush()
        r2_log(session, "api_endpoint", "delete", endpoint.id)
        return {"deleted": True, "id": endpoint.id}


@router.post("/apis/debug")
def debug_api(payload: WritePayload):
    data = payload_dict(payload)
    result = run_api_request(data)
    response = result.get("response_snapshot") or {}
    output: dict[str, Any] = {
        "status_code": response.get("status_code"),
        "duration_ms": result["duration_ms"],
        "headers": response.get("headers", {}),
        "body": response.get("body"),
        "request": result["request_snapshot"],
        "assertion_results": result["assertion_results"],
        "assertions": result["assertion_results"],
        "status": result["status"],
        "error_message": result["error_message"],
    }
    if data.get("save_as_case") or data.get("saveAsCase"):
        try:
            with session_scope() as session:
                endpoint_id = data.get("endpoint_id") or data.get("endpointId") or data.get("api_id") or data.get("apiId")
                endpoint = require_db_item(session, ApiEndpoint, endpoint_id, "endpoint_id")
                expected_status = int(data.get("expected_status") or data.get("expectedStatus") or response.get("status_code") or 200)
                case = ApiTestCase(
                    endpoint_id=endpoint.id,
                    lib_id=endpoint.lib_id,
                    requirement_item_id=endpoint.requirement_item_id,
                    name=data.get("case_name") or data.get("caseName") or data.get("name") or f"{endpoint.name} debug case",
                    category=data.get("category", "debug"),
                    request_headers=sanitize_payload(data.get("headers") or {}),
                    request_query=sanitize_payload(data.get("query") or data.get("params") or {}),
                    request_body=sanitize_payload(data.get("body")),
                    content_type=data.get("content_type") or data.get("contentType") or "application/json",
                    expected_status=expected_status,
                    assertions=sanitize_payload(data.get("assertions") or [{"type": "status_code", "expected": expected_status}]),
                    pre_script=data.get("pre_script"),
                    post_script=data.get("post_script"),
                    status="ready",
                )
                session.add(case)
                session.flush()
                r2_log(session, "api_test_case", "save_debug_case", case.id, {"endpoint_id": endpoint.id})
                saved_case = model_dict(case)
                saved_case["api_id"] = case.endpoint_id
                output["saved_case_id"] = case.id
                output["test_case"] = saved_case
                output["saved_case"] = saved_case
        except Exception as exc:
            output["save_error"] = sanitize_payload({"error": str(exc)[:500]})
    return output


def _active_api_environment(session: Any, lib_id: int) -> ApiEnvironment | None:
    return session.scalar(
        select(ApiEnvironment).where(
            ApiEnvironment.lib_id == lib_id,
            ApiEnvironment.is_active.is_(True),
            ApiEnvironment.is_deleted.is_(False),
        )
    )


def _api_case_payload(case: ApiTestCase, endpoint: ApiEndpoint, environment: ApiEnvironment | None, overrides: dict[str, Any]) -> dict[str, Any]:
    return build_case_request_payload(case, endpoint, environment, overrides)


def _create_api_execution(
    session: Any,
    case: ApiTestCase,
    run_type: str,
    result: dict[str, Any],
    environment: ApiEnvironment | None = None,
) -> ApiExecution:
    execution = ApiExecution(
        lib_id=case.lib_id,
        endpoint_id=case.endpoint_id,
        case_id=case.id,
        environment_id=environment.id if environment else None,
        run_type=run_type,
        status=result["status"],
        request_snapshot=sanitize_api_payload(result.get("request_snapshot")),
        response_snapshot=sanitize_api_payload(result.get("response_snapshot")),
        assertion_results=sanitize_api_payload(result.get("assertion_results") or []),
        duration_ms=result.get("duration_ms"),
        error_message=sanitize_api_payload({"error": result.get("error_message")}).get("error"),
    )
    session.add(execution)
    session.flush()
    return execution


@router.post("/apis/{apiId}/generate-test-cases")
def generate_api_test_cases(apiId: str, payload: WritePayload | None = None):
    data = payload_dict(payload)
    with session_scope() as session:
        api = require_db_item(session, ApiEndpoint, apiId, "apiId")
        case = ApiTestCase(
            endpoint_id=api.id,
            lib_id=api.lib_id,
            requirement_item_id=api.requirement_item_id,
            name=data.get("name") or f"{api.name} normal response",
            category=data.get("category", "contract"),
            request_headers=sanitize_payload(data.get("request_headers") or {}),
            request_query=sanitize_payload(data.get("request_query") or {}),
            request_body=sanitize_payload(data.get("request_body")),
            content_type=data.get("content_type", "application/json"),
            expected_status=int(data.get("expected_status", 200)),
            assertions=data.get("assertions") or [{"type": "status_code", "expected": 200}],
            pre_script=data.get("pre_script"),
            post_script=data.get("post_script"),
            status="draft",
        )
        session.add(case)
        session.flush()
        lib = require_db_item(session, ApiTestLib, api.lib_id, "lib_id")
        job = create_db_job(session, lib.project_id, "generate_api_test_cases", {"api_id": api.id, **data}, {"test_case_ids": [case.id]})
        result = model_dict(case)
        result["api_id"] = case.endpoint_id
        return {"job": model_dict(job), "test_cases": [result]}


@router.get("/apis/{apiId}/test-cases")
def list_api_test_cases(apiId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        require_db_item(session, ApiEndpoint, apiId, "apiId")
        result = db_page(session, ApiTestCase, page_num, page_size, ApiTestCase.endpoint_id == to_int(apiId, "apiId"), ApiTestCase.is_deleted.is_(False), order_by=ApiTestCase.id.desc())
        for item in result["list"]:
            item["api_id"] = item.get("endpoint_id")
        return result


@router.post("/api-test-cases/{caseId}/execute")
def execute_api_test_case(caseId: str, payload: WritePayload | None = None):
    data = payload_dict(payload)
    with session_scope() as session:
        case = require_db_item(session, ApiTestCase, caseId, "caseId")
        endpoint = require_db_item(session, ApiEndpoint, case.endpoint_id, "endpoint_id")
        environment_id = data.get("environment_id") or data.get("environmentId")
        environment = require_db_item(session, ApiEnvironment, environment_id, "environment_id") if environment_id else _active_api_environment(session, case.lib_id)
        if environment is not None or data.get("base_url") or data.get("baseUrl"):
            request_payload = _api_case_payload(case, endpoint, environment, data)
            result = attach_runtime_context(run_api_request(request_payload), request_payload.get("_runtime_context"))
            execution = _create_api_execution(session, case, "case", result, environment)
        else:
            result = {
                "status": "passed",
                "request_snapshot": sanitize_payload({"method": endpoint.method, "path": endpoint.path, "headers": case.request_headers, "query": case.request_query, "body": case.request_body}),
                "response_snapshot": {"status_code": case.expected_status, "body": {"placeholder": True}},
                "assertion_results": [{"type": "status_code", "passed": True, "expected": case.expected_status, "actual": case.expected_status}],
                "duration_ms": 20,
                "error_message": None,
            }
            execution = ApiExecution(
                lib_id=case.lib_id,
                endpoint_id=case.endpoint_id,
                case_id=case.id,
                run_type="case",
                status=result["status"],
                request_snapshot=result["request_snapshot"],
                response_snapshot=result["response_snapshot"],
                assertion_results=result["assertion_results"],
                duration_ms=result["duration_ms"],
            )
            session.add(execution)
            session.flush()
        r2_log(session, "api_execution", "execute_case", execution.id, {"case_id": case.id})
        response = model_dict(execution)
        if isinstance(result, dict) and result.get("variables"):
            response["variables"] = sanitize_runtime_payload(result["variables"])
        if isinstance(result, dict) and result.get("missing_variables"):
            response["missing_variables"] = sanitize_runtime_payload(result["missing_variables"])
        return response


@router.post("/api-test-cases/batch-executions")
def batch_execute_api_test_cases(payload: WritePayload):
    data = payload_dict(payload)
    ids = data.get("case_ids", [])
    executions = []
    with session_scope() as session:
        environment_id = data.get("environment_id") or data.get("environmentId")
        specified_environment = require_db_item(session, ApiEnvironment, environment_id, "environment_id") if environment_id else None
        for case_id in ids:
            case = require_db_item(session, ApiTestCase, case_id, "case_id")
            endpoint = require_db_item(session, ApiEndpoint, case.endpoint_id, "endpoint_id")
            environment = specified_environment or _active_api_environment(session, case.lib_id)
            if environment is not None or data.get("base_url") or data.get("baseUrl"):
                request_payload = _api_case_payload(case, endpoint, environment, data)
                result = attach_runtime_context(run_api_request(request_payload), request_payload.get("_runtime_context"))
                execution = _create_api_execution(session, case, "batch", result, environment)
            else:
                result = {
                    "status": "passed",
                    "request_snapshot": sanitize_payload({"method": endpoint.method, "path": endpoint.path, "headers": case.request_headers, "query": case.request_query, "body": case.request_body}),
                    "response_snapshot": {"status_code": case.expected_status, "body": {"placeholder": True}},
                    "assertion_results": [{"type": "status_code", "passed": True, "expected": case.expected_status, "actual": case.expected_status}],
                    "duration_ms": 20,
                    "error_message": None,
                }
                execution = ApiExecution(
                    lib_id=case.lib_id,
                    endpoint_id=case.endpoint_id,
                    case_id=case.id,
                    run_type="batch",
                    status=result["status"],
                    request_snapshot=result["request_snapshot"],
                    response_snapshot=result["response_snapshot"],
                    assertion_results=result["assertion_results"],
                    duration_ms=result["duration_ms"],
                )
                session.add(execution)
                session.flush()
            execution_payload = model_dict(execution)
            if isinstance(result, dict) and result.get("variables"):
                execution_payload["variables"] = sanitize_runtime_payload(result["variables"])
            if isinstance(result, dict) and result.get("missing_variables"):
                execution_payload["missing_variables"] = sanitize_runtime_payload(result["missing_variables"])
            executions.append(execution_payload)
        r2_log(session, "api_execution", "batch_execute", None, {"count": len(executions)})
        return {"executions": executions}


@router.get("/api-test-libs/{libId}/environments")
def list_api_environments(libId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        require_db_item(session, ApiTestLib, libId, "libId")
        return db_page(session, ApiEnvironment, page_num, page_size, ApiEnvironment.lib_id == to_int(libId, "libId"), ApiEnvironment.is_deleted.is_(False), order_by=ApiEnvironment.id.desc())


@router.post("/api-test-libs/{libId}/environments")
def create_api_environment(libId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        require_db_item(session, ApiTestLib, libId, "libId")
        env = ApiEnvironment(
            lib_id=to_int(libId, "libId"),
            name=data.get("name") or "Default",
            base_url=data.get("base_url") or data.get("baseUrl") or "http://localhost",
            headers=sanitize_payload(data.get("headers") or {}),
            variables=sanitize_payload(data.get("variables") or {}),
            is_active=bool(data.get("is_active", data.get("active", False))),
            sort_order=int(data.get("sort_order", 0)),
        )
        session.add(env)
        session.flush()
        r2_log(session, "api_environment", "create", env.id, {"lib_id": libId})
        return model_dict(env)


@router.patch("/api-environments/{envId}")
def update_api_environment(envId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        env = require_db_item(session, ApiEnvironment, envId, "envId")
        if "baseUrl" in data and "base_url" not in data:
            data["base_url"] = data["baseUrl"]
        if "active" in data and "is_active" not in data:
            data["is_active"] = data["active"]
        update_columns(env, data, ("name", "base_url", "headers", "variables", "is_active", "sort_order"))
        session.flush()
        r2_log(session, "api_environment", "update", env.id)
        return model_dict(env)


@router.post("/api-environments/{envId}/activate")
def activate_api_environment(envId: str):
    with session_scope() as session:
        env = require_db_item(session, ApiEnvironment, envId, "envId")
        session.execute(text("UPDATE api_environment SET is_active = 0 WHERE lib_id = :lib_id"), {"lib_id": env.lib_id})
        env.is_active = True
        session.flush()
        r2_log(session, "api_environment", "activate", env.id, {"lib_id": env.lib_id})
        return model_dict(env)


@router.get("/api-test-libs/{libId}/mock-rules")
@router.get("/api-test-libs/{libId}/mocks")
def list_api_mock_rules(libId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        lib = require_db_item(session, ApiTestLib, libId, "libId")
        return list_api_mocks(session, lib.id, page_num, page_size)


@router.post("/api-test-libs/{libId}/mock-rules")
@router.post("/api-test-libs/{libId}/mocks")
def create_api_mock_rule(libId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        lib = require_db_item(session, ApiTestLib, libId, "libId")
        mock = create_api_mock(session, lib, data)
        r2_log(session, "api_mock", "create", mock.get("id"), {"lib_id": lib.id})
        return mock


@router.post("/api-test-libs/{libId}/mock/dispatch")
def dispatch_api_mock_for_lib(libId: str, payload: WritePayload):
    data = payload_dict(payload)
    data["lib_id"] = to_int(libId, "libId")
    with session_scope() as session:
        require_db_item(session, ApiTestLib, libId, "libId")
        return dispatch_api_mock(session, data)


@router.post("/api-mocks/dispatch")
def dispatch_api_mock_global(payload: WritePayload):
    with session_scope() as session:
        return dispatch_api_mock(session, payload_dict(payload))


@router.get("/api-test-libs/{libId}/scenarios")
def list_api_scenarios(libId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        require_db_item(session, ApiTestLib, libId, "libId")
        return db_page(session, ApiScenario, page_num, page_size, ApiScenario.lib_id == to_int(libId, "libId"), order_by=ApiScenario.id.desc())


@router.post("/api-test-libs/{libId}/scenarios")
def create_api_scenario(libId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        require_db_item(session, ApiTestLib, libId, "libId")
        scenario = ApiScenario(
            lib_id=to_int(libId, "libId"),
            name=data.get("name") or "API Scenario",
            description=data.get("description"),
            nodes=sanitize_scenario_nodes(data.get("nodes") or []),
            edges=sanitize_payload(data.get("edges") or []),
            data_mappings=sanitize_scenario_mapping_definition(data.get("data_mappings") or data.get("dataMappings") or {}),
        )
        session.add(scenario)
        session.flush()
        r2_log(session, "api_scenario", "create", scenario.id, {"lib_id": libId})
        return model_dict(scenario)


@router.patch("/api-scenarios/{scenarioId}")
def update_api_scenario(scenarioId: str, payload: WritePayload):
    data = payload_dict(payload)
    if "dataMappings" in data and "data_mappings" not in data:
        data["data_mappings"] = data["dataMappings"]
    with session_scope() as session:
        scenario = require_db_item(session, ApiScenario, scenarioId, "scenarioId")
        if "name" in data:
            scenario.name = sanitize_payload(data["name"])
        if "description" in data:
            scenario.description = sanitize_payload(data["description"])
        if "nodes" in data:
            scenario.nodes = sanitize_scenario_nodes(data["nodes"])
        if "edges" in data:
            scenario.edges = sanitize_payload(data["edges"])
        if "data_mappings" in data:
            scenario.data_mappings = sanitize_scenario_mapping_definition(data["data_mappings"])
        session.flush()
        r2_log(session, "api_scenario", "update", scenario.id)
        return model_dict(scenario)


@router.post("/api-scenarios/{scenarioId}/execute")
def execute_api_scenario(scenarioId: str, payload: WritePayload | None = None):
    data = payload_dict(payload)
    with session_scope() as session:
        scenario = require_db_item(session, ApiScenario, scenarioId, "scenarioId")
        result = run_api_scenario(session, scenario, data)
        r2_log(session, "api_execution", "execute_scenario", result.get("execution_id") or result.get("id"), {"scenario_id": scenario.id})
        return result


@router.get("/api-test-libs/{libId}/schedules")
def list_api_schedules(libId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        require_db_item(session, ApiTestLib, libId, "libId")
        return db_page(session, ApiSchedule, page_num, page_size, ApiSchedule.lib_id == to_int(libId, "libId"), ApiSchedule.is_deleted.is_(False), order_by=ApiSchedule.id.desc())


@router.post("/api-test-libs/{libId}/schedules")
def create_api_schedule(libId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        require_db_item(session, ApiTestLib, libId, "libId")
        schedule = ApiSchedule(
            lib_id=to_int(libId, "libId"),
            name=data.get("name") or "API Schedule",
            cron_expression=data.get("cron_expression") or data.get("cron") or "0 0 * * *",
            target_type=data.get("target_type", "case"),
            target_ids=[to_int(item, "target_id") for item in data.get("target_ids", [])],
            is_enabled=bool(data.get("is_enabled", data.get("enabled", False))),
            last_result=sanitize_payload(data.get("last_result")),
        )
        session.add(schedule)
        session.flush()
        r2_log(session, "api_schedule", "create", schedule.id, {"lib_id": libId})
        return model_dict(schedule)


@router.patch("/api-schedules/{scheduleId}")
def update_api_schedule(scheduleId: str, payload: WritePayload):
    data = payload_dict(payload)
    if "cron" in data and "cron_expression" not in data:
        data["cron_expression"] = data["cron"]
    if "enabled" in data and "is_enabled" not in data:
        data["is_enabled"] = data["enabled"]
    with session_scope() as session:
        schedule = require_db_item(session, ApiSchedule, scheduleId, "scheduleId")
        update_columns(schedule, data, ("name", "cron_expression", "target_type", "target_ids", "is_enabled", "last_result"))
        session.flush()
        r2_log(session, "api_schedule", "update", schedule.id)
        return model_dict(schedule)


@router.post("/api-schedules/{scheduleId}/toggle")
def toggle_api_schedule(scheduleId: str):
    with session_scope() as session:
        schedule = require_db_item(session, ApiSchedule, scheduleId, "scheduleId")
        schedule.is_enabled = not schedule.is_enabled
        session.flush()
        r2_log(session, "api_schedule", "toggle", schedule.id, {"is_enabled": schedule.is_enabled})
        return model_dict(schedule)


@router.post("/api-schedules/{scheduleId}/run")
def run_api_schedule_now(scheduleId: str, payload: WritePayload | None = None):
    data = payload_dict(payload)
    with session_scope() as session:
        schedule = require_db_item(session, ApiSchedule, scheduleId, "scheduleId")
        result = run_api_schedule(session, schedule, data)
        r2_log(session, "api_schedule", "run", schedule.id, {"status": result.get("status"), "executed": result.get("executed")})
        return result


@router.post("/api-schedules/run-due")
def run_due_api_schedule_now(payload: WritePayload | None = None):
    data = payload_dict(payload)
    with session_scope() as session:
        result = run_due_api_schedules(session, data)
        r2_log(session, "api_schedule", "run_due", None, {"executed": len(result.get("executed", [])), "skipped": len(result.get("skipped", []))})
        return result


@router.get("/projects/{projectId}/auto-projects")
def list_auto_projects(projectId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        pid = to_int(projectId, "projectId")
        return db_page(session, AutoProject, page_num, page_size, AutoProject.project_id == pid, AutoProject.is_deleted.is_(False), order_by=AutoProject.id.desc())


@router.post("/projects/{projectId}/auto-projects")
def create_auto_project(projectId: str, payload: WritePayload):
    data = sanitize_payload(payload_dict(payload))
    with session_scope() as session:
        require_db_item(session, Project, projectId, "projectId")
        project = AutoProject(
            project_id=to_int(projectId, "projectId"),
            name=data.get("name") or "Automation Project",
            type=data.get("type", "ui"),
            language=data.get("language", "python"),
            framework=data.get("framework", "pytest"),
            extra_config=data.get("extra_config") or data.get("config") or {"status": "draft"},
            git_repo_url=data.get("git_repo_url"),
            git_auth_ref=data.get("git_auth_ref"),
        )
        session.add(project)
        session.flush()
        r2_log(session, "auto_project", "create", project.id, {"project_id": project.project_id})
        return model_dict(project)


@router.patch("/auto-projects/{autoProjectId}")
def update_auto_project(autoProjectId: str, payload: WritePayload):
    data = sanitize_payload(payload_dict(payload))
    if "config" in data and "extra_config" not in data:
        data["extra_config"] = data["config"]
    with session_scope() as session:
        project = require_db_item(session, AutoProject, autoProjectId, "autoProjectId")
        update_columns(project, data, ("name", "type", "language", "framework", "extra_config", "git_repo_url", "git_auth_ref", "framework_files", "readme"))
        session.flush()
        r2_log(session, "auto_project", "update", project.id)
        return model_dict(project)


@router.delete("/auto-projects/{autoProjectId}")
def delete_auto_project(autoProjectId: str):
    with session_scope() as session:
        project = require_db_item(session, AutoProject, autoProjectId, "autoProjectId")
        project.is_deleted = True
        session.flush()
        r2_log(session, "auto_project", "delete", project.id)
        return {"deleted": True, "id": project.id}


@router.post("/auto-candidates/screen")
def screen_auto_candidates(payload: WritePayload):
    data = sanitize_payload(payload_dict(payload))
    with session_scope() as session:
        auto_project = None
        parent_id = data.get("auto_project_id") or data.get("autoProjectId")
        if parent_id is not None:
            auto_project = require_db_item(session, AutoProject, parent_id, "autoProjectId")
        result = screen_auto_candidates_payload(session, payload=data, auto_project=auto_project)
        if auto_project is not None:
            session.flush()
            r2_log(session, "auto_candidate", "screen", auto_project.id, {"total": result.get("total", 0)})
        return result


@router.get("/auto-projects/{autoProjectId}/candidates")
def list_auto_candidates(autoProjectId: str, recommendation: str | None = Query(None)):
    with session_scope() as session:
        project = require_db_item(session, AutoProject, autoProjectId, "autoProjectId")
        result = list_project_candidates(session, project)
        if recommendation:
            candidates = [
                item
                for item in result.get("candidates", [])
                if isinstance(item, dict) and str(item.get("automation_recommendation")) == str(recommendation)
            ]
            result["candidates"] = candidates
            result["total"] = len(candidates)
        session.flush()
        return result


@router.post("/auto-projects/{autoProjectId}/candidates/selection")
def select_auto_candidates(autoProjectId: str, payload: WritePayload):
    data = sanitize_payload(payload_dict(payload))
    with session_scope() as session:
        project = require_db_item(session, AutoProject, autoProjectId, "autoProjectId")
        result = update_candidate_selection(session, project, data)
        session.flush()
        r2_log(session, "auto_candidate", "select", project.id, {"selection": result.get("selection")})
        return result


def _auto_framework_files(project: AutoProject) -> dict[str, str]:
    if is_playwright_project(project):
        return playwright_framework_files(project)
    return {"README.md": f"# {project.name}\n", "tests/test_generated.py": "def test_generated_placeholder():\n    assert True\n"}


def _auto_case_file_payload(project: AutoProject) -> dict[str, Any]:
    return fallback_case_file_payload(project)


def _playwright_case_content(extension: str) -> str:
    if extension == "ts":
        return "import { test, expect } from '@playwright/test';\n\ntest('generated smoke', async ({ page }) => {\n  await page.goto('about:blank');\n  await expect(page.locator('body')).toBeVisible();\n});\n"
    return "const { test, expect } = require('@playwright/test');\n\ntest('generated smoke', async ({ page }) => {\n  await page.goto('about:blank');\n  await expect(page.locator('body')).toBeVisible();\n});\n"


@router.post("/auto-projects/{autoProjectId}/generate-framework")
def generate_auto_framework(autoProjectId: str):
    with session_scope() as session:
        project = require_db_item(session, AutoProject, autoProjectId, "autoProjectId")
        files = _auto_framework_files(project)
        project.framework_files = files
        project.readme = files["README.md"]
        job = create_db_job(session, project.project_id, "generate_auto_framework", {"auto_project_id": project.id}, {"files": list(files)})
        session.flush()
        return {"job": model_dict(job), "files": list(files), "auto_project": model_dict(project)}


@router.post("/auto-projects/{autoProjectId}/generate-cases")
def generate_auto_cases(autoProjectId: str, payload: WritePayload | None = None):
    data = sanitize_payload(payload_dict(payload))
    with session_scope() as session:
        project = require_db_item(session, AutoProject, autoProjectId, "autoProjectId")
        selected_candidates = selected_generation_candidates(session, project, data)
        generated_payloads = build_case_file_payloads(session, project, selected_candidates) if selected_candidates is not None else [_auto_case_file_payload(project)]
        case_files: list[AutoCaseFile] = []
        for item in generated_payloads:
            case_file = AutoCaseFile(
                auto_project_id=project.id,
                source_case_id=item.get("source_case_id"),
                source_api_case_id=item.get("source_api_case_id"),
                file_name=item["file_name"],
                file_path=item["file_path"],
                content=item["content"],
                case_count=int(item.get("case_count") or 1),
                automation_dsl=item.get("automation_dsl"),
            )
            session.add(case_file)
            case_files.append(case_file)
        session.flush()
        job = create_db_job(
            session,
            project.project_id,
            "generate_auto_cases",
            {"auto_project_id": project.id, **data},
            {"auto_case_file_ids": [case_file.id for case_file in case_files]},
        )
        public_cases = [auto_file_public_dict(case_file) for case_file in case_files]
        return {"job": model_dict(job), "cases": public_cases, "files": public_cases}


@router.get("/auto-projects/{autoProjectId}/files")
def list_auto_project_files(autoProjectId: str):
    with session_scope() as session:
        project = require_db_item(session, AutoProject, autoProjectId, "autoProjectId")
        files = list(
            session.scalars(
                select(AutoCaseFile)
                .where(AutoCaseFile.auto_project_id == project.id, AutoCaseFile.is_deleted.is_(False))
                .order_by(AutoCaseFile.id)
            )
        )
        items = [auto_file_public_dict(item) for item in files]
        return {"auto_project_id": project.id, "list": items, "items": items, "files": items, "total": len(items)}


@router.post("/auto-projects/{autoProjectId}/files")
def save_auto_project_file(autoProjectId: str, payload: WritePayload):
    data = sanitize_payload(payload_dict(payload))
    try:
        with session_scope() as session:
            project = require_db_item(session, AutoProject, autoProjectId, "autoProjectId")
            case_file_id = data.get("id") or data.get("case_file_id") or data.get("caseFileId")
            if case_file_id is not None:
                case_file = require_db_item(session, AutoCaseFile, case_file_id, "caseFileId")
                if case_file.auto_project_id != project.id:
                    raise HTTPException(status_code=404, detail=f"AutoCaseFile({case_file_id}) not found")
                fields = build_case_file_patch_fields(case_file, data)
                for key, value in fields.items():
                    setattr(case_file, key, value)
                session.flush()
                r2_log(session, "auto_case_file", "update", case_file.id, {"auto_project_id": project.id, "file_path": case_file.file_path})
                return {"created": False, "file": auto_file_public_dict(case_file), **auto_file_public_dict(case_file)}

            fields = build_case_file_create_fields(project, data)
            existing = session.scalar(
                select(AutoCaseFile).where(
                    AutoCaseFile.auto_project_id == project.id,
                    AutoCaseFile.file_path == fields["file_path"],
                    AutoCaseFile.is_deleted.is_(False),
                )
            )
            if existing is not None:
                for key, value in fields.items():
                    if key != "auto_project_id":
                        setattr(existing, key, value)
                session.flush()
                r2_log(session, "auto_case_file", "update", existing.id, {"auto_project_id": project.id, "file_path": existing.file_path})
                return {"created": False, "file": auto_file_public_dict(existing), **auto_file_public_dict(existing)}

            case_file = AutoCaseFile(**fields)
            session.add(case_file)
            session.flush()
            r2_log(session, "auto_case_file", "create", case_file.id, {"auto_project_id": project.id, "file_path": case_file.file_path})
            return {"created": True, "file": auto_file_public_dict(case_file), **auto_file_public_dict(case_file)}
    except AutoCenterValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/auto-case-files/{caseFileId}")
def get_auto_case_file(caseFileId: str):
    with session_scope() as session:
        case_file = require_db_item(session, AutoCaseFile, caseFileId, "caseFileId")
        return auto_file_public_dict(case_file)


@router.patch("/auto-case-files/{caseFileId}")
def update_auto_case_file(caseFileId: str, payload: WritePayload):
    data = sanitize_payload(payload_dict(payload))
    try:
        with session_scope() as session:
            case_file = require_db_item(session, AutoCaseFile, caseFileId, "caseFileId")
            fields = build_case_file_patch_fields(case_file, data)
            for key, value in fields.items():
                setattr(case_file, key, value)
            session.flush()
            r2_log(session, "auto_case_file", "update", case_file.id, {"file_path": case_file.file_path})
            return auto_file_public_dict(case_file)
    except AutoCenterValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/auto-case-files/{caseFileId}")
def delete_auto_case_file(caseFileId: str):
    with session_scope() as session:
        case_file = require_db_item(session, AutoCaseFile, caseFileId, "caseFileId")
        case_file.is_deleted = True
        session.flush()
        r2_log(session, "auto_case_file", "delete", case_file.id, {"auto_project_id": case_file.auto_project_id})
        return {"deleted": True, "id": case_file.id}


@router.post("/auto-projects/{autoProjectId}/execute")
def execute_auto_project(autoProjectId: str, payload: WritePayload | None = None):
    data = sanitize_payload(payload_dict(payload))
    with session_scope() as session:
        project = require_db_item(session, AutoProject, autoProjectId, "autoProjectId")
        total_available = session.scalar(select(func.count()).select_from(AutoCaseFile).where(AutoCaseFile.auto_project_id == project.id, AutoCaseFile.is_deleted.is_(False))) or 0
        stmt = select(AutoCaseFile).where(AutoCaseFile.auto_project_id == project.id, AutoCaseFile.is_deleted.is_(False))
        requested_file_ids = data.get("case_file_ids") if "case_file_ids" in data else data.get("caseFileIds")
        has_file_filter = isinstance(requested_file_ids, list)
        if has_file_filter:
            file_ids = [int(item) for item in requested_file_ids if str(item).isdigit()]
            if file_ids:
                stmt = stmt.where(AutoCaseFile.id.in_(file_ids))
            else:
                stmt = stmt.where(AutoCaseFile.id.in_([]))
        files = list(session.scalars(stmt.order_by(AutoCaseFile.id)))
        if str(data.get("mode") or "").lower() == "placeholder":
            execution = AutoExecution(
                auto_project_id=project.id,
                status="completed",
                summary={"total": len(files), "passed": len(files), "failed": 0, "errors": 0},
                artifacts={"report": f"/api/v2/auto-projects/{project.id}/download", "runner": {"mode": "placeholder"}, "return_code": 0, "files": []},
                log_excerpt="Automation execution used explicit placeholder mode.",
                duration_ms=20,
            )
            session.add(execution)
            session.flush()
            file_result = {
                "execution_id": execution.id,
                "status": execution.status,
                "summary": execution.summary,
                "return_code": (execution.artifacts or {}).get("return_code"),
                "runner": (execution.artifacts or {}).get("runner"),
            }
            for file in files:
                file.last_result = file_result
            r2_log(session, "auto_execution", "execute", execution.id, {"auto_project_id": project.id, "runner": {"mode": "placeholder"}})
            return model_dict(execution)
        if has_file_filter and total_available > 0 and not files:
            execution = AutoExecution(
                auto_project_id=project.id,
                status="error",
                summary={"total": 0, "passed": 0, "failed": 0, "errors": 1},
                artifacts={"files": [], "return_code": None, "runner": {"mode": "selection"}, "error": "No matching AutoCaseFile records found for case_file_ids."},
                log_excerpt="No matching AutoCaseFile records found for case_file_ids.",
                duration_ms=1,
            )
            session.add(execution)
            session.flush()
            r2_log(session, "auto_execution", "execute", execution.id, {"auto_project_id": project.id, "runner": {"mode": "selection"}})
            return model_dict(execution)
        if files:
            result = run_auto_project(
                [
                    AutoCaseFileInput(
                        id=item.id,
                        file_name=item.file_name,
                        file_path=item.file_path,
                        content=item.content,
                        case_count=item.case_count,
                    )
                    for item in files
                ],
                framework_files=project.framework_files or {},
                timeout_ms=data.get("timeout_ms"),
                env=data.get("env") if isinstance(data.get("env"), dict) else {},
                mode=str(data.get("mode") or "auto"),
                artifact_root=data.get("artifact_root"),
            )
            execution = AutoExecution(
                auto_project_id=project.id,
                status=result["status"],
                summary=result["summary"],
                artifacts=result["artifacts"],
                log_excerpt=result["log_excerpt"],
                duration_ms=result["duration_ms"],
            )
            session.add(execution)
            session.flush()
            file_result = {
                "execution_id": execution.id,
                "status": execution.status,
                "summary": execution.summary,
                "return_code": (execution.artifacts or {}).get("return_code"),
                "runner": (execution.artifacts or {}).get("runner"),
            }
            for file in files:
                file.last_result = file_result
            r2_log(session, "auto_execution", "execute", execution.id, {"auto_project_id": project.id, "runner": file_result.get("runner")})
            return model_dict(execution)

        execution = AutoExecution(
            auto_project_id=project.id,
            status="completed",
            summary={"total": total_available, "passed": total_available, "failed": 0, "errors": 0},
            artifacts={"report": f"/api/v2/auto-projects/{project.id}/download", "runner": {"mode": "placeholder"}, "return_code": 0, "files": []},
            log_excerpt="Automation execution skipped real runner and completed deterministic placeholder.",
            duration_ms=30,
        )
        session.add(execution)
        session.flush()
        r2_log(session, "auto_execution", "execute", execution.id, {"auto_project_id": project.id})
        return model_dict(execution)


@router.get("/auto-executions/{executionId}")
def get_auto_execution(executionId: str):
    with session_scope() as session:
        execution = session.get(AutoExecution, to_int(executionId, "executionId"))
        if execution is None:
            raise HTTPException(status_code=404, detail=f"AutoExecution({executionId}) not found")
        return auto_execution_detail(execution)


@router.get("/auto-executions/{executionId}/artifacts")
def list_auto_execution_artifacts(executionId: str):
    with session_scope() as session:
        execution = session.get(AutoExecution, to_int(executionId, "executionId"))
        if execution is None:
            raise HTTPException(status_code=404, detail=f"AutoExecution({executionId}) not found")
        return auto_execution_artifacts_payload(execution)


@router.get("/auto-executions/{executionId}/artifacts/preview")
def preview_auto_execution_artifact_route(executionId: str, relativePath: str = Query(...)):
    with session_scope() as session:
        execution = session.get(AutoExecution, to_int(executionId, "executionId"))
        if execution is None:
            raise HTTPException(status_code=404, detail=f"AutoExecution({executionId}) not found")
        try:
            return preview_auto_execution_artifact(execution, relativePath)
        except AutoCenterValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except AutoCenterNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/auto-executions/{executionId}/events")
def auto_execution_events(executionId: str):
    with session_scope() as session:
        if session.get(AutoExecution, to_int(executionId, "executionId")) is None:
            raise HTTPException(status_code=404, detail=f"AutoExecution({executionId}) not found")
    return StreamingResponse(iter([f"data: {json.dumps({'execution_id': executionId, 'status': 'completed'})}\n\n"]), media_type="text/event-stream")


@router.get("/auto-executions/{executionId}/artifacts/download")
def download_auto_execution_artifacts(executionId: str):
    with session_scope() as session:
        try:
            return build_auto_execution_artifacts_zip(session, execution_id=to_int(executionId, "executionId"))
        except ExportPayloadError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/auto-projects/{autoProjectId}/download")
def download_auto_project(autoProjectId: str):
    with session_scope() as session:
        try:
            return build_auto_project_zip(session, auto_project_id=to_int(autoProjectId, "autoProjectId"))
        except ExportPayloadError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/auto-projects/{autoProjectId}/git-pull")
def auto_git_pull(autoProjectId: str):
    with session_scope() as session:
        project = require_db_item(session, AutoProject, autoProjectId, "autoProjectId")
        r2_log(session, "auto_project", "git_pull_skipped", project.id)
        return {"auto_project_id": project.id, "status": "skipped", "reason": "Git operation is disabled in round 2."}


@router.post("/auto-projects/{autoProjectId}/git-push")
def auto_git_push(autoProjectId: str):
    with session_scope() as session:
        project = require_db_item(session, AutoProject, autoProjectId, "autoProjectId")
        r2_log(session, "auto_project", "git_push_skipped", project.id)
        return {"auto_project_id": project.id, "status": "skipped", "reason": "Git operation is disabled in round 2."}


@router.get("/projects/{projectId}/perf-plans")
def list_perf_plans(projectId: str, page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        pid = to_int(projectId, "projectId")
        return db_page(session, PerfPlan, page_num, page_size, PerfPlan.project_id == pid, PerfPlan.is_deleted.is_(False), order_by=PerfPlan.id.desc())


@router.post("/projects/{projectId}/perf-plans")
def create_perf_plan(projectId: str, payload: WritePayload):
    data = payload_dict(payload)
    try:
        plan_schema = normalize_plan_schema_template_params(data.get("plan_schema")) if data.get("plan_schema") is not None else None
        jmx_script = data.get("jmx_script")
        if not jmx_script and template_params_from_schema(plan_schema):
            jmx_script = render_jmeter_script(plan_schema)
    except PerfPayloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with session_scope() as session:
        require_db_item(session, Project, projectId, "projectId")
        plan = PerfPlan(
            project_id=to_int(projectId, "projectId"),
            source_document_id=to_int(data["source_document_id"], "source_document_id") if data.get("source_document_id") is not None else None,
            name=data.get("name") or "Performance Plan",
            description=data.get("description"),
            requirement_item_ids_json=[to_int(item, "requirement_item_id") for item in data.get("requirement_item_ids", [])],
            target_assets_json=sanitize_payload(data.get("target_assets") or data.get("target_assets_json") or {}),
            target_doc=data.get("target_doc") or data.get("targetDoc"),
            plan_content=data.get("plan_content"),
            plan_schema=plan_schema,
            jmx_script=jmx_script,
            status=data.get("status", "draft"),
        )
        session.add(plan)
        session.flush()
        r2_log(session, "perf_plan", "create", plan.id, {"project_id": plan.project_id})
        return model_dict(plan)


@router.patch("/perf-plans/{planId}")
def update_perf_plan(planId: str, payload: WritePayload):
    data = payload_dict(payload)
    if "target_assets" in data and "target_assets_json" not in data:
        data["target_assets_json"] = data["target_assets"]
    with session_scope() as session:
        plan = require_db_item(session, PerfPlan, planId, "planId")
        plan_schema_changed = False
        try:
            if "plan_schema" in data:
                data["plan_schema"] = normalize_plan_schema_template_params(data["plan_schema"])
                plan_schema_changed = True
            if "template_params" in data:
                data["plan_schema"] = merge_jmeter_template_params(data.get("plan_schema") if "plan_schema" in data else plan.plan_schema, {"template_params": data["template_params"]})
                plan_schema_changed = True
        except PerfPayloadError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        update_columns(plan, data, ("name", "description", "requirement_item_ids_json", "target_assets_json", "target_doc", "plan_content", "plan_schema", "jmx_script", "status"))
        if plan_schema_changed and "jmx_script" not in data and template_params_from_schema(plan.plan_schema):
            plan.jmx_script = render_jmeter_script(plan.plan_schema, plan.jmx_script)
        session.flush()
        r2_log(session, "perf_plan", "update", plan.id)
        return model_dict(plan)


@router.patch("/perf-plans/{planId}/jmeter-params")
def update_perf_plan_jmeter_params(planId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        plan = require_db_item(session, PerfPlan, planId, "planId")
        try:
            plan.plan_schema = merge_jmeter_template_params(plan.plan_schema, data)
            plan.jmx_script = render_jmeter_script(plan.plan_schema, plan.jmx_script)
        except PerfPayloadError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        plan.status = "scripted"
        session.flush()
        r2_log(session, "perf_plan", "update_jmeter_params", plan.id)
        return {
            "plan": model_dict(plan),
            "template_params": template_params_from_schema(plan.plan_schema),
            "script": {"tool": "jmeter", "download_url": f"/api/v2/perf-plans/{plan.id}/download-script"},
        }


@router.delete("/perf-plans/{planId}")
def delete_perf_plan(planId: str):
    with session_scope() as session:
        plan = require_db_item(session, PerfPlan, planId, "planId")
        plan.is_deleted = True
        session.flush()
        r2_log(session, "perf_plan", "delete", plan.id)
        return {"deleted": True, "id": plan.id}


@router.post("/perf-plans/{planId}/generate-plan")
def generate_perf_plan(planId: str):
    with session_scope() as session:
        plan = require_db_item(session, PerfPlan, planId, "planId")
        schema = {"scenarios": [{"name": "baseline", "users": 10, "duration": "1m"}], "targets": {"p95_ms": 500, "error_rate": 0.01}}
        plan.plan_schema = schema
        plan.plan_content = "Deterministic placeholder performance plan."
        plan.status = "planned"
        job = create_db_job(session, plan.project_id, "generate_perf_plan", {"plan_id": plan.id}, {"plan_schema": schema})
        session.flush()
        return {"job": model_dict(job), "plan": model_dict(plan)}


@router.post("/perf-plans/{planId}/generate-script")
def generate_perf_script(planId: str):
    with session_scope() as session:
        plan = require_db_item(session, PerfPlan, planId, "planId")
        script = render_jmeter_script(plan.plan_schema or {}, plan.jmx_script)
        plan.jmx_script = script
        plan.status = "scripted"
        job = create_db_job(session, plan.project_id, "generate_perf_script", {"plan_id": plan.id}, {"tool": "jmeter"})
        session.flush()
        return {"job": model_dict(job), "script": {"tool": "jmeter", "content": sanitize_perf_payload(script)}}


@router.get("/perf-plans/{planId}/download-script")
def download_perf_script(planId: str):
    with session_scope() as session:
        try:
            return export_perf_script(session, plan_id=to_int(planId, "planId"))
        except ExportPayloadError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/perf-plans/{planId}/execute")
def execute_perf_plan(planId: str, payload: WritePayload | None = None):
    with session_scope() as session:
        plan = require_db_item(session, PerfPlan, planId, "planId")
        data = payload_dict(payload)
        try:
            thresholds = resolve_thresholds(plan.plan_schema, data)
            effective_schema = merge_jmeter_template_params(plan.plan_schema, data) if isinstance(data.get("template_params"), dict) else normalize_plan_schema_template_params(plan.plan_schema)
        except PerfPayloadError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        use_real_runner = data.get("real") is True or str(data.get("mode") or "").lower() == "real"
        use_jmeter_runner = bool(plan.jmx_script and data.get("use_jmeter") is True)
        if use_real_runner or use_jmeter_runner:
            runner_result = run_jmeter_plan(render_jmeter_script(effective_schema, plan.jmx_script), data)
            summary_data, threshold_status = apply_thresholds(runner_result["summary_data"], thresholds)
            result_status = status_after_thresholds(runner_result["status"], threshold_status)
            result = PerfResult(
                plan_id=plan.id,
                project_id=plan.project_id,
                status=result_status,
                summary_data=summary_data,
                timeline_data=runner_result["timeline_data"],
                error_details=runner_result["error_details"],
                artifacts=runner_result["artifacts"],
                raw_data_path=runner_result.get("raw_data_path"),
                duration=runner_result["duration"],
            )
            session.add(result)
            plan.status = "executed" if result_status == "completed" else "execution_failed"
            session.flush()
            job = create_db_job(
                session,
                plan.project_id,
                "execute_perf_plan",
                {"plan_id": plan.id, "mode": "jmeter", "payload": sanitize_perf_payload(data)},
                {"perf_result_id": result.id, "status": result.status},
            )
            return {"job": model_dict(job), "result": model_dict(result)}
        summary_data, threshold_status = apply_thresholds({"avg_ms": 120, "p95_ms": 240, "error_rate": 0, "tps": 20}, thresholds)
        result_status = status_after_thresholds("completed", threshold_status)
        result = PerfResult(
            plan_id=plan.id,
            project_id=plan.project_id,
            status=result_status,
            summary_data=summary_data,
            timeline_data=[{"second": 1, "avg_ms": 120}],
            error_details=[],
            artifacts={"jtl": None, "html_report": None},
            duration=60,
        )
        session.add(result)
        plan.status = "executed" if result_status == "completed" else "execution_failed"
        session.flush()
        job = create_db_job(session, plan.project_id, "execute_perf_plan", {"plan_id": plan.id, "payload": sanitize_perf_payload(data)}, {"perf_result_id": result.id, "status": result.status})
        return {"job": model_dict(job), "result": model_dict(result)}


@router.get("/perf-plans/{planId}/results")
def list_perf_results(planId: str):
    with session_scope() as session:
        require_db_item(session, PerfPlan, planId, "planId")
        return db_page(session, PerfResult, 1, 200, PerfResult.plan_id == to_int(planId, "planId"), order_by=PerfResult.id.desc())


@router.get("/perf-plans/{planId}/results/{resultId}/compare")
def compare_perf_result(planId: str, resultId: str, baselineId: str = Query(...)):
    with session_scope() as session:
        plan = require_db_item(session, PerfPlan, planId, "planId")
        current = session.get(PerfResult, to_int(resultId, "resultId"))
        baseline = session.get(PerfResult, to_int(baselineId, "baselineId"))
        if current is None:
            raise HTTPException(status_code=404, detail=f"PerfResult({resultId}) not found")
        if baseline is None:
            raise HTTPException(status_code=404, detail=f"PerfResult({baselineId}) not found")
        try:
            return compare_perf_results(plan, current, baseline)
        except PerfPayloadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/perf-plans/{planId}/results/{resultId}/download")
def download_perf_result(planId: str, resultId: str, format: str = Query("json")):
    with session_scope() as session:
        try:
            return export_perf_result(
                session,
                plan_id=to_int(planId, "planId"),
                result_id=None if str(resultId).lower() == "latest" else to_int(resultId, "resultId"),
                output_format=format,
            )
        except ExportPayloadError as exc:
            raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc


@router.get("/perf-results/{resultId}/artifacts/download")
def download_perf_result_artifacts(resultId: str):
    with session_scope() as session:
        try:
            return build_perf_result_artifacts_zip(session, result_id=to_int(resultId, "resultId"))
        except ExportPayloadError as exc:
            raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc


@router.post("/perf-results/{resultId}/abort")
def abort_perf_execution(resultId: str, payload: WritePayload | None = None):
    data = payload_dict(payload)
    with session_scope() as session:
        result = session.get(PerfResult, to_int(resultId, "resultId"))
        if result is None:
            raise HTTPException(status_code=404, detail=f"PerfResult({resultId}) not found")
        try:
            abort = abort_perf_result(result, data.get("reason") or data.get("message"))
        except PerfPayloadError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        session.flush()
        r2_log(session, "perf_result", "abort", result.id, {"status": result.status, "reason": abort.get("reason")})
        return {"result": model_dict(result), "abort": sanitize_perf_payload(abort)}


@router.post("/perf-plans/{planId}/generate-report")
def generate_perf_report(planId: str):
    with session_scope() as session:
        try:
            report, result = create_performance_report(session, plan_id=to_int(planId, "planId"))
            job = create_db_job(
                session,
                report.project_id,
                "generate_perf_report",
                {"plan_id": to_int(planId, "planId")},
                {"report_id": report.id, "perf_result_id": result.id if result else None},
            )
            return {"job": model_dict(job), "report": model_dict(report), "perf_result": sanitize_perf_payload(model_dict(result)) if result else None}
        except ReportingPayloadError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/perf/quick-tests")
def perf_quick_tests(payload: WritePayload):
    data = sanitize_payload(payload_dict(payload))
    with session_scope() as session:
        return r2_create(session, "perf_quick_test", {"status": "completed", "metrics": {"avg_ms": 100, "p95_ms": 180, "error_rate": 0}, "input": data})


@router.get("/projects/{projectId}/performance-trend")
def get_project_performance_trend(projectId: str, days: int = Query(7, ge=1, le=90)):
    with session_scope() as session:
        project = require_db_item(session, Project, projectId, "projectId")
        return project_performance_trend(session, project_id=project.id, days=days)


def report_error_detail(message: str, *, field: str | None = None, error_code: str = "report_center_validation_failed") -> dict[str, Any]:
    detail: dict[str, Any] = {"error_code": error_code, "message": message}
    if field:
        detail["field_errors"] = {field: message}
    return detail


def report_todo_public(todo: ReportTodo) -> dict[str, Any]:
    data = model_dict(todo)
    data["todo_id"] = todo.id
    data["source_refs"] = data.get("source_refs_json") or {}
    return sanitize_payload(data)


def parse_report_datetime(value: Any, *, end_of_day: bool = False) -> datetime | None:
    if value in (None, ""):
        return None
    text_value = str(value).strip()
    try:
        if len(text_value) == 10:
            suffix = "T23:59:59.999999+00:00" if end_of_day else "T00:00:00+00:00"
            return datetime.fromisoformat(text_value + suffix)
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
        return parsed
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=report_error_detail("invalid date range", field="date")) from exc


@router.get("/projects/{projectId}/reports")
def list_reports(
    projectId: str,
    page_num: int = Query(1, alias="page"),
    page_size: int = Query(20, alias="pageSize"),
    report_type: str | None = Query(None, alias="type"),
    q: str | None = None,
    requirementItemId: str | None = None,
    sourceDocumentId: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    sort: str | None = None,
):
    with session_scope() as session:
        pid = to_int(projectId, "projectId")
        stmt = select(Report).where(Report.project_id == pid)
        if report_type:
            stmt = stmt.where(Report.type == report_type)
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(or_(Report.name.like(pattern), Report.type.like(pattern), Report.content.like(pattern)))
        start_at = parse_report_datetime(dateFrom)
        end_at = parse_report_datetime(dateTo, end_of_day=True)
        if start_at is not None:
            stmt = stmt.where(Report.generated_at >= start_at)
        if end_at is not None:
            stmt = stmt.where(Report.generated_at <= end_at)
        reports = list(session.scalars(stmt))
        if requirementItemId:
            item_id = to_int(requirementItemId, "requirementItemId")
            reports = [report for report in reports if item_id in (report.requirement_item_ids_json or [])]
        if sourceDocumentId:
            document_id = to_int(sourceDocumentId, "sourceDocumentId")
            reports = [report for report in reports if document_id in (report.source_document_ids_json or [])]
        sort_key, _, sort_direction = (sort or "generated_at:desc").partition(":")
        reverse = (sort_direction or "desc").lower() != "asc"
        allowed_sort = {
            "generated_at": lambda report: report.generated_at or datetime.min,
            "id": lambda report: report.id,
            "name": lambda report: report.name or "",
            "type": lambda report: report.type or "",
        }
        reports.sort(key=allowed_sort.get(sort_key, allowed_sort["generated_at"]), reverse=reverse)
        total = len(reports)
        start = max(page_num - 1, 0) * page_size
        return list_result(reports[start : start + page_size], page_num, page_size, total)


@router.post("/reports/comprehensive")
def create_comprehensive_report(payload: WritePayload):
    data = payload_dict(payload)
    project_id = data.get("project_id") or (data.get("scope") or {}).get("project_id")
    if project_id is None:
        raise HTTPException(status_code=400, detail="project_id is required")
    item_ids = data.get("requirement_item_ids") or (data.get("scope") or {}).get("requirement_item_ids") or []
    document_ids = data.get("source_document_ids") or data.get("sourceDocumentIds") or (data.get("scope") or {}).get("source_document_ids") or (data.get("scope") or {}).get("sourceDocumentIds") or []
    module_types = data.get("module_types") or data.get("moduleTypes") or (data.get("scope") or {}).get("module_types") or (data.get("scope") or {}).get("moduleTypes") or []
    time_range = data.get("time_range") or data.get("timeRange") or (data.get("scope") or {}).get("time_range") or (data.get("scope") or {}).get("timeRange")
    with session_scope() as session:
        try:
            report = create_report_from_aggregator(
                session,
                project_id=to_int(project_id, "project_id"),
                name=data.get("title") or data.get("name") or "综合测试报告",
                report_type=data.get("type", "comprehensive"),
                requirement_item_ids=[to_int(item_id, "requirement_item_id") for item_id in item_ids],
                source_document_ids=[to_int(document_id, "source_document_id") for document_id in document_ids],
                module_types=[str(module) for module in module_types],
                time_range=time_range if isinstance(time_range, dict) else None,
                template_id=to_int(data["template_id"], "template_id") if data.get("template_id") is not None else None,
                related_scope=sanitize_payload(data.get("scope") or {"project_id": project_id, "requirement_item_ids": item_ids}),
            )
            result = model_dict(report)
            result["report"] = model_dict(report)
            return result
        except ReportingPayloadError as exc:
            raise HTTPException(status_code=400, detail=report_error_detail(str(exc))) from exc
        except Exception as exc:
            raise repo_error(exc)


@router.get("/reports/{reportId}")
def get_report(reportId: str):
    with session_scope() as session:
        report = session.get(Report, to_int(reportId, "reportId"))
        if report is None:
            raise HTTPException(status_code=404, detail=f"Report({reportId}) not found")
        return model_dict(report)


@router.get("/reports/{reportId}/download")
def download_report(reportId: str, format: str = Query("markdown")):
    with session_scope() as session:
        report = session.get(Report, to_int(reportId, "reportId"))
        if report is None:
            raise HTTPException(status_code=404, detail=f"Report({reportId}) not found")
        if (format or "").lower() in {"pdf", "word", "doc", "docx"}:
            raise HTTPException(
                status_code=415,
                detail=report_error_detail(
                    "unsupported export format; supported formats are markdown, html, json",
                    field="format",
                    error_code="unsupported_report_export_format",
                ),
            )
        try:
            return export_report(report, format)
        except ReportingPayloadError as exc:
            raise HTTPException(status_code=400, detail=report_error_detail(str(exc), field="format")) from exc


@router.get("/reports/{reportId}/drilldown")
def get_report_drilldown(reportId: str, section: str | None = None):
    with session_scope() as session:
        report = session.get(Report, to_int(reportId, "reportId"))
        if report is None:
            raise HTTPException(status_code=404, detail=f"Report({reportId}) not found")
        try:
            return report_drilldown(report, section or "")
        except ReportingPayloadError as exc:
            raise HTTPException(status_code=400, detail=report_error_detail(str(exc), field="section")) from exc


@router.get("/reports/{reportId}/risks")
def get_report_risks(reportId: str):
    with session_scope() as session:
        report = session.get(Report, to_int(reportId, "reportId"))
        if report is None:
            raise HTTPException(status_code=404, detail=f"Report({reportId}) not found")
        return report_risks_payload(report)


@router.post("/reports/{reportId}/risks/{riskKey}/todos")
def create_report_risk_todo(reportId: str, riskKey: str, payload: WritePayload | None = None):
    data = payload_dict(payload)
    with session_scope() as session:
        report = session.get(Report, to_int(reportId, "reportId"))
        if report is None:
            raise HTTPException(status_code=404, detail=f"Report({reportId}) not found")
        try:
            todo, created = create_todo_from_report_risk(session, report, riskKey, sanitize_payload(data))
            session.flush()
            result = report_todo_public(todo)
            result["created"] = created
            return result
        except ReportingPayloadError as exc:
            raise HTTPException(status_code=400, detail=report_error_detail(str(exc), field="riskKey")) from exc


@router.get("/report-todos")
def list_report_todos(
    page_num: int = Query(1, alias="page"),
    page_size: int = Query(20, alias="pageSize"),
    reportId: str | None = None,
    riskKey: str | None = None,
    status: str | None = None,
    projectId: str | None = None,
):
    with session_scope() as session:
        stmt = select(ReportTodo)
        count_stmt = select(func.count()).select_from(ReportTodo)
        criteria = []
        if reportId:
            criteria.append(ReportTodo.report_id == to_int(reportId, "reportId"))
        if projectId:
            criteria.append(ReportTodo.project_id == to_int(projectId, "projectId"))
        if riskKey:
            criteria.append(ReportTodo.risk_key == riskKey)
        if status:
            criteria.append(ReportTodo.status == status)
        if criteria:
            stmt = stmt.where(*criteria)
            count_stmt = count_stmt.where(*criteria)
        total = session.scalar(count_stmt) or 0
        items = list(session.scalars(stmt.order_by(ReportTodo.id.desc()).offset((page_num - 1) * page_size).limit(page_size)))
        records = [report_todo_public(item) for item in items]
        return {"list": records, "todos": records, "total": total, "page": page_num, "pageSize": page_size}


@router.patch("/report-todos/{todoId}")
def patch_report_todo(todoId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        todo = require_db_item(session, ReportTodo, todoId, "todoId")
        try:
            update_report_todo(todo, sanitize_payload(data))
            report = session.get(Report, todo.report_id)
            if report is not None:
                # Keep the report export snapshot aligned with report-derived todo state.
                create_todo_from_report_risk(session, report, todo.risk_key)
            session.flush()
            return report_todo_public(todo)
        except ReportingPayloadError as exc:
            raise HTTPException(status_code=400, detail=report_error_detail(str(exc), field="status")) from exc


@router.get("/report-templates")
def list_report_templates(page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize"), report_type: str | None = None):
    with session_scope() as session:
        stmt = select(ReportTemplate)
        count_stmt = select(func.count()).select_from(ReportTemplate)
        if report_type:
            stmt = stmt.where(ReportTemplate.report_type == report_type)
            count_stmt = count_stmt.where(ReportTemplate.report_type == report_type)
        items = list(session.scalars(stmt.order_by(ReportTemplate.id.desc()).offset((page_num - 1) * page_size).limit(page_size)))
        return {"list": [report_template_public_dict(item) for item in items], "total": session.scalar(count_stmt) or 0, "page": page_num, "pageSize": page_size}


@router.post("/report-templates")
def create_report_template(payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        try:
            fields = normalize_report_template_payload(data)
            template = ReportTemplate(**fields)
            session.add(template)
            session.flush()
            enforce_single_default_template(session, template)
            session.flush()
            r2_log(session, "report_template", "create", template.id)
            return report_template_public_dict(template)
        except ReportingPayloadError as exc:
            field = "supported_formats" if "supported_formats" in str(exc) else "sections"
            raise HTTPException(status_code=400, detail=report_error_detail(str(exc), field=field)) from exc


@router.patch("/report-templates/{templateId}")
def update_report_template(templateId: str, payload: WritePayload):
    data = payload_dict(payload)
    if "type" in data and "report_type" not in data:
        data["report_type"] = data["type"]
    with session_scope() as session:
        template = require_db_item(session, ReportTemplate, templateId, "templateId")
        try:
            fields = normalize_report_template_payload(data, template)
            for key, value in fields.items():
                setattr(template, key, value)
            session.flush()
            enforce_single_default_template(session, template)
            session.flush()
            r2_log(session, "report_template", "update", template.id)
            return report_template_public_dict(template)
        except ReportingPayloadError as exc:
            field = "supported_formats" if "supported_formats" in str(exc) else "sections"
            raise HTTPException(status_code=400, detail=report_error_detail(str(exc), field=field)) from exc


@router.delete("/report-templates/{templateId}")
def delete_report_template(templateId: str):
    with session_scope() as session:
        template = require_db_item(session, ReportTemplate, templateId, "templateId")
        session.delete(template)
        r2_log(session, "report_template", "delete", to_int(templateId, "templateId"))
        return {"deleted": True, "id": to_int(templateId, "templateId")}


@router.post("/reports/lightweight-conclusions")
def lightweight_conclusions(payload: WritePayload):
    data = payload_dict(payload)
    scope = data.get("scope") if isinstance(data.get("scope"), dict) else {}
    project_id = data.get("project_id") or data.get("projectId") or scope.get("project_id") or scope.get("projectId")
    item_ids = data.get("requirement_item_ids") or data.get("requirementItemIds") or scope.get("requirement_item_ids") or scope.get("requirementItemIds") or []
    conclusion_type = data.get("type") or data.get("conclusion_type") or data.get("scene") or "brief"
    save = bool(data.get("save", False))
    with session_scope() as session:
        try:
            return build_lightweight_conclusion(
                session,
                project_id=to_int(project_id, "project_id") if project_id is not None else None,
                requirement_item_ids=[to_int(item_id, "requirement_item_id") for item_id in item_ids],
                conclusion_type=str(conclusion_type),
                save=save,
                name=data.get("name") or data.get("title"),
            )
        except ReportingPayloadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/llm-configs")
def list_llm_configs(page_num: int = Query(1, alias="page"), page_size: int = Query(100, alias="pageSize")):
    with session_scope() as session:
        return db_page(session, LlmConfig, page_num, page_size, order_by=(LlmConfig.sort_order.asc(), LlmConfig.id.desc()))


@router.post("/llm-configs")
def create_llm_config(payload: WritePayload):
    data = sanitize_payload(payload_dict(payload))
    with session_scope() as session:
        config = LlmConfig(
            name=data.get("name") or "LLM Config",
            base_url=data.get("base_url"),
            api_key_ref=data.get("api_key_ref") or ("***" if data.get("api_key") else None),
            model_name=data.get("model_name") or data.get("model") or "placeholder",
            max_tokens=int(data.get("max_tokens", 4096)),
            temperature=float(data.get("temperature", 0.7)),
            is_default=bool(data.get("is_default", False)),
            is_enabled=bool(data.get("is_enabled", data.get("enabled", True))),
            module_binding=sanitize_payload(data.get("module_binding") or {}),
            sort_order=int(data.get("sort_order", 0)),
        )
        session.add(config)
        session.flush()
        r2_log(session, "llm_config", "create", config.id)
        return model_dict(config)


@router.patch("/llm-configs/{configId}")
def update_llm_config(configId: str, payload: WritePayload):
    data = sanitize_payload(payload_dict(payload))
    if "model" in data and "model_name" not in data:
        data["model_name"] = data["model"]
    if "enabled" in data and "is_enabled" not in data:
        data["is_enabled"] = data["enabled"]
    if data.get("api_key") and "api_key_ref" not in data:
        data["api_key_ref"] = "***"
    with session_scope() as session:
        config = require_db_item(session, LlmConfig, configId, "configId")
        update_columns(config, data, ("name", "base_url", "api_key_ref", "model_name", "max_tokens", "temperature", "is_default", "is_enabled", "module_binding", "sort_order"))
        session.flush()
        r2_log(session, "llm_config", "update", config.id)
        return model_dict(config)


@router.post("/llm-configs/{configId}/test")
def test_llm_config(configId: str):
    with session_scope() as session:
        config = require_db_item(session, LlmConfig, configId, "configId")
        fallback, settings = require_llm_runtime(config)
        if fallback is not None:
            record_llm_usage(session, config.id, "llm_config_test", duration_ms=1)
            return sanitize_payload(sanitize_llm_payload({**fallback, "config": llm_config_public(config)}))

        assert settings.base_url is not None and settings.api_key is not None
        client = OpenAICompatibleClient(base_url=settings.base_url, api_key=settings.api_key)
        try:
            models_response, duration_ms = client.list_models()
            record_llm_usage(session, config.id, "llm_config_test", duration_ms=duration_ms)
            models = models_response.get("data") if isinstance(models_response.get("data"), list) else []
            model_ids = [item.get("id") for item in models if isinstance(item, dict) and item.get("id")]
            return sanitize_payload(
                sanitize_llm_payload(
                    {
                        "enabled": True,
                        "connected": True,
                        "status": "ok",
                        "model": settings.model,
                        "model_available": settings.model in model_ids if model_ids else None,
                        "models": model_ids[:20],
                        "config": llm_config_public(config),
                    }
                )
            )
        except LlmClientError as exc:
            record_llm_usage(session, config.id, "llm_config_test", duration_ms=1)
            return sanitize_payload(
                sanitize_llm_payload(
                    {
                        "enabled": True,
                        "connected": False,
                        "status": "fallback",
                        "error": str(exc),
                        "config": llm_config_public(config),
                    }
                )
            )


@router.delete("/llm-configs/{configId}")
def delete_llm_config(configId: str):
    with session_scope() as session:
        config = require_db_item(session, LlmConfig, configId, "configId")
        config.is_enabled = False
        r2_log(session, "llm_config", "delete", to_int(configId, "configId"))
        return {"deleted": True, "id": to_int(configId, "configId")}


@router.get("/llm-usage/statistics")
def llm_usage_statistics():
    with session_scope() as session:
        rows = session.execute(
            select(LlmUsage.module, func.sum(LlmUsage.input_tokens), func.sum(LlmUsage.output_tokens), func.count()).group_by(LlmUsage.module)
        ).all()
        by_module = [
            {"module": row[0], "input_tokens": row[1] or 0, "output_tokens": row[2] or 0, "count": row[3] or 0}
            for row in rows
        ]
        return {
            "total_tokens": sum(item["input_tokens"] + item["output_tokens"] for item in by_module),
            "total_cost": 0,
            "by_module": by_module,
        }


def _llm_usage_summary(session: Any, config_id: int | None = None) -> dict[str, Any]:
    total_stmt = select(
        func.count(LlmUsage.id),
        func.coalesce(func.sum(LlmUsage.input_tokens), 0),
        func.coalesce(func.sum(LlmUsage.output_tokens), 0),
    )
    module_stmt = select(
        LlmUsage.module,
        func.coalesce(func.sum(LlmUsage.input_tokens), 0),
        func.coalesce(func.sum(LlmUsage.output_tokens), 0),
        func.count(LlmUsage.id),
    ).group_by(LlmUsage.module)
    if config_id is not None:
        total_stmt = total_stmt.where(LlmUsage.config_id == config_id)
        module_stmt = module_stmt.where(LlmUsage.config_id == config_id)

    usage_count, input_tokens, output_tokens = session.execute(total_stmt).one()
    by_module = []
    for module, module_input_tokens, module_output_tokens, module_count in session.execute(module_stmt).all():
        by_module.append(
            {
                "module": _safe_llm_status_text(module),
                "usage_count": int(module_count or 0),
                "input_tokens": int(module_input_tokens or 0),
                "output_tokens": int(module_output_tokens or 0),
                "total_tokens": int(module_input_tokens or 0) + int(module_output_tokens or 0),
            }
        )
    return {
        "usage_count": int(usage_count or 0),
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "total_tokens": int(input_tokens or 0) + int(output_tokens or 0),
        "by_module": by_module,
    }


def _safe_llm_status_text(value: Any) -> str | None:
    if value is None:
        return None
    return sanitize_llm_payload(str(value))


def _llm_config_status(config: LlmConfig) -> dict[str, Any]:
    return {
        "id": config.id,
        "name": _safe_llm_status_text(config.name),
        "model_name": _safe_llm_status_text(config.model_name),
        "is_default": bool(config.is_default),
        "is_enabled": bool(config.is_enabled),
        "base_url_configured": bool(config.base_url),
        "credential_ref_configured": bool(config.api_key_ref),
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
    }


def _llm_status_name(config: LlmConfig | None, settings: Any) -> str:
    if not settings.enabled:
        return "disabled"
    if config is None and not any((settings.base_url, settings.model, settings.api_key)):
        return "unconfigured"
    if not settings.base_url or not settings.model or not settings.api_key:
        return "incomplete"
    return "ready"


@router.get("/system/llm-status")
def system_llm_status():
    with session_scope() as session:
        config = default_llm_config(session)
        settings = resolve_llm_settings(
            config_base_url=config.base_url if config is not None else None,
            config_model=config.model_name if config is not None else None,
        )
        enabled_configs = list(
            session.scalars(
                select(LlmConfig)
                .where(LlmConfig.is_enabled.is_(True))
                .order_by(LlmConfig.sort_order.asc(), LlmConfig.id.asc())
                .limit(20)
            )
        )
        usage = _llm_usage_summary(session)
        selected_usage = _llm_usage_summary(session, config.id) if config is not None else _llm_usage_summary(session, -1)
        missing = []
        if settings.enabled:
            if not settings.base_url:
                missing.append("base_url")
            if not settings.model:
                missing.append("model")
            if not settings.api_key:
                missing.append("credentials")

        status = {
            "status": _llm_status_name(config, settings),
            "enabled": bool(settings.enabled),
            "configured": bool(settings.base_url and settings.model and settings.api_key),
            "connected": None,
            "provider_check": "not_performed",
            "provider_call_performed": False,
            "model": _safe_llm_status_text(settings.model),
            "model_name": _safe_llm_status_text(settings.model),
            "config_name": _safe_llm_status_text(config.name) if config is not None else None,
            "config_id": config.id if config is not None else None,
            "config": _llm_config_status(config) if config is not None else None,
            "enabled_config_count": len(enabled_configs),
            "enabled_configs": [_llm_config_status(item) for item in enabled_configs],
            "runtime": {
                "enabled": bool(settings.enabled),
                "base_url_configured": bool(settings.base_url),
                "credentials_configured": bool(settings.api_key),
                "model_configured": bool(settings.model),
                "missing": missing,
            },
            "usage": usage,
            "selected_config_usage": selected_usage,
            "checked_at": now_iso(),
        }
        return status


PROMPT_VARIABLE_RE = re.compile(r"\{\{\s*([a-zA-Z_][\w.-]*)\s*\}\}|\{([a-zA-Z_][\w.-]*)\}")


def _slugify_prompt_scene(value: Any) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return slug[:80] or "prompt"


def _unique_prompt_scene(session: Any, name: Any) -> str:
    base = f"custom_{_slugify_prompt_scene(name)}"
    candidate = base[:128]
    suffix = 2
    while session.scalar(select(PromptTemplate.id).where(PromptTemplate.scene == candidate)):
        tail = f"_{suffix}"
        candidate = f"{base[:128 - len(tail)]}{tail}"
        suffix += 1
    return candidate


def _extract_prompt_variables(content: str) -> list[str]:
    variables: list[str] = []
    seen: set[str] = set()
    for match in PROMPT_VARIABLE_RE.finditer(content or ""):
        name = match.group(1) or match.group(2)
        if name and name not in seen:
            seen.add(name)
            variables.append(name)
    return variables


def _normalize_prompt_variables(value: Any, content: str) -> list[str]:
    raw_items = value if isinstance(value, list) else _extract_prompt_variables(content)
    variables: list[str] = []
    seen: set[str] = set()
    for item in raw_items or []:
        name = str(item).strip()
        if name and not is_sensitive_key_name(name) and name not in seen:
            seen.add(name)
            variables.append(name)
    return variables


def _prompt_template_public(template: PromptTemplate) -> dict[str, Any]:
    data = model_dict(template)
    data["variables"] = [item for item in (data.get("variables") or []) if not is_sensitive_key_name(item)]
    return safe_summary_payload(data)


def _prompt_test_variables(data: dict[str, Any]) -> dict[str, Any]:
    if isinstance(data.get("variables"), dict):
        return dict(data["variables"])
    return {key: value for key, value in data.items() if key != "variables"}


def _render_prompt_content(content: str, variables: dict[str, Any]) -> str:
    rendered = content or ""
    for key, value in variables.items():
        text = str(value)
        rendered = rendered.replace("{{" + key + "}}", text)
        rendered = rendered.replace("{{ " + key + " }}", text)
        rendered = rendered.replace("{" + key + "}", text)
    return redact_sensitive_text(rendered)


@router.get("/prompt-templates")
def list_prompt_templates(page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        existing = session.scalar(select(func.count()).select_from(PromptTemplate)) or 0
        if existing == 0:
            session.add(
                PromptTemplate(
                    scene="test_case_generation",
                    name="Test Case Generation Prompt",
                    content="Generate test cases for {{requirement}}.",
                    variables=["requirement"],
                    is_builtin=True,
                )
            )
            session.flush()
        stmt = select(PromptTemplate).order_by(PromptTemplate.id.desc()).offset((page_num - 1) * page_size).limit(page_size)
        total = session.scalar(select(func.count()).select_from(PromptTemplate)) or 0
        items = list(session.scalars(stmt))
        return {"list": [_prompt_template_public(item) for item in items], "total": total, "page": page_num, "pageSize": page_size}


@router.post("/prompt-templates")
def create_prompt_template(payload: WritePayload):
    data = sanitize_payload(payload_dict(payload))
    name = str(data.get("name") or "").strip()
    content = str(data.get("content") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    with session_scope() as session:
        scene = str(data.get("scene") or "").strip() or _unique_prompt_scene(session, name)
        if session.scalar(select(PromptTemplate.id).where(PromptTemplate.scene == scene)):
            raise HTTPException(status_code=409, detail=f"PromptTemplate scene already exists: {scene}")
        template = PromptTemplate(
            scene=scene,
            name=name,
            content=content,
            variables=_normalize_prompt_variables(data.get("variables"), content),
            is_builtin=bool(data.get("is_builtin", False)),
        )
        session.add(template)
        session.flush()
        r2_log(session, "prompt_template", "create", template.id, {"scene": scene})
        return _prompt_template_public(template)


@router.patch("/prompt-templates/{templateId}")
def update_prompt_template(templateId: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        template = require_db_item(session, PromptTemplate, templateId, "templateId")
        update_columns(template, data, ("scene", "name", "content", "variables", "is_builtin"))
        session.flush()
        r2_log(session, "prompt_template", "update", template.id)
        return _prompt_template_public(template)


@router.post("/prompt-templates/{templateId}/test")
def test_prompt_template(templateId: str, payload: WritePayload | None = None):
    data = payload_dict(payload)
    with session_scope() as session:
        template = require_db_item(session, PromptTemplate, templateId, "templateId")
        raw_variables = _prompt_test_variables(data)
        render_variables = sanitize_payload(raw_variables)
        rendered = _render_prompt_content(template.content, render_variables)
        return {"template_id": template.id, "rendered": rendered, "input": safe_summary_payload(raw_variables)}


@router.delete("/prompt-templates/{templateId}")
def delete_prompt_template(templateId: str):
    with session_scope() as session:
        template = require_db_item(session, PromptTemplate, templateId, "templateId")
        if template.is_builtin:
            raise HTTPException(status_code=400, detail="builtin prompt template cannot be deleted")
        template_id = template.id
        session.delete(template)
        session.flush()
        r2_log(session, "prompt_template", "delete", template_id)
        return {"deleted": True, "id": template_id}


def _context_project_id(context: dict[str, Any]) -> int | None:
    raw = context.get("project_id") or context.get("projectId")
    if raw is None and isinstance(context.get("project"), dict):
        raw = context["project"].get("id")
    if raw is None:
        return None
    try:
        return to_int(raw, "project_id")
    except HTTPException:
        return None


def _safe_chat_aggregation_context(session: Any, context: dict[str, Any]) -> dict[str, Any] | None:
    project_id = _context_project_id(context)
    if project_id is None:
        return None
    try:
        return build_aggregation_context(session, project_id=project_id)
    except Exception:
        return None


def _compact_chat_facts(aggregation_context: dict[str, Any] | None) -> dict[str, Any]:
    if not aggregation_context:
        return {}
    data = aggregation_context.get("data_snapshot") or {}
    return sanitize_payload(
        {
            "project": data.get("project") or {},
            "metrics": data.get("summary_metrics") or {},
            "risk_items": (data.get("risk_items") or [])[:5],
            "execution_summary": data.get("execution_summary") or {},
            "api_summary": data.get("api_summary") or {},
            "automation_summary": data.get("automation_summary") or {},
            "performance_summary": data.get("performance_summary") or {},
            "source_refs": aggregation_context.get("source_refs_json") or {},
        }
    )


def _assistant_project_facts(session: Any, project_id: int | None) -> dict[str, Any]:
    if project_id is None:
        return {}
    aggregation_context = _safe_chat_aggregation_context(session, {"project_id": project_id})
    if not aggregation_context:
        return {"project_id": project_id, "available": False}
    compact = _compact_chat_facts(aggregation_context)
    return safe_summary_payload(
        {
            "project": compact.get("project") or {},
            "metrics": compact.get("metrics") or {},
            "risk_items": (compact.get("risk_items") or [])[:3],
            "execution_summary": compact.get("execution_summary") or {},
            "api_summary": compact.get("api_summary") or {},
            "automation_summary": compact.get("automation_summary") or {},
            "performance_summary": compact.get("performance_summary") or {},
            "source_refs": {
                "project_id": project_id,
                "counts": ((compact.get("source_refs") or {}).get("counts") or {}),
            },
        }
    )


def _recent_activity_brief(activity: dict[str, Any]) -> dict[str, Any]:
    return safe_summary_payload(
        {
            "id": activity.get("id"),
            "title": activity.get("title") or activity.get("name") or activity.get("route"),
            "route": activity.get("route"),
            "target_type": activity.get("target_type"),
            "target_id": activity.get("target_id"),
            "project_id": activity.get("project_id"),
            "created_at": activity.get("created_at"),
            "updated_at": activity.get("updated_at"),
        }
    )


def _operation_log_brief(log: OperationLog) -> dict[str, Any]:
    return safe_summary_payload(
        {
            "id": log.id,
            "module": log.module,
            "action": log.action,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "detail": log.detail if isinstance(log.detail, dict) else {},
            "created_at": log.created_at.isoformat() if hasattr(log.created_at, "isoformat") else log.created_at,
        }
    )


def _prompt_template_brief(template: PromptTemplate) -> dict[str, Any]:
    return safe_summary_payload(
        {
            "id": template.id,
            "scene": template.scene,
            "name": template.name,
            "variables": template.variables or [],
            "is_builtin": template.is_builtin,
            "updated_at": template.updated_at.isoformat() if hasattr(template.updated_at, "isoformat") else template.updated_at,
        }
    )


def _list_values(container: Any) -> list[Any]:
    if isinstance(container, dict):
        value = container.get("list") or container.get("items") or container.get("records") or []
        return value if isinstance(value, list) else []
    return container if isinstance(container, list) else []


def _chat_context_note(context: dict[str, Any]) -> str:
    sources = [context]
    if isinstance(context.get("assistant_context"), dict):
        sources.insert(0, context["assistant_context"])
    parts: list[str] = []
    for source in sources:
        recent = _list_values(source.get("recent_activities"))
        titles = [
            str(item.get("title") or item.get("name") or item.get("route"))
            for item in recent
            if isinstance(item, dict) and (item.get("title") or item.get("name") or item.get("route"))
        ][:3]
        if titles:
            parts.append("recent: " + " | ".join(titles))
        facts = source.get("project_facts")
        if isinstance(facts, dict):
            metrics = facts.get("metrics") or {}
            if metrics:
                parts.append(
                    "facts: "
                    + ", ".join(
                        f"{key}={metrics.get(key)}"
                        for key in ("requirement_item_count", "test_case_count", "open_defect_count")
                        if key in metrics
                    )
                )
    note = "; ".join(part for part in parts if part)
    return str(safe_summary_payload(note)) if note else ""


def _append_chat_context_note(reply: str, context: dict[str, Any]) -> str:
    note = _chat_context_note(context)
    if not note:
        return reply
    return f"{reply}\n\nAssistant context: {note}"


@router.get("/assistant/context")
def assistant_context(
    projectId: str | None = None,
    project_id: str | None = None,
    activeTab: str | None = None,
    active_tab: str | None = None,
    limit: int = Query(5, ge=1, le=20),
):
    raw_project_id = project_id if project_id is not None else projectId
    resolved_project_id = to_int(raw_project_id, "projectId") if raw_project_id is not None else None
    with session_scope() as session:
        recent = list_recent_activities(session, project_id=resolved_project_id, limit=limit)
        logs = list(session.scalars(select(OperationLog).order_by(OperationLog.id.desc()).limit(limit)))
        templates = list(session.scalars(select(PromptTemplate).order_by(PromptTemplate.id.desc()).limit(20)))
        payload = {
            "project_id": resolved_project_id,
            "active_tab": active_tab or activeTab,
            "recent_activities": {
                "list": [_recent_activity_brief(item) for item in recent.get("list", [])],
                "total": recent.get("total", 0),
            },
            "operation_logs": {"list": [_operation_log_brief(log) for log in logs], "total": len(logs)},
            "prompt_templates": {"list": [_prompt_template_brief(template) for template in templates], "total": len(templates)},
            "project_facts": _assistant_project_facts(session, resolved_project_id),
            "provider_call_performed": False,
            "generated_at": now_iso(),
        }
        return safe_summary_payload(payload)


def _draft_subject(message: str, context: dict[str, Any]) -> str:
    normalized = " ".join(message.split())
    if normalized:
        return normalized[:120]
    facts = context.get("project_facts") if isinstance(context, dict) else {}
    project = facts.get("project") if isinstance(facts, dict) else {}
    if isinstance(project, dict) and (project.get("name") or project.get("code")):
        return str(project.get("name") or project.get("code"))[:120]
    return "current scope"


def _test_points_draft(subject: str, context: dict[str, Any]) -> dict[str, Any]:
    items = [
        {"title": f"正常流程覆盖：{subject}", "point_type": "functional", "priority": "P1"},
        {"title": f"边界条件覆盖：{subject}", "point_type": "boundary", "priority": "P1"},
        {"title": f"异常与错误提示：{subject}", "point_type": "exception", "priority": "P2"},
        {"title": f"权限、数据校验与审计：{subject}", "point_type": "security", "priority": "P2"},
    ]
    metrics = ((context.get("project_facts") or {}).get("metrics") or {}) if isinstance(context, dict) else {}
    if metrics.get("open_defect_count", 0):
        items.append({"title": f"缺陷回归验证：{subject}", "point_type": "regression", "priority": "P1"})
    return {"items": items, "text": "\n".join(f"- {item['title']}" for item in items)}


def _clarifying_questions_draft(subject: str, context: dict[str, Any]) -> dict[str, Any]:
    active_tab = context.get("active_tab") or context.get("activeTab") or "current page"
    questions = [
        f"{subject} 的核心用户角色和成功标准是什么？",
        "哪些输入、状态或权限组合必须被明确覆盖？",
        f"在 {active_tab} 场景下，失败、超时或数据为空时前端应该如何反馈？",
        "这次范围内是否有必须兼容的历史数据或外部系统约束？",
    ]
    return {"items": questions, "text": "\n".join(f"{index}. {question}" for index, question in enumerate(questions, start=1))}


def _defect_note_draft(subject: str, context: dict[str, Any]) -> dict[str, Any]:
    active_tab = context.get("active_tab") or context.get("activeTab") or "current page"
    note = {
        "title": f"待确认缺陷：{subject}",
        "severity": "normal",
        "status": "open",
        "environment": active_tab,
        "steps_to_reproduce": [
            f"进入 {active_tab}",
            f"执行与 {subject} 相关的操作",
            "观察实际结果并保存截图、请求或日志证据",
        ],
        "actual_result": subject,
        "expected_result": "功能表现应符合需求说明，错误状态应有明确提示且不泄漏敏感信息。",
        "impact": "需要产品、前端和后端共同确认影响范围后再定级。",
    }
    return {"note": note, "text": json.dumps(note, ensure_ascii=False)}


def _assistant_draft_payload(draft_type: str, message: str, context: dict[str, Any]) -> dict[str, Any]:
    subject = _draft_subject(message, context)
    if draft_type == "test_points":
        return _test_points_draft(subject, context)
    if draft_type == "clarifying_questions":
        return _clarifying_questions_draft(subject, context)
    if draft_type == "defect_note":
        return _defect_note_draft(subject, context)
    raise HTTPException(status_code=400, detail=f"unsupported draft type: {draft_type}")


@router.post("/assistant/drafts")
def assistant_drafts(payload: WritePayload):
    data = payload_dict(payload)
    draft_type = str(data.get("type") or data.get("draft_type") or "").strip()
    if not draft_type:
        raise HTTPException(status_code=400, detail="type is required")
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    message = str(data.get("message") or "").strip()
    safe_context = safe_summary_payload(context)
    safe_message = redact_sensitive_text(message)
    draft = _assistant_draft_payload(draft_type, safe_message, safe_context)
    return safe_summary_payload(
        {
            "type": draft_type,
            "draft_type": draft_type,
            "message": safe_message,
            "context": safe_context,
            "draft": draft,
            "source": "deterministic-rules-v1",
            "provider_call_performed": False,
            "llm_provider_called": False,
            "created_at": now_iso(),
        }
    )


def _build_chat_fallback_reply(message: str, context: dict[str, Any], aggregation_context: dict[str, Any] | None) -> str:
    compact = _compact_chat_facts(aggregation_context)
    project = compact.get("project") or {}
    metrics = compact.get("metrics") or {}
    risks = compact.get("risk_items") or []
    query = message.lower()
    active_tab = context.get("active_tab") or context.get("activeTab") or "当前页面"

    if not metrics:
        return (
            f"我已收到你在「{active_tab}」中的问题。当前请求没有携带可追溯项目范围，"
            "请先在顶部项目选择器选中项目，或在问题中补充项目 ID；随后我会基于后端执行、缺陷、接口、自动化和性能事实生成分析。"
        )

    project_name = project.get("name") or project.get("code") or f"项目 {project.get('id')}"
    risk_lines = "；".join(f"{item.get('title')}：{item.get('detail')}" for item in risks[:3]) or "暂无高风险事实。"
    base = (
        f"基于后端事实数据，项目「{project_name}」当前有需求项 {metrics.get('requirement_item_count', 0)} 个、"
        f"测试用例 {metrics.get('test_case_count', 0)} 条、主链执行 {metrics.get('execution_count', 0)} 次，"
        f"主链通过率 {metrics.get('execution_pass_rate', 0)}%。接口通过率 {metrics.get('api_pass_rate', 0)}%，"
        f"自动化通过率 {metrics.get('auto_pass_rate', 0)}%，未关闭缺陷 {metrics.get('open_defect_count', 0)} 个。"
    )

    if any(keyword in query for keyword in ("待办", "todo", "风险", "阻塞", "失败")):
        return f"{base}\n\n优先级建议：{risk_lines}\n\n下一步：{'; '.join(_summary_next_actions(metrics, risks))}"
    if any(keyword in query for keyword in ("日报", "周报", "报告", "总结", "summary")):
        return f"{base}\n\n可写入报告的摘要：{risk_lines} 建议同步最新执行证据后生成综合报告并归档。"
    if any(keyword in query for keyword in ("通过率", "质量", "准出", "上线")):
        release_hint = "暂不建议直接放行，需先处理高风险项。" if any(item.get("level") == "high" for item in risks) else "当前风险整体可控，可继续推进后续验证。"
        return f"{base}\n\n准出判断：{release_hint}\n风险依据：{risk_lines}"
    return f"{base}\n\n针对你的问题「{message}」，建议先看这几项事实：{risk_lines}"


def handle_chat_request(request: ChatRequest) -> dict[str, Any]:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    context = sanitize_llm_payload(sanitize_payload(request.context or {}))
    with session_scope() as session:
        aggregation_context = _safe_chat_aggregation_context(session, context)
        if aggregation_context:
            context = {**context, "project_facts": _compact_chat_facts(aggregation_context)}
        fallback_reply = _build_chat_fallback_reply(message, context, aggregation_context)
        fallback_reply = _append_chat_context_note(fallback_reply, context)
        config = default_llm_config(session, context.get("config_id") or context.get("configId"))
        if config is None:
            return create(
                "chat_messages",
                {
                    "message": message,
                    "context": safe_summary_payload(context),
                    "reply": fallback_reply,
                    "status": "fallback",
                    "reason": "No enabled LLM config found.",
                    "provider_call_performed": False,
                    "llm_provider_called": False,
                },
            )

        fallback, settings = require_llm_runtime(config)
        if fallback is not None:
            record_llm_usage(session, config.id, "chat", duration_ms=1)
            record = create(
                "chat_messages",
                {
                    "message": message,
                    "context": safe_summary_payload(context),
                    "reply": fallback_reply,
                    "status": fallback["status"],
                    "llm": fallback,
                    "provider_call_performed": False,
                    "llm_provider_called": False,
                },
            )
            return sanitize_payload(sanitize_llm_payload(record))

        assert settings.base_url is not None and settings.api_key is not None and settings.model is not None
        messages = [
            {
                "role": "system",
                "content": "你是 AI 测试平台内的测试分析助手。优先使用上下文中的 project_facts 作答，不要输出密钥、token、cookie 或凭证。",
            },
            {"role": "user", "content": message},
        ]
        if isinstance(context.get("messages"), list):
            history_messages = [
                {"role": str(item.get("role", "user")), "content": str(item.get("content", ""))}
                for item in context["messages"]
                if isinstance(item, dict) and item.get("content")
            ]
            if history_messages:
                messages = [messages[0], *history_messages]
        if context.get("project_facts"):
            messages.insert(1, {"role": "system", "content": json.dumps({"project_facts": context["project_facts"]}, ensure_ascii=False)})
        client = OpenAICompatibleClient(base_url=settings.base_url, api_key=settings.api_key)
        try:
            response, duration_ms = client.chat_completions(
                model=settings.model,
                messages=messages,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )
            reply = extract_chat_reply(response)
            input_tokens, output_tokens = extract_usage_tokens(response)
            record_llm_usage(session, config.id, "chat", input_tokens, output_tokens, duration_ms)
            record = create(
                "chat_messages",
                {
                    "message": message,
                    "context": context,
                    "reply": reply,
                    "status": "ok",
                    "model": settings.model,
                    "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens, "duration_ms": duration_ms},
                    "provider_call_performed": True,
                    "llm_provider_called": True,
                },
            )
            return sanitize_payload(sanitize_llm_payload(record))
        except LlmClientError as exc:
            record_llm_usage(session, config.id, "chat", duration_ms=1)
            record = create(
                "chat_messages",
                {
                    "message": message,
                    "context": context,
                    "reply": fallback_reply,
                    "status": "fallback",
                    "error": str(exc),
                    "model": settings.model,
                    "provider_call_performed": True,
                    "llm_provider_called": True,
                },
            )
            return sanitize_payload(sanitize_llm_payload(record))


@router.post("/chat")
def chat_real_llm(request: ChatRequest):
    return handle_chat_request(request)


def chat_legacy_placeholder(request: ChatRequest):
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    record = create("chat_messages", {"message": message, "context": request.context or {}, "reply": "这是第一轮 API 的 AI 助手占位回复，尚未接入真实 LLM。"})
    return record


@router.get("/chat/favorites")
def chat_favorites():
    return store.list("chat_favorites")


@router.post("/system/backup")
def system_backup(payload: WritePayload | None = None):
    data = payload_dict(payload)
    project_id = data.get("project_id") or data.get("projectId")
    with session_scope() as session:
        snapshot = AitestRepository(session).create_backup_snapshot(
            project_id=to_int(project_id, "project_id") if project_id is not None else None,
            name=data.get("name"),
        )
        return public_backup_snapshot(snapshot)


@router.get("/system/backup-status")
def system_backup_status(projectId: str | None = None, project_id: str | None = None):
    raw_project_id = project_id if project_id is not None else projectId
    with session_scope() as session:
        return build_backup_status(
            session,
            project_id=to_int(raw_project_id, "projectId") if raw_project_id is not None else None,
        )


@router.get("/system/storage-summary")
def system_storage_summary():
    with session_scope() as session:
        return build_storage_summary(session)


@router.post("/system/cleanup")
def system_cleanup(payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        try:
            return cleanup_system(session, data)
        except DataManagementError as exc:
            detail = str(exc)
            status_code = 403 if "path" in detail.lower() or "root" in detail.lower() else 400
            raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/system/restore")
def system_restore(payload: RestorePayload):
    data = payload.model_dump(exclude_unset=True, by_alias=True)
    with session_scope() as session:
        try:
            return restore_system_backup(session, data)
        except RestorePayloadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/system/schema-status")
def system_schema_status():
    return get_schema_status()


@router.get("/system/runtime-dependencies")
def system_runtime_dependencies():
    return {
        "auto_runner": inspect_auto_runner_dependencies(),
        "perf_runner": {"jmeter": inspect_jmeter_dependency()},
        "checked_at": now_iso(),
    }


@router.get("/system/operation-logs")
def operation_logs(page_num: int = Query(1, alias="page"), page_size: int = Query(20, alias="pageSize")):
    with session_scope() as session:
        return db_page(session, OperationLog, page_num, page_size, order_by=OperationLog.id.desc())


@router.get("/system/preferences")
def system_preferences():
    with session_scope() as session:
        return list_preferences(session)


@router.get("/system/preferences/{prefKey}")
def system_get_preference(prefKey: str):
    with session_scope() as session:
        try:
            return get_preference(session, prefKey)
        except SystemStateError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/system/preferences/{prefKey}")
def system_save_preference(prefKey: str, payload: WritePayload):
    data = payload_dict(payload)
    with session_scope() as session:
        try:
            return save_preference(session, prefKey, data.get("value", data))
        except SystemStateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/system/recent-activities")
def system_recent_activities(projectId: str | None = None, limit: int = Query(20, ge=1, le=100)):
    with session_scope() as session:
        return list_recent_activities(session, project_id=to_int(projectId, "projectId") if projectId is not None else None, limit=limit)


@router.post("/system/recent-activities")
def system_record_recent_activity(payload: WritePayload):
    with session_scope() as session:
        return record_recent_activity(session, payload_dict(payload))


@router.get("/system/recycle-bin")
def recycle_bin():
    items: list[dict[str, Any]] = []
    with session_scope() as session:
        items.extend(list_db_recycle_items(session))
    for table, rows in store.tables.items():
        items.extend({"type": table, **item} for item in rows.values() if item.get("deleted"))
    return {"list": items, "total": len(items)}


@router.post("/system/recycle-bin/{id}/restore")
def restore_recycle_item(id: str):
    if ":" in id:
        with session_scope() as session:
            try:
                return restore_db_recycle_item(session, id)
            except SystemStateError as exc:
                raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc
    for table, rows in store.tables.items():
        if id in rows:
            return update(table, id, {"deleted": False})
    raise HTTPException(status_code=404, detail=f"recycle item {id} not found")


@router.get("/search")
def search(q: str = Query("", min_length=0), types: str | None = None):
    if not q:
        return {"list": [], "total": 0}
    requested = set(types.split(",")) if types else None
    results: list[dict[str, Any]] = []
    lowered = q.lower()
    escaped = lowered.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like_pattern = f"%{escaped}%"
    with session_scope() as session:
        searchable = [
            ("projects", Project, ("name", "description")),
            ("api_test_libs", ApiTestLib, ("name", "description")),
            ("api_endpoints", ApiEndpoint, ("name", "path", "description")),
            ("api_test_cases", ApiTestCase, ("name", "category")),
            ("auto_projects", AutoProject, ("name", "framework", "language")),
            ("perf_plans", PerfPlan, ("name", "description", "target_doc")),
            ("reports", Report, ("name", "type", "content")),
            ("report_templates", ReportTemplate, ("name", "report_type")),
            ("llm_configs", LlmConfig, ("name", "model_name", "base_url")),
            ("prompt_templates", PromptTemplate, ("scene", "name", "content")),
        ]
        for table, model, fields in searchable:
            if requested and table not in requested:
                continue
            stmt = select(model)
            if hasattr(model, "is_deleted"):
                stmt = stmt.where(model.is_deleted.is_(False))
            stmt = stmt.where(or_(*(func.lower(getattr(model, field)).like(like_pattern, escape="\\") for field in fields)))
            if hasattr(model, "id"):
                stmt = stmt.order_by(model.id.desc())
            for item in session.scalars(stmt.limit(200)):
                record = model_dict(item)
                results.append({"type": table, "id": record["id"], "title": record.get("name") or record.get("title") or record["id"], "record": record})
        if requested is None or "round2_resource" in requested:
            r2_init(session)
            rows = session.execute(
                text(
                    """
                    SELECT *
                    FROM round2_resource
                    WHERE is_deleted = 0
                      AND (
                        lower(resource_type) LIKE :pattern ESCAPE '\\'
                        OR lower(COALESCE(project_id, '')) LIKE :pattern ESCAPE '\\'
                        OR lower(COALESCE(parent_type, '')) LIKE :pattern ESCAPE '\\'
                        OR lower(COALESCE(parent_id, '')) LIKE :pattern ESCAPE '\\'
                        OR lower(COALESCE(name, '')) LIKE :pattern ESCAPE '\\'
                        OR lower(payload_json) LIKE :pattern ESCAPE '\\'
                      )
                    ORDER BY id DESC
                    LIMIT 200
                    """
                ),
                {"pattern": like_pattern},
            ).mappings()
            for row in rows:
                record = r2_decode(row)
                results.append({"type": row.resource_type, "id": record["id"], "title": record.get("name") or record.get("title") or record["id"], "record": record})
    return {"list": results, "total": len(results)}
